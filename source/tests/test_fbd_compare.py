"""Finite comparisons/limits, BOOL dataflow and mixed stateless/stateful rollback."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.fbd_compare import SCHEMAS,default
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from test_st_timers import logic

SAMPLE=Path(__file__).resolve().parents[1]/'samples/FBDCompareLab.L5X'
RECORDS=('EqualState','NotEqualState','GreaterState','GreaterEqualState','LessState','LessEqualState','RangeState')


class FBDCompareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="CompareSignals"]/FBDContent/Sheet')

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        p=Path(self.tmp.name)/'compare.L5X';E.ElementTree(root).write(p,encoding='utf8',xml_declaration=True)
        return Engine(Project(p),mode,'MainProgram/CompareSignals' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def settings(e,**values):
        for tag,value in values.items():e.memory.write(tag,value)

    @staticmethod
    def unknown(e,ref):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,None)

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def step(self,e):
        e.step(10);return tuple(e.memory.read(t) for t in ('Equal','NotEqual','Greater','GreaterEqual','Less','LessEqual','InRange'))

    def test_all_six_comparison_relations(self):
        e=self.checked()
        for a,b,expected in ((1,2,(False,True,False,False,True,True)),(2,2,(True,False,False,True,False,True)),(3,2,(False,True,True,True,False,False))):
            self.settings(e,A=a,B=b);self.assertEqual(self.step(e)[:6],expected)

    def test_negative_operands_preserve_source_order(self):
        e=self.checked();self.settings(e,A=-3,B=-2);self.assertEqual(self.step(e)[:6],(False,True,False,False,True,True))
        self.settings(e,A=-1);self.assertEqual(self.step(e)[:6],(False,True,True,True,False,False))

    def test_results_and_member_types_are_bool_not_integer_or_real(self):
        e=self.checked();v=self.step(e);self.assertTrue(all(type(x) is bool for x in v))
        for tag,dtype in (('EqualState','FBD_COMPARE'),('RangeState','FBD_LIMIT')):
            self.assertNotIn(dtype,e.project.data_only_types)
            for member,kind in SCHEMAS[dtype].items():self.assertEqual(e.memory.resolve(tag+'.'+member)[2],kind)
            self.assertTrue(default(dtype)['EnableIn']);self.assertFalse(default(dtype)['Dest'])
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(101,27))

    def test_ascending_limits_include_both_boundaries(self):
        e=self.checked();self.settings(e,LowLimit=0,HighLimit=10)
        for a,expected in ((-1,False),(0,True),(1,True),(10,True),(11,False)):
            self.settings(e,A=a);self.assertIs(self.step(e)[6],expected)

    def test_reversed_limits_accept_outside_and_both_boundaries(self):
        e=self.checked();self.settings(e,LowLimit=10,HighLimit=0)
        for a,expected in ((-1,True),(0,True),(1,False),(9,False),(10,True),(11,True)):
            self.settings(e,A=a);self.assertIs(self.step(e)[6],expected)

    def test_equal_limits_accept_exact_value_only(self):
        e=self.checked();self.settings(e,LowLimit=5,HighLimit=5)
        for a,expected in ((4,False),(5,True),(6,False)):
            self.settings(e,A=a);self.assertIs(self.step(e)[6],expected)

    def test_comparison_uses_float32_values_without_tolerance(self):
        e=self.checked();self.settings(e,A=16777216,B=16777217)
        self.assertEqual(self.step(e)[:6],(True,False,False,True,False,True))
        self.settings(e,A=1,B=1.0000001192092896);self.assertFalse(self.step(e)[0])

    def test_positive_and_negative_zero_compare_equal(self):
        e=self.checked();self.settings(e,A=0.0,B=-0.0,LowLimit=-0.0,HighLimit=0.0)
        self.assertEqual(self.step(e),(True,False,False,True,False,True,True))

    def test_limit_reads_all_required_inputs_without_short_circuit_inference(self):
        e=self.checked();self.settings(e,A=-100,LowLimit=0);self.unknown(e,'HighLimit');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'LIM HighLimit is unknown'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_unknown_compare_operands_never_become_false_or_true(self):
        for tag in ('A','B'):
            e=self.checked();self.unknown(e,tag);before=self.snapshot(e)
            with self.subTest(tag=tag),self.assertRaisesRegex(ModelError,'unknown'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_nonfinite_inputs_are_explicitly_excluded_for_every_comparison(self):
        for ident,tag in enumerate(RECORDS[:6],1):
            def unwire(root):
                sheet=self.sheet(root);sheet.remove(sheet.find(f'Wire[@ToID="{ident*100}"][@ToParam="SourceA"]'))
            for value in (float('nan'),float('inf'),float('-inf')):
                e=self.checked(unwire);key,parts,_=e.memory.resolve(tag+'.SourceA');e.memory.store(key,parts,value)
                with self.subTest(tag=tag,value=value),self.assertRaisesRegex(ModelError,'finite REAL'):self.step(e)
                self.assertIs(e.memory.at(key,parts),value);self.assertEqual(e.scan_count,0)

    def test_bool_or_string_corruption_is_rejected_at_unwired_record_input(self):
        def unwire(root):
            sheet=self.sheet(root);sheet.remove(sheet.find('Wire[@ToID="100"][@ToParam="SourceA"]'))
        for value in (True,'1'):
            e=self.checked(unwire);key,parts,_=e.memory.resolve('EqualState.SourceA');e.memory.store(key,parts,value)
            with self.assertRaisesRegex(ModelError,'not REAL'):self.step(e)

    def test_bool_comparison_drives_real_selector(self):
        e=self.checked();self.step(e);self.assertEqual(e.memory.read('SelectedValue'),100)
        self.settings(e,A=1);self.step(e);self.assertEqual(e.memory.read('SelectedValue'),0)
        self.settings(e,A=2);self.step(e);self.assertEqual(e.memory.read('SelectedValue'),0)

    def test_in_range_bool_drives_timer_and_out_of_range_resets(self):
        e=self.checked();self.step(e);self.assertEqual(e.memory.read('TimerACC'),0)
        self.step(e);self.assertEqual(e.memory.read('TimerACC'),10);self.assertFalse(e.memory.read('TimerDone'))
        self.step(e);self.assertEqual(e.memory.read('TimerACC'),20);self.assertTrue(e.memory.read('TimerDone'))
        self.settings(e,A=11);self.step(e);self.assertEqual(e.memory.read('TimerACC'),0);self.assertFalse(e.memory.read('TimerDone'))

    def test_timer_reset_is_separate_from_comparison_truth(self):
        e=self.checked();self.step(e);self.step(e);self.settings(e,ResetTimer=True)
        self.assertTrue(self.step(e)[6]);self.assertEqual(e.memory.read('TimerACC'),0)

    def test_disabled_blocks_hold_destinations_and_skip_unknown_inputs(self):
        e=self.checked();expected=self.step(e);history=copy.deepcopy(e.last_timer);self.settings(e,BlockEnable=False)
        for tag in ('A','B','LowLimit','HighLimit'):self.unknown(e,tag)
        self.assertEqual(self.step(e),expected);self.assertEqual(e.last_timer,history);self.assertFalse(e.memory.read('CompareEnabled'))

    def test_unknown_enable_rolls_back_without_selecting_a_value(self):
        e=self.checked();self.unknown(e,'BlockEnable');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'EnableIn is unknown'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_skipped_graph_holds_flags_and_timer_history_until_resumed(self):
        e=self.checked();expected=self.step(e);history=copy.deepcopy(e.last_timer)
        self.settings(e,ExecuteGraph=False,A=11);self.assertEqual(self.step(e),expected);self.assertEqual(e.last_timer,history)
        self.settings(e,ExecuteGraph=True);self.assertFalse(self.step(e)[6]);self.assertEqual(e.memory.read('TimerACC'),0)

    def test_unwired_compare_enables_execute_despite_saved_false(self):
        def unwire(root):
            sheet=self.sheet(root)
            for wire in list(sheet.findall('Wire')):
                if wire.get('ToParam')=='EnableIn' and int(wire.get('ToID'))<=700:sheet.remove(wire)
        e=self.checked(unwire);self.settings(e,BlockEnable=False)
        for tag in RECORDS:e.memory.write(tag+'.EnableIn',False)
        self.assertEqual(self.step(e),(False,True,True,True,False,False,True));self.assertTrue(e.memory.read('CompareEnabled'))

    def test_prescan_retains_comparison_values_but_clears_timer_selector_enables(self):
        def saved(root):
            for tag in RECORDS:
                obj=root.find(f'./Controller/Tags/Tag[@Name="{tag}"]/Data/Structure')
                for member in ('EnableOut','Dest'):obj.find(f'DataValueMember[@Name="{member}"]').set('Value','1')
        e=self.checked(saved)
        for tag in RECORDS:self.assertTrue(e.memory.read(tag+'.EnableOut'));self.assertTrue(e.memory.read(tag+'.Dest'))
        self.assertFalse(e.memory.read('Choice.EnableOut'));self.assertFalse(e.memory.read('OnDelay.EnableOut'))
        self.step(e);e.enter_run();self.assertTrue(e.memory.read('GreaterState.EnableOut'));self.assertTrue(e.memory.read('GreaterState.Dest'))
        self.assertFalse(e.memory.read('Choice.EnableOut'));self.assertEqual(e.last_timer,{})

    def test_direct_comparison_dest_write_holds_disabled_then_recomputes(self):
        e=self.checked();self.step(e);self.settings(e,BlockEnable=False,**{'EqualState.Dest':True})
        self.assertTrue(self.step(e)[0]);self.settings(e,BlockEnable=True);self.assertFalse(self.step(e)[0])

    def test_omitted_saved_input_is_unknown_without_default_substitution(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="EqualState"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="SourceB"]'))
            sheet=self.sheet(root);sheet.remove(sheet.find('Wire[@ToID="100"][@ToParam="SourceB"]'))
        e=self.checked(missing)
        with self.assertRaisesRegex(ModelError,'EQU SourceB is unknown'):self.step(e)

    def test_late_unknown_limit_restores_earlier_flags_and_timer_state(self):
        e=self.checked();self.step(e);self.settings(e,A=1);self.unknown(e,'HighLimit');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'LIM HighLimit'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,HighLimit=10);self.assertTrue(self.step(e)[4])

    def test_late_ladder_fault_restores_timer_elapsed_and_all_comparisons(self):
        e=self.checked();self.step(e);self.settings(e,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,FaultDivisor=1)
        self.step(e);self.assertEqual(e.memory.read('TimerACC'),10)

    def test_run_resets_stateful_history_but_comparisons_have_no_hidden_state(self):
        e=self.checked();self.step(e);self.step(e);self.assertEqual(len(e.last_timer),2)
        e.enter_run();self.assertEqual(e.last_timer,{})
        self.assertTrue(e.memory.read('RangeState.Dest'));self.assertEqual(self.step(e)[:6],(False,True,True,True,False,False))

    def test_periodic_and_harness_profiles(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','Periodic');t.set('Rate','10')
        self.assertTrue(self.step(self.checked(periodic))[6])
        e=self.checked(mode='routine',defer=True);e.enter_run();self.assertTrue(e.memory.read('EqualState.EnableIn'));self.assertTrue(self.step(e)[6])

    def test_record_call_overloads_and_tagless_functions_remain_blocked(self):
        for language in ('ST','RLL'):
            def wrong(root):
                routine=root.find('.//Routine[@Name="MainRoutine"]')
                if language=='ST':logic(routine,['EQU(EqualState);'])
                else:routine.find('RLLContent/Rung/Text').text='EQU(EqualState);'
            with self.subTest(language=language):self.assertTrue(self.engine(wrong).blockers)
        def function(root):self.sheet(root).find('Block').tag='Function'
        self.assertTrue(self.engine(function).blockers)

    def test_local_comparison_alias_and_nested_limit_record(self):
        def nested(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="GreaterState"]');tags.remove(tag);root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='LocalGreater',TagType='Alias',AliasFor='Program:MainProgram.GreaterState');self.sheet(root).find('Block[@Type="GRT"]').set('Operand','LocalGreater')
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='RangeCell',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Range',DataType='FBD_LIMIT',Dimension='0')
            tag=tags.find('Tag[@Name="RangeState"]');structure=tag.find('Data/Structure');tags.remove(tag)
            arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='RangeCell',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='RangeCell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='RangeCell');item=copy.deepcopy(structure);item.tag='StructureMember';item.set('Name','Range');obj.append(item)
            self.sheet(root).find('Block[@Type="LIM"]').set('Operand','Cells[1].Range')
        e=self.checked(nested);self.assertTrue(self.step(e)[6]);self.assertFalse(e.memory.read('Cells[0].Range.Dest'))

    def test_unrelated_limit_prefix_udt_retains_declared_member_types(self):
        def extra(root):
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_LIMIT_CUSTOM',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Value',DataType='DINT',Dimension='0')
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Custom',TagType='Base',DataType='FBD_LIMIT_CUSTOM');obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='FBD_LIMIT_CUSTOM');E.SubElement(obj,'DataValueMember',Name='Value',DataType='DINT',Value='7')
        e=self.checked(extra);self.assertEqual(e.memory.resolve('Custom.Value')[2],'DINT')

    def test_profile_constants_types_redefinition_and_wire_directions_block(self):
        for kind in ('profile','constant','record','redefined','wiretype','output','boolsource'):
            def mutate(root):
                sheet=self.sheet(root)
                if kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                elif kind=='constant':root.find('./Controller/Tags/Tag[@Name="EqualState"]').set('Constant','true')
                elif kind=='record':sheet.find('Block[@Type="EQU"]').set('Operand','RangeState')
                elif kind=='redefined':
                    m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_COMPARE',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Dest',DataType='BOOL',Dimension='0')
                elif kind=='wiretype':sheet.find('IRef[@ID="1"]').set('Operand','TimerPreset')
                elif kind=='output':sheet.find('Wire[@ToID="100"]').set('ToParam','Dest')
                else:wire=sheet.find('Wire[@ToID="100"]');wire.set('FromID','300');wire.set('FromParam','Dest')
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def event_engine(self,fault=False):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(CompareSignals,0); EVENT(CompareEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='MainRoutine' if fault else 'CompareSignals',Class='Standard',Disabled='false');E.SubElement(p,'Tags');rs=E.SubElement(p,'Routines')
            if fault:logic(E.SubElement(rs,'Routine',Name='MainRoutine',Type='ST'),['GuardResult:=1/FaultDivisor;'])
            else:rs.append(copy.deepcopy(root.find('.//Routine[@Name="CompareSignals"]')))
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='CompareEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        return self.checked(event)

    def test_event_calls_share_timer_timestamp_and_bool_outputs(self):
        e=self.event_engine();self.step(e);self.step(e);self.assertEqual(e.memory.read('TimerACC'),10)

    def test_event_failure_restores_earlier_comparison_and_timer_updates(self):
        e=self.event_engine(True);self.step(e);self.settings(e,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_budget_failure_rolls_back_comparisons_and_stateful_consumers(self):
        e=self.checked();e.instruction_limit=25;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_detached_rll_replacement_preserves_flags_timer_and_inventory(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();self.step(e);self.step(e);before=self.snapshot(e)
        texts=['JSR(CompareSignals,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(texts):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(texts),'MainProgram',0)
        self.assertEqual(self.snapshot(e),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.step(candidate);self.assertEqual(candidate.memory.read('TimerACC'),20)
        self.assertTrue(all(candidate.project.instruction_counts[n]==1 for n in ('EQU','NEQ','GRT','GEQ','LES','LEQ','LIM')))

    def test_report_has_forty_six_blocks_and_finite_comparison_contract(self):
        e=self.checked();p=e.report()['function_blocks'];self.assertEqual(len(p['instructions']),46)
        self.assertEqual(p['blocks']['comparison']['instructions'],['EQU','GEQ','GRT','LEQ','LES','LIM','NEQ'])
        self.assertIn('Inclusive',p['blocks']['comparison']['limits']);self.assertFalse(p['blocks']['comparison']['native_runtime_parity'])


if __name__=='__main__':unittest.main()
