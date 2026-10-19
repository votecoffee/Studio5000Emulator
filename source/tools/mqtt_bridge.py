"""Optional MQTT device bridge. All broker I/O runs outside the simulator.

Install requirements-mqtt.txt in a separate environment. No controller or
simulation-control credentials are used; the source is a loopback device API.
"""
import argparse
from collections import OrderedDict
import json
import os
import queue
import re
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid


MAX_COMMAND = 65536
MAX_PENDING = 64
REQUEST_ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')


class HTTPSource:
    def __init__(self, url):
        parts = urlsplit(url)
        if (parts.scheme != 'http' or parts.hostname != '127.0.0.1' or not parts.port or
            parts.username or parts.password or parts.path not in ('','/') or parts.query or parts.fragment):
            raise ValueError('Source must be http://127.0.0.1:<port>')
        self.url = url.rstrip('/'); self.session = {}; self.etag = None

    def refresh(self):
        with urlopen(self.url+'/api/device-io/session',timeout=2) as response:
            value = json.load(response)
        if self.session.get('instance_id') != value['instance_id']:self.etag = None
        self.session = value

    def request(self, path, body=None, *, write=False, headers=None):
        token = self.session.get('write_token' if write else 'read_token')
        request = Request(self.url+'/api/device-io/'+path,
                          json.dumps(body,allow_nan=False).encode() if body is not None else None,
                          {'X-Logix-Device-Token':token or '', 'Content-Type':'application/json', **(headers or {})})
        return urlopen(request,timeout=2)

    def snapshot(self):
        try:
            with self.request('snapshot',headers={'If-None-Match':self.etag} if self.etag else {}) as response:
                raw = response.read(8_000_001)
                if len(raw) > 8_000_000:raise ValueError('Snapshot exceeds bridge byte limit')
                self.etag = response.headers.get('ETag'); return raw
        except HTTPError as error:
            if error.code == 304:return None
            raise

    def enqueue(self, body):
        with self.request('write',body,write=True) as response:return json.load(response)

    def receipt(self, request_id):
        with self.request('requests/'+request_id) as response:return json.load(response)


class LatestPublisher:
    """One MQTT QoS-1 message in flight; bounded/coalesced outgoing topics."""
    def __init__(self, prefix):
        self.fixed = {prefix+'/snapshot',prefix+'/status'}
        self.pending = OrderedDict(); self.inflight = None; self.dropped = 0
        self.deliveries = queue.Queue(maxsize=8)

    def delivered(self, mid):
        try:self.deliveries.put_nowait(mid)
        except queue.Full:pass

    def offer(self, topic, payload, *, retain=False):
        if not isinstance(payload, bytes):payload = json.dumps(payload,allow_nan=False,separators=(',',':')).encode()
        self.pending[topic] = (payload,retain)
        while len(self.pending) > MAX_PENDING+2:
            oldest = next(key for key in self.pending if key not in self.fixed)
            del self.pending[oldest];self.dropped += 1

    def pump(self, client):
        while not self.deliveries.empty():
            mid = self.deliveries.get_nowait()
            if self.inflight is not None and getattr(self.inflight,'mid',None) == mid:self.inflight = None
        if self.inflight is not None:
            try:
                if not self.inflight.is_published():return
            except RuntimeError:
                # A disconnect race can leave info.rc=NO_CONN after delivery;
                # on_publish is authoritative and releases this slot.
                return
            self.inflight = None
        if not client.is_connected() or not self.pending:return
        topic,(raw,retain) = next(iter(self.pending.items()))
        info = client.publish(topic,raw,qos=1,retain=retain)
        # Paho keeps a QoS-1 packet across a disconnect. Its queue is also capped.
        if info.rc in (0,4):
            del self.pending[topic];self.inflight = info


