"""Shared RLIM/MAXC/MINC models through typed FBD wires and enable gates."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError,Project
from logixlab.runtime import Engine
from test_st_timers import logic

SAMPLE=Path(__file__).resolve().parents[1]/'samples/FBDTrendLab.L5X'


class FBDTrendTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="RampAndCapture"]/FBDContent/Sheet')

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'trends.L5X';E.ElementTree(root).write(path,encoding='utf8',xml_declaration=True)
        return Engine(Project(path),mode,'MainProgram/RampAndCapture' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def unknown(e,ref):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,None)

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    @staticmethod
    def values(e):return tuple(e.memory.read(t) for t in ('Limited','Maximum','Minimum'))

    def step(self,e,dt=10):e.step(dt);return self.values(e)

    def oversample(self,e):
        e.memory.write('TimingMode',1);e.memory.write('SampleTime',0.25);return e

    def test_first_input_initializes_rate_and_both_extrema_without_zero_seed(self):
        e=self.checked();e.memory.write('Signal',-7);self.assertEqual(self.step(e),(-7,-7,-7))
        self.assertEqual(e.memory.read('Elapsed'),0);self.assertEqual(len(e.last_timer),3)

    def test_oversample_rises_falls_and_captures_without_overshooting(self):
        e=self.oversample(self.checked());self.step(e);e.memory.write('Signal',1)
        self.assertEqual(self.step(e),(.5,.5,0));self.assertEqual(self.step(e),(1,1,0))
        self.assertEqual(self.step(e),(1,1,0));e.memory.write('Signal',-1)
        self.assertEqual(self.step(e),(0,1,0));self.assertEqual(self.step(e),(-1,1,-1))

    def test_elapsed_continuous_timing_and_disabled_gap(self):
        e=self.checked();self.step(e);e.memory.write('Signal',10);self.step(e)
        e.memory.write('BlockEnable',False);prior=self.values(e);history=copy.deepcopy(e.last_timer)
        self.assertEqual(self.step(e,40),prior);self.assertEqual(e.last_timer,history)
        e.memory.write('BlockEnable',True);v=self.step(e)
        self.assertAlmostEqual(v[0],.12,places=6);self.assertAlmostEqual(e.memory.read('Elapsed'),.05,places=7)

    def test_disabled_first_call_has_no_history_and_initializes_on_enable(self):
        e=self.checked();e.memory.write('BlockEnable',False);e.memory.write('Signal',-5)
        self.assertEqual(self.step(e),(0,0,0));self.assertEqual(e.last_timer,{})
        e.memory.write('BlockEnable',True);self.assertEqual(self.step(e),(-5,-5,-5))

    def test_disabled_blocks_skip_unknown_inputs_and_unsupported_timing(self):
        e=self.checked();self.step(e);history=copy.deepcopy(e.last_timer);e.memory.write('BlockEnable',False)
        for tag in ('Signal','IncreaseRate','DecreaseRate','Bypass','ResetCapture','MaximumReset','MinimumReset'):self.unknown(e,tag)
        e.memory.write('TimingMode',2);self.assertEqual(self.step(e),(0,0,0));self.assertEqual(e.last_timer,history)
        self.assertTrue(all(not e.memory.read(t+'.EnableOut') for t in ('Ramp','HighCapture','LowCapture')))

    def test_bypass_reseeds_ramp_and_downstream_captures(self):
        e=self.oversample(self.checked());self.step(e);e.memory.write('Signal',5);e.memory.write('Bypass',True)
        self.assertEqual(self.step(e),(5,5,0));e.memory.write('Bypass',False);e.memory.write('Signal',0)
        self.assertEqual(self.step(e),(4,5,0))

    def test_capture_reset_is_level_sensitive_and_retains_new_baselines(self):
        e=self.checked();e.memory.write('ResetCapture',True);self.assertEqual(self.step(e),(0,10,-10))
        e.memory.write('MaximumReset',8);e.memory.write('MinimumReset',-8);self.assertEqual(self.step(e),(0,8,-8))
        e.memory.write('ResetCapture',False);self.assertEqual(self.step(e),(0,8,-8))

    def test_capture_ignores_unknown_unused_reset_values(self):
        e=self.checked();self.unknown(e,'MaximumReset');self.unknown(e,'MinimumReset')
        self.assertEqual(self.step(e),(0,0,0));e.memory.write('ResetCapture',True)
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'ResetValue'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_reset_capture_can_ignore_unknown_input_wire(self):
        def disconnect(root):
            sheet=self.sheet(root)
            for ident in (200,300):
                sheet.remove(sheet.find(f'Wire[@ToID="{ident}"][@ToParam="In"]'))
        e=self.checked(disconnect);self.unknown(e,'HighCapture.In');self.unknown(e,'LowCapture.In')
        e.memory.write('ResetCapture',True);self.assertEqual(self.step(e),(0,10,-10))

    def test_direct_output_writes_do_not_replace_ramp_or_extrema_history(self):
        e=self.oversample(self.checked());self.step(e);e.memory.write('Signal',4);self.step(e)
        for t,value in (('Ramp.Out',90),('HighCapture.Out',-90),('LowCapture.Out',90)):e.memory.write(t,value)
        self.assertEqual(self.step(e),(1,1,0))

    def test_negative_rates_publish_bool_diagnostics_and_valid_call_recovers(self):
        e=self.oversample(self.checked());self.step(e);e.memory.write('Signal',5);e.memory.write('IncreaseRate',-1);e.memory.write('DecreaseRate',-2)
        self.assertEqual(self.step(e),(0,0,0));self.assertEqual(e.memory.read('RateStatus'),7)
        for tag in ('RateFault','IncreaseInvalid','DecreaseInvalid'):self.assertIs(e.memory.read(tag),True)
        self.assertEqual((e.memory.read('Ramp.IncRate'),e.memory.read('Ramp.DecRate')),(0,0))
        e.memory.write('IncreaseRate',2);e.memory.write('DecreaseRate',4);self.assertEqual(self.step(e),(.5,.5,0))
        self.assertEqual(e.memory.read('RateStatus'),0);self.assertFalse(e.memory.read('RateFault'))

    def test_invalid_oversample_holds_signed_dint_diagnostic_then_recovers(self):
        e=self.oversample(self.checked());self.step(e);e.memory.write('Signal',5);e.memory.write('SampleTime',0)
        self.assertEqual(self.step(e),(0,0,0));self.assertEqual(e.memory.read('RateStatus'),-2147483647)
        self.assertTrue(e.memory.read('SampleInvalid'));self.assertEqual(e.memory.read('Elapsed'),0)
        e.memory.write('SampleTime',.25);self.assertEqual(self.step(e),(.5,.5,0));self.assertFalse(e.memory.read('SampleInvalid'))

    def test_invalid_mode_holds_and_rts_mode_faults_transactionally(self):
        e=self.checked();self.step(e);e.memory.write('Signal',5);e.memory.write('TimingMode',9)
        self.assertEqual(self.step(e),(0,0,0));self.assertTrue(e.memory.read('TimingInvalid'))
        self.assertEqual(e.memory.read('RateStatus'),(1<<27)|1);e.memory.write('TimingMode',2);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'real time sampling'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_status_bool_wire_can_gate_downstream_capture(self):
        def gate(root):
            w=self.sheet(root).find('Wire[@ToID="200"][@ToParam="EnableIn"]');w.set('FromID','100');w.set('FromParam','IncRateInv')
        e=self.oversample(self.checked(gate));self.step(e);self.assertFalse(e.memory.read('HighCapture.EnableOut'))
        e.memory.write('Bypass',True);e.memory.write('Signal',4);e.memory.write('IncreaseRate',-1)
        self.assertEqual(self.step(e),(4,4,0));self.assertTrue(e.memory.read('HighCapture.EnableOut'))

    def test_independent_disabled_limiter_still_publishes_held_output_to_capture(self):
        def independent(root):
            sheet=self.sheet(root)
            for ident in (200,300):sheet.remove(sheet.find(f'Wire[@ToID="{ident}"][@ToParam="EnableIn"]'))
        e=self.checked(independent);e.memory.write('Signal',2);self.step(e);e.memory.write('BlockEnable',False)
        e.memory.write('ResetCapture',True);self.assertEqual(self.step(e),(2,10,-10))
        e.memory.write('ResetCapture',False);e.memory.write('Signal',50);self.assertEqual(self.step(e),(2,10,-10))
        self.assertFalse(e.memory.read('Ramp.EnableOut'));self.assertTrue(e.memory.read('HighCapture.EnableOut'))

    def test_unknown_enable_and_required_input_fault_without_defaulting(self):
        for ref in ('BlockEnable','Signal','IncreaseRate','ResetCapture'):
            e=self.checked();self.unknown(e,ref);before=self.snapshot(e)
            with self.subTest(ref=ref),self.assertRaises(ModelError):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_omitted_saved_rate_input_stays_unknown(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="Ramp"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="IncRate"]'))
            sheet=self.sheet(root);sheet.remove(sheet.find('Wire[@ToID="100"][@ToParam="IncRate"]'))
        e=self.checked(missing)
        with self.assertRaisesRegex(ModelError,'IncRate is unknown'):self.step(e)

    def test_skipped_graph_keeps_history_and_resumes_with_elapsed_gap(self):
        e=self.checked();self.step(e);e.memory.write('ExecuteGraph',False);e.memory.write('Signal',10);history=copy.deepcopy(e.last_timer)
        self.assertEqual(self.step(e,40),(0,0,0));self.assertEqual(e.last_timer,history)
        e.memory.write('ExecuteGraph',True);self.assertAlmostEqual(self.step(e)[0],.1,places=7)

    def test_late_ladder_fault_restores_rate_clock_and_both_extrema(self):
        e=self.oversample(self.checked());self.step(e);e.memory.write('Signal',10);e.memory.write('ResetCapture',True);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);e.memory.write('FaultDivisor',1);e.memory.write('ResetCapture',False)
        self.assertEqual(self.step(e),(.5,.5,0))

    def test_late_capture_fault_restores_earlier_rate_and_maximum(self):
        e=self.oversample(self.checked());self.step(e);e.memory.write('Signal',10);e.memory.write('ResetCapture',True);self.unknown(e,'MinimumReset');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'MINC ResetValue'):self.step(e)
        self.assertEqual(self.snapshot(e),before);e.memory.write('MinimumReset',-10)
        self.assertEqual(self.step(e),(.5,10,-10))

    def test_run_entry_discards_hidden_history_and_reseeds_from_current_input(self):
        e=self.oversample(self.checked());self.step(e);e.memory.write('Signal',5);self.step(e)
        e.enter_run();self.assertEqual(e.last_timer,{});self.assertEqual(self.values(e),(.5,.5,0))
        self.assertEqual(self.step(e),(5,5,5))

    def test_periodic_and_routine_harness_share_existing_timing_rules(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','Periodic');t.set('Rate','10')
        e=self.checked(periodic);self.step(e);e.memory.write('Signal',1);self.assertAlmostEqual(self.step(e)[0],.02,places=7)
        self.assertAlmostEqual(e.memory.read('Elapsed'),.01,places=7)
        e=self.checked(mode='routine',defer=True);self.assertTrue(e.memory.read('Ramp.EnableIn'));e.enter_run();self.assertFalse(e.memory.read('Ramp.EnableIn'))
        self.assertEqual(self.step(e),(0,0,0))

    def test_st_fbd_sites_share_record_history_and_continuous_timestamp(self):
        def st(root):logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(RampAndCapture,0); RLIM(Ramp); MAXC(HighCapture); MINC(LowCapture);'])
        e=self.checked(st);self.step(e);e.memory.write('Signal',10);self.step(e)
        self.assertAlmostEqual(e.memory.read('Ramp.Out'),.02,places=7);self.assertEqual(e.memory.read('Ramp.DeltaT'),0)
        self.assertEqual(len(e.last_timer),3)

    def event_engine(self,*,fault=False):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(RampAndCapture,0); EVENT(TrendEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='MainRoutine' if fault else 'RampAndCapture',Class='Standard',Disabled='false');E.SubElement(p,'Tags');routines=E.SubElement(p,'Routines')
            if fault:logic(E.SubElement(routines,'Routine',Name='MainRoutine',Type='ST'),['GuardResult:=1/FaultDivisor;'])
            else:routines.append(copy.deepcopy(root.find('.//Routine[@Name="RampAndCapture"]')))
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='TrendEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        return self.checked(event)

    def test_event_repeated_continuous_timestamp_does_not_double_ramp(self):
        e=self.event_engine();self.step(e);e.memory.write('Signal',10);self.assertAlmostEqual(self.step(e)[0],.02,places=7)
        self.assertEqual(e.memory.read('Ramp.DeltaT'),0);self.assertEqual(len(e.last_timer),3)

    def test_event_late_fault_rolls_back_elapsed_clock_and_extrema(self):
        e=self.oversample(self.event_engine(fault=True));self.step(e);e.memory.write('Signal',10);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);e.memory.write('FaultDivisor',1);self.assertEqual(self.step(e),(.5,.5,0))

    def test_nested_rate_record_and_program_local_capture_alias(self):
        def nested(root):
            tags=root.find('./Controller/Tags');gate=tags.find('Tag[@Name="HighCapture"]');tags.remove(gate);root.find('./Controller/Programs/Program/Tags').append(gate)
            E.SubElement(tags,'Tag',Name='LocalHigh',TagType='Alias',AliasFor='Program:MainProgram.HighCapture');self.sheet(root).find('Block[@Type="MAXC"]').set('Operand','LocalHigh')
            m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='RateCell',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Rate',DataType='RATE_LIMITER',Dimension='0')
            gate=tags.find('Tag[@Name="Ramp"]');structure=gate.find('Data/Structure');tags.remove(gate)
            arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='RateCell',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='RateCell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='RateCell');item=copy.deepcopy(structure);item.tag='StructureMember';item.set('Name','Rate');obj.append(item)
            self.sheet(root).find('Block[@Type="RLIM"]').set('Operand','Cells[1].Rate')
        e=self.oversample(self.checked(nested));self.step(e);e.memory.write('Signal',10);self.assertEqual(self.step(e),(.5,.5,0))
        self.assertEqual(e.memory.read('Cells[0].Rate.Out'),0)

    def test_profile_constant_redefinition_wrong_record_and_pin_guards(self):
        for kind in ('profile','constant','redefined','record','wiretype','output','aliasinput','function'):
            def mutate(root):
                sheet=self.sheet(root)
                if kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                elif kind=='constant':root.find('./Controller/Tags/Tag[@Name="Ramp"]').set('Constant','true')
                elif kind=='redefined':
                    m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='RATE_LIMITER',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
                elif kind=='record':sheet.find('Block[@Type="RLIM"]').set('Operand','HighCapture')
                elif kind=='wiretype':sheet.find('IRef[@ID="1"]').set('Operand','TimingMode')
                elif kind=='output':sheet.find('Wire[@ToID="100"]').set('ToParam','Out')
                elif kind=='aliasinput':sheet.find('Wire[@ToID="100"]').set('ToParam','IncRateInv')
                else:sheet.find('Block').tag='Function'
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def test_instruction_budget_rolls_back_shared_history_and_wires(self):
        e=self.checked();e.instruction_limit=15;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_detached_rll_replacement_retains_rate_and_extrema(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.oversample(self.checked());self.step(e);e.memory.write('Signal',10);self.step(e);before=self.snapshot(e)
        texts=['JSR(RampAndCapture,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(texts):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(texts),'MainProgram',0)
        self.assertEqual(self.snapshot(e),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.assertEqual(self.step(candidate),(1,1,0));self.assertTrue(all(candidate.project.instruction_counts[n]==1 for n in ('RLIM','MAXC','MINC')))

    def test_registry_reports_twenty_three_blocks_and_qualified_status_pins(self):
        e=self.checked();profile=e.report()['function_blocks'];self.assertEqual(len(profile['instructions']),23)
        self.assertEqual(profile['blocks']['status_aliases']['RATE_LIMITER']['DeltaTInv'],'Status.31')
        self.assertFalse(profile['native_runtime_parity']);self.assertIn('extrema',profile['blocks']['rate_capture'])


if __name__=='__main__':unittest.main()
