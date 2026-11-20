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

    def test_grouped_dint_inputs_copy_during_prescan_and_false_and_true_calls(self):
        self.definition().set('ExecuteEnableInFalse', 'false')
        for source, expected in (('2#0000 0011', 3), ('8#377 7777 7777', -1), ('16#FFFF FFFE', -2)):
            with self.subTest(source=source):
                engine = self.engine([f'XIC(EnableA)LabAccumulator(AccumulatorA,{source},TotalA,SharedA);'])
                self.assertEqual(engine.blockers, [])
                self.assertEqual(engine.memory.read('AccumulatorA.Step'), expected)

                engine.memory.write('EnableA', False)
                engine.memory.write('AccumulatorA.Step', 123)
                engine.memory.write('TotalA', 77)
                engine.step()
                self.assertEqual(engine.memory.read('AccumulatorA.Step'), expected)
                self.assertEqual(engine.memory.read('TotalA'), 77)

                engine.memory.write('EnableA', True)
                engine.step()
                self.assertEqual(engine.memory.read('TotalA'), expected)

    def test_grouped_dint_input_keeps_real_conversion_in_st_and_nested_calls(self):
        main = self.root.find('./Controller/Programs/Program/Routines/Routine')
        main.remove(main.find('RLLContent'))
        main.set('Type', 'ST')
        E.SubElement(E.SubElement(main, 'STContent'), 'Line', Number='0').text = (
            'LabWrapper(NestedScale,16#FFFF FFFE,ScaledValue);')
        self.body('LabWrapper')[0].find('Text').text = 'LabScale(Core,16#FFFF FFFD,2.0,Result);'
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        engine.step()
        self.assertEqual(engine.memory.read('NestedScale.Raw'), -2.0)
        self.assertEqual(engine.memory.read('NestedScale.Core.Raw'), -3.0)
        self.assertEqual(engine.memory.read('ScaledValue'), -6.0)

    def test_grouped_aoi_inputs_keep_profile_width_and_writable_operand_guards(self):
        for operands in ('2#0000 0020,TotalA,SharedA', '16#1 0000 0000,TotalA,SharedA',
                         '16#0000 0001U,TotalA,SharedA', '1,16#0000 0001,SharedA',
                         '1,TotalA,16#0000 0001'):
            with self.subTest(operands=operands):
                self.assertTrue(self.engine([f'AFI()LabAccumulator(AccumulatorA,{operands});']).blockers)
        self.root.find('Controller').set('MajorRev', '34')
        self.assertTrue(self.engine(['LabAccumulator(AccumulatorA,2#0000 0011,TotalA,SharedA);']).blockers)

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

    def test_constant_inout_reads_constant_alias_and_live_mutable_tag(self):
        self.definition().find('Parameters/Parameter[@Name="Shared"]').set('Constant', 'true')
        self.body()[0].find('Text').text = 'MOV(Shared,Total);'
        tags = self.root.find('Controller/Tags')
        tags.find('Tag[@Name="SharedA"]').set('Constant', 'true')
        E.SubElement(tags, 'Tag', Name='FixedSource', TagType='Alias', AliasFor='SharedA')
        engine = self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,FixedSource);',
                              'LabAccumulator(AccumulatorB,StepB,TotalB,SharedB);'])
        self.assertEqual(engine.blockers, [])
        engine.step()
        self.assertEqual((engine.memory.read('TotalA'), engine.memory.read('TotalB')), (10, 20))
        engine.memory.write('SharedB', 33)
        engine.step()
        self.assertEqual(engine.memory.read('TotalB'), 33)
        self.assertEqual(engine.memory.read('SharedA'), 10)

    def test_constant_inout_rejects_direct_and_bit_writes_in_ladder_and_st(self):
        definition = self.definition()
        definition.find('Parameters/Parameter[@Name="Shared"]').set('Constant', 'true')
        for rung in ('AFI()MOV(5,Shared);', 'AFI()OTE(Shared.0);'):
            with self.subTest(rung=rung):
                self.body()[0].find('Text').text = rung
                self.assertTrue(any('Constant AOI InOut' in b for b in self.engine().blockers))
        routine = definition.find('Routines/Routine[@Name="Logic"]')
        routine.remove(routine.find('RLLContent'))
        routine.set('Type', 'ST')
        line = E.SubElement(E.SubElement(routine, 'STContent'), 'Line', Number='0')
        line.text = 'IF FALSE THEN Shared := 5; END_IF;'
        self.assertTrue(any('Constant AOI InOut' in b for b in self.engine().blockers))

    def test_nested_inout_preserves_read_only_parameter_contract(self):
        outer = self.definition('LabWrapper').find('Parameters/Parameter[@Name="Raw"]')
        inner = self.definition('LabScale').find('Parameters/Parameter[@Name="Raw"]')
        for parameter in (outer, inner):
            parameter.set('Usage', 'InOut')
            parameter.set('Constant', 'true')
        saved = self.root.find('Controller/Tags/Tag[@Name="NestedScale"]/Data/Structure')
        saved.remove(saved.find('DataValueMember[@Name="Raw"]'))
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        engine.step()
        self.assertEqual(engine.memory.read('ScaledValue'), 25.5)

        inner.set('Constant', 'false')
        self.assertTrue(any('Constant AOI InOut' in b for b in self.engine().blockers))

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

    def test_st_protected_safety_and_nonlocal_alias_definitions_are_blocked(self):
        for change in ('st','protected','safety','alias'):
            with self.subTest(change=change):
                root=copy.deepcopy(self.root);d=self.definition()
                if change=='st':d.find('./Routines/Routine').set('Type','ST')
                elif change=='protected':d.find('Routines').clear()
                elif change=='safety':d.set('Class','Safety')
                else:d.find('./Parameters/Parameter[@Name="Step"]').set('AliasFor','Limit')
                self.assertTrue(self.engine().blockers);self.root=root

    def alias_accumulator(self, *, include_input=True):
        definition = self.definition()
        names = ('Step', 'Total') if include_input else ('Total',)
        for name in names:
            item = definition.find(f'Parameters/Parameter[@Name="{name}"]')
            item.set('TagType', 'Alias')
            item.set('AliasFor', 'Count')
        for name in ('AccumulatorA', 'AccumulatorB'):
            saved = self.root.find(f'Controller/Tags/Tag[@Name="{name}"]/Data/Structure')
            for parameter in names:
                saved.remove(saved.find(f'DataValueMember[@Name="{parameter}"]'))
        return definition

    def test_input_and_output_alias_share_one_local_in_ladder_and_st(self):
        definition = self.alias_accumulator()
        definition.set('ExecuteEnableInFalse', 'false')
        logic = definition.find('Routines/Routine[@Name="Logic"]')
        self.body()[0].find('Text').text = 'ADD(Step,1,Count);'
        for kind in ('RLL', 'ST'):
            with self.subTest(kind=kind):
                if kind == 'ST':
                    logic.remove(logic.find('RLLContent'))
                    logic.set('Type', 'ST')
                    E.SubElement(E.SubElement(logic,'STContent'),'Line',Number='0').text = 'Count := Step + 1;'
                engine = self.engine()
                self.assertEqual(engine.blockers, [])
                engine.step()
                refs = ('AccumulatorA.Step', 'AccumulatorA.Total', 'AccumulatorA.Count', 'TotalA')
                self.assertEqual([engine.memory.read(ref) for ref in refs], [3, 3, 3, 3])
                self.assertNotIn('Step', engine.memory.values['accumulatora'])
                engine.memory.write('StepA', 7)
                engine.memory.write('EnableA', False)
                engine.step()
                self.assertEqual([engine.memory.read(ref) for ref in refs], [7, 7, 7, 3])

    def test_saved_output_alias_loads_local_and_rejects_conflicting_saved_values(self):
        definition = self.alias_accumulator(include_input=False)
        definition.set('ExecutePrescan', 'false')
        saved = self.root.find('Controller/Tags/Tag[@Name="AccumulatorA"]/Data/Structure')
        E.SubElement(saved, 'DataValueMember', Name='Total', DataType='DINT', Value='17')
        second = self.root.find('Controller/Tags/Tag[@Name="AccumulatorB"]/Data/Structure')
        E.SubElement(second, 'DataValueMember', Name='Total', DataType='DINT', Value='0')
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        self.assertEqual(engine.memory.read('AccumulatorA.Count'), 17)
        engine.memory.write('AccumulatorA.Total', 24)
        rows = {row['name']: row for row in engine.memory.leaves()}
        self.assertEqual(rows['AccumulatorA.Total']['value'], 24)
        self.assertFalse(rows['AccumulatorA.Total']['aoi_local'])
        self.assertEqual(rows['AccumulatorA.Count']['value'], 24)
        E.SubElement(saved, 'DataValueMember', Name='Count', DataType='DINT', Value='18')
        self.assertTrue(any('Conflicting decorated AOI values' in blocker for blocker in self.engine().blockers))

    def test_aois_reject_duplicate_aliases_of_same_usage_and_inexact_types(self):
        definition = self.alias_accumulator()
        second = E.SubElement(definition.find('Parameters'), 'Parameter', Name='StepAgain', Usage='Input',
                              DataType='DINT', AliasFor='Count')
        self.assertTrue(any('only one Input alias' in blocker for blocker in self.engine().blockers))
        second.set('Usage', 'InOut')
        self.assertTrue(any('ordinary Input or Output' in blocker for blocker in self.engine().blockers))
        second.set('Usage', 'Input')
        second.set('DataType', 'REAL')
        self.assertTrue(any('matching scalar local target' in blocker for blocker in self.engine().blockers))

    def local_alias_record(self, target, *, include_input=True):
        definition = self.alias_accumulator(include_input=include_input)
        parameters = definition.find('Parameters')
        for name in ('Step', 'Total') if include_input else ('Total',):
            parameters.find(f'Parameter[@Name="{name}"]').set('AliasFor', target)
        controller = self.root.find('Controller')
        types = controller.find('DataTypes')
        if types is None:
            types = E.SubElement(controller, 'DataTypes')
        members = E.SubElement(E.SubElement(types,'DataType',Name='AliasState',Class='User'),'Members')
        E.SubElement(members,'Member',Name='Position',DataType='DINT',Dimension='0')
        E.SubElement(members,'Member',Name='Samples',DataType='DINT',Dimension='3')
        E.SubElement(definition.find('LocalTags'),'LocalTag',Name='State',DataType='AliasState')
        for name in ('AccumulatorA', 'AccumulatorB'):
            saved = controller.find(f'Tags/Tag[@Name="{name}"]/Data/Structure')
            record = E.SubElement(saved,'StructureMember',Name='State',DataType='AliasState')
            E.SubElement(record,'DataValueMember',Name='Position',DataType='DINT',Value='21')
            array = E.SubElement(record,'ArrayMember',Name='Samples',DataType='DINT',Dimensions='3')
            E.SubElement(array,'Element',Index='[0]',Value='41')
            E.SubElement(array,'Element',Index='[2]',Value='66')
        return definition

    def test_local_alias_paths_share_a_member_or_fixed_element_without_touching_siblings(self):
        original = self.root
        for target in ('State.Position', 'state.Samples[1]'):
            with self.subTest(target=target):
                self.root = copy.deepcopy(original)
                self.local_alias_record(target)
                self.body()[0].find('Text').text = f'ADD(Step,1,{target});'
                engine = self.engine()
                self.assertEqual(engine.blockers, [])
                engine.step()
                refs = ('AccumulatorA.Step', 'AccumulatorA.Total', 'AccumulatorA.' + target, 'TotalA')
                self.assertEqual([engine.memory.read(ref) for ref in refs], [3, 3, 3, 3])
                engine.memory.write('AccumulatorA.Total', 12)
                self.assertEqual(engine.memory.read('AccumulatorA.Step'), 12)
                array = engine.memory.read('AccumulatorA.State.Samples')
                self.assertEqual((array[0], array[2]), (41, 66))
                if '[' in target:
                    self.assertEqual(array[1], 12)
                    self.assertEqual(engine.memory.read('AccumulatorA.State.Position'), 21)

    def test_saved_alias_value_fills_only_one_array_element_and_rejects_conflicts(self):
        definition = self.local_alias_record('State.Samples[1]', include_input=False)
        definition.set('ExecutePrescan','false')
        for name,value in (('AccumulatorA','17'),('AccumulatorB','0')):
            saved = self.root.find(f'Controller/Tags/Tag[@Name="{name}"]/Data/Structure')
            E.SubElement(saved,'DataValueMember',Name='Total',DataType='DINT',Value=value)
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        self.assertEqual(engine.memory.read('AccumulatorA.State.Samples'), [41, 17, 66])
        record = self.root.find('Controller/Tags/Tag[@Name="AccumulatorA"]/Data/Structure/StructureMember[@Name="State"]')
        E.SubElement(record.find('ArrayMember[@Name="Samples"]'),'Element',Index='[1]',Value='18')
        self.assertTrue(any('Conflicting decorated AOI values for State.Samples[1]' in blocker
                            for blocker in self.engine().blockers))

    def test_reject_invalid_paths_and_normalized_duplicate_aliases(self):
        definition = self.local_alias_record('State.Samples[1]')
        inputs = definition.find('Parameters')
        parameter = inputs.find('Parameter[@Name="Step"]')
        for target in ('State.Samples[Step]', 'State.Samples[3]', 'State.Samples', 'State.Missing'):
            with self.subTest(target=target):
                parameter.set('AliasFor', target)
                self.assertTrue(any('AOI alias' in blocker for blocker in self.engine().blockers))
        parameter.set('AliasFor','State.Samples[1]')
        E.SubElement(inputs,'Parameter',Name='StepAgain',Usage='Input',DataType='DINT',AliasFor='STATE.samples[01]')
        self.assertTrue(any('only one Input alias' in blocker for blocker in self.engine().blockers))

    def test_timer_field_aliases_copy_preset_accumulator_and_done(self):
        definition = self.alias_accumulator()
        parameters = definition.find('Parameters')
        parameters.find('Parameter[@Name="Step"]').set('AliasFor', 'Clock.PRE')
        parameters.find('Parameter[@Name="Total"]').set('AliasFor', 'Clock.ACC')
        E.SubElement(parameters, 'Parameter', Name='Done', Usage='Output', DataType='BOOL',
                     TagType='Alias', AliasFor='clock.dn', Required='true', Visible='true')
        E.SubElement(definition.find('LocalTags'), 'LocalTag', Name='Clock', DataType='TIMER')
        self.body()[0].find('Text').text = 'TON(Clock,?,?);'
        engine = self.engine(['XIC(EnableA)LabAccumulator(AccumulatorA,StepA,TotalA,SharedA,AReady);'])
        self.assertEqual(engine.blockers, [])
        engine.memory.write('StepA', 15)
        refs = ('AccumulatorA.Step', 'AccumulatorA.Clock.PRE', 'AccumulatorA.Total',
                'TotalA', 'AccumulatorA.Done', 'AReady')
        for elapsed, done in ((0, False), (10, False), (20, True)):
            engine.step()
            self.assertEqual([engine.memory.read(ref) for ref in refs], [15, 15, elapsed, elapsed, done, done])
        rows = {row['name']: row for row in engine.memory.leaves()}
        self.assertIs(rows['AccumulatorA.Done']['value'], True)
        self.assertFalse(rows['AccumulatorA.Done']['aoi_local'])

    def test_aliases_to_counter_and_control_array_fields(self):
        original = self.root
        for dtype, first, second in (('COUNTER', 'PRE', 'ACC'), ('CONTROL', 'LEN', 'POS')):
            with self.subTest(dtype=dtype):
                self.root = copy.deepcopy(original)
                definition = self.alias_accumulator()
                parameters = definition.find('Parameters')
                parameters.find('Parameter[@Name="Step"]').set('AliasFor', f'LocalState[1].{first}')
                parameters.find('Parameter[@Name="Total"]').set('AliasFor', f'LocalState[1].{second}')
                E.SubElement(definition.find('LocalTags'), 'LocalTag', Name='LocalState', DataType=dtype,
                             Dimensions='2')
                self.body()[0].find('Text').text = 'MOV(Step,Total);'
                engine = self.engine()
                self.assertEqual(engine.blockers, [])
                before = copy.deepcopy(engine.memory.read('AccumulatorA.LocalState[0]'))
                engine.step()
                self.assertEqual(engine.memory.read('TotalA'), 2)
                self.assertEqual(engine.memory.read(f'AccumulatorA.LocalState[1].{first}'), 2)
                self.assertEqual(engine.memory.read(f'AccumulatorA.LocalState[1].{second}'), 2)
                self.assertEqual(engine.memory.read('AccumulatorA.LocalState[0]'), before)

    def test_record_aliases_reject_unknown_fields_and_mismatched_types(self):
        definition = self.alias_accumulator()
        E.SubElement(definition.find('LocalTags'), 'LocalTag', Name='Clock', DataType='TIMER')
        step = definition.find('Parameters/Parameter[@Name="Step"]')
        for target, diagnostic in (('Clock.Missing','TIMER has no field'), ('Clock.DN','matching scalar local target')):
            with self.subTest(target=target):
                step.set('AliasFor', target)
                self.assertTrue(any(diagnostic in value for value in self.engine().blockers))

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
