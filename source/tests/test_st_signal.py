"""HLL, SNEG and SSUM signal behavior, type boundaries and transactional execution."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project,coerce
from logixlab.runtime import Engine
from logixlab.st_signal import SCHEMAS,TYPES,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def record(parent,name,dtype,values):
    tag=E.SubElement(parent,'Tag',Name=name,DataType=dtype,TagType='Base')
    data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType=dtype)
    for member,value in (default(dtype)|values).items():
        kind=SCHEMAS[dtype][member]
        E.SubElement(data,'DataValueMember',Name=member,DataType=kind,Value=str(float(value) if kind=='REAL' else int(value)))


class StructuredSignalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,name='HLL',values=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags');dtype=TYPES[name]
        record(tags,'T',dtype,({'HighLimit':10.0} if name=='HLL' else {})|dict(values or {}))
        for tag,kind in (('H','HL_LIMIT'),('N','SELECTABLE_NEGATE'),('S','SELECTED_SUMMER')):
            record(tags,tag,kind,{'HighLimit':10.0} if kind=='HL_LIMIT' else {})
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else [name+'(T);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'signals.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e):e.step(10);return e.memory.read('T')

    def test_hll_both_limits_clamp_and_have_inclusive_endpoint_alarms(self):
        e=self.checked()
        for value,out,high,low in ((5.0,5.0,False,False),(10.0,10.0,True,False),(20.0,10.0,True,False),
                                   (0.0,0.0,False,True),(-5.0,0.0,False,True)):
            e.memory.write('T.In',value);t=self.step(e)
            self.assertEqual((t['Out'],t['HighAlarm'],t['LowAlarm'],t['Status']),(out,high,low,0))

    def test_hll_high_only_does_not_apply_low_limit_or_alarm(self):
        e=self.checked(values={'SelectLimit':1,'In':-5.0});t=self.step(e)
        self.assertEqual(t['Out'],-5.0);self.assertFalse(t['LowAlarm'])
        e.memory.write('T.In',10.0);t=self.step(e);self.assertEqual(t['Out'],10.0);self.assertTrue(t['HighAlarm'])

    def test_hll_low_only_does_not_apply_high_limit_or_alarm(self):
        e=self.checked(values={'SelectLimit':2,'In':20.0});t=self.step(e)
        self.assertEqual(t['Out'],20.0);self.assertFalse(t['HighAlarm'])
        e.memory.write('T.In',0.0);t=self.step(e);self.assertEqual(t['Out'],0.0);self.assertTrue(t['LowAlarm'])

    def test_hll_invalid_selector_falls_back_to_both_without_changing_setting(self):
        for selector in (-1,3,2147483647):
            with self.subTest(selector=selector):
                e=self.checked(values={'SelectLimit':selector,'In':20.0});t=self.step(e)
                self.assertEqual((t['Out'],t['Status'],t['SelectLimit']),(10.0,5,selector))
                self.assertTrue(t['HighAlarm']);self.assertTrue(e.memory.read('T.SelectLimitInv'))

    def test_hll_equal_or_reversed_both_limits_use_low_endpoint_and_status(self):
        for high,low,value in ((5.0,5.0,5.0),(0.0,10.0,5.0)):
            with self.subTest(high=high,low=low):
                e=self.checked(values={'HighLimit':high,'LowLimit':low,'In':value});t=self.step(e)
                self.assertEqual((t['Out'],t['Status']),(low,3));self.assertTrue(t['HighAlarm']);self.assertTrue(t['LowAlarm'])
                self.assertTrue(t['EnableOut']);self.assertFalse(e.fault)

    def test_hll_combined_diagnostics_and_recovery(self):
        e=self.checked(values={'SelectLimit':9,'HighLimit':0.0,'LowLimit':10.0,'In':5.0})
        self.assertEqual(self.step(e)['Status'],7);e.memory.write('T.HighLimit',20.0);self.assertEqual(self.step(e)['Status'],5)
        e.memory.write('T.SelectLimit',0);self.assertEqual(self.step(e)['Status'],0)

    def test_hll_single_limit_ignores_inactive_unknown_or_crossed_bound(self):
        for mode,inactive,active,expected in ((1,'LowLimit','HighLimit',10.0),(2,'HighLimit','LowLimit',0.0)):
            with self.subTest(mode=mode):
                e=self.checked(values={'SelectLimit':mode,'In':10.0 if mode==1 else -5.0})
                e.memory.read('T')[inactive]=None;t=self.step(e);self.assertEqual(t['Out'],expected);self.assertEqual(t['Status'],0)
                e.memory.write('T.'+inactive,100.0 if mode==1 else -100.0);self.assertEqual(self.step(e)['Status'],0)

    def test_hll_status_aliases_have_one_backing_word_and_case_insensitive_names(self):
        e=self.checked()
        for name,expected in (('LimitsInv',2),('SelectLimitInv',6),('InstructFault',7)):
            e.memory.write('t.'+name,True);self.assertEqual(e.memory.read('T.Status'),expected)
        e.memory.write('T.Status',5);self.assertFalse(e.memory.read('T.limitsinv'));self.assertTrue(e.memory.read('T.selectlimitinv'))
        self.step(e);self.assertEqual(e.memory.read('T.Status'),0)
        with self.assertRaisesRegex(ModelError,'Invalid HL_LIMIT status alias'):e.memory.read('T.LimitsInv.0')

    def test_sneg_passes_or_negates_positive_and_negative_inputs(self):
        e=self.checked(name='SNEG')
        for value,enabled,out in ((7.5,True,-7.5),(-7.5,True,7.5),(7.5,False,7.5),(-7.5,False,-7.5)):
            e.memory.write('T.In',value);e.memory.write('T.NegateEnable',enabled);self.assertEqual(self.step(e)['Out'],out)

    def test_sneg_default_negates_and_preserves_the_selected_zero_sign(self):
        e=self.checked(name='SNEG');self.assertTrue(e.memory.read('T.NegateEnable'))
        self.assertEqual(math.copysign(1,self.step(e)['Out']),-1)
        e.memory.write('T.In',-0.0);self.assertEqual(math.copysign(1,self.step(e)['Out']),1)
        e.memory.write('T.NegateEnable',False);self.assertEqual(math.copysign(1,self.step(e)['Out']),-1)

    def test_ssum_no_selected_inputs_returns_bias(self):
        e=self.checked(name='SSUM',values={'Bias':12.5});self.assertEqual(self.step(e)['Out'],12.5)

    def test_ssum_each_of_eight_channels_can_be_selected(self):
        e=self.checked(name='SSUM',values={'Bias':1.0})
        for i in range(1,9):
            with self.subTest(channel=i):
                for n in range(1,9):e.memory.write('T.Select'+str(n),n==i)
                e.memory.write('T.In'+str(i),float(i));e.memory.write('T.Gain'+str(i),2.0)
                self.assertEqual(self.step(e)['Out'],2*i+1)

    def test_ssum_algebraic_gains_selected_values_and_bias(self):
        e=self.checked(name='SSUM',values={'In1':10.0,'Gain1':2.0,'Select1':True,'In2':3.0,'Gain2':-4.0,
                                          'Select2':True,'In8':7.0,'Gain8':0.5,'Select8':True,'Bias':-1.5})
        self.assertEqual(self.step(e)['Out'],10.0)

    def test_ssum_all_channels_with_default_gains(self):
        values={name+str(i):value for i in range(1,9) for name,value in (('In',float(i)),('Select',True))}
        e=self.checked(name='SSUM',values=values);self.assertEqual(self.step(e)['Out'],36.0)
        self.assertTrue(all(e.memory.read('T.Gain'+str(i))==1.0 for i in range(1,9)))

    def test_ssum_unselected_unknown_or_nonfinite_pairs_are_not_read(self):
        e=self.checked(name='SSUM',values={'Bias':7.0})
        e.memory.read('T').update(In1=None,Gain1=None,In8=float('nan'),Gain8=float('inf'))
        self.assertEqual(self.step(e)['Out'],7.0);e.memory.write('T.Select1',True)
        with self.assertRaisesRegex(ModelError,'In1 is unknown'):e.step()

    def test_ssum_weighted_products_are_summed_then_bias_with_final_float32_rounding(self):
        e=self.checked(name='SSUM',values={'In1':1.0,'Gain1':0.1,'Select1':True,'In2':2.0,'Gain2':0.2,'Select2':True,'Bias':0.3})
        expected=coerce(coerce(0.1,'REAL')+2*coerce(0.2,'REAL')+coerce(0.3,'REAL'),'REAL')
        self.assertEqual(self.step(e)['Out'],expected)

    def test_ssum_finite_overflow_rolls_back_and_deselection_allows_retry(self):
        e=self.checked(name='SSUM',values={'In1':3e38,'Gain1':2.0,'Select1':True,'Out':17.0})
        before=copy.deepcopy((e.memory.values,e.scan_count,e.time_ms,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'finite REAL'):e.step()
        self.assertEqual((e.memory.values,e.scan_count,e.time_ms,e.scheduler_description()),before)
        e.memory.write('T.Select1',False);self.assertEqual(self.step(e)['Out'],0.0)

    def test_reached_st_calls_ignore_stored_enable_and_establish_outputs(self):
        for name in TYPES:
            with self.subTest(name=name):
                e=self.checked(name=name,values={'EnableIn':False});e.memory.read('T').update(EnableIn=None,Out=None)
                t=self.step(e);self.assertTrue(t['EnableIn']);self.assertTrue(t['EnableOut']);self.assertIsInstance(t['Out'],float)

    def test_skipped_calls_retain_outputs_and_status_until_reached(self):
        e=self.checked(['IF StartPB THEN HLL(T); END_IF;'],values={'In':20.0})
        e.memory.write('StartPB',True);self.step(e);before=copy.deepcopy(e.memory.read('T'))
        e.memory.write('StartPB',False);e.memory.write('T.In',-5.0);self.step(e)
        for key in ('Out','HighAlarm','LowAlarm','Status'):self.assertEqual(e.memory.read('T')[key],before[key])
        e.memory.write('StartPB',True);self.assertTrue(self.step(e)['LowAlarm'])

    def test_repeated_calls_observe_new_inputs_in_the_same_scan(self):
        e=self.checked(['N.In := 10.0;','SNEG(N);','T.In := N.Out;','HLL(T);','N.NegateEnable := FALSE;','SNEG(N);'])
        self.assertEqual(self.step(e)['Out'],0.0);self.assertEqual(e.memory.read('N.Out'),10.0)

    def test_required_unknown_selectors_values_and_active_bounds_fault(self):
        cases=(('HLL','SelectLimit',{}),('HLL','In',{}),('HLL','HighLimit',{}),('HLL','LowLimit',{}),
               ('SNEG','In',{}),('SNEG','NegateEnable',{}),('SSUM','Select8',{}),('SSUM','Bias',{}),
               ('SSUM','In1',{'Select1':True}),('SSUM','Gain1',{'Select1':True}))
        for name,field,values in cases:
            with self.subTest(name=name,field=field):
                e=self.checked(name=name,values=values);e.memory.read('T')[field]=None;before=copy.deepcopy(e.memory.values)
                with self.assertRaisesRegex(ModelError,'unknown'):e.step()
                self.assertEqual(e.memory.values,before)

    def test_required_nonfinite_and_wrong_value_types_fault(self):
        for name,field,value in (('HLL','In',float('nan')),('HLL','SelectLimit',True),('SNEG','NegateEnable',1),
                                  ('SNEG','In',float('inf')),('SSUM','Select1',1),('SSUM','Bias',float('inf'))):
            with self.subTest(name=name,field=field):
                e=self.checked(name=name);e.memory.read('T')[field]=value;before=repr(e.memory.values)
                with self.assertRaises(ModelError):e.step()
                self.assertEqual(repr(e.memory.values),before)

    def test_missing_exported_values_remain_unknown(self):
        def mutate(root):
            data=root.find('./Controller/Tags/Tag[@Name="T"]/Data/Structure');data.remove(data.find('DataValueMember[@Name="In"]'))
        e=self.checked(mutate=mutate);self.assertIsNone(e.memory.read('T')['In'])
        with self.assertRaisesRegex(ModelError,'omitted by export'):e.memory.read('T.In')
        with self.assertRaisesRegex(ModelError,'In is unknown'):e.step()

    def test_prescan_run_and_deferred_preview_retain_outputs_and_settings(self):
        for name in TYPES:
            with self.subTest(name=name):
                e=self.checked(name=name,values={'Out':17.0,'EnableOut':True},defer=True)
                self.assertTrue(e.memory.read('T.EnableIn'));e.enter_run();t=e.memory.read('T')
                self.assertFalse(t['EnableIn']);self.assertFalse(t['EnableOut']);self.assertEqual(t['Out'],17.0)
                result=self.step(e)['Out'];e.enter_run();self.assertEqual(e.memory.read('T.Out'),result)
                self.assertEqual(self.step(e)['Out'],result)

    def test_late_fault_rolls_back_all_three_records_and_schedule(self):
        e=self.checked(['HLL(H);','SNEG(N);','SSUM(S);','SpeedCommand := 1 / SpeedSetpoint;'])
        e.memory.write('H.In',20.0);e.memory.write('N.In',7.0);e.memory.write('S.Bias',3.0);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e.scan_count,e.time_ms,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual((e.memory.values,e.scan_count,e.time_ms,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual((e.memory.read('H.Out'),e.memory.read('N.Out'),e.memory.read('S.Out')),(10.0,-7.0,3.0))

    def test_budget_failures_restore_scan_and_prescan_values(self):
        e=self.checked(['HLL(T);','SpeedCommand := 7;']);before=copy.deepcopy(e.memory.values);e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(e.memory.values,before);e.instruction_limit=100;self.step(e);before=copy.deepcopy((e.memory.values,e.prescan_count))
        e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan.*budget'):e.enter_run()
        self.assertEqual((e.memory.values,e.prescan_count),before)

    def test_program_local_alias_refers_to_the_same_record(self):
        def mutate(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="T"]');tags.remove(tag)
            root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='AliasT',TagType='Alias',AliasFor='Program:MainProgram.T')
        e=self.checked(['SNEG(AliasT);'],name='SNEG',values={'In':7.0},mutate=mutate);e.step()
        self.assertEqual(e.memory.read('Program:MainProgram.T.Out'),-7.0)

    def test_array_records_and_udt_members_have_declared_member_types(self):
        def mutate(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='HolderType',Class='User',Family='NoFamily'),'Members')
            E.SubElement(m,'Member',Name='Summer',DataType='SELECTED_SUMMER',Dimension='0')
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Holder',DataType='HolderType',TagType='Base')
            data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='HolderType')
            item=copy.deepcopy(root.find('./Controller/Tags/Tag[@Name="S"]/Data/Structure'));item.tag='StructureMember';item.set('Name','Summer');data.append(item)
            t=root.find('./Controller/Tags/Tag[@Name="T"]');data=t.find('Data');item=copy.deepcopy(data[0]);data.clear();data.set('Format','Decorated');t.set('Dimensions','2')
            a=E.SubElement(data,'Array',DataType='HL_LIMIT',Dimensions='2')
            for i in range(2):E.SubElement(a,'Element',Index=f'[{i}]').append(copy.deepcopy(item))
        e=self.checked(['HLL(T[0]);','HLL(T[1]);','SSUM(Holder.Summer);'],mutate=mutate)
        e.memory.write('T[1].In',20.0);e.memory.write('Holder.Summer.Bias',7.0);e.step()
        self.assertEqual((e.memory.read('T[0].Out'),e.memory.read('T[1].Out'),e.memory.read('Holder.Summer.Out')),(0.0,10.0,7.0))
        for ref,dtype in (('Holder.Summer.Gain8','REAL'),('Holder.Summer.Select8','BOOL'),('T[1].Status','DINT'),('T[1].LimitsInv','BOOL')):
            self.assertEqual(e.memory.resolve(ref)[2],dtype)

    def test_aoi_inout_binding_and_periodic_routine_harness(self):
        def mutate(root):
            definitions=root.find('./Controller/AddOnInstructionDefinitions')
            if definitions is None:definitions=E.SubElement(root.find('Controller'),'AddOnInstructionDefinitions')
            d=E.SubElement(definitions,'AddOnInstructionDefinition',Name='SignalBlock',Class='Standard',Revision='1.0',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            p=E.SubElement(d,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):
                E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(p,'Parameter',Name='State',TagType='Base',DataType='SELECTED_SUMMER',Usage='InOut',Required='true',Visible='true')
            E.SubElement(d,'LocalTags');logic(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='ST'),['SSUM(State);'])
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='SignalBlock',TagType='Base')
            data=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='SignalBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(data,'DataValueMember',Name=name,DataType='BOOL',Value='0')
            task=root.find('./Controller/Tasks/Task');task.set('Type','PERIODIC');task.set('Rate','10')
        e=self.checked(['SignalBlock(Instance,T);'],name='SSUM',values={'Bias':7.0},mutate=mutate)
        self.assertEqual(self.step(e)['Out'],7.0);harness=Engine(e.project,'routine','MainProgram/MainRoutine')
        self.assertEqual(harness.blockers,[]);self.assertEqual(self.step(harness)['Out'],7.0)

    def test_for_calls_and_status_dependency_guards(self):
        e=self.checked(['FOR DisplayedPartCount := 0 TO 2 DO HLL(T); END_FOR;'],values={'In':20.0})
        self.assertEqual(self.step(e)['Out'],10.0)
        e=self.engine(['FOR DisplayedPartCount := 0 TO T.Status DO HLL(T); END_FOR;'])
        self.assertTrue(any('bounds/step' in b for b in e.blockers),e.blockers)

    def test_arity_types_constants_other_profiles_and_ladder_forms_are_blocked(self):
        for name in TYPES:
            for line in (name+'();',name+'(T,H);',name+'(Parts);',name+'(T.Out);',name+'(3);','RES(T);'):
                self.assertTrue(self.engine([line],name=name).blockers,line)
            def constant(root):root.find('./Controller/Tags/Tag[@Name="T"]').set('Constant','true')
            self.assertTrue(self.engine(name=name,mutate=constant).blockers)
        for processor,version in (('1756-L75','35'),('1756-L85E','34')):
            def profile(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',version)
            self.assertTrue(self.engine(mutate=profile).blockers)
        def ladder(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');logic(routine,[]);routine.set('Type','RLL');routine.remove(routine.find('STContent'))
            E.SubElement(E.SubElement(E.SubElement(routine,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='HLL(T);'
        self.assertTrue(self.engine(mutate=ladder).blockers)

    def test_redefined_named_schemas_remain_blocked(self):
        for name,dtype in TYPES.items():
            def mutate(root):
                m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name=dtype,Class='User',Family='NoFamily'),'Members')
                E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
            self.assertTrue(self.engine(name=name,mutate=mutate).blockers)

    def test_signal_lab_connects_limits_negation_and_weighted_selection(self):
        from logixlab.server import SAMPLES as names
        self.assertIn('SignalLab',names);e=Engine(Project(SAMPLES/'SignalLab.L5X'));self.assertEqual(e.blockers,[])
        e.step();self.assertEqual((e.memory.read('LimitedValue'),e.memory.read('NegatedValue'),e.memory.read('SumValue')),(5.0,5.0,6.0))
        for name,value in (('Input',20.0),('UseNegated',True),('Negate',True)):e.memory.write(name,value)
        e.step();self.assertEqual(e.memory.read('SumValue'),-9.0);self.assertTrue(e.memory.read('HighAlarm'))
        e.memory.write('LimitMode',2);e.step();self.assertEqual(e.memory.read('SumValue'),1.0);self.assertFalse(e.memory.read('HighAlarm'))
        for name,value in (('UseLimited',False),('UseNegated',False),('Bias',7.0)):e.memory.write(name,value)
        e.step();self.assertEqual(e.memory.read('SumValue'),7.0)

    def test_detached_routine_replacement_preserves_all_three_active_records(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def mutate(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0]
            main.set('Type','RLL');main.remove(main.find('STContent'))
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(SignalLogic,0);'
            logic(E.SubElement(routines,'Routine',Name='SignalLogic',Type='ST'),['HLL(H);','SNEG(N);','SSUM(S);'])
        e=self.checked(mutate=mutate);e.memory.write('H.In',20.0);e.memory.write('N.In',7.0);e.memory.write('S.Bias',3.0);e.step()
        before=copy.deepcopy(e.memory.values);neutral=['JSR(SignalLogic,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        source=decode(container(E.tostring(xml,encoding='utf-8')));candidate,_=prepare(e,source,tuple(neutral),'MainProgram',0)
        self.assertEqual(e.memory.values,before);candidate.memory.write('S.Bias',11.0);candidate.step()
        self.assertEqual((candidate.memory.read('H.Out'),candidate.memory.read('N.Out'),candidate.memory.read('S.Out')),(10.0,-7.0,11.0))
        self.assertEqual(e.memory.values,before)

    def test_builtin_classification_counts_and_reports_are_qualified(self):
        e=self.checked()
        for dtype in SCHEMAS:
            self.assertNotIn(dtype,e.project.data_only_types);self.assertNotIn(dtype.lower(),e.project.udts)
        self.assertEqual(len(ARITIES),99);self.assertEqual(set(ST_ONLY_ARITIES),{'TONR','TOFR','RTOR','CTUD','OSRI','OSFI','SCL','HLL','SNEG','SSUM'})
        profile=e.report()['st_signal'];self.assertEqual(profile['instructions'],['HLL','SNEG','SSUM']);self.assertFalse(profile['native_runtime_parity'])


if __name__=='__main__':unittest.main()
