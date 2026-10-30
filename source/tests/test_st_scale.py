"""ST analog scaling, range diagnostics, finite results and transaction boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project,coerce
from logixlab.runtime import Engine
from logixlab.st_scale import FIELDS,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def record(parent,name,values):
    tag=E.SubElement(parent,'Tag',Name=name,DataType='SCALE',TagType='Base')
    data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='SCALE')
    for member,value in (default()|values).items():
        E.SubElement(data,'DataValueMember',Name=member,DataType=FIELDS[member],Value=str(int(value) if FIELDS[member]!='REAL' else float(value)))


class StructuredScaleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,values=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        for tag in ('T','U'):record(tags,tag,{'InRawMax':4095.0,'InEUMax':100.0}|dict(values or {}))
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else ['SCL(T);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'scale.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e):e.step(10);return e.memory.read('T')

    def test_endpoints_and_midpoint_scale_without_alarms(self):
        e=self.checked()
        for value,result in ((0.0,0.0),(2047.5,50.0),(4095.0,100.0)):
            e.memory.write('T.In',value);t=self.step(e);self.assertEqual(t['Out'],result)
            self.assertFalse(t['MaxAlarm']);self.assertFalse(t['MinAlarm']);self.assertEqual(t['Status'],0)

    def test_nonzero_raw_and_engineering_offsets(self):
        e=self.checked(values={'InRawMin':4.0,'InRawMax':20.0,'InEUMin':-50.0,'InEUMax':150.0,'In':12.0})
        self.assertEqual(self.step(e)['Out'],50.0)

    def test_unlimited_input_extrapolates_and_updates_raw_alarms(self):
        e=self.checked(values={'InRawMax':100.0,'In':150.0})
        t=self.step(e);self.assertEqual(t['Out'],150.0);self.assertTrue(t['MaxAlarm']);self.assertFalse(t['MinAlarm'])
        e.memory.write('T.In',-25.0);t=self.step(e);self.assertEqual(t['Out'],-25.0)
        self.assertTrue(t['MinAlarm']);self.assertFalse(t['MaxAlarm'])

    def test_limiting_clamps_to_corresponding_endpoints_without_clearing_alarms(self):
        e=self.checked(values={'InRawMax':100.0,'Limiting':True,'In':150.0})
        t=self.step(e);self.assertEqual(t['Out'],100.0);self.assertTrue(t['MaxAlarm'])
        e.memory.write('T.In',-25.0);t=self.step(e);self.assertEqual(t['Out'],0.0);self.assertTrue(t['MinAlarm'])

    def test_descending_eu_range_maps_and_limits_by_raw_endpoints(self):
        e=self.checked(values={'InRawMax':10.0,'InEUMin':100.0,'InEUMax':-100.0,'In':2.5})
        self.assertEqual(self.step(e)['Out'],50.0);e.memory.write('T.Limiting',True)
        e.memory.write('T.In',20.0);self.assertEqual(self.step(e)['Out'],-100.0)
        e.memory.write('T.In',-10.0);self.assertEqual(self.step(e)['Out'],100.0)

    def test_equal_eu_endpoints_are_valid_and_alarms_still_follow_raw_input(self):
        e=self.checked(values={'InEUMin':7.0,'InEUMax':7.0,'In':5000.0})
        t=self.step(e);self.assertEqual(t['Out'],7.0);self.assertEqual(t['Status'],0);self.assertTrue(t['MaxAlarm'])

    def test_negative_raw_range_works(self):
        e=self.checked(values={'InRawMin':-100.0,'InRawMax':-20.0,'In':-60.0})
        self.assertEqual(self.step(e)['Out'],50.0)

    def test_final_result_rounds_to_float32(self):
        e=self.checked(values={'InRawMax':3.0,'InEUMax':1.0,'In':1.0})
        self.assertEqual(self.step(e)['Out'],coerce(1/3,'REAL'))

    def test_invalid_equal_or_reversed_raw_range_retains_output_and_alarms(self):
        for minimum,maximum in ((5.0,5.0),(10.0,-10.0)):
            with self.subTest(minimum=minimum,maximum=maximum):
                e=self.checked(values={'InRawMin':minimum,'InRawMax':maximum,'Out':17.0,'MaxAlarm':True})
                t=self.step(e);self.assertEqual((t['Out'],t['MaxAlarm'],t['MinAlarm']),(17.0,True,False))
                self.assertEqual(t['Status'],3);self.assertTrue(t['EnableOut']);self.assertFalse(e.fault)

    def test_valid_range_recovery_recalculates_and_clears_status(self):
        e=self.checked(values={'InRawMax':0.0,'In':50.0,'Out':17.0});self.assertEqual(self.step(e)['Status'],3)
        e.memory.write('T.InRawMax',100.0);t=self.step(e);self.assertEqual(t['Out'],50.0);self.assertEqual(t['Status'],0)

    def test_invalid_range_needs_no_unavailable_signal_or_eu_values(self):
        e=self.checked(values={'InRawMax':0.0})
        for name in ('In','InEUMin','InEUMax','Limiting','Out','MaxAlarm','MinAlarm'):e.memory.read('T')[name]=None
        t=self.step(e);self.assertEqual(t['Status'],3);self.assertIsNone(t['Out']);self.assertIsNone(t['MaxAlarm'])

    def test_status_aliases_share_backing_word_case_insensitively(self):
        e=self.checked();e.memory.write('t.InRawRangeInv',True);self.assertEqual(e.memory.read('T.Status'),2)
        e.memory.write('T.InstructFault',True);self.assertEqual(e.memory.read('T.Status'),3)
        e.memory.write('T.Status',1);self.assertFalse(e.memory.read('T.inrawrangeinv'));self.assertTrue(e.memory.read('T.InstructFault'))
        self.step(e);self.assertEqual(e.memory.read('T.Status'),0)
        with self.assertRaisesRegex(ModelError,'Invalid SCALE status alias'):e.memory.read('T.InRawRangeInv.0')

    def test_st_call_executes_despite_false_or_unknown_enable(self):
        e=self.checked(values={'EnableIn':False,'In':4095.0});e.memory.read('T')['EnableIn']=None
        t=self.step(e);self.assertEqual(t['Out'],100.0);self.assertTrue(t['EnableIn']);self.assertTrue(t['EnableOut'])

    def test_skipped_call_retains_outputs_alarms_and_status(self):
        e=self.checked(['IF StartPB THEN SCL(T); END_IF;'],values={'In':5000.0})
        e.memory.write('StartPB',True);self.step(e);before=copy.deepcopy(e.memory.read('T'))
        e.memory.write('StartPB',False);e.memory.write('T.In',-1.0);self.step(e)
        for name in ('Out','MaxAlarm','MinAlarm','Status'):self.assertEqual(e.memory.read('T')[name],before[name])
        e.memory.write('StartPB',True);self.assertTrue(self.step(e)['MinAlarm'])

    def test_each_call_reads_current_inputs_even_at_the_same_timestamp(self):
        e=self.checked(['T.In := 0.0;','SCL(T);','U.In := T.Out;','T.In := 4095.0;','SCL(T);'])
        t=self.step(e);self.assertEqual(t['Out'],100.0);self.assertEqual(e.memory.read('U.In'),0.0)

    def test_required_unknown_inputs_fault_and_roll_back(self):
        for name in ('InRawMin','InRawMax','In','InEUMin','InEUMax','Limiting'):
            with self.subTest(name=name):
                e=self.checked();e.memory.read('T')[name]=None;before=copy.deepcopy(e.memory.values)
                with self.assertRaisesRegex(ModelError,'unknown'):e.step()
                self.assertEqual(e.memory.values,before)

    def test_nonfinite_or_bad_value_types_fault_and_roll_back(self):
        for name,value in (('In',float('nan')),('InEUMax',float('inf')),('InRawMin',True),('Limiting',1)):
            with self.subTest(name=name,value=value):
                e=self.checked();e.memory.read('T')[name]=value;before=copy.deepcopy(e.memory.values)
                with self.assertRaises(ModelError):e.step()
                # NaN is not equal to itself; compare the preserved object representation.
                self.assertEqual(repr(e.memory.values),repr(before))

    def test_unlimited_real_overflow_rolls_back_and_limited_retry_is_finite(self):
        e=self.checked(values={'InRawMax':1.0,'InEUMax':3e38,'In':2.0,'Out':17.0})
        before=copy.deepcopy((e.memory.values,e.scan_count,e.time_ms,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'finite REAL'):e.step()
        self.assertEqual((e.memory.values,e.scan_count,e.time_ms,e.scheduler_description()),before)
        e.memory.write('T.Limiting',True);t=self.step(e);self.assertEqual(t['Out'],coerce(3e38,'REAL'));self.assertTrue(t['MaxAlarm'])

    def test_missing_saved_output_is_unknown_until_successful_calculation(self):
        def mutate(root):
            data=root.find('./Controller/Tags/Tag[@Name="T"]/Data/Structure');data.remove(data.find('DataValueMember[@Name="Out"]'))
        e=self.checked(mutate=mutate,defer=True);self.assertIsNone(e.memory.read('T')['Out'])
        with self.assertRaisesRegex(ModelError,'omitted by export'):e.memory.read('T.Out')
        self.assertEqual(self.step(e)['Out'],0.0)

    def test_prescan_only_clears_enable_pair_and_run_has_no_hidden_history(self):
        e=self.checked(values={'In':4095.0,'Out':17.0,'MaxAlarm':True,'Status':3,'EnableOut':True},defer=True)
        self.assertTrue(e.memory.read('T.EnableIn'));e.enter_run();t=e.memory.read('T')
        self.assertFalse(t['EnableIn']);self.assertFalse(t['EnableOut']);self.assertEqual((t['Out'],t['MaxAlarm'],t['Status']),(17.0,True,3))
        self.assertEqual(self.step(e)['Out'],100.0);e.enter_run();self.assertEqual(self.step(e)['Out'],100.0)

    def test_late_fault_rolls_back_valid_and_invalid_range_updates_then_retries(self):
        for maximum,expected in ((4095.0,0),(0.0,3)):
            with self.subTest(maximum=maximum):
                e=self.checked(['SCL(T);','SpeedCommand := 1 / SpeedSetpoint;'],values={'InRawMax':maximum,'In':2047.5,'Out':17.0})
                e.memory.write('SpeedSetpoint',0);before=copy.deepcopy((e.memory.values,e.scan_count,e.time_ms,e.scheduler_description()))
                with self.assertRaisesRegex(ModelError,'zero'):e.step()
                self.assertEqual((e.memory.values,e.scan_count,e.time_ms,e.scheduler_description()),before)
                e.memory.write('SpeedSetpoint',1);t=self.step(e);self.assertEqual(t['Status'],expected)
                self.assertEqual(t['Out'],17.0 if expected else 50.0)

    def test_scan_and_prescan_budget_failures_restore_state(self):
        e=self.checked(['SCL(T);','SpeedCommand := 7;']);before=copy.deepcopy(e.memory.values);e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(e.memory.values,before);e.instruction_limit=100;self.step(e)
        before=copy.deepcopy((e.memory.values,e.prescan_count));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan.*budget'):e.enter_run()
        self.assertEqual((e.memory.values,e.prescan_count),before)

    def test_alias_and_program_local_references_resolve_the_same_record(self):
        def mutate(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="T"]');tags.remove(tag)
            root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='AliasT',TagType='Alias',AliasFor='Program:MainProgram.T')
        e=self.checked(['SCL(AliasT);'],mutate=mutate);e.memory.write('Program:MainProgram.T.In',4095.0);e.step()
        self.assertEqual(e.memory.read('Program:MainProgram.T.Out'),100.0)

    def test_array_records_are_independent(self):
        def mutate(root):
            t=root.find('./Controller/Tags/Tag[@Name="T"]');data=t.find('Data');item=copy.deepcopy(data[0])
            data.clear();data.set('Format','Decorated');t.set('Dimensions','2')
            a=E.SubElement(data,'Array',DataType='SCALE',Dimensions='2')
            for i in range(2):E.SubElement(a,'Element',Index=f'[{i}]').append(copy.deepcopy(item))
        e=self.checked(['SCL(T[0]);','SCL(T[1]);'],mutate=mutate);e.memory.write('T[1].In',4095.0);e.step()
        self.assertEqual((e.memory.read('T[0].Out'),e.memory.read('T[1].Out')),(0.0,100.0))

    def test_nested_udt_record_members_have_real_bool_and_status_types(self):
        def mutate(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='HolderType',Class='User',Family='NoFamily'),'Members')
            E.SubElement(m,'Member',Name='ScaleState',DataType='SCALE',Dimension='0')
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Holder',DataType='HolderType',TagType='Base')
            data=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='HolderType')
            item=copy.deepcopy(root.find('./Controller/Tags/Tag[@Name="T"]/Data/Structure'));item.tag='StructureMember';item.set('Name','ScaleState');data.append(item)
        e=self.checked(['SCL(Holder.ScaleState);'],mutate=mutate);e.memory.write('Holder.ScaleState.In',4095.0);e.step()
        self.assertEqual(e.memory.read('Holder.ScaleState.Out'),100.0)
        for member,dtype in (('Out','REAL'),('MaxAlarm','BOOL'),('Status','DINT'),('InRawRangeInv','BOOL')):
            self.assertEqual(e.memory.resolve('Holder.ScaleState.'+member)[2],dtype)

    def test_aoi_inout_binding_scales_the_supplied_record(self):
        def mutate(root):
            definitions=root.find('./Controller/AddOnInstructionDefinitions')
            if definitions is None:definitions=E.SubElement(root.find('Controller'),'AddOnInstructionDefinitions')
            d=E.SubElement(definitions,'AddOnInstructionDefinition',Name='ScaleBlock',Class='Standard',Revision='1.0',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            p=E.SubElement(d,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):
                E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(p,'Parameter',Name='State',TagType='Base',DataType='SCALE',Usage='InOut',Required='true',Visible='true')
            E.SubElement(d,'LocalTags');logic(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='ST'),['SCL(State);'])
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='ScaleBlock',TagType='Base')
            data=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='ScaleBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(data,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['ScaleBlock(Instance,T);'],mutate=mutate,values={'In':4095.0});self.assertEqual(self.step(e)['Out'],100.0)

    def test_periodic_routine_harness_and_for_calls(self):
        def mutate(root):t=root.find('./Controller/Tasks/Task');t.set('Type','PERIODIC');t.set('Rate','10')
        e=self.checked(mutate=mutate,values={'In':4095.0});self.assertEqual(self.step(e)['Out'],100.0)
        harness=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(harness.blockers,[])
        self.assertEqual(self.step(harness)['Out'],100.0)
        e=self.checked(['FOR DisplayedPartCount := 0 TO 2 DO SCL(T); END_FOR;'],values={'In':4095.0})
        self.assertEqual(self.step(e)['Out'],100.0)

    def test_for_bounds_cannot_depend_on_status_written_by_scl(self):
        e=self.engine(['FOR DisplayedPartCount := 0 TO T.Status DO SCL(T); END_FOR;'])
        self.assertTrue(any('bounds/step' in message for message in e.blockers),e.blockers)

    def test_bad_arity_types_constants_profiles_and_ladder_forms_are_blocked(self):
        for line in ('SCL();','SCL(T,U);','SCL(Parts);','SCL(T.Out);','SCL(3);','RES(T);'):
            self.assertTrue(self.engine([line]).blockers,line)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="T"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        for processor,version in (('1756-L75','35'),('1756-L85E','34')):
            def profile(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',version)
            self.assertTrue(self.engine(mutate=profile).blockers)
        def ladder(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');logic(routine,[]);routine.set('Type','RLL');routine.remove(routine.find('STContent'))
            E.SubElement(E.SubElement(E.SubElement(routine,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='SCL(T);'
        self.assertTrue(self.engine(mutate=ladder).blockers)

    def test_redefined_scale_schema_is_rejected(self):
        def mutate(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='SCALE',Class='User',Family='NoFamily'),'Members')
            E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
        self.assertTrue(self.engine(mutate=mutate).blockers)

    def test_scale_lab_exposes_scaling_limits_and_status_aliases(self):
        from logixlab.server import SAMPLES as names
        self.assertIn('ScaleLab',names);e=Engine(Project(SAMPLES/'ScaleLab.L5X'));self.assertEqual(e.blockers,[])
        e.memory.write('RawValue',2047.5);e.step();self.assertEqual(e.memory.read('ScaledValue'),50.0)
        e.memory.write('RawValue',8190.0);e.step();self.assertEqual(e.memory.read('ScaledValue'),200.0);self.assertTrue(e.memory.read('HighAlarm'))
        e.memory.write('LimitOutput',True);e.step();self.assertEqual(e.memory.read('ScaledValue'),100.0)
        e.memory.write('RawMaximum',0.0);e.step();self.assertTrue(e.memory.read('ScaleFault'));self.assertTrue(e.memory.read('InvalidRange'))
        self.assertEqual(e.memory.read('ScaledValue'),100.0);e.memory.write('RawMaximum',4095.0);e.step();self.assertFalse(e.memory.read('ScaleFault'))

    def test_detached_routine_replacement_preserves_active_scale_values(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def mutate(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0]
            main.set('Type','RLL');main.remove(main.find('STContent'))
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(ScaleLogic,0);'
            logic(E.SubElement(routines,'Routine',Name='ScaleLogic',Type='ST'),['SCL(T);'])
        e=self.checked(mutate=mutate,values={'In':2047.5});self.step(e);before=copy.deepcopy(e.memory.values)
        neutral=['JSR(ScaleLogic,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        source=decode(container(E.tostring(xml,encoding='utf-8')));candidate,_=prepare(e,source,tuple(neutral),'MainProgram',0)
        self.assertEqual(e.memory.values,before);candidate.memory.write('T.In',4095.0);candidate.step()
        self.assertEqual(candidate.memory.read('T.Out'),100.0);self.assertEqual(e.memory.values,before)

    def test_builtin_classification_counts_and_report_qualification(self):
        e=self.checked();self.assertNotIn('SCALE',e.project.data_only_types);self.assertNotIn('scale',e.project.udts)
        self.assertEqual(set(e.memory.read('T')),set(FIELDS));self.assertEqual(len(ARITIES),101)
        self.assertTrue({'TONR','TOFR','RTOR','CTUD','OSRI','OSFI','SCL'}<=set(ST_ONLY_ARITIES))
        profile=e.report()['st_scale'];self.assertEqual(profile['instructions'],['SCL']);self.assertFalse(profile['native_runtime_parity'])
        self.assertEqual(profile['status_aliases']['InRawRangeInv'],'Status.1')


if __name__=='__main__':unittest.main()
