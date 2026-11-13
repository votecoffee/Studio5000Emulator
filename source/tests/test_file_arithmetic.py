"""FAL array transforms, numeric scan distribution and transactional failures."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_array_statistics as fixtures
from logixlab.model import ModelError


def real_overflow_logic(mode='ALL'):
    return f'XIC(StartPB)FAL(Ctl,?,?,{mode},Queue[Ctl.POS],Queue[Ctl.POS]*2);'


def file_state(engine):
    return copy.deepcopy((engine.memory.values,engine.memory.frames,engine.memory._resolved,
                          engine.addons.instances,engine.scan_count,engine.time_ms,engine.last_timer,
                          engine.trace,engine.scheduler_description(),engine._file_incremental,
                          engine._file_arithmetic_retry))


class FileArithmeticTests(unittest.TestCase):
    setUp=fixtures.ArrayStatisticsTests.setUp
    engine=fixtures.ArrayStatisticsTests.engine
    checked=fixtures.ArrayStatisticsTests.checked

    def overflow(self,mode='ALL',*,rungs=None,mutate=None):
        return self.checked(rungs or [real_overflow_logic(mode)],dtype='REAL',length=3,
                            queue=(2,3e38,6,8,999),mutate=mutate)

    def test_real_all_overflow_preserves_prefix_and_retries_failing_element(self):
        e=self.overflow(rungs=[real_overflow_logic()[:-1]+'OTE(RunLatch);'])
        source=copy.deepcopy(e.memory.read('Queue'));e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Queue'),[4,source[1],6,8,999])
        self.assertEqual([e.memory.read('Ctl.'+n) for n in ('EN','DN','ER','POS')],[True,False,True,1])
        self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(len(e._file_arithmetic_retry),1)
        e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.step()
        self.assertEqual(e.memory.read('Queue'),[4,6,12,8,999])
        self.assertTrue(e.memory.read('Ctl.DN'));self.assertEqual(e._file_arithmetic_retry,set())

    def test_real_numeric_overflow_retries_while_active_rung_is_false(self):
        e=self.overflow('1');e.memory.write('StartPB',True);e.step()
        e.memory.write('StartPB',False);e.step()
        self.assertTrue(e.memory.read('Ctl.ER'));self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.step()
        self.assertEqual(e.memory.read('Queue')[:3],[4,6,6]);self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.step();self.assertEqual(e.memory.read('Queue')[:3],[4,6,12])
        self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.read('Ctl.EN'))
        self.assertEqual(e._file_arithmetic_retry,set())

    def test_real_incremental_overflow_retains_retry_across_prescan_and_requires_new_edge(self):
        e=self.overflow('INC');e.memory.write('StartPB',True);e.step()
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
        self.assertTrue(e.memory.read('Ctl.ER'));self.assertEqual(e.memory.read('Ctl.POS'),1)
        pending=e._file_arithmetic_retry.copy();values=copy.deepcopy(e.memory.values)
        e._apply_prescan(preview=True)
        self.assertEqual(e.memory.values,values);self.assertEqual(e._file_arithmetic_retry,pending)
        e.enter_run();self.assertEqual(e._file_arithmetic_retry,pending)
        e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.step()
        self.assertEqual(e.memory.read('Queue')[:3],[4,3,6]);self.assertEqual(e._file_arithmetic_retry,pending)
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Queue')[:3],[4,6,6]);self.assertEqual(e._file_arithmetic_retry,set())
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Queue')[:3],[4,6,12]);self.assertTrue(e.memory.read('Ctl.DN'))

    def test_real_overflow_and_prefix_roll_back_on_a_later_fault(self):
        e=self.overflow(rungs=[real_overflow_logic(),'DIV(1,0,SpeedCommand);'])
        e.memory.write('StartPB',True);before=file_state(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(file_state(e),before)

    def test_reset_retry_state_is_transactional_and_clears_on_success(self):
        e=self.overflow(rungs=['XIC(RunLatch)RES(Ctl);',real_overflow_logic(),
                               'DIV(1,SpeedCommand,Outgoing);'])
        e.memory.write('SpeedCommand',1);e.memory.write('StartPB',True);e.step()
        self.assertTrue(e._file_arithmetic_retry)
        e.memory.write('StartPB',False);e.memory.write('RunLatch',True);e.memory.write('SpeedCommand',0)
        before=file_state(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(file_state(e),before)
        e.memory.write('SpeedCommand',1);e.step()
        self.assertFalse(e.memory.read('Ctl.ER'));self.assertEqual(e.memory.read('Ctl.POS'),0)
        self.assertEqual(e._file_arithmetic_retry,set())

    def test_routine_replacement_copies_retry_without_mutating_active_engine(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        text=real_overflow_logic();e=self.overflow();e.memory.write('StartPB',True);e.step()
        source=decode(container(E.tostring(xml_source(text=text),encoding='utf-8')))
        candidate,_=prepare(e,source,(text,),'MainProgram',0)
        self.assertEqual(candidate._file_arithmetic_retry,e._file_arithmetic_retry)
        self.assertIsNot(candidate._file_arithmetic_retry,e._file_arithmetic_retry)
        candidate.memory.write('Queue[1]',3);candidate.memory.write('Ctl.ER',False);candidate.step()
        self.assertEqual(candidate.memory.read('Queue')[:3],[4,6,12])
        self.assertEqual(candidate._file_arithmetic_retry,set());self.assertTrue(e._file_arithmetic_retry)
        self.assertTrue(e.memory.read('Ctl.ER'));self.assertEqual(e.memory.read('Queue[0]'),4)

    def test_unknown_domain_and_binary64_calculation_failures_keep_whole_advance_rollback(self):
        def wide(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='WideInput',DataType='LREAL',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='LREAL',Value='1e200')
        for expression,mutate in (('Queue[Ctl.POS]/0.0',None),('WideInput*WideInput',wide)):
            e=self.overflow(rungs=[f'FAL(Ctl,?,?,ALL,Queue[Ctl.POS],{expression});'],mutate=mutate)
            before=file_state(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(file_state(e),before)
        e=self.overflow();e.memory.write('StartPB',True);e.memory.values['queue'][1]=None;before=file_state(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(file_state(e),before)

    def test_real_overflow_retry_uses_canonical_control_alias(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='ControlView',DataType='CONTROL',TagType='Alias',AliasFor='Ctl')
        e=self.overflow(rungs=[real_overflow_logic().replace('Ctl','ControlView')],mutate=alias)
        e.memory.write('StartPB',True);e.step()
        self.assertEqual(e._file_arithmetic_retry,{('ctl',())})
        e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.step()
        self.assertEqual(e.memory.read('Queue')[:3],[4,6,12])

    def test_real_overflow_inside_aoi_preserves_prefix_and_retries_caller_data(self):
        def worker(root):
            c=root.find('Controller')
            a=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='OverflowWorker',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            params=E.SubElement(a,'Parameters')
            for name,dtype,usage,size in [('EnableIn','BOOL','Input',0),('EnableOut','BOOL','Output',0),('Data','REAL','InOut',5),('State','CONTROL','InOut',0)]:
                required='true' if usage=='InOut' else 'false'
                p=E.SubElement(params,'Parameter',Name=name,DataType=dtype,TagType='Base',Usage=usage,Required=required,Visible=required)
                if size:p.set('Dimensions',str(size))
            E.SubElement(a,'LocalTags')
            content=E.SubElement(E.SubElement(E.SubElement(a,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='FAL(State,?,?,ALL,Data[State.POS],Data[State.POS]*2);'
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Worker',DataType='OverflowWorker',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='OverflowWorker')
            for name in ('EnableIn','EnableOut'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.overflow(rungs=['OverflowWorker(Worker,Queue,Ctl);'],mutate=worker)
        e.step();self.assertEqual(e.memory.read('Queue[0]'),4);self.assertTrue(e.memory.read('Ctl.ER'))
        self.assertEqual(e._file_arithmetic_retry,{('ctl',())})
        e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.step()
        self.assertEqual(e.memory.read('Queue')[:3],[4,6,12]);self.assertEqual(e._file_arithmetic_retry,set())

    def store_overflow(self,mode='ALL',*,rungs=None,mutate=None):
        def outputs(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Output',DataType='REAL',TagType='Base',Dimensions='5')
            data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='REAL',Dimensions='5')
            for i,value in enumerate((11,22,33,44,999)):E.SubElement(data,'Element',Index=f'[{i}]',Value=str(value))
            if mutate:mutate(root)
        text=f'XIC(StartPB)FAL(Ctl,?,?,{mode},Output[Ctl.POS],Queue[Ctl.POS]*2);'
        return self.checked(rungs or [text],dtype='LREAL',length=3,queue=(2,1e100,6,8,999),mutate=outputs)

    def test_binary64_to_real_store_overflow_retains_source_and_prefix_then_retries(self):
        e=self.store_overflow();source=e.memory.read('Queue').copy();e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Output'),[4,22,33,44,999]);self.assertEqual(e.memory.read('Queue'),source)
        self.assertEqual([e.memory.read('Ctl.'+n) for n in ('EN','DN','ER','POS')],[True,False,True,1])
        self.assertEqual(e._file_arithmetic_retry,{('ctl',())})
        e.memory.values['queue'][0]=None;e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.step()
        self.assertEqual(e.memory.read('Output'),[4,6,12,44,999]);self.assertTrue(e.memory.read('Ctl.DN'))
        self.assertEqual(e._file_arithmetic_retry,set())

    def test_binary64_store_overflow_numeric_false_rung_keeps_incoming_power(self):
        text='XIC(StartPB)FAL(Ctl,?,?,1,Output[Ctl.POS],Queue[Ctl.POS]*2)OTE(RunLatch);'
        e=self.store_overflow(rungs=[text]);e.memory.write('StartPB',True);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e.memory.write('StartPB',False);e.step();self.assertFalse(e.memory.read('RunLatch'))
        self.assertTrue(e.memory.read('Ctl.ER'));self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.step()
        self.assertEqual(e.memory.read('Output'),[4,6,33,44,999]);self.assertFalse(e.memory.read('RunLatch'))
        e.step();self.assertEqual(e.memory.read('Output'),[4,6,12,44,999]);self.assertTrue(e.memory.read('Ctl.DN'))
        self.assertFalse(e.memory.read('Ctl.EN'));self.assertEqual(e._file_arithmetic_retry,set())

    def test_binary64_store_overflow_inc_preserves_retry_through_run_and_needs_new_edge(self):
        e=self.store_overflow('INC');e.memory.write('StartPB',True);e.step()
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
        self.assertTrue(e.memory.read('Ctl.ER'));pending=e._file_arithmetic_retry.copy();values=copy.deepcopy(e.memory.values)
        e._apply_prescan(preview=True);self.assertEqual(e.memory.values,values)
        e.enter_run();self.assertEqual(e._file_arithmetic_retry,pending)
        e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.step()
        self.assertEqual(e.memory.read('Output'),[4,22,33,44,999]);self.assertEqual(e._file_arithmetic_retry,pending)
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Output'),[4,6,33,44,999]);self.assertEqual(e._file_arithmetic_retry,set())

    def test_binary64_store_overflow_inhibits_unknown_source_until_reset(self):
        text='XIC(RunLatch)RES(Ctl);'
        fal='XIC(StartPB)FAL(Ctl,?,?,ALL,Output[Ctl.POS],Queue[Ctl.POS]*2);'
        e=self.store_overflow(rungs=[text,fal]);e.memory.write('StartPB',True);e.step()
        e.memory.values['queue'][1]=None;e.step();self.assertTrue(e.memory.read('Ctl.ER'))
        e.memory.write('StartPB',False);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('RunLatch',True);e.step()
        self.assertEqual([e.memory.read('Ctl.'+n) for n in ('EN','DN','ER','POS')],[False,False,False,0])
        self.assertEqual(e._file_arithmetic_retry,set());self.assertEqual(e.memory.read('Output'),[4,22,33,44,999])

    def test_binary64_store_overflow_rolls_back_on_later_fault_and_restores_pending_retry(self):
        text='XIC(StartPB)FAL(Ctl,?,?,ALL,Output[Ctl.POS],Queue[Ctl.POS]*2);'
        e=self.store_overflow(rungs=[text,'DIV(1,SpeedCommand,Outgoing);'])
        e.memory.write('StartPB',True);e.memory.write('SpeedCommand',0);before=file_state(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(file_state(e),before)
        e.memory.write('SpeedCommand',1);e.step();self.assertTrue(e.memory.read('Ctl.ER'))
        e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.memory.write('SpeedCommand',0);before=file_state(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(file_state(e),before);self.assertTrue(e._file_arithmetic_retry)
        e.memory.write('SpeedCommand',1);e.step();self.assertEqual(e.memory.read('Output'),[4,6,12,44,999])

    def test_binary64_store_retry_uses_control_and_output_aliases(self):
        def aliases(root):
            tags=root.find('./Controller/Tags')
            E.SubElement(tags,'Tag',Name='ControlView',DataType='CONTROL',TagType='Alias',AliasFor='Ctl')
            E.SubElement(tags,'Tag',Name='OutputView',DataType='REAL',TagType='Alias',AliasFor='Output[1]')
        text='XIC(StartPB)FAL(ControlView,?,?,ALL,OutputView,Queue[ControlView.POS]*2);'
        e=self.store_overflow(rungs=[text],mutate=aliases);e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Output'),[11,4,33,44,999]);self.assertEqual(e._file_arithmetic_retry,{('ctl',())})
        e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.step()
        self.assertEqual(e.memory.read('Output'),[11,12,33,44,999]);self.assertEqual(e._file_arithmetic_retry,set())

    def test_binary64_store_retry_survives_routine_replacement_independently(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        text='XIC(StartPB)FAL(Ctl,?,?,ALL,Output[Ctl.POS],Queue[Ctl.POS]*2);'
        e=self.store_overflow();e.memory.write('StartPB',True);e.step()
        source=decode(container(E.tostring(xml_source(text=text),encoding='utf-8')))
        candidate,_=prepare(e,source,(text,),'MainProgram',0)
        candidate.memory.write('Queue[1]',3);candidate.memory.write('Ctl.ER',False);candidate.step()
        self.assertEqual(candidate.memory.read('Output'),[4,6,12,44,999]);self.assertEqual(candidate._file_arithmetic_retry,set())
        self.assertEqual(e.memory.read('Output'),[4,22,33,44,999]);self.assertTrue(e._file_arithmetic_retry)

    def test_binary64_to_real_store_overflow_inside_aoi_retries_caller_output(self):
        def worker(root):
            c=root.find('Controller')
            a=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='StoreWorker',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            params=E.SubElement(a,'Parameters')
            for name,dtype,usage,size in [('EnableIn','BOOL','Input',0),('EnableOut','BOOL','Output',0),('Data','LREAL','InOut',5),('Mapped','REAL','InOut',5),('State','CONTROL','InOut',0)]:
                required='true' if usage=='InOut' else 'false'
                p=E.SubElement(params,'Parameter',Name=name,DataType=dtype,TagType='Base',Usage=usage,Required=required,Visible=required)
                if size:p.set('Dimensions',str(size))
            E.SubElement(a,'LocalTags')
            content=E.SubElement(E.SubElement(E.SubElement(a,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='FAL(State,?,?,ALL,Mapped[State.POS],Data[State.POS]*2);'
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Worker',DataType='StoreWorker',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='StoreWorker')
            for name in ('EnableIn','EnableOut'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.store_overflow(rungs=['StoreWorker(Worker,Queue,Output,Ctl);'],mutate=worker);e.step()
        self.assertTrue(e.memory.read('Ctl.ER'));self.assertEqual(e.memory.read('Output'),[4,22,33,44,999])
        self.assertEqual(e._file_arithmetic_retry,{('ctl',())})
        e.memory.write('Queue[1]',3);e.memory.write('Ctl.ER',False);e.step()
        self.assertEqual(e.memory.read('Output'),[4,6,12,44,999]);self.assertEqual(e._file_arithmetic_retry,set())

    def test_binary64_store_overflow_signs_boundaries_and_integer_errors_stay_separate(self):
        for value in (1e100,-1e100):
            e=self.store_overflow();e.memory.write('Queue[1]',value);e.memory.write('StartPB',True);e.step()
            self.assertTrue(e.memory.read('Ctl.ER'));self.assertEqual(e.memory.read('Output'),[4,22,33,44,999])
            e.memory.write('Queue[1]',1.5e38 if value>0 else -1.5e38);e.memory.write('Ctl.ER',False);e.step()
            self.assertTrue(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Output[1]')>0,value>0)
        # An independently valid DINT destination still uses its existing range failure.
        text='FAL(Ctl,?,?,ALL,SpeedCommand,Queue[Ctl.POS]);'
        e=self.store_overflow(rungs=[text]);before=file_state(e)
        with self.assertRaisesRegex(ModelError,'DINT overflow'):e.step()
        self.assertEqual(file_state(e),before)

    def test_all_transforms_each_element_and_retains_guard(self):
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]*2+1);']);e.step()
        self.assertEqual(e.memory.read('Queue'),[5,9,13,17,999])
        self.assertEqual([e.memory.read('Ctl.'+n) for n in ('POS','EN','DN','ER')],[3,True,True,False])

    def test_done_holds_until_false_cleanup_then_rearms(self):
        e=self.checked(['XIC(StartPB)FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+1);'])
        e.memory.write('StartPB',True);e.step();e.step();self.assertEqual(e.memory.read('Queue'),[3,5,7,9,999])
        e.memory.write('StartPB',False);e.step()
        self.assertEqual([e.memory.read('Ctl.'+n) for n in ('POS','EN','DN')],[0,False,False])
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue'),[4,6,8,10,999])

    def test_numeric_continues_on_false_then_cleans_up_one_scan_after_completion(self):
        e=self.checked(['XIC(StartPB)FAL(Ctl,?,?,2,Queue[Ctl.POS],Queue[Ctl.POS]+10)OTE(RunLatch);'])
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue'),[12,14,6,8,999])
        self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('RunLatch'))
        e.memory.write('StartPB',False);e.step();self.assertEqual(e.memory.read('Queue'),[12,14,16,18,999])
        self.assertTrue(e.memory.read('Ctl.DN'));self.assertFalse(e.memory.read('Ctl.EN'));self.assertFalse(e.memory.read('RunLatch'))
        e.step();self.assertFalse(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Ctl.POS'),0)
        e.step();self.assertEqual(e.memory.read('Queue'),[12,14,16,18,999])

    def test_one_per_scan_continues_without_enable_edges_and_uses_live_source(self):
        e=self.checked(['FAL(Ctl,?,?,1,Queue[Ctl.POS],Incoming);'])
        for i in range(4):
            e.memory.write('Incoming',i+20);e.step()
            self.assertEqual(e.memory.read(f'Queue[{i}]'),i+20);self.assertEqual(e.memory.read('Ctl.POS'),i)
            self.assertEqual(e.memory.read('Ctl.DN'),i==3)

    def test_numeric_mode_clamps_to_remaining_length(self):
        e=self.checked(['FAL(Ctl,?,?,2147483647,Queue[Ctl.POS],1);']);e.step()
        self.assertEqual(e.memory.read('Queue'),[1,1,1,1,999]);self.assertTrue(e.memory.read('Ctl.DN'))

    def test_scalar_destination_accumulates_in_sequential_order(self):
        e=self.checked(['FAL(Ctl,?,?,ALL,Outgoing,Outgoing+Queue[Ctl.POS]);']);e.memory.write('Outgoing',0);e.step()
        self.assertEqual(e.memory.read('Outgoing'),20);self.assertEqual(e.memory.read('Queue'),[2,4,6,8,999])

    def test_overlapping_array_reads_see_prior_iteration_writes(self):
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS+1],Queue[Ctl.POS]);']);e.step()
        self.assertEqual(e.memory.read('Queue'),[2,2,2,2,2])

    def test_supported_numeric_types_and_real_expression_rounding(self):
        for dtype in ('SINT','INT','DINT','REAL'):
            e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],ABS(Queue[Ctl.POS]-3));'],dtype=dtype,queue=(2,4,6,8,99))
            e.step();self.assertEqual(e.memory.read('Queue'),[1,1,3,5,99])
        e=self.checked(['FAL(Ctl,?,?,ALL,Result,Queue[Ctl.POS]/2.0);']);e.step()
        self.assertEqual(e.memory.read('Result'),4.0)
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]/2.0);'],queue=(1,3,5,7,999));e.step()
        self.assertEqual(e.memory.read('Queue'),[0,2,2,4,999])

    def test_integer_math_does_not_lose_precision_above_float32_range(self):
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+1);'],queue=(16777217,16777219,-16777217,-16777219,999))
        e.step();self.assertEqual(e.memory.read('Queue'),[16777218,16777220,-16777216,-16777218,999])

    def test_bitwise_precedence_and_functions(self):
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],(Queue[Ctl.POS] AND 7) XOR 2);']);e.step()
        self.assertEqual(e.memory.read('Queue'),[0,6,4,2,999])
        e=self.checked(['FAL(Ctl,?,?,ALL,Result,SQR(Queue[Ctl.POS]));']);e.step()
        self.assertAlmostEqual(e.memory.read('Result'),2.828427076,places=6)

    def test_zero_length_and_saved_end_complete_without_reading_unknown_data(self):
        for length,position in ((0,0),(4,4)):
            e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Incoming);'],length=length,position=position)
            e.memory.values['incoming']=None;e.step()
            self.assertTrue(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Ctl.POS'),position)

    def test_saved_position_and_enable_resume(self):
        for enabled,expected in ((False,[2,5,7,9,999]),(True,[2,4,7,9,999])):
            e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+1);'],position=1)
            e.memory.write('Ctl.EN',enabled);e.step();self.assertEqual(e.memory.read('Queue'),expected)

    def test_prescan_and_unrelated_control_flags_are_retained(self):
        def flags(root):
            obj=root.find('./Controller/Tags/Tag[@Name="Ctl"]/Data/Structure')
            for n in ('EN','DN','ER','IN','FD','EU'):obj.find(f'DataValueMember[@Name="{n}"]').set('Value','1')
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],1);'],position=2,mutate=flags)
        self.assertTrue(all(e.memory.read('Ctl.'+n) for n in ('EN','DN','ER','IN','FD','EU')))
        self.assertEqual(e.memory.read('Ctl.POS'),2)
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],1);']);e.memory.write('Ctl.IN',True);e.memory.write('Ctl.FD',True);e.step()
        self.assertEqual(e.memory.read('Queue'),[1,1,1,1,999]);self.assertTrue(e.memory.read('Ctl.IN'));self.assertTrue(e.memory.read('Ctl.FD'))

    def test_error_inhibits_even_false_cleanup(self):
        e=self.checked(['AFI()FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Incoming);'])
        for n in ('ER','DN','EN'):e.memory.write('Ctl.'+n,True)
        e.memory.write('Ctl.POS',2);before=copy.deepcopy(e.memory.values);e.step();self.assertEqual(e.memory.values,before)

    def test_inactive_all_clears_only_enable_without_consuming_data(self):
        e=self.checked(['AFI()FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Incoming);'],position=2)
        e.memory.write('Ctl.EN',True);e.memory.values['incoming']=None;e.step()
        self.assertEqual(e.memory.read('Ctl.POS'),2);self.assertFalse(e.memory.read('Ctl.EN'));self.assertFalse(e.memory.read('Ctl.DN'))

    def test_unknown_destination_can_be_overwritten_but_required_source_is_deferred(self):
        e=self.checked(['FAL(Ctl,?,?,1,Queue[Ctl.POS],Incoming);'])
        e.memory.values['queue'][0]=None;e.step();self.assertEqual(e.memory.read('Queue[0]'),11)
        e.memory.values['incoming']=None;before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.values,before);self.assertFalse(e.memory.structural)

    def test_budget_overflow_divide_by_zero_and_late_bounds_roll_back(self):
        for expression,queue in (('Queue[Ctl.POS+2]',(2,4,6,8,999)),('Queue[Ctl.POS]/0.0',(2,4,6,8,999)),
                                 ('Queue[Ctl.POS]+1',(2,4,2147483647,8,999))):
            e=self.checked([f'FAL(Ctl,?,?,ALL,Queue[Ctl.POS],{expression});'],queue=queue);before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual((e.scan_count,e.time_ms),(0,0))
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],1);']);e.instruction_limit=3;before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_later_instruction_fault_restores_search_writes_and_scheduler(self):
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],1);','DIV(1,0,SpeedCommand);']);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],0)

    def test_invalid_lengths_positions_and_unknown_state_fail_transactionally(self):
        for length,position in ((-1,0),(4,-1),(4,5),(4097,0)):
            e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],1);'],length=length,position=position);before=copy.deepcopy(e.memory.values)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before)
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],1);']);e.memory.values['ctl']['LEN']=None
        with self.assertRaises(ModelError):e.step()

    def test_control_alias_destination_alias_and_constant_source(self):
        def aliases(root):
            tags=root.find('./Controller/Tags');tags.find('Tag[@Name="Queue"]').set('Constant','true')
            for name,dtype,target in (('AliasCtl','CONTROL','Ctl'),('Dest','DINT','Outgoing')):
                E.SubElement(tags,'Tag',Name=name,TagType='Alias',DataType=dtype,AliasFor=target)
        e=self.checked(['FAL(AliasCtl,?,?,ALL,Dest,Queue[AliasCtl.POS]);'],mutate=aliases);e.step()
        self.assertEqual(e.memory.read('Outgoing'),8);self.assertEqual(e.memory.read('Queue'),[2,4,6,8,999])

    def test_multidimensional_destination_uses_current_position_and_preserves_other_rows(self):
        change=fixtures.ArrayStatisticsTests.multidimensional((2,3),(2,4,6,8,10,12))
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[1,Ctl.POS],Queue[0,Ctl.POS]+1);'],length=3,mutate=change);e.step()
        self.assertEqual(e.memory.read('Queue'),[[2,4,6],[3,5,7]])
        e=self.checked(['FAL(Ctl,?,?,ALL,Queue[1,Ctl.POS],1);'],length=4,mutate=change);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)

    def test_udt_array_member_bounds_preserve_neighboring_guard(self):
        def member(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Values',DataType='DINT',Dimension='4');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            arr=E.SubElement(obj,'ArrayMember',Name='Values',DataType='DINT',Dimensions='4')
            for i,v in enumerate((8,2,6,4)):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(v))
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='999')
        e=self.checked(['FAL(Ctl,?,?,ALL,Packet1.Values[Ctl.POS],Queue[Ctl.POS]+1);'],mutate=member);e.step()
        self.assertEqual(e.memory.read('Packet1.Values'),[3,5,7,9]);self.assertEqual(e.memory.read('Packet1.Guard'),999)
        e=self.checked(['FAL(Ctl,?,?,ALL,Packet1.Values[Ctl.POS],1);'],length=5,mutate=member);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)

    def test_dynamic_destination_rechecks_control_overlap_on_each_iteration(self):
        from test_control_operations import control_data
        def records(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Ctls',DataType='CONTROL',TagType='Base',Dimensions='2')
            arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='CONTROL',Dimensions='2')
            for i in range(2):control_data(E.SubElement(arr,'Element',Index=f'[{i}]'),2)
        e=self.checked(['FAL(Ctls[1],?,?,ALL,Ctls[Ctls[1].POS].POS,1);'],mutate=records)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'overlap'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_unqualified_modes_types_destinations_and_expressions_block(self):
        for mode in ('BAD','0','-1','1.5','Incoming','2147483648','TRUE'):
            self.assertTrue(self.engine([f'FAL(Ctl,?,?,{mode},Outgoing,Incoming);']).blockers,mode)
        for text in ('FAL(Ctl,Incoming,0,ALL,Outgoing,Incoming);','FAL(Ctl,?,?,ALL,Queue,Incoming);',
                     'FAL(Ctl,?,?,ALL,Ctl.POS,1);','FAL(Ctl,?,?,ALL,RunLatch,Incoming);',
                     'FAL(Ctl,?,?,ALL,Outgoing,FRD(Incoming)+0.0);','FAL(Ctl,?,?,ALL,Outgoing,EXP(Incoming));',
                     'FAL(Ctl,?,?,ALL,Outgoing,Incoming>1);','FAL(Ctl,?,?,ALL,Outgoing);'):
            self.assertTrue(self.engine([text]).blockers,text)
        for name in ('Ctl','Queue'):
            def constant(root):root.find(f'./Controller/Tags/Tag[@Name="{name}"]').set('Constant','true')
            self.assertTrue(self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],1);'],mutate=constant).blockers)

    def test_st_other_controller_profiles_and_native_status_remain_unqualified(self):
        def st(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='FAL(Ctl,ALL,Outgoing,Incoming);'
        self.assertTrue(self.engine([],mutate=st).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['FAL(Ctl,?,?,ALL,Outgoing,Incoming);'],mutate=old).blockers)
        report=self.checked(['FAL(Ctl,?,?,ALL,Outgoing,Incoming);']).report()['file_arithmetic']
        self.assertFalse(report['native_cursor_parity']);self.assertFalse(report['native_fault_classification']);self.assertFalse(report['native_math_status'])


    def test_bundled_stats_lab_all_and_numeric_transform_examples(self):
        from pathlib import Path
        from logixlab.model import Project
        from logixlab.runtime import Engine
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/StatsLab.L5X'))
        self.assertEqual(e.blockers,[]);e.memory.write('Transform',True);e.memory.write('BatchTransform',True);e.step()
        self.assertEqual(e.memory.read('MappedValues'),[5,9,13,17,999])
        self.assertEqual(e.memory.read('BatchValues'),[5,9,0,0,999]);self.assertFalse(e.memory.read('BatchTransformControl.DN'))
        e.memory.write('BatchTransform',False);e.step()
        self.assertEqual(e.memory.read('BatchValues'),[5,9,13,17,999]);self.assertFalse(e.memory.read('BatchTransformControl.EN'))
        self.assertTrue(e.memory.read('BatchTransformControl.DN'))


if __name__=='__main__':unittest.main()
