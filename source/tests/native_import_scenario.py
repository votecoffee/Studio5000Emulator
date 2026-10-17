"""Optional integration check against the installed SDK, using our own demo ACD."""
import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from logixlab.server import Application


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--acd', default=str(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.ACD'))
    parser.add_argument('--work-dir', required=True, help='Private output folder for copied ACD, export, and logs')
    parser.add_argument('--converter')
    args=parser.parse_args()
    source=Path(args.acd)
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    app=Application(args.work_dir)
    if args.converter:app.converter=args.converter
    app.command('load', {'name':source.name, 'content':base64.b64encode(source.read_bytes()).decode()})
    assert not app.engine.blockers,app.engine.blockers
    app.command('write', {'tag':'StartPB','value':True})
    app.command('step', {'count':1,'dt':10})
    app.command('write', {'tag':'StartPB','value':False})
    app.command('step', {'count':100,'dt':10})
    assert app.engine.memory.read('MotorRunning') is True
    for _ in range(5):
        for value in (True,False):
            app.command('write', {'tag':'PartSensor','value':value})
            app.command('step', {'dt':10})
    assert app.engine.memory.read('Parts.ACC')==5
    assert app.engine.memory.read('BatchComplete') is True
    assert app.engine.memory.read('DisplayedPartCount')==5
    app.command('write', {'tag':'StopPB','value':True})
    app.command('step', {'dt':10})
    assert app.engine.memory.read('MotorRunning') is False
    assert app.engine.memory.read('SpeedCommand')==0
    assert before==hashlib.sha256(source.read_bytes()).hexdigest()
    result=app.command('snapshot', {})
    Path(args.work_dir,'scenario-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(f'PASS: {app.engine.scan_count} scans, v{app.engine.project.version}, source unchanged; native execution equivalence untested')


if __name__=='__main__':main()
