"""Model acceptance checks for authored or freshly SDK-exported Call Lab L5X."""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab.model import Project,ModelError
from logixlab.runtime import Engine


def check(path):
    before=hashlib.sha256(path.read_bytes()).hexdigest();e=Engine(Project(path));assert not e.blockers,e.blockers
    assert e.memory.read('FormalInput')==0  # Prescan passes no routine parameters.
    for _ in range(3):e.step()
    expected={'Result':24,'RealOutput':7.5,'ArrayOutput':[10,25,30],'PairOutput':{'A':13,'B':9},
              'ArrayInput':[10,20,30],'PairInput':{'A':4,'B':9},'CompareOK':True,'MaskOK':True,'CallCount':3}
    for ref,value in expected.items():assert e.memory.read(ref)==value,(ref,e.memory.read(ref))
    e.memory.write('EarlyReturn',True);e.step()
    assert e.memory.read('Result')==12 and e.memory.read('RealOutput')==2.5
    e.memory.write('Enabled',False);e.memory.write('InputValue',99);e.step()
    assert e.memory.read('FormalInput')==7 and e.memory.read('CallCount')==4 and e.memory.read('Result')==12
    assert not e.calls.stack
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
    return {'l5x_sha256':before,'source_unchanged':True,'scans':e.scan_count,'expected_after_3_scans':expected,
            'early_return':{'Result':12,'RealOutput':2.5},'false_call_no_transfer':True,
            'report':e.report(),'native_runtime_equivalence':'NOT TESTED'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--l5x',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();r=check(Path(a.l5x));Path(a.out).write_text(json.dumps(r,indent=2),encoding='utf-8')
    print('PASS: nested typed calls, independent array/UDT copies, early RET, CMP/MEQ and false-call preservation')
