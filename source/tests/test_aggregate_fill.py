"""Declared-schema zero FLL, unknown records, scoped windows and rollback."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_runtime as fixtures
from logixlab.model import ModelError


class AggregateFillTests(unittest.TestCase):
    setUp=fixtures.RuntimeTests.setUp

    @staticmethod
    def fields(root):
        types=root.find('./Controller/DataTypes');tags=root.find('./Controller/Tags')
        text=E.SubElement(E.SubElement(types,'DataType',Name='TinyText'),'Members')
        for name,dtype,size in [('LEN','DINT',0),('DATA','SINT',8)]:E.SubElement(text,'Member',Name=name,DataType=dtype,Dimension=str(size))
        cell=E.SubElement(E.SubElement(types,'DataType',Name='FillCell'),'Members')
        for name,dtype,size in [('Enabled','BOOL',0),('Count','DINT',0),('Measure','REAL',0),('Wide','LINT',0),('Bytes','SINT',4),('Flags','BOOL',3),('Timer','TIMER',0),('Counter','COUNTER',0),('State','CONTROL',0),('Text','TinyText',0)]:E.SubElement(cell,'Member',Name=name,DataType=dtype,Dimension=str(size))
        for name,value in [('Index',99),('SourceIndex',99)]:
            tag=E.SubElement(tags,'Tag',Name=name,DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=str(value))
        for name,dtype in [('Records','FillCell'),('Timers','TIMER'),('Counters','COUNTER'),('Controls','CONTROL'),('Texts','STRING'),('CustomTexts','TinyText'),('Lengths','DINT'),('Zeros','DINT')]:
            tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base',Dimensions='3');array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions='3')
            if name=='Records':
                obj=E.SubElement(E.SubElement(array,'Element',Index='[2]'),'Structure',DataType=dtype)
                for field,kind,value in [('Enabled','BOOL',1),('Count','DINT',777),('Measure','REAL',1.25)]:E.SubElement(obj,'DataValueMember',Name=field,DataType=kind,Value=str(value))

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

    def assert_cell_zero(self,obj):
        self.assertIs(obj['Enabled'],False);self.assertIs(type(obj['Measure']),float);self.assertEqual(obj['Measure'],0.0)
        self.assertEqual((obj['Count'],obj['Wide']),(0,0));self.assertEqual(obj['Bytes'],[0]*4);self.assertTrue(all(value is False for value in obj['Flags']))
        self.assertEqual(obj['Timer'],dict(PRE=0,ACC=0,EN=False,TT=False,DN=False));self.assertIs(obj['Timer']['EN'],False)
        self.assertEqual(obj['Counter'],dict(PRE=0,ACC=0,CU=False,CD=False,DN=False,OV=False,UN=False));self.assertIs(obj['Counter']['CU'],False)
        self.assertIs(obj['State']['EM'],False);self.assertEqual(obj['Text'],dict(LEN=0,DATA=[0]*8))

    def test_unknown_nested_records_get_typed_zeros_and_guards_and_copies_are_independent(self):
        e=self.checked(['FLL(0,Records[0],2);']);guard=copy.deepcopy(e.memory.read('Records')[2]);e.step();rows=e.memory.read('Records')
        for obj in rows[:2]:self.assert_cell_zero(obj)
        self.assertEqual(rows[2],guard);self.assertIsNot(rows[0],rows[1]);e.memory.write('Records[0].Flags[0]',True);self.assertIs(e.memory.read('Records')[1]['Flags'][0],False)

    def test_all_five_basic_record_kinds_and_custom_strings_establish_unknowns(self):
        for name in ('Timers','Counters','Controls','Texts','CustomTexts'):
            e=self.checked([f'FLL(0,{name}[0],2);']);e.step();rows=e.memory.read(name)
            self.assertEqual(rows[0],rows[1]);self.assertIsNone(rows[2]['LEN' if name in ('Texts','CustomTexts') else 'ACC' if name in ('Timers','Counters') else 'LEN'])
            if name=='Controls':self.assertIs(rows[0]['EM'],False);self.assertIs(rows[0]['EN'],False)
            if name in ('Texts','CustomTexts'):self.assertEqual(e.memory.string(name+'[0]'),'');self.assertTrue(all(v==0 and type(v) is int for v in rows[0]['DATA']))
            if name=='Timers':self.assertIs(rows[0]['EN'],False)
            if name=='Counters':self.assertIs(rows[0]['CU'],False)

    def test_false_and_prescan_skip_unknown_lengths_source_values_and_live_indices(self):
        e=self.checked(['XIC(StartPB)FLL(Zeros[SourceIndex],Records[Index],Lengths[0]);']);before=copy.deepcopy(e.memory.values);e.step();self.assertEqual(e.memory.values,before);e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Lengths[0]',1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);e.memory.write('SourceIndex',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Zeros[0]',0);e.step();self.assert_cell_zero(e.memory.read('Records')[0]);self.assertIsNone(e.memory.read('Records')[1]['Enabled'])

    def test_zero_length_resolves_destination_but_skips_invalid_unknown_source(self):
        e=self.checked(['FLL(Zeros[SourceIndex],Records[Index],0);']);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Index',0);e.step();self.assertIsNone(e.memory.read('Records')[0]['Enabled']);self.assertEqual(e.memory.read('SourceIndex'),99)

    def test_source_tag_must_be_zero_only_when_positive_window_executes(self):
        e=self.checked(['XIC(StartPB)FLL(Zeros[0],Records[0],1);']);e.memory.write('Zeros[0]',7);e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'integer zero only'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Zeros[0]',0);e.step();self.assert_cell_zero(e.memory.read('Records')[0])

    def test_length_and_overlapping_zero_source_are_captured_before_any_store(self):
        e=self.checked(['FLL(Records[0].Bytes[0],Records[0],Records[0].Count);']);e.memory.write('Records[0].Count',2);e.memory.write('Records[0].Bytes[0]',0);guard=copy.deepcopy(e.memory.read('Records')[2]);e.step()
        for obj in e.memory.read('Records')[:2]:self.assert_cell_zero(obj)
        self.assertEqual(e.memory.read('Records')[2],guard)

    def test_zeroed_timer_and_counter_can_be_consumed_as_typed_records(self):
        e=self.checked(['FLL(0,Timers[0],1);','FLL(0,Counters[0],1);','TON(Timers[0],?,?);','CTU(Counters[0],?,?);']);e.step();self.assertTrue(e.memory.read('Timers[0].DN'));self.assertEqual(e.memory.read('Counters[0].ACC'),1);self.assertTrue(e.memory.read('Counters[0].DN'))

    def test_static_and_dynamic_lengths_regions_and_budget_remain_bounded(self):
        for count in ('-1','100001','1.0','StartPB'):
            self.assertTrue(self.engine([f'AFI()FLL(0,Records[0],{count});']).blockers,count)
        e=self.checked(['MOV(99,SpeedCommand);','FLL(0,Records[Index],Lengths[0]);']);e.memory.write('Index',2);e.memory.write('Lengths[0]',2);e.step();self.assert_cell_zero(e.memory.read('Records')[2])
        e.memory.write('Index',0);e.memory.write('Lengths[0]',1);e.instruction_limit=10;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'scalar-member budget'):e.step()
        self.assertEqual(self.snapshot(e),before);e.instruction_limit=1000;e.step();self.assert_cell_zero(e.memory.read('Records')[0])

    def test_later_fault_restores_full_records_and_flags(self):
        e=self.checked(['FLL(0,Records[0],2);','DIV(1,SpeedSetpoint,SpeedCommand);']);e.memory.write('SpeedSetpoint',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('SpeedSetpoint',1);e.step();self.assert_cell_zero(e.memory.read('Records')[1])

    def test_alias_multidimensional_member_regions_and_constant_source(self):
        def setup(root):
            tags=root.find('./Controller/Tags');grid=E.SubElement(tags,'Tag',Name='Grid',DataType='FillCell',TagType='Base',Dimensions='2,2');E.SubElement(E.SubElement(grid,'Data',Format='Decorated'),'Array',DataType='FillCell',Dimensions='2,2')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='View',DataType='FillCell',TagType='Alias',AliasFor='Grid')
            source=E.SubElement(tags,'Tag',Name='ZeroConstant',DataType='DINT',TagType='Base',Constant='true');E.SubElement(E.SubElement(source,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
        e=self.checked(['FLL(ZeroConstant,View[0,1],2);'],setup);e.step();self.assertIsNone(e.memory.read('Grid')[0][0]['Enabled']);self.assertIsNone(e.memory.read('Grid')[1][1]['Enabled']);self.assert_cell_zero(e.memory.read('Grid')[0][1]);self.assert_cell_zero(e.memory.read('Grid')[1][0]);self.assertEqual(e.memory.read('ZeroConstant'),0)

    @staticmethod
    def aoi_logic(root):
        c=root.find('Controller');tags=c.find('Tags')
        for name,value in [('EnabledA',1),('EnabledB',1),('IndexA',0),('IndexB',99)]:
            kind='BOOL' if name.startswith('Enabled') else 'DINT';tag=E.SubElement(tags,'Tag',Name=name,DataType=kind,TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=kind,Value=str(value))
        definition=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='FillWorker',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false');params=E.SubElement(definition,'Parameters')
        for name,dtype,usage,required,size in [('EnableIn','BOOL','Input','false',0),('EnableOut','BOOL','Output','false',0),('Buffer','FillCell','InOut','true',3),('Position','DINT','Input','true',0)]:
            p=E.SubElement(params,'Parameter',Name=name,DataType=dtype,TagType='Base',Usage=usage,Required=required,Visible=required)
            if size:p.set('Dimensions',str(size))
        E.SubElement(E.SubElement(definition,'LocalTags'),'LocalTag',Name='LocalCells',DataType='FillCell',Dimensions='2');content=E.SubElement(E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
        for i,text in enumerate(['FLL(0,Buffer[Position],1);','FLL(0,LocalCells[Position],1);']):E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        for name in ('First','Second'):
            obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name=name,DataType='FillWorker',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='FillWorker')
            for field,kind,value in [('EnableIn','BOOL',0),('EnableOut','BOOL',0),('Position','DINT',0)]:E.SubElement(obj,'DataValueMember',Name=field,DataType=kind,Value=str(value))
            E.SubElement(obj,'ArrayMember',Name='LocalCells',DataType='FillCell',Dimensions='2')

    def test_aoi_local_and_inout_records_fill_independently_and_restore_bindings(self):
        e=self.checked(['XIC(EnabledA)FillWorker(First,Records,IndexA);','XIC(EnabledB)FillWorker(Second,Records,IndexB);'],self.aoi_logic);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('IndexB',1);e.step();self.assert_cell_zero(e.memory.read('First.LocalCells')[0]);self.assert_cell_zero(e.memory.read('Second.LocalCells')[1]);self.assertIsNone(e.memory.read('First.LocalCells')[1]['Enabled']);self.assertIsNone(e.memory.read('Second.LocalCells')[0]['Enabled'])
        e.memory.write('EnabledB',False);e.memory.write('IndexB',99);e.step();e.memory.write('EnabledB',True);e.memory.write('Records[0].Count',17);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_unsupported_patterns_types_and_operational_members_stay_blocked(self):
        for source in ('1','0.0','TRUE','Records','Records[0].Wide'):
            self.assertTrue(self.engine([f'AFI()FLL({source},Records[0],1);']).blockers,source)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Records"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()FLL(0,Records[0],1);'],constant).blockers)
        def operational(root):root.find('./Controller/DataTypes/DataType[@Name="FillCell"]/Members/Member[@Name="Timer"]').set('DataType','PID')
        self.assertTrue(self.engine(['AFI()FLL(0,Records[0],1);'],operational).blockers)
        def older(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['AFI()FLL(0,Records[Index],Lengths[0]);'],older).blockers)
        report=self.checked(['AFI()FLL(0,Records[0],1);']).report()['aggregate_fill'];self.assertTrue(report['available']);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
