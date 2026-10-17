import copy
import unittest
from xml.etree import ElementTree as E
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine
from logixlab.server import Application
import test_runtime as fixtures


class AddOnTests(unittest.TestCase):
    setUp=fixtures.RuntimeTests.setUp
    engine=fixtures.RuntimeTests.engine

    def setUp(self):
        fixtures.RuntimeTests.setUp(self)
        self.root=E.parse(__import__('pathlib').Path(__file__).resolve().parents[1]/'samples/AOILab.L5X').getroot()

    def definition(self,name='LabAccumulator'):
        return self.root.find(f'./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name="{name}"]')

    def body(self,name='LabAccumulator',mode='Logic'):
        return self.definition(name).find(f'./Routines/Routine[@Name="{mode}"]/RLLContent')

    def test_lab_prescan_and_independent_instance_state(self):
        e=self.engine();self.assertEqual(e.blockers,[])
        self.assertEqual(e.memory.read('TotalA'),0);self.assertEqual(e.memory.read('AccumulatorA.Count'),0)
        self.assertEqual(e.memory.read('AccumulatorA.Step'),2)
        for _ in range(3):e.step()
        for ref,value in {'TotalA':6,'TotalB':9,'SharedA':16,'SharedB':29,'ScaledValue':25.5,'Truncated':25,'AReady':False,'BReady':True}.items():
            self.assertEqual(e.memory.read(ref),value,ref)
        self.assertEqual(e.memory.read('NestedScale.Core.Scaled'),25.5)

    def test_false_mode_copies_input_executes_false_routine_and_copies_output(self):
        e=self.engine();e.step();e.memory.write('EnableA',False);e.memory.write('StepA',7);e.step()
        self.assertEqual(e.memory.read('AccumulatorA.Step'),7)
        self.assertEqual(e.memory.read('TotalA'),-1)
        self.assertEqual(e.memory.read('AccumulatorA.Count'),2)
        self.assertEqual(e.memory.read('SharedA'),12)
        self.assertFalse(e.memory.read('AccumulatorA.EnableOut'))

    def test_false_without_optional_routine_only_copies_required_inputs(self):
        self.definition().set('ExecuteEnableInFalse','false')
        e=self.engine();e.step();e.memory.write('EnableA',False);e.memory.write('StepA',8);e.memory.write('TotalA',123);e.step()
        self.assertEqual(e.memory.read('AccumulatorA.Step'),8)
        self.assertEqual(e.memory.read('TotalA'),123)
        self.assertEqual(e.memory.read('AccumulatorA.Total'),2)

    def test_false_routine_cannot_force_rung_out_true(self):
        self.body(mode='EnableInFalse')[0].find('Text').text='OTL(EnableOut);'
        e=self.engine();e.memory.write('EnableA',False);e.step()
        self.assertFalse(e.memory.read('AccumulatorA.EnableOut'));self.assertFalse(e.memory.read('AReady'))

    def test_enableout_controls_following_ladder_instruction(self):
        e=self.engine();e.memory.write('AccumulatorA.Limit',2);e.step()
        self.assertEqual(e.memory.read('TotalA'),2);self.assertFalse(e.memory.read('AReady'))
        self.assertTrue(e.memory.read('AccumulatorA.EnableIn'))

    def test_hidden_defaults_are_not_assumed_saved_state(self):
        self.definition().set('ExecutePrescan','false')
        e=self.engine();self.assertEqual(e.blockers,[])
        with self.assertRaisesRegex(ModelError,'Unknown'):e.memory.read('AccumulatorA.Count')
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scan_count,0);self.assertEqual(e.time_ms,0)

    def test_local_write_before_read_establishes_known_value(self):
        self.definition().set('ExecutePrescan','false')
        self.body()[0].find('Text').text='MOV(4,Count)ADD(Count,Step,Count)MOV(Count,Total);'
        e=self.engine();self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('TotalA'),6)

    def test_local_name_cannot_fall_back_to_controller_tag(self):
        self.body()[0].find('Text').text='MOV(StepA,Count);'
        self.assertTrue(any('Unknown AOI' in b for b in self.engine().blockers))

    def test_explicit_program_access_inside_aoi_is_blocked(self):
        self.body()[0].find('Text').text='MOV(Program:MainProgram.StepA,Count);'
        self.assertTrue(any('only its parameters' in b for b in self.engine().blockers))

    def test_inout_wrong_type_constant_and_literal_are_blocked(self):
        for argument in ('RawValue','3','AccumulatorA.Count.0'):
            with self.subTest(argument=argument):
                e=self.engine([f'LabAccumulator(AccumulatorA,StepA,TotalA,{argument});'])
                self.assertTrue(e.blockers)
        self.root.find('./Controller/Tags/Tag[@Name="SharedA"]').set('Constant','true')
        self.assertTrue(self.engine().blockers)

    def test_output_requires_exact_type_writable_reference(self):
        for target in ('RawValue','4','EnableA'):
            with self.subTest(target=target):
                self.assertTrue(self.engine([f'LabAccumulator(AccumulatorA,StepA,{target},SharedA);']).blockers)

    def test_wrong_instance_type_and_operand_count_are_blocked(self):
        for rung in ('LabAccumulator(NestedScale,StepA,TotalA,SharedA);','LabAccumulator(AccumulatorA,StepA,TotalA);'):
            with self.subTest(rung=rung):self.assertTrue(self.engine([rung]).blockers)

    def test_same_instance_rebinds_inout_for_each_call(self):
        e=self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);','LabAccumulator(AccumulatorA,StepB,TotalB,SharedB);'])
        self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('TotalA'),2);self.assertEqual(e.memory.read('TotalB'),5)
        self.assertEqual(e.memory.read('SharedA'),12);self.assertEqual(e.memory.read('SharedB'),23)

    def test_later_fault_rolls_back_local_output_inout_time_and_timer_metadata(self):
        e=self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);','DIV(1,0,TotalB);'])
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'divide'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.last_timer,{})
        self.assertEqual(e.time_ms,0);self.assertTrue(e.memory.first_scan)

    def test_aoi_unsupported_false_body_is_blocked(self):
        self.body()[0].find('Text').text='AFI()MAGIC(Count);'
        self.assertTrue(any('unsupported MAGIC' in b for b in self.engine().blockers))

    def test_enabled_mode_missing_routine_blocks(self):
        rr=self.definition().find('Routines');rr.remove(rr.find('./Routine[@Name="EnableInFalse"]'))
        self.assertTrue(any('missing or protected' in b for b in self.engine().blockers))

    def test_st_protected_safety_and_alias_definitions_are_blocked(self):
        for change in ('st','protected','safety','alias'):
            with self.subTest(change=change):
                root=copy.deepcopy(self.root);d=self.definition()
                if change=='st':d.find('./Routines/Routine').set('Type','ST')
                elif change=='protected':d.find('Routines').clear()
                elif change=='safety':d.set('Class','Safety')
                else:d.find('./Parameters/Parameter[@Name="Step"]').set('AliasFor','Count')
                self.assertTrue(self.engine().blockers);self.root=root

    def test_recursive_aoi_call_is_blocked(self):
        E.SubElement(self.definition().find('Parameters'),'Parameter',Name='Peer',DataType='LabAccumulator',Usage='InOut',Required='true')
        self.body()[0].find('Text').text='AFI()LabAccumulator(Peer,Step,Total,Shared,Peer);'
        e=self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA,AccumulatorA);'])
        self.assertTrue(any('Recursive AOI' in b for b in e.blockers),e.blockers)

    def test_jump_and_budget_apply_inside_aoi(self):
        self.body()[0].find('Text').text='LBL(Again)JMP(Again);'
        e=self.engine();self.assertEqual(e.blockers,[]);e.instruction_limit=50
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(e.memory.read('AccumulatorA.Count'),0)

    def test_prescan_failure_restores_all_imported_values(self):
        self.body(mode='Prescan')[0].find('Text').text='MOV(42,Total)DIV(1,0,Count);'
        e=self.engine();self.assertTrue(any('Prescan:' in b for b in e.blockers))
        self.assertEqual(e.memory.values,e.project.initial)

    def test_optional_output_is_updated_only_in_instance(self):
        p=self.definition('LabScale').find('./Parameters/Parameter[@Name="Result"]');p.set('Required','false')
        wrapper=self.body('LabWrapper');wrapper[0].find('Text').text='LabScale(Core,Raw,2.0)MOV(Core.Result,Result);'
        e=self.engine();self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('ScaledValue'),25.5)

    def test_instance_arrays_have_independent_local_state(self):
        tag=self.root.find('./Controller/Tags/Tag[@Name="AccumulatorA"]');s=copy.deepcopy(tag.find('Data/Structure'))
        tag.set('Dimensions','2');data=tag.find('Data');data.clear();data.set('Format','Decorated')
        arr=E.SubElement(data,'Array',DataType='LabAccumulator',Dimensions='2')
        for i in range(2):E.SubElement(arr,'Element',Index=f'[{i}]').append(copy.deepcopy(s))
        e=self.engine(['LabAccumulator(AccumulatorA[0],StepA,TotalA,SharedA);','LabAccumulator(AccumulatorA[1],StepB,TotalB,SharedB);'])
        self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('AccumulatorA[0].Count'),2);self.assertEqual(e.memory.read('AccumulatorA[1].Count'),3)

    def test_inout_array_type_and_dimension_contract(self):
        p=self.definition().find('./Parameters/Parameter[@Name="Shared"]');p.set('Dimensions','2')
        self.body()[0].find('Text').text='ADD(Shared[0],Step,Shared[0])MOV(Shared[0],Total);'
        t=self.root.find('./Controller/Tags/Tag[@Name="SharedA"]');t.set('Dimensions','2');d=t.find('Data');d.clear();d.set('Format','Decorated')
        arr=E.SubElement(d,'Array',DataType='DINT',Dimensions='2')
        for i,v in enumerate((10,20)):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(v))
        e=self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);']);self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('SharedA'),[12,20])
        p.set('Dimensions','3');self.assertTrue(self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);']).blockers)

    def test_trace_identifies_nested_instance(self):
        e=self.engine();e.step();trace=[t for t in e.trace if t['routine']=='AOI:LabScale/Logic']
        self.assertTrue(trace);self.assertEqual(trace[0]['context'],'NestedScale.Core')

    def test_trn_truncates_towards_zero_without_rounding(self):
        for value,result in ((3.9,3),(-3.9,-3),(2.5,2),(-0.7,0)):
            with self.subTest(value=value):
                e=self.engine([f'TRN({value},Truncated);']);e.step();self.assertEqual(e.memory.read('Truncated'),result)

    def test_trn_false_does_not_write_and_overflow_rolls_back(self):
        e=self.engine(['AFI()TRN(1.0e30,Truncated);']);e.step();self.assertEqual(e.memory.read('Truncated'),0)
        e=self.engine(['TRN(1.0e30,Truncated);'])
        with self.assertRaisesRegex(ModelError,'overflow'):e.step()

    def test_trn_immediate_is_float32_before_truncation(self):
        e=self.engine(['TRN(16777217.0,Truncated);']);e.step();self.assertEqual(e.memory.read('Truncated'),16777216)

    def test_case_insensitive_parameter_and_local_resolution(self):
        self.body()[0].find('Text').text='ADD(cOuNt,sTeP,COUNT)MOV(count,tOtAl);'
        e=self.engine(['labaccumulator(accumulatora,stepa,totala,shareda);']);self.assertEqual(e.blockers,[])
        e.step();self.assertEqual(e.memory.read('TotalA'),2)

    def test_aoi_local_watch_and_report_are_explicit(self):
        e=self.engine();local=next(t for t in e.memory.leaves() if t['name']=='AccumulatorA.Count')
        self.assertTrue(local['aoi_local']);self.assertEqual(local['value'],0)
        r=e.report()['add_on_instructions'];self.assertIn('LabWrapper',r['active_definitions'])
        self.assertEqual(r['instances']['NestedScale.Core']['definition'],'LabScale')

    def test_local_timers_keep_separate_instance_timestamps(self):
        E.SubElement(self.definition().find('LocalTags'),'LocalTag',Name='Clock',DataType='TIMER')
        self.body()[0].find('Text').text='TON(Clock,?,?)MOV(Clock.ACC,Total);'
        self.body(mode='Prescan')[0].find('Text').text='CLR(Count)CLR(Total)MOV(20,Clock.PRE);'
        e=self.engine();self.assertEqual(e.blockers,[]);e.step();e.step()
        self.assertEqual(e.memory.read('AccumulatorA.Clock.ACC'),10)
        self.assertEqual(e.memory.read('AccumulatorB.Clock.ACC'),10)
        self.assertEqual(len(e.last_timer),2)
        e.memory.write('EnableA',False);e.step()
        self.assertEqual(e.memory.read('AccumulatorA.Clock.ACC'),10)
        self.assertEqual(e.memory.read('AccumulatorB.Clock.ACC'),20)

    def test_local_integer_bit_read_after_prescan_initialization(self):
        self.body()[0].find('Text').text='XIC(Count.1)OTE(EnableOut);'
        self.body(mode='Prescan')[0].find('Text').text='MOV(2,Count)CLR(Total);'
        e=self.engine();self.assertEqual(e.blockers,[]);e.step();self.assertTrue(e.memory.read('AReady'))

    def test_enablein_cannot_be_written_by_aoi_logic(self):
        self.body()[0].find('Text').text='OTE(EnableIn);'
        self.assertTrue(any('EnableIn is read-only' in b for b in self.engine().blockers))

    def test_application_bundled_aoi_lab_and_view_only_definition_routines(self):
        app=Application(self.tmp.name);state=app.command('demo',{'sample':'AOILab'})
        self.assertEqual(state['blockers'],[])
        aoi=next(r for r in state['routines'] if r['key']=='AOI:LabAccumulator/Logic')
        self.assertFalse(aoi['harness']);self.assertTrue(aoi['active'])
        self.assertTrue(app.command('configure',{'mode':'routine','routine':aoi['key']})['blockers'])


if __name__=='__main__':unittest.main()
