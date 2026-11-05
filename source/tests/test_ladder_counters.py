"""Known counter inputs, unknown edge history and typed timer/counter resets."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_runtime as fixtures
from logixlab.model import ModelError


class LadderCounterTests(unittest.TestCase):
    setUp=fixtures.RuntimeTests.setUp

    @staticmethod
    def fields(root):
        tags=root.find('./Controller/Tags')
        for name,value in [('Index',0),('ResetIndex',99)]:
            tag=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType='DINT')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=str(value))
        for name,dtype in [('CounterCells','COUNTER'),('TimerCells','TIMER'),('Positions','DINT')]:
            tag=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType=dtype,Dimensions='3')
            arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions='3')
            if dtype=='COUNTER':
                obj=E.SubElement(E.SubElement(arr,'Element',Index='[0]'),'Structure',DataType=dtype)
                E.SubElement(obj,'DataValueMember',Name='PRE',DataType='DINT',Value='3')

    def engine(self,rungs,mutate=None):
        self.root=E.parse(fixtures.SAMPLE).getroot()
        def fields(root):
            self.fields(root)
            if mutate:mutate(root)
        return fixtures.RuntimeTests.engine(self,rungs,fields)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);self.assertFalse(e.memory.structural);return e

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved,e.addons.instances,e.scan_count,e.time_ms,e.scheduler_description(),e.trace,e.last_timer))

    def test_counter_unknown_acc_is_required_even_when_false_and_recovers(self):
        for op,delta,edge in [('CTU',1,'CU'),('CTD',-1,'CD')]:
            e=self.checked([f'XIC(StartPB){op}(CounterCells[Index],?,?);']);self.assertTrue(e.memory.read('CounterCells')[0][edge]);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'COUNTER.ACC.*unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('CounterCells[0].ACC',0);e.step();self.assertFalse(e.memory.read('CounterCells[0].'+edge))
            e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('CounterCells[0].ACC'),delta);self.assertIsNone(e.memory.read('CounterCells')[0]['OV']);self.assertIsNone(e.memory.read('CounterCells')[0]['UN'])

    def test_unknown_preset_is_not_inferred_from_acc_or_done(self):
        e=self.checked(['CTU(CounterCells[1],?,?);']);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'COUNTER.PRE.*unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('CounterCells[1].PRE',-1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'COUNTER.ACC.*unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('CounterCells[1].ACC',0);e.step();self.assertTrue(e.memory.read('CounterCells[1].DN'));self.assertEqual(e.memory.read('CounterCells[1].ACC'),0)

    def test_unknown_edge_history_cannot_create_a_count_false_establishes_it(self):
        for op,edge,other,delta in [('CTU','CU','CD',1),('CTD','CD','CU',-1)]:
            e=self.checked([f'XIC(StartPB){op}(CounterCells[0],?,?);']);e.memory.write('CounterCells[0].ACC',0);e.memory.values['countercells'][0][edge]=None;e.memory.write('StartPB',True);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'COUNTER.'+edge+'.*unknown'):e.step()
            self.assertEqual(self.snapshot(e),before);e.memory.write('StartPB',False);e.step();self.assertFalse(e.memory.read('CounterCells[0].'+edge));self.assertIsNone(e.memory.read('CounterCells')[0][other])
            e.memory.write('StartPB',True);e.step();e.step();self.assertEqual(e.memory.read('CounterCells[0].ACC'),delta)

    def test_res_skips_false_indices_and_establishes_unknown_timer_counter_fields(self):
        e=self.checked(['XIC(StartPB)RES(CounterCells[ResetIndex]);','XIC(StartPB)RES(TimerCells[ResetIndex]);']);before=copy.deepcopy(e.memory.values);e.step();self.assertEqual(e.memory.values,before)
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('ResetIndex',1);e.step()
        for name in ('CounterCells','TimerCells'):
            obj=e.memory.read(name)[1];self.assertIsNone(obj['PRE']);self.assertEqual(obj['ACC'],0);self.assertTrue(all(value is False for field,value in obj.items() if field not in ('PRE','ACC')));self.assertIsNone(e.memory.read(name)[2]['ACC'])

    def test_reset_preserves_negative_and_unknown_presets_and_skips_unknown_index_value(self):
        e=self.checked(['XIC(StartPB)RES(CounterCells[Positions[0]]);']);e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Positions[0]',0);e.memory.write('CounterCells[0].PRE',-7);e.step();self.assertEqual(e.memory.read('CounterCells[0].PRE'),-7);self.assertFalse(e.memory.read('CounterCells[0].DN'))

    def test_signed_wrap_establishes_only_its_latched_overflow_flag(self):
        for op,start,wanted,flag,untouched in [('CTU',2147483647,-2147483648,'OV','UN'),('CTD',-2147483648,2147483647,'UN','OV')]:
            e=self.checked([f'XIC(StartPB){op}(CounterCells[0],?,?);']);e.memory.write('CounterCells[0].ACC',start);e.step();e.memory.write('StartPB',True);e.step();obj=e.memory.read('CounterCells')[0]
            self.assertEqual(obj['ACC'],wanted);self.assertTrue(obj[flag]);self.assertIsNone(obj[untouched]);self.assertEqual(obj['DN'],wanted>=3)
            e.memory.write('StartPB',False);e.step();self.assertTrue(e.memory.read('CounterCells[0].'+flag))

    def test_shared_counter_up_down_edges_done_and_res_order(self):
        e=self.checked(['XIC(ResetPB)RES(CounterCells[0]);','XIC(StartPB)CTU(CounterCells[0],?,?);','XIC(PartSensor)CTD(CounterCells[0],?,?);']);e.memory.write('ResetPB',True);e.step();e.memory.write('ResetPB',False);e.memory.write('CounterCells[0].PRE',1)
        e.memory.write('StartPB',True);e.step();e.step();self.assertEqual(e.memory.read('CounterCells[0].ACC'),1);self.assertTrue(e.memory.read('CounterCells[0].DN'))
        e.memory.write('PartSensor',True);e.step();self.assertEqual(e.memory.read('CounterCells[0].ACC'),0);self.assertFalse(e.memory.read('CounterCells[0].DN'));e.memory.write('ResetPB',True);e.step();self.assertEqual(e.memory.read('CounterCells[0].ACC'),0)

    def test_constant_alias_and_nested_udt_records_keep_permissions_and_siblings(self):
        def records(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Record'),'Members')
            E.SubElement(members,'Member',Name='Count',DataType='COUNTER',Dimension='0');E.SubElement(members,'Member',Name='Timer',DataType='TIMER',Dimension='0')
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Records',TagType='Base',DataType='Record',Dimensions='2');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='Record',Dimensions='2')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='View',TagType='Alias',DataType='Record',AliasFor='Records')
        e=self.checked(['XIC(StartPB)RES(View[ResetIndex].Count);','XIC(StartPB)RES(View[ResetIndex].Timer);'],records);e.step();e.memory.write('ResetIndex',1);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Records')[1]['Count']['ACC'],0);self.assertIsNone(e.memory.read('Records')[0]['Count']['ACC']);self.assertIsNone(e.memory.read('Records')[1]['Count']['PRE'])
        def constant(root):root.find('./Controller/Tags/Tag[@Name="CounterCells"]').set('Constant','true')
        for text in ('RES(CounterCells[0]);','CTU(CounterCells[0],?,?);','CTD(CounterCells[0],?,?);'):self.assertTrue(self.engine(['AFI()'+text],constant).blockers)

    @staticmethod
    def aoi_logic(root):
        c=root.find('Controller');tags=c.find('Tags')
        for name,value in [('EnabledA',1),('EnabledB',1),('ResetA',1),('ResetB',0)]:
            obj=E.SubElement(tags,'Tag',Name=name,DataType='BOOL',TagType='Base');E.SubElement(E.SubElement(obj,'Data',Format='Decorated'),'DataValue',DataType='BOOL',Value=str(value))
        arr=tags.find('Tag[@Name="CounterCells"]/Data/Array');obj=E.SubElement(E.SubElement(arr,'Element',Index='[1]'),'Structure',DataType='COUNTER');E.SubElement(obj,'DataValueMember',Name='PRE',DataType='DINT',Value='3')
        definition=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='CounterWorker',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
        params=E.SubElement(definition,'Parameters')
        for name,dtype,usage,required in [('EnableIn','BOOL','Input','false'),('EnableOut','BOOL','Output','false'),('State','COUNTER','InOut','true'),('Trigger','BOOL','Input','true'),('Reset','BOOL','Input','true')]:E.SubElement(params,'Parameter',Name=name,DataType=dtype,TagType='Base',Usage=usage,Required=required,Visible=required)
        E.SubElement(E.SubElement(definition,'LocalTags'),'LocalTag',Name='LocalCount',DataType='COUNTER')
        content=E.SubElement(E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
        for i,text in enumerate(['XIC(Reset)RES(State);','XIC(Reset)RES(LocalCount);','XIC(Trigger)CTU(State,?,?);','XIC(Trigger)CTU(LocalCount,?,?);']):E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        for name in ('First','Second'):
            obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name=name,DataType='CounterWorker',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='CounterWorker')
            for field in ('EnableIn','EnableOut','Trigger','Reset'):E.SubElement(obj,'DataValueMember',Name=field,DataType='BOOL',Value='0')
            local=E.SubElement(obj,'StructureMember',Name='LocalCount',DataType='COUNTER');E.SubElement(local,'DataValueMember',Name='PRE',DataType='DINT',Value='2')

    def test_aoi_unknown_reset_initialization_independence_and_binding_rollback(self):
        e=self.checked(['XIC(EnabledA)CounterWorker(First,CounterCells[0],StartPB,ResetA);','XIC(EnabledB)CounterWorker(Second,CounterCells[1],PartSensor,ResetB);'],self.aoi_logic);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'COUNTER.ACC.*unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('ResetB',True);e.step()
        for name in ('CounterCells[0].ACC','CounterCells[1].ACC','First.LocalCount.ACC','Second.LocalCount.ACC'):self.assertEqual(e.memory.read(name),0)
        e.memory.write('ResetA',False);e.memory.write('ResetB',False);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('CounterCells[0].ACC'),1);self.assertEqual(e.memory.read('CounterCells[1].ACC'),0)
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.memory.values['countercells'][1]['PRE']=None;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'COUNTER.PRE.*unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_late_fault_restores_resets_counts_flags_and_schedule(self):
        e=self.checked(['RES(CounterCells[0]);','CTU(CounterCells[0],?,?);','DIV(1,SpeedSetpoint,SpeedCommand);']);e.memory.write('SpeedSetpoint',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual(e.memory.read('CounterCells[0].ACC'),1);self.assertFalse(e.memory.read('CounterCells[0].OV'))

    def test_static_type_shape_operands_and_counter_prescan_indices_stay_strict(self):
        for text in ('CTU(TimerCells[0],?,?);','CTD(CounterCells,?,?);','RES(CounterCells[99]);','RES(StartPB);','CTU(CounterCells[Index],1,2);'):
            e=self.engine(['AFI()'+text]);self.assertTrue(e.blockers,text);self.assertFalse(e.memory.structural)
        e=self.engine(['AFI()CTU(CounterCells[ResetIndex],?,?);']);self.assertTrue(any('Prescan' in b and 'outside bounds' in b for b in e.blockers))
        def older(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['AFI()RES(CounterCells[ResetIndex]);'],older).blockers)
        report=self.checked(['AFI()RES(CounterCells[ResetIndex]);']).report()['ladder_counters'];self.assertEqual(report['instructions'],['CTU','CTD','RES']);self.assertFalse(report['native_runtime_parity'])

    def test_signed_counter_initializers_feed_normal_edges_without_reapplication(self):
        for op, delta in (('CTU', 1), ('CTD', -1)):
            with self.subTest(op=op):
                engine = self.checked([f'XIC(StartPB){op}(CounterCells[0],-2,-4);'])
                self.assertEqual((engine.memory.read('CounterCells[0].PRE'), engine.memory.read('CounterCells[0].ACC')), (-2, -4))
                engine.step()
                engine.memory.write('CounterCells[0].PRE', -3)
                engine.memory.write('StartPB', True)
                engine.step()
                engine.step()
                self.assertEqual((engine.memory.read('CounterCells[0].PRE'), engine.memory.read('CounterCells[0].ACC')), (-3, -4 + delta))

    def test_counter_placeholder_preserves_saved_preset_and_can_establish_unknown_acc(self):
        engine = self.checked(['AFI()CTU(CounterCells[0],?,-2147483648);'])
        engine.step()
        self.assertEqual(engine.memory.read('CounterCells[0].PRE'), 3)
        self.assertEqual(engine.memory.read('CounterCells[0].ACC'), -2147483648)
        self.assertFalse(engine.memory.read('CounterCells[0].DN'))

    def test_counter_literal_target_requires_a_direct_writable_record(self):
        def alias(root):
            E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='Selected', TagType='Alias',
                         AliasFor='CounterCells[0]', DataType='COUNTER')
        def constant(root):
            root.find('./Controller/Tags/Tag[@Name="CounterCells"]').set('Constant', 'true')
        def older(root):
            root.find('Controller').set('ProcessorType', '1756-L75')
        for text, change in (
            ('AFI()CTU(Selected,1,0);', alias),
            ('AFI()CTU(CounterCells[0],1,0);', constant),
            ('AFI()CTU(CounterCells[0],1,0);', older),
            ('AFI()CTD(CounterCells[99],1,0);', None),
            ('AFI()CTU(CounterCells[0],1,-2147483649);', None),
        ):
            with self.subTest(text=text, change=change):
                engine = self.engine([text], change)
                self.assertTrue(engine.blockers)
                self.assertEqual(engine.project.initial['countercells'][0]['PRE'], 3)


if __name__=='__main__':unittest.main()
