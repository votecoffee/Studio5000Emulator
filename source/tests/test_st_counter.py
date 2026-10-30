"""CTUD sampled edges, signed boundaries, initialization and transactions."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from logixlab.st_counter import FIELDS,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def record(parent,name,values):
    tag=E.SubElement(parent,'Tag',Name=name,DataType='FBD_COUNTER',TagType='Base')
    data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='FBD_COUNTER')
    for member,value in (default()|values).items():
        E.SubElement(data,'DataValueMember',Name=member,DataType=FIELDS[member],Value=str(int(value)))


class StructuredCounterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,values=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        for name in ('C','D'):record(tags,name,{'PRE':2}|dict(values or {}))
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else ['CTUD(C);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'counter.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e):e.step();return e.memory.read('C')

    def pulse(self,e,field):
        e.memory.write('C.'+field,False);self.step(e);e.memory.write('C.'+field,True);return self.step(e)

    def test_count_up_held_rearm_done_and_counting_beyond_preset(self):
        e=self.checked();self.step(e)
        for count in (1,2,3):
            c=self.pulse(e,'CUEnable');self.assertEqual(c['ACC'],count);self.assertEqual(c['DN'],count>=2)
            self.assertEqual(self.step(e)['ACC'],count)

    def test_count_down_can_clear_done_and_go_negative(self):
        e=self.checked(values={'ACC':4,'PRE':2});self.step(e)
        for count in (3,2,1,0,-1):
            c=self.pulse(e,'CDEnable');self.assertEqual(c['ACC'],count);self.assertEqual(c['DN'],count>=2)

    def test_first_high_inputs_prime_without_phantom_counts_and_mirror_outputs(self):
        e=self.checked(values={'ACC':9,'CUEnable':True,'CDEnable':True,'CU':False,'CD':False})
        c=self.step(e);self.assertEqual(c['ACC'],9);self.assertTrue(c['CU']);self.assertTrue(c['CD'])
        self.assertTrue(c['EnableIn']);self.assertTrue(c['EnableOut']);self.assertEqual(self.step(e)['ACC'],9)

    def test_independent_edges_count_when_other_input_remains_high(self):
        e=self.checked();self.step(e);self.pulse(e,'CUEnable')
        e.memory.write('C.CDEnable',True);self.assertEqual(self.step(e)['ACC'],0)
        e.memory.write('C.CUEnable',False);self.step(e);e.memory.write('C.CUEnable',True)
        self.assertEqual(self.step(e)['ACC'],1)

    def test_simultaneous_edges_cancel_but_count_up_happens_before_down(self):
        e=self.checked(values={'ACC':2147483647});self.step(e)
        e.memory.write('C.CUEnable',True);e.memory.write('C.CDEnable',True);c=self.step(e)
        self.assertEqual(c['ACC'],2147483647);self.assertTrue(c['OV']);self.assertTrue(c['UN'])
        e=self.checked(values={'ACC':-2147483648});self.step(e)
        e.memory.write('C.CUEnable',True);e.memory.write('C.CDEnable',True);c=self.step(e)
        self.assertEqual(c['ACC'],-2147483648);self.assertFalse(c['OV']);self.assertFalse(c['UN'])

    def test_signed_overflow_and_underflow_wrap_and_flags_retain(self):
        for initial,field,expected,flag in ((2147483647,'CUEnable',-2147483648,'OV'),(-2147483648,'CDEnable',2147483647,'UN')):
            e=self.checked(values={'ACC':initial});self.step(e);c=self.pulse(e,field)
            self.assertEqual(c['ACC'],expected);self.assertTrue(c[flag])
            c=self.pulse(e,field);self.assertTrue(c[flag])
            e.memory.write('C.Reset',True);c=self.step(e);self.assertFalse(c['OV']);self.assertFalse(c['UN']);self.assertEqual(c['ACC'],0)

    def test_reset_takes_priority_consumes_high_inputs_and_clears_wrap_flags(self):
        e=self.checked(values={'ACC':7,'OV':True,'UN':True});self.step(e)
        e.memory.write('C.CUEnable',True);e.memory.write('C.Reset',True);c=self.step(e)
        self.assertEqual(c['ACC'],0);self.assertFalse(c['OV']);self.assertFalse(c['UN']);self.assertTrue(c['CU'])
        e.memory.write('C.Reset',False);self.assertEqual(self.step(e)['ACC'],0)
        self.assertEqual(self.pulse(e,'CUEnable')['ACC'],1)

    def test_zero_negative_and_changed_presets_recompute_done_without_counting(self):
        e=self.checked(values={'PRE':0});self.assertTrue(self.step(e)['DN'])
        e.memory.write('C.PRE',-10);self.assertTrue(self.step(e)['DN'])
        e.memory.write('C.PRE',5);self.assertFalse(self.step(e)['DN']);self.assertEqual(e.memory.read('C.ACC'),0)
        e.memory.write('C.Reset',True);e.memory.write('C.PRE',0);self.assertTrue(self.step(e)['DN'])

    def test_st_calls_ignore_stored_enable_in_and_output_cu_is_not_edge_storage(self):
        e=self.checked(values={'EnableIn':False});e.memory.values['c']['EnableIn']=None;self.step(e)
        self.pulse(e,'CUEnable');e.memory.write('C.CU',False);c=self.step(e)
        self.assertTrue(c['EnableIn']);self.assertTrue(c['CU']);self.assertEqual(c['ACC'],1)

    def test_two_calls_at_one_timestamp_and_for_iterations_do_not_duplicate_edges(self):
        e=self.checked(['CTUD(C);','FOR DisplayedPartCount := 0 TO 2 DO CTUD(C); END_FOR;']);self.step(e)
        e.memory.write('C.CUEnable',True);self.assertEqual(self.step(e)['ACC'],1)

    def test_separate_records_keep_independent_sampled_edges(self):
        e=self.checked(['CTUD(C);','CTUD(D);']);self.step(e);e.memory.write('C.CUEnable',True);self.step(e)
        self.assertEqual(e.memory.read('D.ACC'),0);e.memory.write('D.CUEnable',True);self.step(e)
        self.assertEqual((e.memory.read('C.ACC'),e.memory.read('D.ACC')),(1,1))

    def test_first_reached_call_after_skips_still_primes_inputs(self):
        e=self.checked(['IF StartPB THEN CTUD(C); END_IF;'],values={'CUEnable':True})
        self.step(e);self.step(e);self.assertEqual(e._st_counter_edges,{})
        e.memory.write('StartPB',True);self.assertEqual(self.step(e)['ACC'],0)

    def test_skipped_calls_only_observe_inputs_on_next_reached_call(self):
        e=self.checked(['IF StartPB THEN CTUD(C); END_IF;']);e.memory.write('StartPB',True);self.step(e)
        e.memory.write('StartPB',False);e.memory.write('C.CUEnable',True);self.step(e)
        e.memory.write('C.CUEnable',False);self.step(e);e.memory.write('StartPB',True)
        self.assertEqual(self.step(e)['ACC'],0)
        e.memory.write('StartPB',False);e.memory.write('C.CUEnable',True);self.step(e)
        e.memory.write('StartPB',True);self.assertEqual(self.step(e)['ACC'],1)

    def test_unknown_required_input_or_accumulator_faults_and_preserves_edge_state(self):
        for field in ('CUEnable','CDEnable','Reset','PRE','ACC'):
            e=self.checked();self.step(e);e.memory.values['c'][field]=None
            before=copy.deepcopy((e.memory.values,e._st_counter_edges,e.scan_count,e.time_ms))
            with self.assertRaisesRegex(ModelError,'unknown'):e.step()
            self.assertEqual((e.memory.values,e._st_counter_edges,e.scan_count,e.time_ms),before)

    def test_reset_can_establish_unknown_accumulator_and_wrap_flags(self):
        e=self.checked(values={'Reset':True})
        for name in ('ACC','OV','UN'):e.memory.values['c'][name]=None
        c=self.step(e);self.assertEqual(c['ACC'],0);self.assertFalse(c['OV']);self.assertFalse(c['UN'])

    def test_unneeded_unknown_wrap_flags_remain_unknown_until_set_or_reset(self):
        e=self.checked();e.memory.values['c']['OV']=None;e.memory.values['c']['UN']=None;self.step(e)
        self.assertIsNone(e.memory.values['c']['OV']);self.assertIsNone(e.memory.values['c']['UN'])
        e.memory.write('C.ACC',2147483647);self.pulse(e,'CUEnable');self.assertTrue(e.memory.read('C.OV'))
        self.assertIsNone(e.memory.values['c']['UN'])

    def test_prescan_only_clears_enable_pair_and_deferred_preview_retains_source(self):
        e=self.checked(values={'ACC':7,'CU':True,'CD':True,'DN':True,'OV':True,'UN':True,'EnableOut':True},defer=True)
        self.assertTrue(e.memory.read('C.EnableIn'));self.assertTrue(e.memory.read('C.EnableOut'))
        before=copy.deepcopy(e.memory.read('C'));e.enter_run()
        self.assertEqual(e.memory.read('C'),before|{'EnableIn':False,'EnableOut':False})

    def test_run_entry_reprimes_edges_and_retains_accumulator_without_phantom_count(self):
        e=self.checked();self.step(e);self.pulse(e,'CUEnable');before=(e.scan_count,e.time_ms)
        e.enter_run();self.assertEqual((e.scan_count,e.time_ms),before);self.assertEqual(e._st_counter_edges,{})
        self.assertEqual(self.step(e)['ACC'],1);self.assertEqual(self.pulse(e,'CUEnable')['ACC'],2)

    def test_late_fault_restores_sampled_edge_so_corrected_retry_counts_once(self):
        e=self.checked(['CTUD(C);','SpeedCommand := 1 / SpeedSetpoint;']);e.memory.write('SpeedSetpoint',1);self.step(e)
        e.memory.write('C.CUEnable',True);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e._st_counter_edges,e.scan_count,e.time_ms,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual((e.memory.values,e._st_counter_edges,e.scan_count,e.time_ms,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e)['ACC'],1);self.assertEqual(self.step(e)['ACC'],1)

    def test_first_call_fault_does_not_consume_initialization(self):
        e=self.checked(['CTUD(C);','SpeedCommand := 1 / SpeedSetpoint;'],values={'CUEnable':True});e.memory.write('SpeedSetpoint',0)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e._st_counter_edges,{});e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e)['ACC'],0)

    def test_prescan_and_instruction_budget_failures_restore_values_and_history(self):
        e=self.checked(['CTUD(C);','SpeedCommand := 7;']);self.step(e);e.memory.write('C.CUEnable',True)
        before=copy.deepcopy((e.memory.values,e._st_counter_edges));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual((e.memory.values,e._st_counter_edges),before)
        e.instruction_limit=100;e.step();before=copy.deepcopy((e.memory.values,e._st_counter_edges,e.prescan_count))
        e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan.*budget'):e.enter_run()
        self.assertEqual((e.memory.values,e._st_counter_edges,e.prescan_count),before)

    def test_alias_program_local_counter_resolves_to_same_history(self):
        def mutate(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="C"]');tags.remove(tag)
            root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='AliasC',TagType='Alias',AliasFor='Program:MainProgram.C')
        e=self.checked(['CTUD(AliasC);'],mutate=mutate);e.step();e.memory.write('Program:MainProgram.C.CUEnable',True);e.step()
        self.assertEqual(e.memory.read('Program:MainProgram.C.ACC'),1)

    def test_array_records_use_independent_edges(self):
        def mutate(root):
            t=root.find('./Controller/Tags/Tag[@Name="C"]');data=t.find('Data');item=copy.deepcopy(data[0])
            data.clear();data.set('Format','Decorated');t.set('Dimensions','2')
            a=E.SubElement(data,'Array',DataType='FBD_COUNTER',Dimensions='2')
            for i in range(2):E.SubElement(a,'Element',Index=f'[{i}]').append(copy.deepcopy(item))
        e=self.checked(['CTUD(C[0]);','CTUD(C[1]);'],mutate=mutate);e.step();e.memory.write('C[1].CUEnable',True);e.step()
        self.assertEqual((e.memory.read('C[0].ACC'),e.memory.read('C[1].ACC')),(0,1))

    def test_udt_member_counter_has_builtin_field_types(self):
        def mutate(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='HolderType',Class='User',Family='NoFamily'),'Members')
            E.SubElement(m,'Member',Name='Counter',DataType='FBD_COUNTER',Dimension='0')
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Holder',DataType='HolderType',TagType='Base')
            data=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='HolderType')
            item=copy.deepcopy(root.find('./Controller/Tags/Tag[@Name="C"]/Data/Structure'));item.tag='StructureMember';item.set('Name','Counter');data.append(item)
        e=self.checked(['CTUD(Holder.Counter);'],mutate=mutate);e.step();e.memory.write('Holder.Counter.CUEnable',True);e.step()
        self.assertEqual(e.memory.read('Holder.Counter.ACC'),1);self.assertEqual(e.memory.resolve('Holder.Counter.CU')[2],'BOOL')

    def test_aoi_inout_counter_uses_resolved_record_identity(self):
        def mutate(root):
            definitions=root.find('./Controller/AddOnInstructionDefinitions')
            if definitions is None:definitions=E.SubElement(root.find('Controller'),'AddOnInstructionDefinitions')
            d=E.SubElement(definitions,'AddOnInstructionDefinition',Name='CounterBlock',Class='Standard',Revision='1.0',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            p=E.SubElement(d,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):
                E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(p,'Parameter',Name='CounterState',TagType='Base',DataType='FBD_COUNTER',Usage='InOut',Required='true',Visible='true')
            E.SubElement(d,'LocalTags');logic(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='ST'),['CTUD(CounterState);'])
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='CounterBlock',TagType='Base')
            data=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='CounterBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(data,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['CounterBlock(Instance,C);'],mutate=mutate);self.step(e);self.assertEqual(self.pulse(e,'CUEnable')['ACC'],1)

    def test_periodic_and_routine_harness_calls_preserve_edge_semantics(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','PERIODIC');t.set('Rate','10')
        e=self.checked(mutate=periodic);self.step(e);self.assertEqual(self.pulse(e,'CUEnable')['ACC'],1)
        e=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(e.blockers,[])
        self.step(e);self.assertEqual(self.pulse(e,'CUEnable')['ACC'],1)

    def test_for_bounds_cannot_depend_on_counter_written_by_call(self):
        self.assertTrue(self.engine(['FOR DisplayedPartCount := 0 TO C.ACC DO CTUD(C); END_FOR;']).blockers)

    def test_bad_arities_types_constants_profiles_and_ladder_forms_are_blocked(self):
        for line in ('CTUD();','CTUD(C,D);','CTUD(Parts);','CTUD(C.ACC);','CTUD(3);','RES(C);'):
            self.assertTrue(self.engine([line]).blockers,line)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="C"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        for processor,version in (('1756-L75','35'),('1756-L85E','34')):
            def profile(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',version)
            self.assertTrue(self.engine(mutate=profile).blockers)
        def ladder(root):
            r=root.find('./Controller/Programs/Program/Routines/Routine');r.set('Type','RLL');r.remove(r.find('STContent'))
            E.SubElement(E.SubElement(E.SubElement(r,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='CTUD(C);'
        self.assertTrue(self.engine(mutate=ladder).blockers)

    def test_builtin_counter_is_not_decorated_only_and_does_not_inflate_rll_count(self):
        e=self.checked();self.assertNotIn('FBD_COUNTER',e.project.data_only_types);self.assertNotIn('fbd_counter',e.project.udts)
        self.assertEqual(len(ARITIES),99);self.assertEqual(set(ST_ONLY_ARITIES),{'TONR','TOFR','RTOR','CTUD'})
        self.assertEqual(set(e.memory.read('C')),set(FIELDS));self.assertEqual(e.memory.resolve('C.ACC')[2],'DINT')

    def test_report_exposes_sampled_initialization_order_reset_and_qualification(self):
        p=self.checked().report()['st_counter'];self.assertEqual(p['instructions'],['CTUD']);self.assertEqual(p['language'],'ST')
        self.assertFalse(p['native_runtime_parity']);self.assertIn('Count up before count down',p['ordering'])

    def test_counter_lab_bundles_count_inputs_and_public_scalar_outputs(self):
        from logixlab.server import SAMPLES as names
        self.assertIn('CounterLab',names);e=Engine(Project(SAMPLES/'CounterLab.L5X'));self.assertEqual(e.blockers,[])
        e.step();e.memory.write('UpInput',True);e.step();self.assertEqual(e.memory.read('Count'),1)
        e.step();self.assertEqual(e.memory.read('Count'),1);e.memory.write('DownInput',True);e.step()
        self.assertEqual(e.memory.read('Count'),0);self.assertEqual(e.memory.read('CallCount'),4)

    def test_redefined_counter_schema_is_rejected(self):
        def mutate(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_COUNTER',Class='User',Family='NoFamily'),'Members')
            E.SubElement(m,'Member',Name='ACC',DataType='DINT',Dimension='0')
        self.assertTrue(self.engine(mutate=mutate).blockers)

    def test_detached_routine_replacement_preserves_edge_history_and_active_values(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def mutate(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0]
            main.set('Type','RLL');main.remove(main.find('STContent'))
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(CountLogic,0);'
            logic(E.SubElement(routines,'Routine',Name='CountLogic',Type='ST'),['CTUD(C);'])
        e=self.checked(mutate=mutate);self.step(e);self.pulse(e,'CUEnable');before=copy.deepcopy((e.memory.values,e._st_counter_edges))
        neutral=['JSR(CountLogic,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        source=decode(container(E.tostring(xml,encoding='utf-8')));candidate,_=prepare(e,source,tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e._st_counter_edges),before);self.assertEqual(candidate._st_counter_edges,e._st_counter_edges)
        self.assertIsNot(candidate._st_counter_edges,e._st_counter_edges);candidate.step();self.assertEqual(candidate.memory.read('C.ACC'),1)
        self.assertEqual((e.memory.values,e._st_counter_edges),before)


if __name__=='__main__':unittest.main()
