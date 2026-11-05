"""Latched EVENT request/active-overlap status with live reads and atomic commit."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_event_tasks as events
from logixlab.model import ModelError


def scalar(tags,name,kind,value):
    tag=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType=kind)
    E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=kind,Value=str(value))


class EventStatusTests(unittest.TestCase):
    setUp=events.EventTaskTests.setUp

    def engine(self,bodies=None,*,mutate=None,**kwargs):
        def extra(root):
            tags=root.find('./Controller/Tags')
            for name,kind,value in [('SelfTrigger','BOOL',0),('ClearStatus','BOOL',0),('ReadStatus','BOOL',0),
                    ('Command','DINT',0),('Index','DINT',99),('Divisor','DINT',1),('CallerStatus','DINT',-1),
                    ('EntryStatus','DINT',-1),('AfterStatus','DINT',-1),('ExitStatus','DINT',-1)]:scalar(tags,name,kind,value)
            tag=E.SubElement(tags,'Tag',Name='Values',TagType='Base',DataType='DINT',Dimensions='3')
            array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='3')
            for i,v in ((0,101),(2,999)):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(v))
            if mutate:mutate(root)
        bodies=bodies or [['XIC(StartPB)EVENT(Task1);','GSV(Task,Task1,Status,CallerStatus);'],
                          ['GSV(Task,THIS,Status,EntryStatus);','XIC(SelfTrigger)EVENT(Task1);',
                           'GSV(Task,THIS,Status,AfterStatus);','XIC(ClearStatus)SSV(Task,THIS,Status,Command);',
                           'GSV(Task,THIS,Status,ExitStatus);','ADD(Count1,1,Count1);']]
        return events.EventTaskTests.engine(self,bodies,mutate=extra,**kwargs)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.trace,e.scan_count,e.time_ms,
                              e.scheduler_description(),e._program_timings,e._task_scan_timings,e._task_event_status))

    def fault(self,e,pattern):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,pattern):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertIsNone(e._event_dispatch);self.assertIsNone(e._executing_task)

    def test_initial_status_and_false_trigger_remain_zero(self):
        e=self.checked();self.assertEqual(e._task_event_status,{'task1':0});e.step()
        self.assertEqual(e.memory.read('CallerStatus'),0);self.assertEqual(e.memory.read('EntryStatus'),-1)

    def test_accepted_event_is_visible_in_this_body_and_restored_caller(self):
        e=self.checked();e.memory.write('StartPB',True);e.step()
        self.assertEqual([e.memory.read(n) for n in ('CallerStatus','EntryStatus','AfterStatus','ExitStatus')],[1]*4)
        self.assertEqual(e._task_event_status,{'task1':1});e.memory.write('StartPB',False);e.step();self.assertEqual(e.memory.read('CallerStatus'),1)

    def test_active_self_request_latches_overlap_without_another_execution(self):
        e=self.checked();e.memory.write('StartPB',True);e.memory.write('SelfTrigger',True);e.step()
        self.assertEqual(e.memory.read('EntryStatus'),1);self.assertEqual(e.memory.read('AfterStatus'),5)
        self.assertEqual(e.memory.read('Count1'),1);self.assertEqual(e.scheduler_description()['tasks'][1]['event_instruction_overlaps'],1)
        e.memory.write('StartPB',False);e.step();self.assertEqual(e.memory.read('CallerStatus'),5)

    def test_gsv_clear_one_bit_ssv_keeps_other_bit_and_source(self):
        e=self.checked([['EVENT(Task1);','GSV(Task,Task1,Status,CallerStatus);'],
                        ['EVENT(Task1);','GSV(Task,THIS,Status,Command);','OTU(Command.0);','SSV(Task,THIS,Status,Command);']]);e.step()
        self.assertEqual(e.memory.read('Command'),4);self.assertEqual(e.memory.read('CallerStatus'),4);self.assertEqual(e._task_event_status['task1'],4)

    def test_supported_replacement_words_are_exact_and_source_is_read_only(self):
        e=self.checked([['SSV(Task,task1,STATUS,Command);','GSV(Task,TASK1,status,CallerStatus);'],['NOP();']])
        for value in (0,1,4,5,0):
            e.memory.write('Command',value);e.step();self.assertEqual(e.memory.read('Command'),value);self.assertEqual(e.memory.read('CallerStatus'),value)

    def test_other_status_bits_and_unknown_sources_fault_atomically(self):
        e=self.checked([['SSV(Task,Task1,Status,Command);'],['NOP();']])
        for value in (2,8,-1):e.memory.write('Command',value);self.fault(e,'bits')
        e.memory.values['command']=None;self.fault(e,'Unknown|known')

    def test_false_ssv_and_prescan_skip_invalid_source_index(self):
        e=self.checked([['XIC(ReadStatus)SSV(Task,Task1,Status,Values[Index]);'],['NOP();']]);e.enter_run();e.step()
        self.assertEqual(e._task_event_status['task1'],0);e.memory.write('ReadStatus',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);self.fault(e,'Unknown|known');e.memory.write('Values[1]',4);e.step();self.assertEqual(e._task_event_status['task1'],4)

    def test_gsv_dormant_and_unknown_complete_destinations(self):
        e=self.checked([['XIC(ReadStatus)GSV(Task,Task1,Status,Values[Index]);'],['NOP();']]);e.enter_run();e.step()
        self.assertIsNone(e.memory.read('Values')[1]);e.memory.write('ReadStatus',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Values'),[101,0,999])

    def test_pending_duplicate_has_trigger_bit_but_no_active_overlap(self):
        def periodic(root):root.find('./Controller/Tasks/Task').attrib.update(Type='PERIODIC',Rate='10',Priority='5')
        e=self.checked([['EVENT(Task1);','EVENT(Task1);','GSV(Task,Task1,Status,CallerStatus);'],
                        ['GSV(Task,THIS,Status,EntryStatus);','ADD(Count1,1,Count1);']],priority='14',mutate=periodic);e.step()
        self.assertEqual(e.memory.read('CallerStatus'),1);self.assertEqual(e.memory.read('EntryStatus'),1);self.assertEqual(e.memory.read('Count1'),1)
        row=e.scheduler_description()['tasks'][1];self.assertEqual((row['event_pending_requests_coalesced'],row['event_instruction_overlaps']),(1,0))

    def test_masked_request_status_is_visible_before_uie_dispatch(self):
        e=self.checked([['UID();','EVENT(Task1);','GSV(Task,Task1,Status,CallerStatus);','UIE();'],['GSV(Task,THIS,Status,EntryStatus);']]);e.step()
        self.assertEqual(e.memory.read('CallerStatus'),1);self.assertEqual(e.memory.read('EntryStatus'),1)

    def test_parent_and_event_faults_restore_status_with_other_task_state(self):
        for bodies in ([['EVENT(Task1);','DIV(1,Divisor,SpeedCommand);'],['EVENT(Task1);']],
                       [['EVENT(Task1);'],['EVENT(Task1);','DIV(1,Divisor,SpeedCommand);']]):
            e=self.checked(bodies);e.memory.write('Divisor',0);self.fault(e,'zero');e.memory.write('Divisor',1);e.step();self.assertEqual(e._task_event_status['task1'],5)

    def test_st_named_and_this_status_replacements_share_live_state(self):
        e=self.checked([['EVENT(Task1); GSV(Task,Task1,Status,CallerStatus);'],
                        ['GSV(Task,THIS,Status,EntryStatus); SSV(Task,THIS,Status,Command); GSV(Task,THIS,Status,ExitStatus);']],st=True,event_st=True)
        e.memory.write('Command',4);e.step();self.assertEqual((e.memory.read('EntryStatus'),e.memory.read('ExitStatus'),e.memory.read('CallerStatus')),(1,4,4))

    def test_run_entry_retains_status_and_fresh_model_resets(self):
        e=self.checked();e.memory.write('StartPB',True);e.step();e.enter_run();self.assertEqual(e._task_event_status['task1'],1)
        from logixlab.runtime import Engine
        self.assertEqual(Engine(e.project)._task_event_status['task1'],0)

    def test_invalid_task_context_type_permissions_and_profile_are_guarded(self):
        for text in ('GSV(Task,Task0,Status,CallerStatus);','GSV(Task,Missing,Status,CallerStatus);',
                     'GSV(Task,THIS,Status,CallerStatus);','GSV(Task,Task1,Status,Values);',
                     'GSV(Task,Task1,Status,StartPB);','SSV(Task,Task1,Status,0);','SSV(Task,Task1,Status,CallerStatus.0);'):
            self.assertTrue(self.engine([[text],['NOP();']]).blockers,text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="CallerStatus"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        def timeout(root):events.EventTaskTests.timeout(root,'0.5')
        self.assertTrue(self.engine(mutate=timeout).blockers)

    def test_timeout_status_replacement_and_late_fault_preserve_prior_deadline(self):
        e=self.checked([['DIV(1,Divisor,SpeedCommand);'],
                        ['GSV(Task,THIS,Status,EntryStatus);','SSV(Task,THIS,Status,Command);',
                         'GSV(Task,THIS,Status,ExitStatus);','ADD(Count1,1,Count1);']],
                       mutate=lambda root:events.EventTaskTests.timeout(root,'5'))
        e.memory.write('Command',3);e.memory.write('Divisor',0);self.fault(e,'zero')
        self.assertEqual(e.scheduler_description()['tasks'][1]['next_release_ms'],5)
        self.assertEqual(e._task_event_status['task1'],0)
        e.memory.write('Divisor',1);e.step()
        self.assertEqual((e.memory.read('EntryStatus'),e.memory.read('ExitStatus'),e.memory.read('Count1')),(3,3,2))
        e.memory.write('Command',0);e.step(5)
        self.assertEqual((e.memory.read('EntryStatus'),e.memory.read('ExitStatus')),(3,0))
        self.assertEqual(e.scheduler_description()['tasks'][1]['next_release_ms'],20)
        e.step(2)
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        source=decode(container(E.tostring(xml_source(name='Main',text='NOP();'),encoding='utf-8')))
        candidate,_=prepare(e,source,('NOP();',),'Program0',0)
        self.assertEqual(candidate.scheduler_description()['tasks'][1]['next_release_ms'],20)
        candidate.step(3)
        self.assertEqual(candidate.scheduler_description()['tasks'][1]['next_release_ms'],25)
        self.assertEqual(e.scheduler_description()['tasks'][1]['next_release_ms'],20)
        e.enter_run()
        self.assertEqual(e.scheduler_description()['tasks'][1]['next_release_ms'],22)

    def test_st_loop_write_effects_guard_aliases_and_allow_disjoint_static_output(self):
        e=self.checked([['FOR Command:=0 TO Values[0] DO GSV(Task,Task1,Status,Values[1]); END_FOR;'],['NOP();']],st=True)
        e.step();self.assertEqual(e.memory.read('Values'),[101,0,999])
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='View',TagType='Alias',DataType='DINT',AliasFor='Values[Index]')
        for dest in ('Values[Index]','View'):
            e=self.engine([[f'FOR Command:=0 TO Values[2] DO GSV(Task,Task1,Status,{dest}); END_FOR;'],['NOP();']],st=True,mutate=alias)
            self.assertTrue(any('bounds/step' in b for b in e.blockers),e.blockers)

    def test_detached_edit_retains_status_and_report_keeps_native_boundary(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();e.memory.write('StartPB',True);e.step();before=self.snapshot(e)
        candidate,_=prepare(e,decode(container(E.tostring(xml_source(name='Main',text='NOP();')))),['NOP();'],'Program0',0)
        self.assertEqual(self.snapshot(e),before);self.assertEqual(candidate._task_event_status,e._task_event_status);self.assertIsNot(candidate._task_event_status,e._task_event_status)
        report=e.report()['event_task_status'];self.assertFalse(report['native_protocol_expanded']);self.assertFalse(report['native_runtime_parity']);self.assertEqual(report['values'],{'task1':1})

    def test_inhibited_target_context_and_source_binding_do_not_fabricate_status(self):
        e=self.checked(inhibited=True);e.memory.write('StartPB',True);e.step()
        self.assertEqual(e._task_event_status['task1'],0);self.assertEqual(e.memory.read('Count1'),0)
        from logixlab.runtime import Engine
        self.assertTrue(Engine(e.project,mode='routine',routine='Program1/Main').blockers)
        from logixlab import event_status
        from logixlab.model import Op
        op=Op('GSV',['Task','Task1','Status','CallerStatus']);e.memory.frames['@AOI:test']={}
        with self.assertRaisesRegex(ModelError,'AOI/harness'):event_status.validate(e,op,'@AOI:test')
        e.project.sha256='0'*64
        with self.assertRaisesRegex(ModelError,'source profile'):event_status.validate(e,op,'Program0')
        self.assertEqual(e.task_status_attributes('Task1',source_sha256=e.project.sha256),{})
