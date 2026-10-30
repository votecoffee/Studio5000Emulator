"""ST one-shot transitions, reached-call semantics and transactional history."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from logixlab.st_oneshot import FIELDS,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def record(parent,name,values):
    tag=E.SubElement(parent,'Tag',Name=name,DataType='FBD_ONESHOT',TagType='Base')
    data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='FBD_ONESHOT')
    for member,value in (default()|values).items():
        E.SubElement(data,'DataValueMember',Name=member,DataType=FIELDS[member],Value=str(int(value)))


class StructuredOneshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,name='OSRI',values=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        for tag in ('T','U'):record(tags,tag,dict(values or {}))
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else [name+'(T);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'oneshot.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e):e.step(10);return e.memory.read('T')['OutputBit']

    def test_rising_pulse_requires_observed_transition_and_clears_on_next_call(self):
        e=self.checked()
        for level,pulse in ((False,False),(True,True),(True,False),(False,False),(True,True),(False,False)):
            e.memory.write('T.InputBit',level);self.assertIs(self.step(e),pulse)

    def test_falling_pulse_requires_observed_transition_and_clears_on_next_call(self):
        e=self.checked(name='OSFI')
        for level,pulse in ((False,False),(True,False),(False,True),(False,False),(True,False),(False,True)):
            e.memory.write('T.InputBit',level);self.assertIs(self.step(e),pulse)

    def test_initial_high_or_low_never_generates_a_pulse(self):
        for kind in ('OSRI','OSFI'):
            for level in (False,True):
                with self.subTest(kind=kind,level=level):
                    e=self.checked(name=kind,values={'InputBit':level,'OutputBit':True})
                    self.assertFalse(self.step(e));self.assertFalse(self.step(e))

    def test_st_call_executes_even_when_stored_enable_is_false_or_unknown(self):
        e=self.checked(values={'EnableIn':False});self.step(e)
        e.memory.write('T.InputBit',True);e.memory.read('T')['EnableIn']=None
        self.assertTrue(self.step(e));self.assertTrue(e.memory.read('T.EnableIn'));self.assertTrue(e.memory.read('T.EnableOut'))

    def test_writes_to_visible_output_do_not_replace_hidden_input_history(self):
        e=self.checked();self.step(e);e.memory.write('T.OutputBit',True)
        self.assertFalse(self.step(e));e.memory.write('T.InputBit',True);self.assertTrue(self.step(e))
        e.memory.write('T.OutputBit',False);self.assertFalse(self.step(e))

    def test_skipped_call_retains_a_true_output_until_next_reached_call(self):
        e=self.checked(['IF StartPB THEN OSRI(T); END_IF;']);e.memory.write('StartPB',True)
        self.step(e);e.memory.write('T.InputBit',True);self.assertTrue(self.step(e))
        e.memory.write('StartPB',False);self.assertTrue(self.step(e));self.assertTrue(self.step(e))
        e.memory.write('StartPB',True);self.assertFalse(self.step(e))

    def test_pulses_entirely_between_skipped_calls_are_not_invented(self):
        e=self.checked(['IF StartPB THEN OSRI(T); END_IF;']);e.memory.write('StartPB',True);self.step(e)
        e.memory.write('StartPB',False);e.memory.write('T.InputBit',True);self.step(e)
        e.memory.write('T.InputBit',False);self.step(e);e.memory.write('StartPB',True);self.assertFalse(self.step(e))
        e.memory.write('T.InputBit',True);self.assertTrue(self.step(e))

    def test_a_transition_since_last_reached_call_is_sampled_on_resume(self):
        e=self.checked(['IF StartPB THEN OSFI(T); END_IF;'],values={'InputBit':True})
        e.memory.write('StartPB',True);self.step(e);e.memory.write('StartPB',False)
        e.memory.write('T.InputBit',False);self.step(e);e.memory.write('StartPB',True);self.assertTrue(self.step(e))

    def test_distinct_records_have_independent_history(self):
        e=self.checked(['OSRI(T);','OSFI(U);']);self.step(e)
        e.memory.write('T.InputBit',True);e.memory.write('U.InputBit',True);self.assertTrue(self.step(e))
        self.assertFalse(e.memory.read('U.OutputBit'));e.memory.write('U.InputBit',False);self.assertFalse(self.step(e))
        self.assertTrue(e.memory.read('U.OutputBit'))

    def test_repeated_calls_clear_the_pulse_in_the_same_scan(self):
        e=self.checked(['OSRI(T);','StartPB := T.OutputBit;','OSRI(T);']);self.step(e)
        e.memory.write('T.InputBit',True);self.assertFalse(self.step(e));self.assertTrue(e.memory.read('StartPB'))

    def test_for_calls_consume_each_transition_without_a_time_step(self):
        e=self.checked(['FOR DisplayedPartCount := 0 TO 2 DO OSRI(T); IF T.OutputBit THEN SpeedCommand := SpeedCommand + 1; END_IF; END_FOR;'])
        e.memory.write('SpeedCommand',0);self.step(e);e.memory.write('T.InputBit',True);self.step(e)
        self.assertEqual(e.memory.read('SpeedCommand'),1)

    def test_mixed_instruction_kinds_on_one_record_fault_and_rollback(self):
        e=self.checked(['OSRI(T);','OSFI(T);']);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'Mixed one-shot'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e._st_oneshot_edges,{})

    def test_unknown_input_faults_without_consuming_history(self):
        e=self.checked();self.step(e);e.memory.read('T')['InputBit']=None
        before=copy.deepcopy((e.memory.values,e._st_oneshot_edges))
        with self.assertRaisesRegex(ModelError,'InputBit is unknown'):e.step()
        self.assertEqual((e.memory.values,e._st_oneshot_edges),before)
        e.memory.write('T.InputBit',True);self.assertTrue(self.step(e))

    def test_missing_saved_fields_remain_unknown_until_execution_establishes_outputs(self):
        def mutate(root):
            data=root.find('./Controller/Tags/Tag[@Name="T"]/Data/Structure')
            for child in list(data):
                if child.get('Name')!='InputBit':data.remove(child)
        e=self.checked(mutate=mutate,defer=True);self.assertIsNone(e.memory.read('T')['OutputBit'])
        with self.assertRaisesRegex(ModelError,'omitted by export'):e.memory.read('T.OutputBit')
        self.assertFalse(self.step(e));self.assertTrue(e.memory.read('T.EnableOut'))

    def test_missing_input_is_not_invented_from_type_defaults(self):
        def mutate(root):
            data=root.find('./Controller/Tags/Tag[@Name="T"]/Data/Structure');data.remove(data.find('DataValueMember[@Name="InputBit"]'))
        e=self.checked(mutate=mutate);self.assertIsNone(e.memory.read('T')['InputBit'])
        with self.assertRaisesRegex(ModelError,'omitted by export'):e.memory.read('T.InputBit')
        with self.assertRaisesRegex(ModelError,'InputBit is unknown'):e.step()

    def test_prescan_only_clears_enable_flags(self):
        e=self.checked(values={'InputBit':True,'OutputBit':True,'EnableOut':True})
        self.assertEqual(e.memory.read('T'),{'EnableIn':False,'InputBit':True,'EnableOut':False,'OutputBit':True})
        self.assertFalse(self.step(e))

    def test_run_reentry_reprimes_rising_and_falling_history(self):
        for kind,initial in (('OSRI',False),('OSFI',True)):
            with self.subTest(kind=kind):
                e=self.checked(name=kind,values={'InputBit':initial});self.step(e)
                e.memory.write('T.InputBit',not initial);self.assertTrue(self.step(e));e.enter_run()
                self.assertTrue(e.memory.read('T.OutputBit'));self.assertFalse(self.step(e))
                e.memory.write('T.InputBit',initial);self.step(e);e.memory.write('T.InputBit',not initial)
                self.assertTrue(self.step(e))

    def test_deferred_import_keeps_saved_enables_until_run_entry(self):
        e=self.checked(values={'EnableOut':True,'OutputBit':True},defer=True)
        self.assertTrue(e.memory.read('T.EnableIn'));self.assertTrue(e.memory.read('T.EnableOut'))
        e.enter_run();self.assertFalse(e.memory.read('T.EnableIn'));self.assertTrue(e.memory.read('T.OutputBit'))

    def test_late_fault_restores_edge_and_corrected_retry_pulses_once(self):
        for kind,initial in (('OSRI',False),('OSFI',True)):
            with self.subTest(kind=kind):
                e=self.checked([kind+'(T);','SpeedCommand := 1 / SpeedSetpoint;'],values={'InputBit':initial})
                e.memory.write('SpeedSetpoint',1);self.step(e);e.memory.write('T.InputBit',not initial);e.memory.write('SpeedSetpoint',0)
                before=copy.deepcopy((e.memory.values,e._st_oneshot_edges,e.scan_count,e.time_ms,e.scheduler_description()))
                with self.assertRaisesRegex(ModelError,'zero'):e.step()
                self.assertEqual((e.memory.values,e._st_oneshot_edges,e.scan_count,e.time_ms,e.scheduler_description()),before)
                e.memory.write('SpeedSetpoint',1);self.assertTrue(self.step(e));self.assertFalse(self.step(e))

    def test_first_call_fault_leaves_initialization_unconsumed(self):
        e=self.checked(['OSFI(T);','SpeedCommand := 1 / SpeedSetpoint;'],values={'InputBit':True})
        e.memory.write('SpeedSetpoint',0)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e._st_oneshot_edges,{});e.memory.write('SpeedSetpoint',1);self.assertFalse(self.step(e))
        e.memory.write('T.InputBit',False);self.assertTrue(self.step(e))

    def test_scan_and_prescan_budget_failures_restore_values_and_history(self):
        e=self.checked(['OSRI(T);','SpeedCommand := 7;']);self.step(e);e.memory.write('T.InputBit',True)
        before=copy.deepcopy((e.memory.values,e._st_oneshot_edges));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual((e.memory.values,e._st_oneshot_edges),before)
        e.instruction_limit=100;self.assertTrue(self.step(e));before=copy.deepcopy((e.memory.values,e._st_oneshot_edges,e.prescan_count))
        e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan.*budget'):e.enter_run()
        self.assertEqual((e.memory.values,e._st_oneshot_edges,e.prescan_count),before)

    def test_alias_and_program_local_references_share_history(self):
        def mutate(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="T"]');tags.remove(tag)
            root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='AliasT',TagType='Alias',AliasFor='Program:MainProgram.T')
        e=self.checked(['OSRI(AliasT);'],mutate=mutate);e.step();e.memory.write('Program:MainProgram.T.InputBit',True);e.step()
        self.assertTrue(e.memory.read('Program:MainProgram.T.OutputBit'));e.step();self.assertFalse(e.memory.read('Program:MainProgram.T.OutputBit'))

    def test_array_elements_keep_independent_edges(self):
        def mutate(root):
            t=root.find('./Controller/Tags/Tag[@Name="T"]');data=t.find('Data');item=copy.deepcopy(data[0])
            data.clear();data.set('Format','Decorated');t.set('Dimensions','2')
            a=E.SubElement(data,'Array',DataType='FBD_ONESHOT',Dimensions='2')
            for i in range(2):E.SubElement(a,'Element',Index=f'[{i}]').append(copy.deepcopy(item))
        e=self.checked(['OSRI(T[0]);','OSRI(T[1]);'],mutate=mutate);e.step();e.memory.write('T[1].InputBit',True);e.step()
        self.assertFalse(e.memory.read('T[0].OutputBit'));self.assertTrue(e.memory.read('T[1].OutputBit'))

    def test_nested_udt_members_have_builtin_bool_types(self):
        def mutate(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='HolderType',Class='User',Family='NoFamily'),'Members')
            E.SubElement(m,'Member',Name='Edge',DataType='FBD_ONESHOT',Dimension='0')
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Holder',DataType='HolderType',TagType='Base')
            data=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='HolderType')
            item=copy.deepcopy(root.find('./Controller/Tags/Tag[@Name="T"]/Data/Structure'));item.tag='StructureMember';item.set('Name','Edge');data.append(item)
        e=self.checked(['OSRI(Holder.Edge);'],mutate=mutate);e.step();e.memory.write('Holder.Edge.InputBit',True);e.step()
        self.assertTrue(e.memory.read('Holder.Edge.OutputBit'));self.assertEqual(e.memory.resolve('Holder.Edge.OutputBit')[2],'BOOL')

    def test_aoi_inout_binding_uses_resolved_record_history(self):
        def mutate(root):
            definitions=root.find('./Controller/AddOnInstructionDefinitions')
            if definitions is None:definitions=E.SubElement(root.find('Controller'),'AddOnInstructionDefinitions')
            d=E.SubElement(definitions,'AddOnInstructionDefinition',Name='EdgeBlock',Class='Standard',Revision='1.0',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            p=E.SubElement(d,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):
                E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            E.SubElement(p,'Parameter',Name='Edge',TagType='Base',DataType='FBD_ONESHOT',Usage='InOut',Required='true',Visible='true')
            E.SubElement(d,'LocalTags');logic(E.SubElement(E.SubElement(d,'Routines'),'Routine',Name='Logic',Type='ST'),['OSRI(Edge);'])
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='EdgeBlock',TagType='Base')
            data=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='EdgeBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(data,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['EdgeBlock(Instance,T);'],mutate=mutate);self.step(e);e.memory.write('T.InputBit',True)
        self.assertTrue(self.step(e));self.assertFalse(self.step(e))

    def test_periodic_and_routine_harness_use_reached_call_edges(self):
        def mutate(root):t=root.find('./Controller/Tasks/Task');t.set('Type','PERIODIC');t.set('Rate','10')
        e=self.checked(mutate=mutate);self.step(e);e.memory.write('T.InputBit',True);self.assertTrue(self.step(e))
        harness=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(harness.blockers,[])
        self.step(harness);harness.memory.write('T.InputBit',True);self.assertTrue(self.step(harness))

    def test_for_bounds_cannot_depend_on_a_record_written_by_the_call(self):
        self.assertTrue(self.engine(['FOR DisplayedPartCount := 0 TO T.OutputBit DO OSRI(T); END_FOR;']).blockers)

    def test_wrong_arity_types_constants_and_profiles_are_blocked(self):
        for line in ('OSRI();','OSFI(T,U);','OSRI(Parts);','OSFI(T.OutputBit);','OSRI(3);','RES(T);'):
            self.assertTrue(self.engine([line]).blockers,line)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="T"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        for processor,version in (('1756-L75','35'),('1756-L85E','34')):
            def profile(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',version)
            self.assertTrue(self.engine(mutate=profile).blockers)

    def test_ladder_oneshot_record_forms_remain_blocked(self):
        def mutate(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');logic(routine,[]);routine.set('Type','RLL')
            routine.remove(routine.find('STContent'))
            E.SubElement(E.SubElement(E.SubElement(routine,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='OSRI(T);'
        self.assertTrue(self.engine(mutate=mutate).blockers)

    def test_redefined_builtin_schema_is_rejected(self):
        def mutate(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_ONESHOT',Class='User',Family='NoFamily'),'Members')
            E.SubElement(m,'Member',Name='InputBit',DataType='BOOL',Dimension='0')
        self.assertTrue(self.engine(mutate=mutate).blockers)

    def test_builtin_classification_and_instruction_counts_are_explicit(self):
        e=self.checked();self.assertNotIn('FBD_ONESHOT',e.project.data_only_types);self.assertNotIn('fbd_oneshot',e.project.udts)
        self.assertEqual(set(e.memory.read('T')),set(FIELDS));self.assertEqual(e.memory.resolve('T.OutputBit')[2],'BOOL')
        self.assertEqual(len(ARITIES),99);self.assertEqual(set(ST_ONLY_ARITIES),{'TONR','TOFR','RTOR','CTUD','OSRI','OSFI'})

    def test_report_qualifies_pulses_initialization_skips_and_rollback(self):
        profile=self.checked().report()['st_oneshot'];self.assertEqual(profile['instructions'],['OSFI','OSRI'])
        self.assertFalse(profile['native_runtime_parity']);self.assertEqual(profile['language'],'ST')
        self.assertIn('Retain outputs',profile['skipped_calls']);self.assertIn('complete advance',profile['rollback'])

    def test_pulse_lab_has_public_outputs_and_counts_each_reached_edge_once(self):
        from logixlab.server import SAMPLES as names
        self.assertIn('PulseLab',names);e=Engine(Project(SAMPLES/'PulseLab.L5X'));self.assertEqual(e.blockers,[])
        e.step();e.memory.write('Input',True);e.step()
        self.assertTrue(e.memory.read('RisingOutput'));self.assertEqual(e.memory.read('RisingPulses'),1)
        e.memory.write('CallEdges',False);e.step();self.assertTrue(e.memory.read('RisingOutput'))
        self.assertEqual(e.memory.read('RisingPulses'),1);e.memory.write('CallEdges',True);e.step()
        self.assertFalse(e.memory.read('RisingOutput'));e.memory.write('Input',False);e.step()
        self.assertTrue(e.memory.read('FallingOutput'));self.assertEqual(e.memory.read('FallingPulses'),1)

    def test_detached_routine_replacement_preserves_history_and_original_values(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def mutate(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0]
            main.set('Type','RLL');main.remove(main.find('STContent'))
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(EdgeLogic,0);'
            logic(E.SubElement(routines,'Routine',Name='EdgeLogic',Type='ST'),['OSRI(T);'])
        e=self.checked(mutate=mutate);self.step(e);e.memory.write('T.InputBit',True);self.assertTrue(self.step(e))
        before=copy.deepcopy((e.memory.values,e._st_oneshot_edges))
        neutral=['JSR(EdgeLogic,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        source=decode(container(E.tostring(xml,encoding='utf-8')));candidate,_=prepare(e,source,tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e._st_oneshot_edges),before);self.assertEqual(candidate._st_oneshot_edges,e._st_oneshot_edges)
        self.assertIsNot(candidate._st_oneshot_edges,e._st_oneshot_edges);candidate.step();self.assertFalse(candidate.memory.read('T.OutputBit'))
        self.assertEqual((e.memory.values,e._st_oneshot_edges),before)


if __name__=='__main__':unittest.main()
