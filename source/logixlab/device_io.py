"""Committed snapshots and bounded, idempotent device input transactions.

Readers never acquire the application lock. Network and JSON work stays outside
that lock; producers hand off immutable scalar rows at a command/scan boundary.
"""
import copy
import hashlib
import json
import math
import re
import secrets
import threading
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone

from . import __version__
from .model import ModelError

MAX_REQUEST_BYTES = 65536
MAX_WRITES = 128
MAX_PENDING = 64
MAX_RECEIPTS = 256
MAX_TAGS = 50000
MAX_SNAPSHOT_BYTES = 8_000_000
IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
STATIC_TAG = re.compile(r'(?:Program:[A-Za-z_]\w*\.)?[A-Za-z_][\w:]*(?:\[\d+(?:,\d+)*\]|\.\w+)*\Z', re.ASCII | re.I)


class DeviceIOError(ValueError):
    def __init__(self, status, message): self.status = status; super().__init__(message)


class DeviceIO:
    def __init__(self, instance_id, *, clock=time.monotonic):
        self.instance_id = instance_id; self.clock = clock
        self.lock = threading.Lock(); self.encoding_lock = threading.Lock()
        self.read_token = secrets.token_urlsafe(32); self.write_token = secrets.token_urlsafe(32)
        self.enabled = False; self.generation = 0; self.loaded = False
        self.pending = deque(); self.receipts = OrderedDict(); self.sequence = 0
        self.frame = ({'format_version': 1, 'app_version': __version__, 'instance_id': instance_id,
                       'project_generation': 0, 'sequence': 0, 'loaded': False}, ())
        self.encoded = None; self.encoded_frame = None
        self.last_capture = float('-inf'); self.captures = 0

    def configure(self, enabled):
        if type(enabled) is not bool: raise ModelError('External writes must be boolean')
        with self.lock:
            if self.enabled != enabled:
                self.enabled = enabled; self.write_token = secrets.token_urlsafe(32)
                if not enabled: self._cancel('External writes disabled')

    def bind(self, generation, loaded=True):
        with self.lock:
            self._cancel('Project generation changed')
            self.generation = generation; self.loaded = loaded
            self.write_token = secrets.token_urlsafe(32)

    def _cancel(self, error):
        while self.pending:
            item = self.pending.popleft()
            self.receipts[item['request_id']].update(status='rejected', error=error)

    def session(self):
        with self.lock:
            return {'format_version': 1, 'instance_id': self.instance_id, 'read_token': self.read_token,
                    'write_token': self.write_token if self.enabled else None,
                    'writes_enabled': self.enabled, 'project_generation': self.generation}

    def authorized(self, token, *, write=False):
        with self.lock:
            expected = self.write_token if write else self.read_token
            return (not write or self.enabled) and isinstance(token, str) and secrets.compare_digest(expected, token)

    def description(self):
        with self.lock:
            return {'writes_enabled': self.enabled, 'pending_writes': len(self.pending),
                    'queue_capacity': MAX_PENDING, 'snapshot_sequence': self.sequence,
                    'snapshot_captures': self.captures, 'sampling': 'committed command boundaries; sampled within scan batches',
                    'write_application': 'before a scan; at most four transactions per boundary'}

    def sample_due(self): return self.clock() - self.last_capture >= 0.1

    def capture(self, engine, generation, tags):
        rows = []
        for tag in tags[:MAX_TAGS]:
            value = tag.get('value'); problem = tag.get('problem', '')
            if not (value is None or isinstance(value, (str, bool, int, float))):
                value = None; problem = 'Unsupported telemetry value'
            if isinstance(value, float) and not math.isfinite(value): value = None; problem = 'Non-finite value'
            quality = 'bad' if problem else 'unknown' if value is None else 'good'
            rows.append((tag['name'], tag['type'], value, quality, problem))
        metadata = {'format_version': 1, 'app_version': __version__, 'instance_id': self.instance_id,
                    'project_generation': generation, 'loaded': True, 'project_name': engine.project.name,
                    'source_l5x_sha256': engine.project.sha256, 'scan': engine.scan_count,
                    'logic_revision':getattr(engine.project,'runtime_revision',0),
                    'simulation_ms': engine.time_ms, 'captured_at': datetime.now(timezone.utc).isoformat(),
                    'fault': engine.fault, 'blocked': bool(engine.blockers),
                    'tag_count': len(tags), 'truncated': len(tags) > MAX_TAGS}
        with self.lock:
            self.sequence += 1; metadata['sequence'] = self.sequence
            self.frame = (metadata, tuple(rows)); self.captures += 1; self.last_capture = self.clock()

    def snapshot(self):
        with self.lock: frame = self.frame
        # Encoding/slow readers contend only with one another, never producers.
        with self.encoding_lock:
            if self.encoded_frame is not frame:
                metadata, rows = frame
                value = {**metadata, 'tags': [dict(name=n, type=t, value=v, quality=q, problem=p) for n,t,v,q,p in rows]}
                raw = json.dumps(value, allow_nan=False, separators=(',', ':')).encode('utf-8')
                if len(raw) > MAX_SNAPSHOT_BYTES:
                    raw = json.dumps({**metadata, 'tags': [], 'truncated': True,
                                      'error': 'Snapshot exceeds telemetry byte limit'}, separators=(',', ':')).encode()
                self.encoded = raw; self.encoded_frame = frame
            return f'"{self.instance_id}:{frame[0]["sequence"]}"', self.encoded

    def enqueue(self, data):
        if not isinstance(data, dict) or set(data) - {'request_id','instance_id','project_generation','writes','ttl_ms'}:
            raise DeviceIOError(400, 'Invalid device transaction fields')
        request_id = data.get('request_id'); writes = data.get('writes'); ttl = data.get('ttl_ms', 5000)
        if not isinstance(request_id, str) or not IDENTIFIER.fullmatch(request_id): raise DeviceIOError(400, 'Invalid request_id')
        if type(ttl) is not int or not 1 <= ttl <= 60000: raise DeviceIOError(400, 'ttl_ms must be 1..60000')
        if type(data.get('project_generation')) is not int: raise DeviceIOError(400, 'Invalid project_generation')
        if not isinstance(writes, list) or not 1 <= len(writes) <= MAX_WRITES: raise DeviceIOError(400, 'Expected 1..128 writes')
        for write in writes:
            if not isinstance(write, dict) or set(write) != {'tag','value'}: raise DeviceIOError(400, 'Invalid write fields')
            if not isinstance(write['tag'], str) or len(write['tag']) > 512 or not STATIC_TAG.fullmatch(write['tag']):
                raise DeviceIOError(400, 'Static tag paths required')
            value = write['value']
            if not isinstance(value, (bool,int,float,str)) or isinstance(value,float) and not math.isfinite(value):
                raise DeviceIOError(400, 'Scalar finite values required')
        try: raw = json.dumps(data, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
        except (ValueError, TypeError) as error: raise DeviceIOError(400, 'Invalid device transaction') from error
        if len(raw) > MAX_REQUEST_BYTES: raise DeviceIOError(413, 'Device transaction exceeds byte limit')
        fingerprint = hashlib.sha256(raw).hexdigest()
        with self.lock:
            previous = self.receipts.get(request_id)
            if previous:
                if previous['_fingerprint'] != fingerprint: raise DeviceIOError(409, 'request_id was already used with different content')
                return self._public(previous)
            if not self.enabled: raise DeviceIOError(403, 'External writes disabled')
            if not self.loaded or data.get('instance_id') != self.instance_id or data.get('project_generation') != self.generation:
                raise DeviceIOError(409, 'Stale application instance or project generation')
            self._expire()
            if len(self.pending) >= MAX_PENDING: raise DeviceIOError(429, 'Device input queue is full')
            while len(self.receipts) >= MAX_RECEIPTS:
                oldest = next((key for key,value in self.receipts.items() if value['status'] != 'queued'), None)
                if oldest is None: raise DeviceIOError(429, 'Device receipt capacity reached')
                del self.receipts[oldest]
            item = {'request_id': request_id, 'generation': self.generation, 'deadline': self.clock()+ttl/1000,
                    'writes': tuple((w['tag'],w['value']) for w in writes)}
            receipt = {'request_id': request_id, 'status': 'queued', 'instance_id': self.instance_id,
                       'project_generation': self.generation, '_fingerprint': fingerprint}
            self.pending.append(item); self.receipts[request_id] = receipt
            return self._public(receipt)

    @staticmethod
    def _public(receipt): return {k:v for k,v in receipt.items() if not k.startswith('_')}

    def _expire(self):
        now = self.clock(); remaining = deque()
        for item in self.pending:
            if item['deadline'] <= now: self.receipts[item['request_id']].update(status='rejected',error='Device transaction expired')
            else: remaining.append(item)
        self.pending = remaining

    def receipt(self, request_id):
        with self.lock:
            self._expire()
            if request_id not in self.receipts: raise DeviceIOError(404, 'Device receipt not found or evicted')
            return self._public(self.receipts[request_id])

    def apply(self, app):
        """Caller owns app.lock; input/network code never takes it."""
        from .ethernetip import Router
        router = Router(app, None); engine = app.engine; memory = engine.memory
        with self.lock:
            self._expire()
            items = [self.pending.popleft() for _ in range(min(4,len(self.pending)))]
        for item in items:
            before = {}
            try:
                resolved = []
                for tag,value in item['writes']:
                    key,parts,_ = router.access(tag,True)
                    memory.check_writable(tag)
                    address = (key,tuple(parts))
                    for other_key,other_parts in resolved:
                        if key == other_key and (tuple(parts)[:len(other_parts)] == other_parts or other_parts[:len(parts)] == tuple(parts)):
                            raise ModelError('Device transaction contains overlapping destinations')
                    resolved.append(address)
                before = {key:copy.deepcopy(memory.values[key]) for key,_ in resolved}
                for tag,value in item['writes']: memory.write(tag,value)
                result = {'status':'applied','applied_before_scan':engine.scan_count+1,'simulation_ms':engine.time_ms}
            except Exception as error:
                memory.values.update(before)
                result = {'status':'rejected','error':str(error)}
            with self.lock: self.receipts[item['request_id']].update(result)
