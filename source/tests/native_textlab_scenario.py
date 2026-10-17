"""Model acceptance on authored or freshly SDK-exported Text Lab L5X."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from logixlab.model import Project
from logixlab.runtime import Engine


def check(path):
    sha=hashlib.sha256(path.read_bytes()).hexdigest();e=Engine(Project(path));assert not e.blockers,e.blockers
    assert e.memory.read('ClearedOnRun')==0 and e.memory.read('ScanTotal')==0
    assert e.memory.read('Accumulator.Count')==0
    for _ in range(3):e.step()
    expected={'ScanTotal':3,'ClearedOnRun':17,'Sum':30,'Values':[0,3,6,9,12],'Scaled':61,'CaseResult':20,
              'WhileCount':3,'RepeatCount':2,'SearchResult':3,'AOITotal':6,'Packed':15,'Done':True,'Truth':True}
    for ref,value in expected.items():assert e.memory.read(ref)==value,(ref,e.memory.read(ref))
    assert e.memory.string('Message')=='SCAN 3' and e.memory.string('Shadow')=='SCAN 3'
    assert any(t['routine']=='MainProgram/MainRoutine' and t['number']=='1' and t.get('detail')=='ScanTotal = 3' for t in e.trace)
    assert any(r['number']=='37' and r['nodes'][0].name=='JSR' for r in e.project.routines['mainprogram/mainroutine'].rungs)
    e.memory.write('Enable',False);e.memory.write('Step',9);e.memory.write('Selector',1);e.step()
    assert e.memory.read('State')==-1 and e.memory.read('AOITotal')==6
    assert e.memory.read('Accumulator.Step')==2 and e.memory.read('CaseResult')==10
    assert not e.calls.stack and hashlib.sha256(path.read_bytes()).hexdigest()==sha
    return {'source_l5x_sha256':sha,'source_unchanged':True,'scans':e.scan_count,'expected_after_3_scans':expected,
            'strings_after_3_scans':{'Message':'SCAN 3','Shadow':'SCAN 3'},'skipped_st_aoi_input_preserved':True,
            'native_source_line_trace_and_call_mapping':True,
            'report':e.report(),'native_runtime_equivalence':'NOT TESTED'}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--l5x',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    r=check(Path(a.l5x));Path(a.out).write_text(json.dumps(r,indent=2),encoding='utf-8')
    print('PASS: ST controls, strings, indirect bits, prescan, ST AOI and mixed ST/RLL/ST call chain')