class Bridge:
    def __init__(self, source, client, prefix, *, allow_writes=False, clock=time.monotonic):
        self.source = source;self.client = client;self.prefix = prefix
        self.allow_writes = allow_writes;self.clock = clock
        self.commands = queue.Queue(maxsize=32);self.awaiting = OrderedDict()
        self.publisher = LatestPublisher(prefix);self.reconnected = threading.Event()
        self.last_session = float('-inf');self.last_status = float('-inf')
        self.dropped_commands = 0;self.latest = None

    def on_connect(self, client, userdata, flags, reason_code, properties):
        if not reason_code.is_failure:
            if self.allow_writes:client.subscribe(self.prefix+'/commands',qos=1)
            self.reconnected.set()

    def on_message(self, client, userdata, message):
        if message.retain or len(message.payload) > MAX_COMMAND or not self.allow_writes:
            self.dropped_commands += 1;return
        try:self.commands.put_nowait(bytes(message.payload))
        except queue.Full:self.dropped_commands += 1

    def on_publish(self, client, userdata, mid, reason_code, properties):
        self.publisher.delivered(mid)

    def acknowledge(self, receipt):
        self.publisher.offer(self.prefix+'/acks/'+receipt['request_id'],receipt)

    def tick(self):
        now = self.clock();connected = False
        try:
            if now-self.last_session >= 2 or self.reconnected.is_set():
                self.source.refresh();self.last_session = now
            if self.reconnected.is_set():
                self.reconnected.clear();self.source.etag = None
            raw = self.source.snapshot()
            if raw is not None:
                self.latest = json.loads(raw)
                self.publisher.offer(self.prefix+'/snapshot',raw,retain=True)
            connected = True
            for _ in range(min(4,self.commands.qsize())):
                payload = self.commands.get_nowait();body = None
                try:
                    body = json.loads(payload)
                    if not isinstance(body,dict) or not REQUEST_ID.fullmatch(str(body.get('request_id',''))):
                        raise ValueError('Invalid request ID')
                    if not self.source.session.get('writes_enabled'):raise ValueError('External writes disabled in app')
                    if len(self.awaiting) >= MAX_PENDING and body['request_id'] not in self.awaiting:
                        raise ValueError('Bridge acknowledgement capacity reached')
                    receipt = self.source.enqueue(body);self.acknowledge(receipt)
                    if receipt['status'] == 'queued':self.awaiting[body['request_id']] = True
                except (ValueError,OSError,RecursionError) as error:
                    if isinstance(body,dict) and isinstance(body.get('request_id'),str) and REQUEST_ID.fullmatch(body['request_id']):
                        self.acknowledge({'request_id':body['request_id'],'status':'rejected',
                                          'error':'Device transaction rejected; check source instance, generation, access and queue capacity'})
            # Round-robin polling keeps a stalled request from hiding later acks.
            for _ in range(min(4,len(self.awaiting))):
                request_id,_ = self.awaiting.popitem(last=False)
                try:
                    receipt = self.source.receipt(request_id);self.acknowledge(receipt)
                    if receipt['status'] == 'queued':self.awaiting[request_id] = True
                except HTTPError as error:
                    if error.code != 404: self.awaiting[request_id] = True;raise
                    self.acknowledge({'request_id':request_id,'status':'unknown','error':'Receipt expired or source restarted'})
        except (OSError,ValueError,RecursionError):
            self.last_session = float('-inf')
        if now-self.last_status >= 1:
            self.publisher.offer(self.prefix+'/status',{'source_connected':connected,
                'instance_id':self.source.session.get('instance_id'),
                'snapshot_sequence':self.latest.get('sequence') if self.latest else None,
                'writes_enabled':self.allow_writes and self.source.session.get('writes_enabled',False),
                'updated_at_unix':time.time(),'dropped_commands':self.dropped_commands,
                'dropped_ack_topics':self.publisher.dropped},retain=True)
            self.last_status = now
        self.publisher.pump(self.client)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,help='Local LogixLab HTTP session URL')
    parser.add_argument('--broker',default='127.0.0.1');parser.add_argument('--port',type=int,default=1883)
    parser.add_argument('--topic-prefix',default='logixlab/plc');parser.add_argument('--interval-ms',type=int,default=100)
    parser.add_argument('--allow-writes',action='store_true');parser.add_argument('--tls',action='store_true')
    parser.add_argument('--username-env',default='LOGIXLAB_MQTT_USERNAME')
    parser.add_argument('--password-env',default='LOGIXLAB_MQTT_PASSWORD')
    args = parser.parse_args()
    prefix = args.topic_prefix.rstrip('/')
    if not re.fullmatch(r'[A-Za-z0-9_/-]{1,128}',prefix):parser.error('Topic prefix must contain only letters, digits, _, - and /')
    if not 20 <= args.interval_ms <= 60000:parser.error('Publish interval must be 20..60000 ms')
    if not 1 <= args.port <= 65535:parser.error('Invalid broker port')
    try:
        import paho.mqtt.client as mqtt
    except ImportError:parser.error('Install the optional source/requirements-mqtt.txt dependencies')
    try:source = HTTPSource(args.source)
    except ValueError as error:parser.error(str(error))
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='logixlab-'+uuid.uuid4().hex[:12],protocol=mqtt.MQTTv311)
    client.max_queued_messages_set(1);client.max_inflight_messages_set(1)
    client.will_set(prefix+'/status',json.dumps({'source_connected':False,'reason':'bridge_disconnected'}),qos=1,retain=True)
    username = os.environ.get(args.username_env)
    if username:client.username_pw_set(username,os.environ.get(args.password_env))
    if args.tls:client.tls_set()
    client.reconnect_delay_set(min_delay=1,max_delay=15)
    bridge = Bridge(source,client,prefix,allow_writes=args.allow_writes)
    client.on_connect = bridge.on_connect;client.on_message = bridge.on_message;client.on_publish = bridge.on_publish
    client.connect_async(args.broker,args.port,keepalive=15);client.loop_start()
    try:
        print(f'MQTT bridge: {args.source} -> {args.broker}:{args.port}/{prefix}; interval {args.interval_ms} ms',flush=True)
        while True:
            bridge.tick();time.sleep(args.interval_ms/1000)
    except KeyboardInterrupt:pass
    finally:
        # The retained status/Will makes an old retained snapshot distinguishable.
        if client.is_connected():
            info = client.publish(prefix+'/status',json.dumps({'source_connected':False,'reason':'bridge_stopped'}),qos=1,retain=True)
            try:info.wait_for_publish(timeout=1)
            except (ValueError,RuntimeError):pass
        client.disconnect();client.loop_stop()


if __name__ == '__main__':main()
