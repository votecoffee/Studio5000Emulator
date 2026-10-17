"""Model checks on either authored or freshly SDK-exported AOI Lab L5X."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab.model import Project
from logixlab.runtime import Engine


def check(path):
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    e=Engine(Project(path));assert not e.blockers,e.blockers
    assert e.memory.read('TotalA')==0
    assert e.memory.read('AccumulatorA.Count')==0
    for _ in range(3):e.step(10)
    expected={'TotalA':6,'TotalB':9,'SharedA':16,'SharedB':29,'AReady':False,
              'BReady':True,'ScaledValue':25.5,'Truncated':25,'NestedScale.Core.Scaled':25.5}
    for ref,value in expected.items():assert e.memory.read(ref)==value,(ref,e.memory.read(ref))
    e.memory.write('EnableA',False);e.memory.write('StepA',7);e.step()
    assert e.memory.read('TotalA')==-1
    assert e.memory.read('AccumulatorA.Step')==7
    assert e.memory.read('AccumulatorA.Count')==6
    assert e.memory.read('SharedA')==16
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    return {'l5x_sha256':before,'source_unchanged':True,'scans':e.scan_count,'expected_after_3_scans':expected,
            'false_mode':{'TotalA':-1,'AccumulatorA.Step':7,'AccumulatorA.Count':6,'SharedA':16},
            'report':e.report(),'native_runtime_equivalence':'NOT TESTED'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--l5x',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();result=check(Path(args.l5x));Path(args.out).write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PASS: Prescan, 3 true scans, false-mode input/output transfer, nested state and source preservation')
