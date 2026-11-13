"""Matching record copies and typed zero fills retain precise UDT fields."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_precise_record_queues as fixtures
from logixlab.model import ModelError


class PreciseRecordOperationTests(unittest.TestCase):
    setUp=fixtures.PreciseRecordQueueTests.setUp
    engine=fixtures.PreciseRecordQueueTests.engine
    checked=fixtures.PreciseRecordQueueTests.checked
    precise=fixtures.PreciseRecordQueueTests.precise
    pulse=fixtures.PreciseRecordQueueTests.pulse
    part=fixtures.PreciseRecordQueueTests.part
    sample=fixtures.PreciseRecordQueueTests.sample
    snapshot=fixtures.PreciseRecordQueueTests.snapshot

    def test_cop_and_cps_retain_binary64_time_ticks_and_nested_values(self):
        for op in ('COP','CPS'):
            e=self.precise([f'{op}(IncomingPart,CopiedPart,1);']);expected=self.sample(e)
            e.step();self.assertEqual(e.memory.read('CopiedPart'),expected)
            self.assertEqual(e.memory.read('CopiedPart.Position'),fixtures.POSITION)
            self.assertEqual(e.memory.read('CopiedPart.Timestamp',allow_time=True),fixtures.STAMP+1)

    def test_copy_unknown_fields_and_whole_unknown_destination_without_inference(self):
        e=self.precise(['COP(IncomingPart,CopiedPart,1);']);self.sample(e)
        e.memory.values['incomingpart']['Position']=None;e.memory.values['incomingpart']['Timestamp']=None
        e.memory.values['incomingpart']['Points'][1]['Age']=None
        expected=copy.deepcopy(e.memory.read('IncomingPart'));e.memory.values['copiedpart']=None
        e.step();self.assertEqual(e.memory.read('CopiedPart'),expected)

    def test_copy_owns_nested_storage_independently_of_source(self):
        e=self.precise(['XIC(LoadPart)CPS(IncomingPart,CopiedPart,1);']);expected=self.sample(e)
        e.memory.write('LoadPart',True);e.step();e.memory.write('LoadPart',False)
        self.sample(e,2);e.step();self.assertEqual(e.memory.read('CopiedPart'),expected)
        e.memory.write('CopiedPart.Points[0].Axis',99)
        self.assertEqual(e.memory.read('IncomingPart.Points[0].Axis'),fixtures.POSITION)

    def test_forward_and_backward_overlap_keep_existing_sequential_semantics(self):
        for op in ('COP','CPS'):
            for source,dest in ((0,1),(1,0)):
                e=self.precise([f'{op}(PartQueue[{source}],PartQueue[{dest}],2);'])
                values=[self.sample(e,n) for n in (1,2,3,4)]
                for i,value in enumerate(values):e.memory.store('partqueue',[i],value)
                e.step();expected=[values[0],values[0],values[0],values[3]] if source==0 else [values[1],values[2],values[2],values[3]]
                self.assertEqual(e.memory.read('PartQueue'),expected)

    def test_source_scalar_clipping_retains_unselected_records(self):
        e=self.precise(['COP(IncomingPart,PartQueue[1],100);']);expected=self.sample(e)
        before=copy.deepcopy(e.memory.read('PartQueue'));e.step();before[1]=expected
        self.assertEqual(e.memory.read('PartQueue'),before)

    def test_zero_fill_establishes_all_declared_precise_types_and_detached_cells(self):
        e=self.precise(['FLL(0,PartQueue[1],2);']);self.sample(e)
        for i in (1,2):e.memory.store('partqueue',[i],e.memory.read('IncomingPart'))
        guards=[copy.deepcopy(e.memory.read('PartQueue')[i]) for i in (0,3)]
        e.memory.values['partqueue'][1]['Timestamp']=None;e.memory.values['partqueue'][1]['Position']=None
        e.step();zero=e.project.default('PartRecord')
        self.assertEqual(e.memory.read('PartQueue')[1:3],[zero,zero])
        self.assertEqual([e.memory.read('PartQueue')[i] for i in (0,3)],guards)
        e.memory.write('PartQueue[1].Points[0].Axis',7)
        self.assertEqual(e.memory.read('PartQueue[2].Points[0].Axis'),0.0)

    def test_zero_scalar_fill_clips_and_captures_length_before_clearing(self):
        e=self.precise(['FLL(0,CopiedPart,CopiedPart.Id);'])
        e.memory.store('copiedpart',[],self.sample(e));e.memory.write('CopiedPart.Id',100)
        e.step();self.assertEqual(e.memory.read('CopiedPart'),e.project.default('PartRecord'))

    def test_each_time_family_has_zero_fill_but_no_all_ones_pattern(self):
        for dtype in ('TIME32','TIME','LTIME','DT','LDT'):
            def clock(root):
                members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='ClockRecord',Class='User'),'Members')
                E.SubElement(members,'Member',Name='Ticks',DataType=dtype,Dimension='0')
                obj=E.SubElement(E.SubElement(E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Clock',DataType='ClockRecord',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='ClockRecord')
                E.SubElement(obj,'DataValueMember',Name='Ticks',DataType=dtype,Value='1')
            e=self.precise(['FLL(0,Clock,1);'],clock);e.step()
            self.assertEqual(e.memory.read('Clock'),{'Ticks':0})
            blocked=self.engine(['AFI()FLL(-1,Clock,1);'],clock)
            self.assertTrue(any('time/date' in b for b in blocked.blockers),dtype)

    def test_false_calls_and_zero_copy_lengths_skip_saved_values_and_live_indices(self):
        e=self.precise(['XIC(LoadPart)COP(PartQueue[FaultDivisor],CopiedPart,1);'])
        e.memory.write('FaultDivisor',99);e.step();self.assertEqual(e.memory.read('CopiedPart.Position'),0.0)
        e.memory.write('LoadPart',True);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)
        e=self.precise(['CPS(PartQueue[0],CopiedPart,0);']);before=copy.deepcopy(e.memory.read('CopiedPart'))
        e.memory.values['partqueue'][0]=None;e.step();self.assertEqual(e.memory.read('CopiedPart'),before)

    def test_copy_and_zero_fill_roll_back_on_later_fault_and_retry(self):
        e=self.precise(['XIC(LoadPart)COP(IncomingPart,CopiedPart,1);',
                        'XIC(UnloadPart)FLL(0,CopiedPart,1);','DIV(1,FaultDivisor,GuardResult);'])
        expected=self.sample(e);e.memory.write('LoadPart',True);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('CopiedPart'),expected)
        e.memory.write('LoadPart',False);e.memory.write('UnloadPart',True);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_scalar_work_budget_includes_new_fields(self):
        e=self.precise(['CPS(IncomingPart,CopiedPart,1);']);expected=self.sample(e)
        e.instruction_limit=10;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'scalar-member budget'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.instruction_limit=10000;e.step();self.assertEqual(e.memory.read('CopiedPart'),expected)

    def test_aoi_inout_copy_and_fill_use_the_same_precise_schema(self):
        def worker(root):
            c=root.find('Controller');a=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='PreciseMove',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            params=E.SubElement(a,'Parameters')
            for name,dtype,usage in [('EnableIn','BOOL','Input'),('EnableOut','BOOL','Output'),('Value','PartRecord','InOut'),('Item','PartRecord','InOut'),('Copy','BOOL','Input'),('Clear','BOOL','Input')]:
                required='false' if name.startswith('Enable') else 'true'
                E.SubElement(params,'Parameter',Name=name,DataType=dtype,Usage=usage,Required=required,Visible=required)
            E.SubElement(a,'LocalTags');content=E.SubElement(E.SubElement(E.SubElement(a,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
            for i,text in enumerate(('XIC(Copy)CPS(Value,Item,1);','XIC(Clear)FLL(0,Item,1);')):
                E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Worker',DataType='PreciseMove',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='PreciseMove')
            for name in ('EnableIn','EnableOut','Copy','Clear'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.precise(['PreciseMove(Worker,IncomingPart,CopiedPart,LoadPart,UnloadPart);'],worker)
        expected=self.sample(e);e.memory.write('LoadPart',True);e.step()
        self.assertEqual(e.memory.read('CopiedPart'),expected)
        e.memory.write('LoadPart',False);e.memory.write('UnloadPart',True);e.step()
        self.assertEqual(e.memory.read('CopiedPart'),e.project.default('PartRecord'))

    def test_existing_st_calls_copy_precise_fields_and_protect_for_bounds(self):
        def st(text):
            def change(root):
                routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.remove(routine.find('RLLContent'));routine.set('Type','ST')
                E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text=text
            return change
        for op in ('COP','CPS'):
            e=self.precise(mutate=st(f'{op}(IncomingPart,CopiedPart,1);'));expected=self.sample(e)
            e.step();self.assertEqual(e.memory.read('CopiedPart'),expected)
        for text in ('COP(IncomingPart,CopiedPart,1);','FLL(0,CopiedPart,1);'):
            e=self.engine(mutate=st('FOR GuardResult:=0 TO CopiedPart.Id DO '+text+' END_FOR;'))
            self.assertTrue(any('bounds/step' in b for b in e.blockers))

    def test_public_sample_gates_copy_then_clear_and_report_fields(self):
        e=self.precise();expected=self.sample(e);e.memory.write('CopyPart',True);e.step()
        self.assertEqual(e.memory.read('CopiedPart'),expected)
        e.memory.write('CopyPart',False);e.memory.write('ClearCopiedPart',True);e.step()
        self.assertEqual(e.memory.read('CopiedPart'),e.project.default('PartRecord'))
        report=e.report()
        for key in ('aggregate_copy','aggregate_fill'):
            self.assertTrue({'LREAL','TIME32','TIME','LTIME','DT','LDT'}<=set(report[key]['udt_scalar_fields']))
            self.assertFalse(report[key]['native_runtime_parity'])


if __name__=='__main__':unittest.main()
