"""Paired MCR zones false-scan instructions without leaking invocation state."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError,Project
from logixlab.runtime import Engine

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def rungs(content,logic):
    content.clear()
    for i,text in enumerate(logic):E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text


class McrTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,logic=None,*,mutate=None,sample='ControlLab',mode='project',routine=''):
        root=E.parse(SAMPLES/(sample+'.L5X')).getroot()
        if sample!='ControlLab':
            tags=root.find('./Controller/Tags')
            for tag in E.parse(SAMPLES/'ControlLab.L5X').getroot().findall('./Controller/Tags/Tag'):
                if tag.get('Name').startswith('Zone') or tag.get('Name')=='AfterZone':tags.append(copy.deepcopy(tag))
        if logic is not None:rungs(root.find('./Controller/Programs/Program/Routines/Routine/RLLContent'),logic)
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'mcr.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),mode,routine)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def zone(self,body):return ['XIC(ZoneEnable)MCR();',*body,'MCR();','ADD(AfterZone,1,AfterZone);']

    def test_true_zone_respects_each_rungs_conditions(self):
        e=self.checked(self.zone(['XIC(ZoneInput)OTE(ZoneOutput);']));e.step();self.assertTrue(e.memory.read('ZoneOutput'))
        e.memory.write('ZoneInput',False);e.step();self.assertFalse(e.memory.read('ZoneOutput'));self.assertEqual(e.memory.read('AfterZone'),2)

    def test_false_zone_clears_ote_and_reopens_after_unconditional_end(self):
        e=self.checked(self.zone(['OTE(ZoneOutput);']));e.step();e.memory.write('ZoneEnable',False);e.step()
        self.assertFalse(e.memory.read('ZoneOutput'));self.assertEqual(e.memory.read('AfterZone'),2)
        e.memory.write('ZoneEnable',True);e.step();self.assertTrue(e.memory.read('ZoneOutput'))

    def test_retained_latch_and_math_values_are_not_cleared(self):
        e=self.checked(self.zone(['OTL(ZoneLatch);','ADD(ZoneScans,1,ZoneScans);']));e.step();e.memory.write('ZoneEnable',False);e.step()
        self.assertTrue(e.memory.read('ZoneLatch'));self.assertEqual(e.memory.read('ZoneScans'),1)

    def test_false_zone_does_not_execute_otu_or_res(self):
        e=self.checked(self.zone(['OTU(ZoneLatch);','RES(ZoneCounter);']));e.memory.write('ZoneEnable',False)
        e.memory.write('ZoneLatch',True);e.memory.write('ZoneCounter.ACC',7);e.step()
        self.assertTrue(e.memory.read('ZoneLatch'));self.assertEqual(e.memory.read('ZoneCounter.ACC'),7)

    def test_ton_is_false_scanned_and_reset_while_rto_retains_accumulator(self):
        for op,expected in (('TON',0),('RTO',10)):
            e=self.checked(self.zone([f'{op}(ZoneTimer,?,?);']));e.step();e.step();self.assertEqual(e.memory.read('ZoneTimer.ACC'),10)
            e.memory.write('ZoneEnable',False);e.step();self.assertEqual(e.memory.read('ZoneTimer.ACC'),expected)
            self.assertFalse(e.memory.read('ZoneTimer.EN'));self.assertFalse(e.memory.read('ZoneTimer.TT'))

    def test_counter_retains_count_and_rearms_when_zone_is_disabled(self):
        e=self.checked(self.zone(['CTU(ZoneCounter,?,?);']));e.step();self.assertEqual(e.memory.read('ZoneCounter.ACC'),0)
        e.memory.write('ZoneEnable',False);e.step();self.assertFalse(e.memory.read('ZoneCounter.CU'))
        e.memory.write('ZoneEnable',True);e.step();self.assertEqual(e.memory.read('ZoneCounter.ACC'),1)

    def test_branches_receive_false_input_even_with_true_conditions(self):
        e=self.checked(self.zone(['[XIC(ZoneInput)OTE(ZoneOutput),XIO(ZoneInput)OTL(ZoneLatch)];']))
        e.memory.write('ZoneEnable',False);e.step();self.assertFalse(e.memory.read('ZoneOutput'));self.assertFalse(e.memory.read('ZoneLatch'))
        body=next(row for row in e.trace if row['number']=='1')
        self.assertTrue(body['mcr_forced_false']);self.assertTrue(all(not event['in'] and not event['out'] for event in body['events']))

    def test_unknown_body_conditions_and_division_are_not_read_in_disabled_zone(self):
        e=self.checked(self.zone(['XIC(ZoneInput)OTE(ZoneOutput);','DIV(1,ZoneDivisor,ZoneMath);']))
        e.memory.write('ZoneEnable',False);e.memory.values['zoneinput']=None;e.memory.values['zonedivisor']=None;e.step()
        self.assertFalse(e.memory.read('ZoneOutput'));self.assertEqual(e.memory.read('AfterZone'),1)

    def test_unknown_opening_condition_faults_without_changing_values(self):
        e=self.checked(self.zone(['OTE(ZoneOutput);']));e.memory.values['zoneenable']=None;before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scan_count,0)

    def test_zone_enable_is_sampled_at_opener_not_each_body_rung(self):
        e=self.checked(self.zone(['OTU(ZoneEnable);','OTE(ZoneOutput);']));e.step()
        self.assertFalse(e.memory.read('ZoneEnable'));self.assertTrue(e.memory.read('ZoneOutput'))
        e.step();self.assertFalse(e.memory.read('ZoneOutput'))

    def test_multiple_independent_zones_do_not_share_override(self):
        logic=['XIC(ZoneEnable)MCR();','OTE(ZoneOutput);','MCR();','XIO(ZoneEnable)MCR();','OTL(ZoneLatch);','MCR();','ADD(AfterZone,1,AfterZone);']
        e=self.checked(logic);e.memory.write('ZoneEnable',False);e.step()
        self.assertFalse(e.memory.read('ZoneOutput'));self.assertTrue(e.memory.read('ZoneLatch'));self.assertEqual(e.memory.read('AfterZone'),1)
        self.assertEqual(e.report()['mcr_execution']['planned_zones'],2)

    def test_empty_zone_and_unconditional_enabled_zone_are_valid(self):
        e=self.checked(['XIC(ZoneEnable)MCR();','MCR();','MCR();','OTE(ZoneOutput);','MCR();'])
        e.memory.write('ZoneEnable',False);e.step();self.assertTrue(e.memory.read('ZoneOutput'))

    def test_opening_condition_branches_and_comparisons(self):
        e=self.checked(['[XIC(ZoneEnable),GRT(ZoneScans,2)]MCR();','OTE(ZoneOutput);','MCR();'])
        e.memory.write('ZoneEnable',False);e.memory.write('ZoneScans',3);e.step();self.assertTrue(e.memory.read('ZoneOutput'))
        e.memory.write('ZoneScans',2);e.step();self.assertFalse(e.memory.read('ZoneOutput'))

    def test_case_insensitive_mcr_and_zero_operands(self):
        e=self.checked(['xic(ZoneEnable)mCr();','ote(ZoneOutput);','mcr();']);e.step();self.assertTrue(e.memory.read('ZoneOutput'))

    def test_unpaired_nested_conditional_or_badly_placed_mcr_blocks(self):
        for logic in (['MCR();'],['MCR();','XIC(ZoneInput)MCR();'],['[MCR(),NOP()];','MCR();'],
                      ['MCR()OTE(ZoneOutput);','MCR();'],['MCR()MCR();'],['MCR(1);','MCR();']):
            self.assertTrue(self.engine(logic).blockers,logic)

    def test_opening_rung_side_effects_are_blocked_even_if_unreachable(self):
        for prefix in ('MOV(1,ZoneScans)','OTE(ZoneOutput)','ONS(ZoneOutput)','JMP(done)'):
            self.assertTrue(self.engine(['AFI()'+prefix+'MCR();','NOP();','MCR();','LBL(done)NOP();']).blockers,prefix)

    def test_jump_into_out_of_or_between_zones_is_blocked(self):
        cases=(['JMP(inside);','XIC(ZoneEnable)MCR();','LBL(inside)OTE(ZoneOutput);','MCR();'],
               ['XIC(ZoneEnable)MCR();','JMP(outside);','MCR();','LBL(outside)NOP();'],
               ['MCR();','JMP(second);','MCR();','MCR();','LBL(second)NOP();','MCR();'])
        for logic in cases:self.assertTrue(self.engine(logic).blockers,logic)

    def test_jump_over_complete_zone_retains_skipped_outputs(self):
        e=self.checked(['XIC(ZoneInput)JMP(done);','XIC(ZoneEnable)MCR();','OTE(ZoneOutput);','MCR();','LBL(done)ADD(AfterZone,1,AfterZone);'])
        e.memory.write('ZoneOutput',True);e.memory.write('ZoneEnable',False);e.step();self.assertTrue(e.memory.read('ZoneOutput'))
        e.memory.write('ZoneInput',False);e.step();self.assertFalse(e.memory.read('ZoneOutput'));self.assertEqual(e.memory.read('AfterZone'),2)

    def test_inside_zone_jump_works_when_enabled_and_is_false_when_disabled(self):
        e=self.checked(self.zone(['LBL(again)ADD(ZoneScans,1,ZoneScans);','LES(ZoneScans,3)JMP(again);']))
        e.step();self.assertEqual(e.memory.read('ZoneScans'),3);e.memory.write('ZoneEnable',False);e.step()
        self.assertEqual(e.memory.read('ZoneScans'),3);self.assertEqual(e.memory.read('AfterZone'),2)

    def test_instruction_budget_fault_rolls_back_and_override_does_not_leak_to_retry(self):
        e=self.checked(self.zone(['LBL(loop)ADD(ZoneScans,1,ZoneScans);','JMP(loop);']));e.instruction_limit=25
        before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        e.memory.write('ZoneEnable',False);e.step();self.assertEqual(e.memory.read('ZoneScans'),0);self.assertEqual(e.memory.read('AfterZone'),1)

    def test_tnd_ret_and_sbr_inside_zone_are_unqualified(self):
        for op in ('TND();','RET();','SBR();'):self.assertTrue(self.engine(self.zone([op])).blockers,op)

    def test_prescan_visits_body_without_reading_zone_gate(self):
        def saved(root):
            for name,value in (('ZoneEnable',0),('ZoneOutput',1),('ZoneLatch',1)):
                root.find('./Controller/Tags/Tag[@Name="'+name+'"]/Data/DataValue').set('Value',str(value))
            root.find('./Controller/Tags/Tag[@Name="ZoneTimer"]/Data/Structure/DataValueMember[@Name="ACC"]').set('Value','23')
        e=self.checked(self.zone(['OTE(ZoneOutput);','OTL(ZoneLatch);','TON(ZoneTimer,?,?);']),mutate=saved)
        self.assertFalse(e.memory.read('ZoneOutput'));self.assertTrue(e.memory.read('ZoneLatch'));self.assertEqual(e.memory.read('ZoneTimer.ACC'),0)

    def test_enabling_zone_does_not_reassert_program_first_scan(self):
        e=self.checked(self.zone(['XIC(S:FS)OTE(ZoneOutput);']));e.memory.write('ZoneEnable',False);e.step()
        e.memory.write('ZoneEnable',True);e.step();self.assertFalse(e.memory.read('ZoneOutput'))

    def test_jsr_is_skipped_in_disabled_zone_and_callee_has_independent_plan(self):
        def child(root):
            routine=E.SubElement(root.find('./Controller/Programs/Program/Routines'),'Routine',Name='Child',Type='RLL')
            rungs(E.SubElement(routine,'RLLContent'),['XIO(ZoneEnable)MCR();','OTE(ZoneOutput);','MCR();'])
        e=self.checked(self.zone(['JSR(Child,0);']),mutate=child);e.memory.write('ZoneEnable',False);e.memory.write('ZoneOutput',True);e.step()
        self.assertTrue(e.memory.read('ZoneOutput'));self.assertFalse(any(row['routine'].endswith('/Child') for row in e.trace))
        e.memory.write('ZoneEnable',True);e.step();self.assertFalse(e.memory.read('ZoneOutput'))

    def aoi(self,root):
        content=root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name="LabAccumulator"]/Routines/Routine[@Name="Logic"]/RLLContent')
        rungs(content,['GRT(Step,0)MCR();','ADD(Count,Step,Count)MOV(Count,Total);','MCR();','OTE(EnableOut);'])

    def test_aoi_own_zone_does_not_disable_caller_and_false_routine_runs_normally(self):
        e=self.checked(self.zone(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA)OTE(ZoneOutput);']),mutate=self.aoi,sample='AOILab')
        e.step();self.assertEqual(e.memory.read('TotalA'),2);self.assertTrue(e.memory.read('ZoneOutput'))
        e.memory.write('StepA',0);e.step();self.assertEqual(e.memory.read('TotalA'),2);self.assertTrue(e.memory.read('ZoneOutput'))
        e.memory.write('ZoneEnable',False);e.step();self.assertEqual(e.memory.read('TotalA'),-1);self.assertFalse(e.memory.read('ZoneOutput'))
        e.memory.write('ZoneEnable',True);e.memory.write('StepA',3);e.step();self.assertEqual(e.memory.read('TotalA'),5)

    def test_aoi_instances_have_independent_override_on_each_invocation(self):
        logic=['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);','LabAccumulator(AccumulatorB,StepB,TotalB,SharedB);']
        e=self.checked(logic,mutate=self.aoi,sample='AOILab');e.memory.write('StepB',0);e.step()
        self.assertEqual((e.memory.read('TotalA'),e.memory.read('TotalB')),(2,0))
        e.memory.write('StepA',0);e.memory.write('StepB',3);e.step();self.assertEqual((e.memory.read('TotalA'),e.memory.read('TotalB')),(2,3))

    def test_routine_harness_uses_same_mcr_rules(self):
        e=self.checked(self.zone(['OTE(ZoneOutput);']),mode='routine',routine='MainProgram/MainRoutine')
        e.memory.write('ZoneEnable',False);e.step(7);self.assertFalse(e.memory.read('ZoneOutput'));self.assertEqual(e.memory.read('AfterZone'),1)

    def test_profile_gate_and_st_form_remain_explicit(self):
        for field,value in (('MajorRev','34'),('ProcessorType','1756-L75'),('ProcessorType','5069-L340ERM')):
            self.assertTrue(self.engine(self.zone(['NOP();']),mutate=lambda root:root.find('Controller').set(field,value)).blockers)
        def st(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine');routine.remove(routine.find('RLLContent'));routine.set('Type','ST')
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='MCR();'
        self.assertTrue(self.engine(mutate=st).blockers)

    def test_bundled_control_lab_zone_transitions_and_late_fault_recovery(self):
        e=self.checked();e.step();e.step();self.assertTrue(e.memory.read('ZoneOutput'));self.assertTrue(e.memory.read('ZoneLatch'))
        e.memory.write('ZoneEnable',False);e.memory.write('ZoneDivisor',0);e.step()
        self.assertFalse(e.memory.read('ZoneOutput'));self.assertEqual(e.memory.read('ZoneTimer.ACC'),0)
        self.assertEqual((e.memory.read('ZoneScans'),e.memory.read('AfterZone')),(2,3))
        e.memory.write('ZoneEnable',True);e.memory.write('Load',True);e.memory.write('ShiftLeft',True)
        before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        e.memory.write('ZoneDivisor',1);e.step();self.assertEqual(e.memory.read('QueueControl.POS'),1);self.assertEqual(e.memory.read('ZoneCounter.ACC'),1)

    def test_routine_replacement_rebuilds_zone_plan_without_changing_active_engine(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked(['NOP();']);e.step();logic=self.zone(['OTE(ZoneOutput);'])
        xml=xml_source();content=xml.find('RLLContent')
        for node in list(content):content.remove(node)
        for i,text in enumerate(logic):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        source=decode(container(E.tostring(xml,encoding='utf-8')));candidate,_=prepare(e,source,tuple(logic),'MainProgram',0)
        self.assertEqual(e.report()['mcr_execution']['planned_zones'],0);self.assertEqual(candidate.report()['mcr_execution']['planned_zones'],1)
        candidate.memory.write('ZoneEnable',False);candidate.step();self.assertFalse(candidate.memory.read('ZoneOutput'))

    def test_report_and_trace_retain_evidence_boundaries(self):
        e=self.checked(self.zone(['OTE(ZoneOutput);']));e.memory.write('ZoneEnable',False);e.step()
        row=e.report()['mcr_execution'];self.assertFalse(row['native_runtime_parity']);self.assertEqual(row['planned_zones'],1)
        self.assertFalse(e.trace[0]['mcr_forced_false']);self.assertTrue(e.trace[1]['mcr_forced_false']);self.assertTrue(e.trace[2]['mcr_forced_false'])
        self.assertFalse(e.trace[3]['mcr_forced_false'])

    def test_empty_parallel_path_cannot_restore_true_power_in_disabled_zone(self):
        e=self.checked(self.zone(['[NOP(),];']));e.memory.write('ZoneEnable',False);e.step()
        self.assertFalse(next(row for row in e.trace if row['number']=='1')['power'])

    def test_body_fifo_and_shift_receive_normal_false_execution(self):
        e=self.checked(self.zone(['FFL(Incoming,Queue[0],QueueControl,?,?);','BSL(LeftBits[0],LeftControl,BitIn,?);']))
        e.memory.write('ZoneEnable',False);e.step();self.assertFalse(e.memory.read('QueueControl.EN'))
        before=copy.deepcopy(e.memory.read('LeftBits'));e.memory.write('ZoneEnable',True);e.step()
        self.assertEqual(e.memory.read('QueueControl.POS'),1);self.assertNotEqual(e.memory.read('LeftBits'),before)
        e.memory.write('ZoneEnable',False);e.step();self.assertFalse(e.memory.read('LeftControl.EN'));self.assertEqual(e.memory.read('LeftControl.POS'),0)

    def test_unconditional_end_restores_arithmetic_after_disabled_zone(self):
        e=self.checked(['XIC(ZoneEnable)MCR();','DIV(1,ZoneDivisor,ZoneMath);','MCR();','DIV(1,ZoneDivisor,ZoneMath);'])
        e.memory.write('ZoneEnable',False);e.memory.write('ZoneDivisor',0);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);e.memory.write('ZoneDivisor',1);e.step();self.assertEqual(e.memory.read('ZoneMath'),1)

    def test_aoi_false_routine_has_its_own_mcr_plan(self):
        def false_mode(root):
            self.aoi(root)
            content=root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name="LabAccumulator"]/Routines/Routine[@Name="EnableInFalse"]/RLLContent')
            rungs(content,['LES(Step,2)MCR();','MOV(-10,Total);','MCR();'])
        e=self.checked(self.zone(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);']),mutate=false_mode,sample='AOILab')
        e.memory.write('ZoneEnable',False);e.memory.write('StepA',3);e.step();self.assertEqual(e.memory.read('TotalA'),0)
        e.memory.write('StepA',1);e.step();self.assertEqual(e.memory.read('TotalA'),-10)

    def test_event_task_has_independent_zone_and_disabled_event_instruction_is_skipped(self):
        import test_task_scheduler as tasks
        def event(root):
            task=root.find('./Controller/Tasks/Task[2]');E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
            for tag in E.parse(SAMPLES/'ControlLab.L5X').getroot().findall('./Controller/Tags/Tag'):
                if tag.get('Name').startswith('Zone'):root.find('./Controller/Tags').append(copy.deepcopy(tag))
        bodies=[['XIC(ZoneEnable)MCR();','EVENT(Task1);','MCR();','EVENT(Task1);'],['XIO(ZoneEnable)MCR();','ADD(Count1,1,Count1);','MCR();']]
        e=tasks.TaskSchedulerTests.engine(self,[dict(Type='CONTINUOUS'),dict(Type='EVENT',Priority='1')],bodies,mutate=event)
        self.assertEqual(e.blockers,[]);e.memory.write('ZoneEnable',False);e.step();self.assertEqual(e.memory.read('Count1'),1)
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],1)


if __name__=='__main__':unittest.main()
