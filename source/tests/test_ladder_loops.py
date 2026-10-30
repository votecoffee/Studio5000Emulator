"""Ladder FOR/BRK: control transfers, typed operands and scan transactions."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_runtime as fixtures
from logixlab.model import ModelError
from logixlab.runtime import Engine
from logixlab.server import Application


class LadderLoopTests(unittest.TestCase):
    engine=fixtures.RuntimeTests.engine

    def setUp(self):
        fixtures.RuntimeTests.setUp(self)
        self.root=E.parse(Path(__file__).resolve().parents[1]/'samples/LoopLab.L5X').getroot()

    def routine(self,name,texts,kind='RLL',program='MainProgram'):
        routines=self.root.find(f'./Controller/Programs/Program[@Name="{program}"]/Routines')
        old=routines.find(f'./Routine[@Name="{name}"]')
        if old is not None:routines.remove(old)
        content=E.SubElement(E.SubElement(routines,'Routine',Name=name,Type=kind),'STContent' if kind=='ST' else 'RLLContent')
        for i,text in enumerate(texts):
            if kind=='ST':E.SubElement(content,'Line',Number=str(i)).text=text
            else:E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text

    def tag(self,name,dtype='DINT',value=0,constant=False):
        t=E.SubElement(self.root.find('./Controller/Tags'),'Tag',Name=name,TagType='Base',DataType=dtype,Constant=str(constant).lower())
        E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'DataValue',DataType=dtype,Radix='Decimal',Value=str(value))
        return t

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def values(self,e,*refs):return tuple(e.memory.read(ref) for ref in refs)

    def test_sample_inclusive_range_and_each_scan_restarts_index(self):
        e=self.checked();self.assertEqual(e.memory.read('Index'),99)
        for i in (1,2):
            e.step();self.assertEqual(self.values(e,'Total','Iterations','TailRuns','Index','Scans'),(10,5,5,5,i))
            self.assertTrue(e.memory.read('Completed'));self.assertEqual(e.calls.stack,[])

    def test_descending_stride_and_final_index(self):
        e=self.checked();e.memory.write('Start',5);e.memory.write('Finish',-1);e.memory.write('Increment',-2);e.step()
        self.assertEqual(self.values(e,'Total','Iterations','Index'),(8,4,-3))

    def test_equal_endpoint_executes_once_in_either_direction(self):
        for step in (-2,2):
            e=self.checked();e.memory.write('Start',3);e.memory.write('Finish',3);e.memory.write('Increment',step);e.step()
            self.assertEqual(self.values(e,'Total','Iterations','Index'),(3,1,3+step))

    def test_empty_range_sets_initial_but_does_not_call(self):
        for start,end,step in ((4,0,1),(0,4,-1),(4,0,0)):
            e=self.checked();e.memory.write('Start',start);e.memory.write('Finish',end);e.memory.write('Increment',step);e.step()
            self.assertEqual(self.values(e,'Total','Iterations','Index'),(0,0,start));self.assertTrue(e.memory.read('Completed'))

    def test_false_for_does_not_assign_index_or_execute(self):
        e=self.checked();e.memory.write('Enabled',False);e.step()
        self.assertEqual(self.values(e,'Index','Iterations','Completed'),(99,0,False))

    def test_break_preserves_index_and_skips_tail_and_increment(self):
        e=self.checked();e.memory.write('BreakEnabled',True);e.step()
        self.assertEqual(self.values(e,'Total','Iterations','TailRuns','Index','Completed'),(1,3,2,2,True))
        rows=[row for row in e.trace if row['control']=='break'];self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['events'][-1]['instruction'],'BRK');self.assertTrue(rows[0]['events'][-1]['transfer'])

    def test_break_outside_loop_and_false_break_have_no_action(self):
        self.routine('Accumulate',['AFI()BRK()ADD(Iterations,1,Iterations);','ADD(Total,Index,Total);'])
        e=self.checked(['BRK()FOR(Accumulate,Index,0,2,1)BRK()ADD(Scans,1,Scans);']);e.step()
        self.assertEqual(self.values(e,'Total','Iterations','Index','Scans'),(3,0,3,1))

    def test_ret_and_tnd_end_iteration_but_do_not_break_loop(self):
        for instruction in ('RET','TND'):
            self.routine('Accumulate',[f'ADD(Iterations,1,Iterations){instruction}()ADD(TailRuns,1,TailRuns);'])
            e=self.checked();e.step();self.assertEqual(self.values(e,'Iterations','TailRuns','Index'),(5,0,5))

    def test_nested_for_break_exits_only_innermost(self):
        self.tag('InnerIndex')
        self.routine('Inner',['ADD(Iterations,1,Iterations)BRK()ADD(TailRuns,100,TailRuns);'])
        self.routine('Accumulate',['FOR(Inner,InnerIndex,0,4,1)ADD(TailRuns,1,TailRuns);'])
        e=self.checked();e.step();self.assertEqual(self.values(e,'Iterations','TailRuns','Index','InnerIndex'),(5,5,5,0))
        self.assertEqual(e.calls.stack,[])

    def test_break_unwinds_jsr_and_skips_its_return_transfer(self):
        self.routine('Helper',['ADD(Iterations,1,Iterations)BRK();','RET(Total);'])
        self.routine('Accumulate',['JSR(Helper,0,GuardResult)ADD(TailRuns,1,TailRuns);'])
        e=self.checked(['FOR(Accumulate,Index,0,4,1)ADD(Scans,1,Scans);']);e.step()
        self.assertEqual(self.values(e,'Iterations','TailRuns','Index','Scans','GuardResult'),(1,0,0,1,0))
        self.assertEqual(len([row for row in e.trace if row['control']=='break']),2);self.assertEqual(e.calls.stack,[])

    def test_break_unwinds_structured_text_jsr_bridge(self):
        self.routine('Helper',['BRK();'])
        self.routine('Bridge',['JSR(Helper,0); TailRuns:=TailRuns+1;'],kind='ST')
        self.routine('Accumulate',['JSR(Bridge,0);','ADD(Iterations,1,Iterations);'])
        e=self.checked();e.step();self.assertEqual(self.values(e,'Index','Iterations','TailRuns'),(0,0,0))
        self.assertTrue(any(row.get('detail')=='break' for row in e.trace))

    def test_parameterless_st_target_and_sbr_ret(self):
        self.routine('Accumulate',['SBR(); Total:=Total+Index; RET(); TailRuns:=100;'],kind='ST')
        e=self.checked();e.step();self.assertEqual(self.values(e,'Total','TailRuns','Index'),(10,0,5))

    def test_terminal_and_step_are_live_at_each_test_and_increment(self):
        self.routine('Accumulate',['ADD(Iterations,1,Iterations)MOV(2,Increment)MOV(4,Finish);'])
        e=self.checked();e.memory.write('Finish',20);e.step()
        self.assertEqual(self.values(e,'Iterations','Index','Increment','Finish'),(3,6,2,4))

    def test_called_routine_can_modify_index_before_increment(self):
        self.routine('Accumulate',['ADD(Iterations,1,Iterations)ADD(Index,1,Index);'])
        e=self.checked();e.step();self.assertEqual(self.values(e,'Iterations','Index'),(3,6))

    def test_zero_step_can_exit_with_break(self):
        self.routine('Accumulate',['ADD(Iterations,1,Iterations)GEQ(Iterations,3)BRK();'])
        e=self.checked();e.memory.write('Increment',0);e.step();self.assertEqual(self.values(e,'Iterations','Index'),(3,0))

    def test_zero_step_empty_routine_consumes_budget_and_rolls_back(self):
        self.routine('Accumulate',[]);e=self.checked();e.memory.write('Increment',0);e.instruction_limit=100
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'FOR instruction budget'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual((e.scan_count,e.time_ms,e.calls.stack),(0,0,[]))

    def test_late_fault_restores_loop_writes_trace_and_first_scan_for_retry(self):
        e=self.checked();e.memory.write('FaultDivisor',0);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual((e.time_ms,e.scan_count,e.trace,e.calls.stack),(0,0,[],[]))
        self.assertTrue(e.first_scan_pending);e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual(self.values(e,'Total','Iterations','Scans'),(10,5,1))

    def test_dint_increment_overflow_rolls_back(self):
        self.routine('Accumulate',['NOP();']);e=self.checked(['FOR(Accumulate,Index,2147483647,2147483647,1);'])
        with self.assertRaisesRegex(ModelError,'DINT overflow'):e.step()
        self.assertEqual(e.memory.read('Index'),99);self.assertEqual(e.calls.stack,[])

    def test_both_directions_use_signed_integer_sources_and_literals(self):
        self.tag('Small','SINT',3);self.tag('Short','INT',-1)
        e=self.checked(['FOR(Accumulate,Index,Small,-1,Short);']);e.step()
        self.assertEqual(self.values(e,'Total','Iterations','Index'),(5,5,-2))

    def test_constant_sources_allowed_but_constant_index_blocked_even_false(self):
        self.tag('Limit','DINT',2,True);e=self.checked(['FOR(Accumulate,Index,0,Limit,1);']);e.step();self.assertEqual(e.memory.read('Total'),3)
        self.root.find('./Controller/Tags/Tag[@Name="Index"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()FOR(Accumulate,Index,0,Limit,1);']).blockers)

    def test_unknown_runtime_sources_fault_only_when_reached(self):
        e=self.checked();key,_,_=e.memory.resolve('Start');e.memory.values[key]=None
        e.memory.write('Enabled',False);e.step();e.memory.write('Enabled',True)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual((e.scan_count,e.time_ms,e.memory.read('Index')),(1,10,99));self.assertEqual(e.calls.stack,[])

    def test_static_array_element_and_alias_index(self):
        t=E.SubElement(self.root.find('./Controller/Tags'),'Tag',Name='Indices',TagType='Base',DataType='DINT',Dimensions='2')
        a=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='2',Radix='Decimal')
        for i in range(2):E.SubElement(a,'Element',Index=f'[{i}]',Value='99')
        E.SubElement(self.root.find('./Controller/Tags'),'Tag',Name='LoopIndex',TagType='Alias',AliasFor='Indices[1]')
        self.routine('Accumulate',['ADD(Total,LoopIndex,Total);'])
        e=self.checked(['FOR(Accumulate,LoopIndex,0,2,1);']);e.step()
        self.assertEqual(self.values(e,'Total','Indices[0]','Indices[1]'),(3,99,3))

    def test_bad_arity_types_literals_references_and_targets_block(self):
        self.tag('Wide','LINT');self.tag('RealValue','REAL');self.tag('Short','INT')
        for text in ('FOR(Accumulate,Index,0,2);','BRK(Index);','FOR(Missing,Index,0,2,1);',
                     'FOR(MainRoutine,Index,0,2,1);','FOR(Accumulate,Short,0,2,1);','FOR(Accumulate,2,0,2,1);',
                     'FOR(Accumulate,Index,0,2,1.0);','FOR(Accumulate,Index,0,2,TRUE);',
                     'FOR(Accumulate,Index,Wide,2,1);','FOR(Accumulate,Index,0,RealValue,1);',
                     'FOR(Accumulate,Index,0,2147483648,1);','FOR(Accumulate,Index,0,2,Index.0);'):
            with self.subTest(text=text):self.assertTrue(self.engine([text]).blockers)

    def test_parameterized_target_and_recursive_graph_block(self):
        for body in (['SBR(Total);'],['RET(Total);'],['FOR(Accumulate,Index,0,2,1);'],['JSR(MainRoutine,0);']):
            self.routine('Accumulate',body)
            with self.subTest(body=body):self.assertTrue(self.engine().blockers)

    def test_shared_25_level_for_jsr_nesting_limit(self):
        for count in (25,26):
            for i in range(count):
                self.tag('I'+str(i)) if self.root.find(f'./Controller/Tags/Tag[@Name="I{i}"]') is None else None
                self.routine('Depth'+str(i),[f'FOR(Depth{i+1},I{i},0,0,1);' if i<count-1 else 'ADD(Total,1,Total);'])
            e=self.checked(['JSR(Depth0,0);'])
            if count==25:e.step();self.assertEqual(e.memory.read('Total'),1)
            else:
                with self.assertRaisesRegex(ModelError,'25'):e.step()
                self.assertEqual(e.memory.read('Total'),0)
            self.assertEqual(e.calls.stack,[])

    def test_harness_reaches_and_prescans_called_routines_once(self):
        self.routine('Accumulate',['OTE(Completed);','ADD(Iterations,1,Iterations);'])
        self.routine('MainRoutine',['AFI()FOR(Accumulate,Index,0,2,1);','FOR(Accumulate,Index,0,1,1);'])
        e=self.checked(mode='routine',routine='MainProgram/MainRoutine')
        self.assertEqual(len(e.active),2);self.assertEqual(e.prescan_count,1);self.assertFalse(e.memory.read('Completed'))
        e.step();self.assertEqual(e.memory.read('Iterations'),2)

    def test_disabled_mcr_does_not_call_for_and_break_in_zone_blocks(self):
        e=self.checked(['AFI()MCR();','FOR(Accumulate,Index,0,4,1);','MCR();']);e.step()
        self.assertEqual(self.values(e,'Index','Iterations'),(99,0))
        self.assertTrue(self.engine(['MCR();','BRK();','MCR();']).blockers)

    def test_other_profiles_and_st_instruction_forms_block(self):
        for version,processor in (('34','1756-L85E'),('35','1756-L73')):
            c=self.root.find('Controller');c.set('MajorRev',version);c.set('ProcessorType',processor)
            self.assertTrue(self.engine().blockers)
        c.set('MajorRev','35');c.set('ProcessorType','1756-L85E')
        for text in ('BRK();','FOR(Accumulate,Index,0,2,1);'):
            self.routine('MainRoutine',[text],kind='ST');self.assertTrue(self.engine().blockers)

    def event_fixture(self,fault=False):
        for name in ('EventIndex','EventCount','EventTail'):self.tag(name)
        programs=self.root.find('./Controller/Programs')
        p=E.SubElement(programs,'Program',Name='EventProgram',MainRoutineName='MainRoutine',Disabled='false',Class='Standard')
        E.SubElement(p,'Tags');E.SubElement(p,'Routines')
        self.routine('MainRoutine',['BRK();','FOR(Body,EventIndex,0,1,1);','BRK()ADD(EventTail,1,EventTail);']+(['DIV(1,0,GuardResult);'] if fault else []),program='EventProgram')
        self.routine('Body',['ADD(EventCount,1,EventCount);'],program='EventProgram')
        self.routine('Accumulate',['EVENT(EventTask);','ADD(Iterations,1,Iterations)ADD(Total,Index,Total);'])
        task=E.SubElement(self.root.find('./Controller/Tasks'),'Task',Name='EventTask',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
        E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
        E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')

    def test_preempting_event_has_separate_for_break_stack(self):
        self.event_fixture();e=self.checked();e.step()
        self.assertEqual(self.values(e,'Total','Iterations','Index','EventCount','EventTail','EventIndex'),(10,5,5,10,5,2))
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],5);self.assertEqual(e.calls.stack,[])

    def test_fault_in_preempting_event_restores_parent_loop_and_scheduler(self):
        self.event_fixture(fault=True);e=self.checked();before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule);self.assertEqual(e.calls.stack,[])

    def test_periodic_and_deferred_prescan_loop(self):
        t=self.root.find('./Controller/Tasks/Task');t.set('Type','PERIODIC');t.set('Rate','20')
        e=self.checked();h=Engine(e.project,defer_prescan=True);self.assertEqual(h.blockers,[])
        self.assertEqual(h.memory.read('Index'),99);h.step(20)
        self.assertEqual(self.values(h,'Total','Iterations','Index'),(10,5,5));self.assertEqual(h.prescan_count,1)

    def test_detached_routine_replacement_rebuilds_loop_plan_without_changing_active_state(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();e.step();before=copy.deepcopy((e.memory.values,e.scan_count,e.time_ms))
        neutral=['FOR(Accumulate,Index,0,1,1);'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId='1'),'TextIOI').text=neutral[0]
        source=decode(container(E.tostring(xml,encoding='utf-8')));candidate,_=prepare(e,source,tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e.scan_count,e.time_ms),before);self.assertEqual(candidate.calls.stack,[])
        candidate.step();self.assertEqual(self.values(candidate,'Total','Iterations','Index'),(11,7,2))

    def test_aoi_for_and_break_are_blocked_even_when_false(self):
        from logixlab.model import Project
        path=Path(__file__).resolve().parents[1]/'samples/AOILab.L5X'
        for text in ('AFI()FOR(Accumulate,Index,0,1,1);','AFI()BRK();'):
            root=E.parse(path).getroot();content=root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition/Routines/Routine/RLLContent')
            content[0].find('Text').text=text
            target=Path(self.tmp.name)/'aoi.L5X';E.ElementTree(root).write(target,encoding='utf-8',xml_declaration=True)
            self.assertTrue(Engine(Project(target)).blockers)

    def test_application_sample_and_report_contract(self):
        app=Application(self.tmp.name);state=app.command('demo',{'sample':'LoopLab'});self.assertEqual(state['blockers'],[])
        state=app.command('step',{'count':1});self.assertEqual(state['scan'],1)
        report=app.command('report',{})['ladder_loops'];self.assertEqual(report['targets'],['mainprogram/accumulate'])
        self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
