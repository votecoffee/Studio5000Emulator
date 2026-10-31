"""Enhanced selection, wired requests and derivative history in FBD graphs."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine
from test_st_timers import logic

SAMPLE=Path(__file__).resolve().parents[1]/'samples/FBDProcessLab.L5X'


class FBDProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="SelectAndDifferentiate"]/FBDContent/Sheet')

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        p=Path(self.tmp.name)/'process.L5X';E.ElementTree(root).write(p,encoding='utf8',xml_declaration=True)
        return Engine(Project(p),mode,'MainProgram/SelectAndDifferentiate' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def unknown(e,ref):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,None)

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    @staticmethod
    def settings(e,**values):
        for tag,value in values.items():e.memory.write(tag,value)

    def step(self,e,dt=10):
        e.step(dt);return tuple(e.memory.read(t) for t in ('Selected','SelectedInput','Derivative','ProgramControl'))

    def test_high_low_selection_feeds_downstream_derivative(self):
        e=self.checked();self.assertEqual(self.step(e),(30,3,0,False))
        e.memory.write('Input3',40);self.assertEqual(self.step(e),(40,3,40,False))
        e.memory.write('SelectionMode',2);self.assertEqual(self.step(e),(10,1,-120,False))

    def test_faulted_unknown_and_unused_inputs_are_not_read_as_zero(self):
        e=self.checked();self.settings(e,Fault3=True);self.unknown(e,'Input3')
        self.assertEqual(self.step(e)[:2],(20,2));self.settings(e,InputsUsed=1)
        self.unknown(e,'Fault2');self.assertEqual(self.step(e)[:2],(10,1))

    def test_median_and_ties_select_first_original_matching_input(self):
        e=self.checked();self.settings(e,SelectionMode=3,InputsUsed=4,Input1=10,Input2=3,Input3=20)
        e.memory.write('Selector.In4',7);self.assertEqual(self.step(e)[:2],(10,1))
        self.settings(e,SelectionMode=1,Input1=30,Input2=30,Input3=30);self.assertEqual(self.step(e)[:2],(30,1))

    def test_mean_uses_healthy_prefix_and_reports_zero_selected_index(self):
        e=self.checked();self.settings(e,SelectionMode=4,Fault2=True)
        self.assertEqual(self.step(e)[:2],(20,0));self.settings(e,Fault1=True);self.assertEqual(self.step(e)[:2],(30,0))

    def test_all_faulted_holds_visible_output_and_derivative_observes_that_value(self):
        e=self.checked();self.step(e);self.settings(e,Fault1=True,Fault2=True,Fault3=True)
        self.settings(e,**{'Selector.Out':77,'Selector.SelectedIn':5})
        self.assertEqual(self.step(e)[:3],(77,5,188));self.assertEqual(e.memory.read('SelectionStatus'),3)
        self.assertTrue(e.memory.read('AllInputsFaulted'));self.settings(e,Fault2=False)
        self.assertEqual(self.step(e)[:2],(20,2));self.assertFalse(e.memory.read('SelectionFault'))

    def test_manual_selector_zero_holds_output_and_selection(self):
        e=self.checked();self.settings(e,SelectionMode=0,OperatorSelection=2)
        self.assertEqual(self.step(e)[:2],(20,2));self.settings(e,OperatorSelection=0,Input2=90)
        self.assertEqual(self.step(e)[:3],(20,2,0))

    def test_manual_ignores_health_and_count_but_reports_invalid_count(self):
        e=self.checked();self.settings(e,SelectionMode=0,OperatorSelection=6,InputsUsed=0)
        e.memory.write('Selector.In6Fault',True);self.assertEqual(self.step(e)[:2],(60,6))
        self.assertTrue(e.memory.read('InputCountInvalid'));self.assertEqual(e.memory.read('SelectionStatus'),5)

    def test_program_operator_priority_and_wired_operator_request_consumption(self):
        e=self.checked();self.settings(e,SelectionMode=0,ProgramRequest=True,OperatorRequest=True)
        self.assertFalse(self.step(e)[3]);self.settings(e,OperatorRequest=False,RequestOperator=True)
        self.assertTrue(self.step(e)[3]);self.assertFalse(e.memory.read('Selector.OperOperReq'))
        self.settings(e,ProgramRequest=False);self.assertFalse(self.step(e)[3])

    def test_program_value_reset_clears_record_requests_but_not_source_tags(self):
        e=self.checked();self.settings(e,SelectionMode=0,ProgramRequest=True,ResetRequests=True,RequestOperator=True)
        for _ in range(2):
            self.assertTrue(self.step(e)[3]);self.assertFalse(e.memory.read('Selector.ProgProgReq'))
            self.assertTrue(e.memory.read('ProgramRequest'));self.assertTrue(e.memory.read('RequestOperator'))

    def test_two_wired_operator_requests_are_reapplied_and_switch_each_call(self):
        e=self.checked();self.settings(e,SelectionMode=0,RequestProgram=True,RequestOperator=True)
        self.assertTrue(self.step(e)[3]);self.assertFalse(self.step(e)[3]);self.assertTrue(self.step(e)[3])
        self.assertFalse(e.memory.read('Selector.OperProgReq'));self.assertFalse(e.memory.read('Selector.OperOperReq'))

    def test_unwired_operator_request_is_consumed_only_once(self):
        def unwire(root):
            sheet=self.sheet(root)
            for pin in ('OperProgReq','OperOperReq'):sheet.remove(sheet.find(f'Wire[@ToID="100"][@ToParam="{pin}"]'))
        e=self.checked(unwire);e.memory.write('Selector.OperProgReq',True)
        self.assertTrue(self.step(e)[3]);self.assertTrue(self.step(e)[3]);self.assertFalse(e.memory.read('Selector.OperProgReq'))

    def test_override_uses_manual_pick_but_invalid_mode_still_holds(self):
        e=self.checked();self.settings(e,ForceManual=True,OperatorSelection=2)
        self.assertEqual(self.step(e)[:2],(20,2));self.assertTrue(e.memory.read('OverrideActive'))
        self.settings(e,SelectionMode=9,Input2=80);self.assertEqual(self.step(e)[:2],(20,2));self.assertTrue(e.memory.read('ModeInvalid'))

    def test_derivative_startup_bypass_signed_gain_and_recovery(self):
        e=self.checked();self.settings(e,Bypass=True);self.assertEqual(self.step(e)[2],30)
        self.settings(e,Bypass=False,Input3=40,Gain=-2);self.assertEqual(self.step(e)[2],-80)
        self.settings(e,Bypass=True,Input3=50);self.assertEqual(self.step(e)[2],50)
        self.settings(e,Bypass=False,Input3=60);self.assertEqual(self.step(e)[2],-80)

    def test_zero_invalid_intervals_sample_current_input_for_next_recovery(self):
        e=self.checked();self.step(e);self.settings(e,SampleTime=0,Input3=40)
        self.assertEqual(self.step(e)[2],0);self.assertFalse(e.memory.read('DerivativeFault'))
        self.settings(e,SampleTime=-1,Input3=50);self.assertEqual(self.step(e)[2],0)
        self.assertEqual(e.memory.read('DerivativeStatus'),-2147483647);self.assertTrue(e.memory.read('SampleInvalid'))
        self.settings(e,SampleTime=.25,Input3=60);self.assertEqual(self.step(e)[2],40);self.assertFalse(e.memory.read('DerivativeFault'))

    def test_rts_fault_restores_earlier_selection_and_consumed_requests(self):
        e=self.checked();self.step(e);self.settings(e,TimingMode=2,Input3=40,RequestProgram=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'real time sampling'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,TimingMode=1);self.assertEqual(self.step(e),(40,3,40,True))

    def test_gain_unknown_is_only_required_for_actual_derivative_calculation(self):
        e=self.checked();self.unknown(e,'Gain');self.assertEqual(self.step(e)[2],0)
        self.settings(e,Bypass=True);self.assertEqual(self.step(e)[2],30)
        self.settings(e,Bypass=False,SampleTime=0);self.assertEqual(self.step(e)[2],30)
        self.settings(e,SampleTime=.25);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'DERV Gain'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_disabled_first_call_seeds_no_history_and_skips_unknown_rts_inputs(self):
        e=self.checked();self.settings(e,BlockEnable=False,TimingMode=2,RequestProgram=True)
        for tag in ('Input1','Input2','Input3','Gain'):self.unknown(e,tag)
        self.assertEqual(self.step(e),(0,0,0,False));self.assertEqual(e.last_timer,{})
        self.assertTrue(e.memory.read('Selector.OperProgReq'));self.assertFalse(e.memory.read('Selector.EnableOut'))

    def test_skipped_and_disabled_blocks_preserve_requests_and_derivative_history(self):
        e=self.checked();self.step(e);history=copy.deepcopy(e.last_timer)
        self.settings(e,BlockEnable=False,RequestProgram=True,Input3=40);self.assertEqual(self.step(e)[0],30)
        self.assertEqual(e.last_timer,history);self.assertTrue(e.memory.read('Selector.OperProgReq'))
        self.settings(e,BlockEnable=True,ExecuteGraph=False);self.step(e);self.assertEqual(e.last_timer,history)
        self.settings(e,ExecuteGraph=True);self.assertEqual(self.step(e),(40,3,40,True))

    def test_continuous_disable_gap_uses_last_reached_input_and_elapsed_time(self):
        e=self.checked();self.settings(e,TimingMode=0);self.step(e)
        self.settings(e,BlockEnable=False,Input3=50);self.step(e,40)
        self.settings(e,BlockEnable=True);v=self.step(e);self.assertAlmostEqual(v[2],400,places=4)
        self.assertAlmostEqual(e.memory.read('Elapsed'),.05,places=7)

    def test_direct_derivative_output_writes_do_not_replace_hidden_hold(self):
        e=self.checked();self.step(e);self.settings(e,Input3=40);self.assertEqual(self.step(e)[2],40)
        self.settings(e,SampleTime=0,Input3=50,**{'Slope.Out':999});self.assertEqual(self.step(e)[2],40)
        self.settings(e,SampleTime=.25,Input3=60);self.assertEqual(self.step(e)[2],40)

    def test_status_bool_wire_can_enable_derivative_on_selection_failure(self):
        def gate(root):
            w=self.sheet(root).find('Wire[@ToID="200"][@ToParam="EnableIn"]');w.set('FromID','100');w.set('FromParam','InsFaulted')
        e=self.checked(gate);self.step(e);self.assertFalse(e.memory.read('Slope.EnableOut'));self.assertEqual(len(e.last_timer),1)
        self.settings(e,Fault1=True,Fault2=True,Fault3=True);self.assertEqual(self.step(e)[2],0)
        e.memory.write('Selector.Out',60);self.assertEqual(self.step(e)[2],120)

    def test_unknown_required_health_never_becomes_healthy(self):
        e=self.checked();self.unknown(e,'Fault1');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'In1Fault is unknown'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_partial_saved_input_retains_unknown_instead_of_shape_default(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="Selector"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="In4"]'))
        e=self.checked(missing);self.settings(e,InputsUsed=4)
        with self.assertRaisesRegex(ModelError,'In4 is unknown'):self.step(e)

    def test_late_ladder_fault_restores_control_input_sample_and_request_resets(self):
        e=self.checked();self.step(e);self.settings(e,RequestProgram=True,Input3=40,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,FaultDivisor=1,Input3=50)
        self.assertEqual(self.step(e),(50,3,80,True))

    def test_late_unknown_gain_restores_earlier_selector_changes(self):
        e=self.checked();self.step(e);self.settings(e,RequestProgram=True,Input3=40);self.unknown(e,'Gain');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'DERV Gain'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,Gain=1);self.assertEqual(self.step(e),(40,3,40,True))

    def test_run_resets_control_and_derivative_but_preserves_visible_values_until_call(self):
        e=self.checked();self.settings(e,RequestProgram=True);self.step(e);self.settings(e,RequestProgram=False,Input3=40);self.step(e)
        e.enter_run();self.assertEqual(e.last_timer,{});self.assertTrue(e.memory.read('ProgramControl'))
        self.assertEqual(self.step(e),(40,3,0,False))

    def test_periodic_harness_and_unwired_enable_profiles(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','Periodic');t.set('Rate','10')
        e=self.checked(periodic);self.settings(e,TimingMode=0);self.step(e);self.settings(e,Input3=40)
        self.assertAlmostEqual(self.step(e)[2],1000,places=3)
        e=self.checked(mode='routine',defer=True);e.enter_run();self.assertFalse(e.memory.read('Selector.EnableIn'));self.assertEqual(self.step(e)[:3],(30,3,0))
        def unwire(root):
            sheet=self.sheet(root)
            for w in list(sheet.findall('Wire')):
                if w.get('ToParam')=='EnableIn':sheet.remove(w)
        e=self.checked(unwire);self.settings(e,BlockEnable=False);self.assertEqual(self.step(e)[:3],(30,3,0))

    def test_st_fbd_share_derivative_history_and_ownership(self):
        def st(root):logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(SelectAndDifferentiate,0); ESEL(Selector); DERV(Slope);'])
        e=self.checked(st);self.step(e);self.settings(e,Input3=40,RequestProgram=True)
        self.assertEqual(self.step(e),(40,3,40,True));self.assertEqual(e.memory.read('Slope.Out'),0);self.assertEqual(len(e.last_timer),2)

    def event_engine(self,fault=False):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(SelectAndDifferentiate,0); EVENT(ProcessEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='MainRoutine' if fault else 'SelectAndDifferentiate',Class='Standard',Disabled='false');E.SubElement(p,'Tags');rs=E.SubElement(p,'Routines')
            if fault:logic(E.SubElement(rs,'Routine',Name='MainRoutine',Type='ST'),['GuardResult:=1/FaultDivisor;'])
            else:rs.append(copy.deepcopy(root.find('.//Routine[@Name="SelectAndDifferentiate"]')))
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='ProcessEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        return self.checked(event)

    def test_event_calls_share_zero_elapsed_timestamp_and_reapply_request_wires(self):
        e=self.event_engine();self.settings(e,TimingMode=0,RequestProgram=True,RequestOperator=True)
        self.assertFalse(self.step(e)[3]);self.settings(e,Input3=40)
        v=self.step(e);self.assertAlmostEqual(v[2],1000,places=3);self.assertFalse(v[3]);self.assertEqual(e.memory.read('Elapsed'),0)

    def test_event_late_fault_restores_selection_and_derivative_state(self):
        e=self.event_engine(True);self.step(e);self.settings(e,Input3=40,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,FaultDivisor=1);self.assertEqual(self.step(e)[:3],(40,3,40))

    def test_nested_derivative_and_program_local_selector_alias(self):
        def nested(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="Selector"]');tags.remove(tag);root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='LocalSelector',TagType='Alias',AliasFor='Program:MainProgram.Selector');self.sheet(root).find('Block[@Type="ESEL"]').set('Operand','LocalSelector')
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='SlopeCell',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Rate',DataType='DERIVATIVE',Dimension='0')
            tag=tags.find('Tag[@Name="Slope"]');structure=tag.find('Data/Structure');tags.remove(tag)
            arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='SlopeCell',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='SlopeCell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='SlopeCell');item=copy.deepcopy(structure);item.tag='StructureMember';item.set('Name','Rate');obj.append(item)
            self.sheet(root).find('Block[@Type="DERV"]').set('Operand','Cells[1].Rate')
        e=self.checked(nested);self.step(e);self.settings(e,Input3=40);self.assertEqual(self.step(e)[:3],(40,3,40));self.assertEqual(e.memory.read('Cells[0].Rate.Out'),0)

    def test_profile_constant_record_redefinition_pin_direction_and_function_guards(self):
        for kind in ('profile','constant','record','redefined','wiretype','output','aliasinput','function'):
            def mutate(root):
                sheet=self.sheet(root)
                if kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                elif kind=='constant':root.find('./Controller/Tags/Tag[@Name="Selector"]').set('Constant','true')
                elif kind=='record':sheet.find('Block[@Type="DERV"]').set('Operand','Selector')
                elif kind=='redefined':
                    m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='SELECT_ENHANCED',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
                elif kind=='wiretype':sheet.find('IRef[@ID="1"]').set('Operand','SelectionMode')
                elif kind=='output':sheet.find('Wire[@ToID="100"]').set('ToParam','Out')
                elif kind=='aliasinput':sheet.find('Wire[@ToID="100"]').set('ToParam','InsFaulted')
                else:sheet.find('Block').tag='Function'
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def test_instruction_budget_rolls_back_wires_requests_and_control(self):
        e=self.checked();e.instruction_limit=25;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_detached_rll_replacement_preserves_control_and_derivative_samples(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();self.step(e);self.settings(e,RequestProgram=True,Input3=40);self.step(e);before=self.snapshot(e)
        texts=['JSR(SelectAndDifferentiate,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(texts):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(texts),'MainProgram',0)
        self.assertEqual(self.snapshot(e),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.settings(candidate,Input3=50);self.assertEqual(self.step(candidate),(50,3,40,True))
        self.assertTrue(all(candidate.project.instruction_counts[n]==1 for n in ('ESEL','DERV')))

    def test_report_has_forty_blocks_and_process_diagnostic_pins(self):
        e=self.checked();p=e.report()['function_blocks'];self.assertEqual(len(p['instructions']),40)
        self.assertEqual(p['blocks']['status_aliases']['SELECT_ENHANCED']['InsFaulted'],'Status.1')
        self.assertEqual(p['blocks']['status_aliases']['DERIVATIVE']['DeltaTInv'],'Status.31')
        self.assertIn('reapplied',p['blocks']['requests']);self.assertFalse(p['native_runtime_parity'])


if __name__=='__main__':unittest.main()
