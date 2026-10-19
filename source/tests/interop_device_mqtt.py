"""Optional local-broker integration: isolated app, queued inputs and MQTT acks."""
import argparse
from collections import deque
from contextlib import ExitStack
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import sysconfig
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid


def check(port):
    import paho.mqtt.client as mqtt
    source=Path(__file__).resolve().parents[1]
    # Avoid the Windows venv redirector: wait for the actual child process so
    # its log handles are released before cleaning the temporary directory.
    python=getattr(sys,'_base_executable',sys.executable)
    environment={**os.environ,'PYTHONPATH':sysconfig.get_path('purelib')+os.pathsep+os.environ.get('PYTHONPATH','')}
    prefix='logixlab/test_'+uuid.uuid4().hex[:12]
    messages=queue.Queue();backlog=deque(maxlen=256);client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_message=lambda c,u,m:messages.put((m.topic,json.loads(m.payload) if m.payload else None))
    client.connect('127.0.0.1',port);client.loop_start()
    app=None;bridge=None;token=None;url=None;checks=[]
    def receive(predicate,timeout=10):
        for topic,value in tuple(backlog):
            if predicate(topic,value):backlog.remove((topic,value));return value
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:topic,value=messages.get(timeout=.2)
            except queue.Empty:continue
            if predicate(topic,value):return value
            backlog.append((topic,value))
        raise AssertionError('MQTT observation timed out')
    def post(action,data=None):
        request=Request(url+'/api/'+action,json.dumps(data or {}).encode(),{'X-Logix-Token':token,'Content-Type':'application/json'})
        with urlopen(request,timeout=3) as response:return json.load(response)
    def device(path):
        with urlopen(url+'/api/device-io/session',timeout=3) as response:session=json.load(response)
        with urlopen(Request(url+'/api/device-io/'+path,headers={'X-Logix-Device-Token':session['read_token']}),timeout=3) as response:return json.load(response)
    def publish(body,retain=False):
        client.publish(prefix+'/commands',json.dumps(body),qos=1,retain=retain).wait_for_publish(3)
    def ack(request_id,status):
        return receive(lambda topic,value:topic==prefix+'/acks/'+request_id and value and value.get('status')==status)
    def stop_owned(process):
        if process.poll() is None:process.terminate();process.wait(timeout=5)
    try:
        with ExitStack() as resources:
            folder=resources.enter_context(tempfile.TemporaryDirectory())
            with (Path(folder)/'app.log').open('wb') as app_log,(Path(folder)/'bridge.log').open('wb') as bridge_log:
                app=subprocess.Popen([python,str(source/'launch.py'),'--no-browser','--no-tray','--sample','NetworkLab',
                                      '--device-writes','--data-dir',folder],stdout=app_log,stderr=app_log,env=environment)
                resources.callback(stop_owned,app)
                receipt=Path(folder)/'last-session.json';deadline=time.monotonic()+10
                while not receipt.exists():
                    assert app.poll() is None,'Isolated app exited'
                    if time.monotonic()>deadline:raise AssertionError('App did not start')
                    time.sleep(.05)
                url=json.loads(receipt.read_text())['url']
                with urlopen(url+'/session.js',timeout=3) as response:token=json.loads(re.search(r'LOGIX_TOKEN = (".*?")',response.read().decode())[1])
                first=device('snapshot')
                body={'request_id':'retained_input','instance_id':first['instance_id'],
                      'project_generation':first['project_generation'],'writes':[{'tag':'Command','value':999}]}
                publish(body,True)
                client.subscribe(prefix+'/#',qos=1)
                bridge=subprocess.Popen([python,str(source/'tools/mqtt_bridge.py'),'--source',url,
                    '--broker','127.0.0.1','--port',str(port),'--topic-prefix',prefix,'--interval-ms','20','--allow-writes'],
                    stdout=bridge_log,stderr=bridge_log,env=environment)
                resources.callback(stop_owned,bridge)
                receive(lambda topic,value:topic==prefix+'/snapshot' and value and value.get('loaded'))
                self_state=post('observe')
                assert self_state['device_io']['pending_writes']==0
                checks.append('retained_command_replay_ignored')
                body={**body,'request_id':'input1','writes':[{'tag':'Command','value':123},{'tag':'ControlWord','value':1}]}
                publish(body);ack('input1','queued')
                values={t['name']:t['value'] for t in device('snapshot')['tags']}
                assert values['Command']==2,'Queued write changed memory while paused'
                post('step',{'count':1,'dt':10})
                result=ack('input1','applied');assert result['applied_before_scan']==1
                observed=receive(lambda topic,value:topic==prefix+'/snapshot' and value and value.get('scan',0)>=1)
                values={t['name']:t['value'] for t in observed['tags']};assert values['Observed']==123
                checks.extend(['queued_until_scan','atomic_input_before_logic','applied_ack','output_snapshot'])
                publish(body);assert ack('input1','applied')['applied_before_scan']==1
                assert post('observe')['device_io']['pending_writes']==0
                checks.append('duplicate_command_not_reapplied')
                bad={**body,'request_id':'invalid_input','writes':[{'tag':'Command','value':999},{'tag':'Observed','value':999}]}
                publish(bad);ack('invalid_input','queued');post('step',{'count':1,'dt':10});ack('invalid_input','rejected')
                values={t['name']:t['value'] for t in device('snapshot')['tags']};assert values['Command']==123
                checks.append('invalid_batch_rolled_back')
                post('reset');publish({**body,'request_id':'stale_input'});ack('stale_input','rejected')
                assert post('observe')['device_io']['pending_writes']==0
                checks.append('stale_generation_rejected')
                assert bridge.poll() is None
                # A second subscriber receives the retained latest complete image.
                late=queue.Queue();second=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
                second.on_message=lambda c,u,m:late.put((m.retain,json.loads(m.payload)))
                try:
                    second.connect('127.0.0.1',port);second.loop_start();second.subscribe(prefix+'/snapshot',qos=1)
                    retained,image=late.get(timeout=5);assert retained and image['instance_id']==first['instance_id']
                finally:second.disconnect();second.loop_stop()
                checks.append('late_subscriber_gets_retained_snapshot')
                return {'checks':checks,'passed':len(checks),'broker':'explicit loopback test broker',
                        'app_instance':first['instance_id'],'native_controller_validation':False}
    finally:
        if bridge is not None:
            stop_owned(bridge)
        if app is not None and app.poll() is None:
            try:post('quit');app.wait(timeout=5)
            except Exception:app.terminate();app.wait(timeout=5)
        for suffix in ('commands','snapshot','status'):
            try:client.publish(prefix+'/'+suffix,b'',qos=1,retain=True).wait_for_publish(1)
            except Exception:pass
        client.disconnect();client.loop_stop()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker-port',type=int,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();result=check(args.broker_port)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
