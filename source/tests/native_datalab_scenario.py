"""Optional source-authored Data Lab ACD integration test; requires installed SDK."""
import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab.server import Application


def check(app):
    assert not app.engine.blockers,app.engine.blockers
    for _ in range(10):app.command('step',{'dt':10})
    expected={'Grid[1,1]':50,'Scaled':110.0,'ParsedNumber':50,'LoopCount':3,
              'WideDest':9223372036854775806,'HighBit':True,'SkippedValue':0}
    for tag,value in expected.items():assert app.engine.memory.read(tag)==value,(tag,app.engine.memory.read(tag))
    assert app.engine.memory.string('Message')=='VALUE 50'
    assert app.engine.memory.string('Snippet')=='VAL'
    return expected


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--acd',default=str(Path(__file__).resolve().parents[1]/'samples/DataLab.ACD'));parser.add_argument('--work-dir',required=True);parser.add_argument('--converter')
    args=parser.parse_args();path=Path(args.acd);before=hashlib.sha256(path.read_bytes()).hexdigest();app=Application(args.work_dir)
    if args.converter:app.converter=args.converter
    app.command('load',{'name':path.name,'content':base64.b64encode(path.read_bytes()).decode()})
    expected=check(app)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    result={'source_acd_sha256':before,'source_unchanged':True,'expected':expected,'snapshot':app.command('snapshot',{}),'native_execution_equivalence':'NOT TESTED'}
    Path(args.work_dir,'datalab-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS: DataLab native ACD import and 10 deterministic model scans; source unchanged')


if __name__=='__main__':main()
