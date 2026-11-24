import copy
import struct
import unittest
from unittest.mock import patch
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

    def test_numeric_output_copy_uses_real_precision_in_ladder_scan_modes(self):
        tags = self.root.find('./Controller/Tags')
        E.SubElement(tags, 'Tag', Name='RealOutputAlias', TagType='Alias', AliasFor='ScaledValue')
        engine = self.engine([
            'XIC(EnableA)LabAccumulator(AccumulatorA,16777217,RealOutputAlias,SharedA);',
        ])
        self.assertEqual(engine.blockers, [])
        self.assertTrue(engine.report()['add_on_instructions']['numeric_outputs']['available'])
        self.assertEqual(engine.memory.read('ScaledValue'), 0.0)
        engine.step()
        self.assertEqual(engine.memory.read('AccumulatorA.Total'), 16777217)
        self.assertEqual(engine.memory.read('ScaledValue'), 16777216.0)
        engine.memory.write('EnableA', False)
        engine.step()
        self.assertEqual(engine.memory.read('ScaledValue'), -1.0)

    def test_st_numeric_output_rounds_binary32_source_to_nearest_even(self):
        main = self.root.find('./Controller/Programs/Program/Routines/Routine')
        main.remove(main.find('RLLContent'))
        main.set('Type', 'ST')
        E.SubElement(E.SubElement(main, 'STContent'), 'Line', Number='0').text = (
            'LabWrapper(NestedScale,RawValue,TotalB);')
        self.body('LabWrapper')[0].find('Text').text = 'LabScale(Core,Raw,1.0,Result);'
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        for value, stored, rounded in ((2.50000001, 2.5, 2), (3.5, 3.5, 4), (-2.5, -2.5, -2)):
            with self.subTest(value=value):
                engine.memory.write('RawValue', value)
                engine.step()
                self.assertEqual(engine.memory.read('NestedScale.Result'), stored)
                self.assertEqual(engine.memory.read('TotalB'), rounded)

    def test_narrow_output_overflow_rolls_back_aoi_writes_and_allows_retry(self):
        output = self.root.find('./Controller/Tags/Tag[@Name="TotalA"]')
        output.set('DataType', 'SINT')
        output.find('./Data/DataValue').set('DataType', 'SINT')
        engine = self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);'])
        self.assertEqual(engine.blockers, [])
        engine.memory.write('TotalA', 47)
        engine.memory.write('StepA', 128)
        with self.assertRaisesRegex(ModelError, 'SINT overflow'):
            engine.step()
        self.assertEqual(engine.scan_count, 0)
        self.assertEqual(engine.memory.read('TotalA'), 47)
        self.assertEqual(engine.memory.read('AccumulatorA.Total'), 0)
        self.assertEqual(engine.memory.read('SharedA'), 10)
        engine.memory.write('StepA', -128)
        engine.step()
        self.assertEqual(engine.memory.read('TotalA'), -128)

    def test_numeric_output_does_not_relax_destination_reference_or_profile_checks(self):
        self.set_dint_array('TotalA', (11, 22))
        self.assertTrue(self.engine(['LabWrapper(NestedScale,RawValue,TotalA);']).blockers)
        output = self.root.find('./Controller/Tags/Tag[@Name="ScaledValue"]')
        output.set('Constant', 'true')
        call = 'LabAccumulator(AccumulatorA,StepA,ScaledValue,SharedA);'
        self.assertIn('Read-only destination', str(self.engine([call]).blockers))
        output.set('Constant', 'false')
        self.assertIn('InOut requires type DINT', str(self.engine([
            'LabAccumulator(AccumulatorA,StepA,TotalB,ScaledValue);',
        ]).blockers))
        self.root.find('Controller').set('MajorRev', '34')
        self.assertIn('Output destination type must match exactly', str(self.engine([call]).blockers))

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

    def test_false_without_optional_routine_skips_indexed_results(self):
        self.definition().set('ExecuteEnableInFalse', 'false')
        self.set_dint_array('TotalA', (11, 22))
        self.set_dint_array('SharedA', (10, 20))
        engine = self.engine([
            'XIC(EnableA)LabAccumulator(AccumulatorA,StepA,TotalA[Truncated],SharedA[Truncated])OTE(AReady);',
        ])
        self.assertEqual(engine.blockers, [])
        self.assertEqual(engine.memory.read('TotalA'), [0, 22])  # Prescan copied the output to index 0.
        engine.memory.write('EnableA', False)
        engine.memory.write('StepA', 7)
        engine.memory.write('Truncated', 2)
        engine.step()
        self.assertEqual(engine.memory.read('AccumulatorA.Step'), 7)
        self.assertFalse(engine.memory.read('AccumulatorA.EnableOut'))
        self.assertEqual(engine.memory.read('TotalA'), [0, 22])
        self.assertEqual(engine.memory.read('SharedA'), [10, 20])

        engine.memory.write('EnableA', True)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'Array index outside bounds'):
            engine.step()
        self.assertEqual(engine.memory.values, before)
        self.assertEqual(engine.scan_count, 1)

        engine.memory.write('Truncated', 1)
        engine.step()
        self.assertEqual(engine.memory.read('TotalA'), [0, 7])
        self.assertEqual(engine.memory.read('SharedA'), [10, 27])

    def test_false_with_optional_routine_still_selects_indexed_output(self):
        self.set_dint_array('TotalA', (11, 22))
        engine = self.engine([
            'XIC(EnableA)LabAccumulator(AccumulatorA,StepA,TotalA[Truncated],SharedA);',
        ])
        self.assertEqual(engine.blockers, [])
        engine.memory.write('EnableA', False)
        engine.memory.write('Truncated', 2)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'Array index outside bounds'):
            engine.step()
        self.assertEqual(engine.memory.values, before)
        engine.memory.write('Truncated', 1)
        engine.step()
        self.assertEqual(engine.memory.read('TotalA'), [0, -1])

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

    def test_routine_this_reads_each_aoi_scan_mode_and_restores_the_program_context(self):
        from test_string_operations import string_data

        tags = self.root.find('Controller/Tags')
        tag = E.SubElement(tags, 'Tag', Name='ProgramRoutine', DataType='STRING', TagType='Base')
        string_data(E.SubElement(tag, 'Data', Format='Decorated'), 'saved')

        for name in ('LabAccumulator', 'LabScale'):
            E.SubElement(self.definition(name).find('LocalTags'), 'LocalTag', Name='SeenRoutine', DataType='STRING')
        read_routine = 'GSV(Routine,THIS,Name,SeenRoutine)'
        for mode in ('Logic', 'Prescan', 'EnableInFalse'):
            text = self.body(mode=mode)[0].find('Text')
            text.text = text.text.removesuffix(';') + read_routine + ';'

        logic = self.definition('LabScale').find('Routines/Routine[@Name="Logic"]')
        logic.remove(logic.find('RLLContent'))
        logic.set('Type', 'ST')
        E.SubElement(E.SubElement(logic, 'STContent'), 'Line', Number='0').text = (
            read_routine + '; Result := Raw * Gain;')
        engine = self.engine([
            'XIC(EnableA)LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);',
            'LabWrapper(NestedScale,RawValue,ScaledValue);',
            'GSV(Routine,THIS,Name,ProgramRoutine);',
        ])
        self.assertEqual(engine.blockers, [])
        self.assertEqual(engine.memory.string('AccumulatorA.SeenRoutine'), 'Prescan')

        engine.step()
        self.assertEqual(engine.memory.string('AccumulatorA.SeenRoutine'), 'Logic')
        self.assertEqual(engine.memory.string('NestedScale.Core.SeenRoutine'), 'Logic')
        self.assertEqual(engine.memory.string('ProgramRoutine'), 'MainRoutine')

        engine.memory.write('EnableA', False)
        engine.step()
        self.assertEqual(engine.memory.string('AccumulatorA.SeenRoutine'), 'EnableInFalse')
        self.assertEqual(engine.memory.string('ProgramRoutine'), 'MainRoutine')

    def test_routine_name_in_aoi_requires_this_and_a_writable_string(self):
        for operands, message in (
            ('Logic,Name,Total', 'requires THIS inside an AOI'),
            ('THIS,Name,Total', 'scalar LEN/DATA string'),
        ):
            with self.subTest(operands=operands):
                self.body()[0].find('Text').text = f'AFI()GSV(Routine,{operands});'
                engine = self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);'])
                self.assertTrue(any(message in item for item in engine.blockers), engine.blockers)

    def test_owner_this_tracks_the_same_aoi_instance_across_programs_and_tasks(self):
        from test_string_operations import string_data

        controller = self.root.find('Controller')
        for suffix in ('Program', 'Task'):
            E.SubElement(self.definition().find('Parameters'), 'Parameter', Name='Seen' + suffix,
                         DataType='STRING', Usage='InOut', Required='true')
            for prefix in ('Main', 'Aux'):
                tag = E.SubElement(controller.find('Tags'), 'Tag', Name=prefix + suffix + 'Name',
                                   DataType='STRING', TagType='Base')
                string_data(E.SubElement(tag, 'Data', Format='Decorated'), 'saved')
        for mode in ('Logic', 'Prescan', 'EnableInFalse'):
            text = self.body(mode=mode)[0].find('Text')
            text.text = text.text.removesuffix(';') + (
                'GSV(Program,THIS,Name,SeenProgram)GSV(Task,THIS,Name,SeenTask);')

        call = 'LabAccumulator(AccumulatorA,StepA,TotalA,SharedA,{prefix}ProgramName,{prefix}TaskName);'
        auxiliary = E.SubElement(controller.find('Programs'), 'Program', Name='AuxProgram',
                                 MainRoutineName='AuxLogic', Class='Standard')
        E.SubElement(auxiliary, 'Tags')
        routine = E.SubElement(E.SubElement(auxiliary, 'Routines'), 'Routine', Name='AuxLogic', Type='ST')
        E.SubElement(E.SubElement(routine, 'STContent'), 'Line', Number='0').text = call.format(prefix='Aux')
        task = E.SubElement(controller.find('Tasks'), 'Task', Name='AuxTask', Type='PERIODIC', Class='Standard',
                            Rate='10', Priority='2', Watchdog='500', InhibitTask='false', DisableUpdateOutputs='false')
        E.SubElement(E.SubElement(task, 'ScheduledPrograms'), 'ScheduledProgram', Name='AuxProgram')

        engine = self.engine(['XIC(EnableA)' + call.format(prefix='Main')])
        self.assertEqual(engine.blockers, [])
        expected = {'MainProgramName': 'MainProgram', 'MainTaskName': 'MainTask',
                    'AuxProgramName': 'AuxProgram', 'AuxTaskName': 'AuxTask'}
        for tag, name in expected.items():
            self.assertEqual(engine.memory.string(tag), name)  # Startup Prescan.
            engine.memory.write_string(tag, '')
        engine.memory.write('EnableA', False)
        engine.step()
        for tag, name in expected.items():
            self.assertEqual(engine.memory.string(tag), name)

    def test_nested_st_aoi_inherits_the_calling_program_and_task_names(self):
        scale = self.definition('LabScale')
        for name in ('SeenProgram', 'SeenTask'):
            E.SubElement(scale.find('LocalTags'), 'LocalTag', Name=name, DataType='STRING')
        logic = scale.find('Routines/Routine[@Name="Logic"]')
        logic.remove(logic.find('RLLContent'))
        logic.set('Type', 'ST')
        E.SubElement(E.SubElement(logic, 'STContent'), 'Line', Number='0').text = (
            'GSV(Program,THIS,Name,SeenProgram); GSV(Task,THIS,Name,SeenTask); Result := Raw * Gain;')
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        engine.step()
        self.assertEqual(engine.memory.string('NestedScale.Core.SeenProgram'), 'MainProgram')
        self.assertEqual(engine.memory.string('NestedScale.Core.SeenTask'), 'MainTask')

        harness = self.engine(mode='routine', routine='MainProgram/MainRoutine')
        self.assertTrue(any('ordinary v35 5580 project' in blocker for blocker in harness.blockers), harness.blockers)

    def test_task_this_configuration_in_aoi_reads_live_periodic_values_and_rolls_back(self):
        from test_gsv_configuration import scalar

        self.root.find('Controller/Tasks/Task').attrib.update(
            Type='PERIODIC', Rate='10', Priority='2', DisableUpdateOutputs='false')
        scalar(self.root.find('Controller/Tags'), 'WantedPriority', 'INT', 4)
        fields = [('Rate', 'DINT', 10000, 20000), ('Watchdog', 'DINT', 500000, 12345),
                  ('Priority', 'INT', 2, 4), ('DisableUpdateOutputs', 'DINT', 0, 1),
                  ('InhibitTask', 'DINT', 0, 1), ('Instance', 'DINT', 0, 0),
                  ('Status', 'DINT', 0, 0), ('OverlapCount', 'DINT', 0, 0)]
        for name, dtype, _, _ in fields:
            E.SubElement(self.definition().find('LocalTags'), 'LocalTag', Name='Seen' + name, DataType=dtype)
        reads = ''.join(f'GSV(Task,tHiS,{name},Seen{name})' for name, _, _, _ in fields)
        for mode in ('Logic', 'Prescan'):
            text = self.body(mode=mode)[0].find('Text')
            text.text = text.text.removesuffix(';') + reads + ';'
        engine = self.engine([
            'MOV(20000,TotalB)SSV(Task,THIS,Rate,TotalB);',
            'MOV(12345,TotalB)SSV(Task,THIS,Watchdog,TotalB);',
            'SSV(Task,THIS,Priority,WantedPriority);',
            'MOV(1,TotalB)SSV(Task,THIS,DisableUpdateOutputs,TotalB)SSV(Task,THIS,InhibitTask,TotalB);',
            'LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);',
            'CPT(TotalB,1/Truncated);',
        ])
        self.assertEqual(engine.blockers, [])
        for name, _, initial, _ in fields:
            self.assertEqual(engine.memory.read('AccumulatorA.Seen' + name), initial)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'divide'):
            engine.step(10)
        self.assertEqual(engine.memory.values, before)
        self.assertEqual(engine.fixed_scan_interval(), 10)
        engine.memory.write('Truncated', 1)
        engine.step(10)
        for name, _, _, updated in fields:
            self.assertEqual(engine.memory.read('AccumulatorA.Seen' + name), updated)

    def test_task_this_event_configuration_and_diagnostics_in_st_aoi(self):
        controller = self.root.find('Controller')
        task = E.SubElement(controller.find('Tasks'), 'Task', Name='EventTask', Type='EVENT', Class='Standard',
                            Rate='15', Priority='2', Watchdog='500', InhibitTask='false', DisableUpdateOutputs='true')
        E.SubElement(E.SubElement(task, 'ScheduledPrograms'), 'ScheduledProgram', Name='EventProgram')
        E.SubElement(task, 'EventInfo', EventTrigger='EVENT Instruction Only', EnableTimeout='true')
        program = E.SubElement(controller.find('Programs'), 'Program', Name='EventProgram',
                               Class='Standard', MainRoutineName='OnEvent')
        E.SubElement(program, 'Tags')
        main = E.SubElement(E.SubElement(program, 'Routines'), 'Routine', Name='OnEvent', Type='ST')
        E.SubElement(E.SubElement(main, 'STContent'), 'Line', Number='0').text = (
            'TotalB := 20000; SSV(Task,THIS,Rate,TotalB); EVENT(EventTask); '
            'LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);')
        for name in ('SeenRate', 'SeenTimeout', 'SeenStatus', 'SeenOverlaps'):
            E.SubElement(self.definition().find('LocalTags'), 'LocalTag', Name=name, DataType='DINT')
        logic = self.definition().find('Routines/Routine[@Name="Logic"]')
        logic.remove(logic.find('RLLContent'))
        logic.set('Type', 'ST')
        E.SubElement(E.SubElement(logic, 'STContent'), 'Line', Number='0').text = (
            'GSV(Task,THIS,Rate,SeenRate); GSV(Task,THIS,EnableTimeOut,SeenTimeout); '
            'GSV(Task,THIS,Status,SeenStatus); GSV(Task,THIS,OverlapCount,SeenOverlaps); Total := SeenRate;')
        diagnostics = 'GSV(Task,THIS,Status,SeenStatus)GSV(Task,THIS,OverlapCount,SeenOverlaps);'
        prescan = self.body(mode='Prescan')[0].find('Text')
        prescan.text = prescan.text.removesuffix(';') + diagnostics

        engine = self.engine(['EVENT(EventTask);', 'CPT(TotalB,1/Truncated);'])
        self.assertEqual(engine.blockers, [])
        self.assertEqual(engine.memory.read('AccumulatorA.SeenStatus'), 0)
        self.assertEqual(engine.memory.read('AccumulatorA.SeenOverlaps'), 0)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'divide'):
            engine.step(10)
        self.assertEqual(engine.memory.values, before)
        self.assertEqual(engine._task_event_status['eventtask'], 0)

        engine.memory.write('Truncated', 1)
        engine.step(10)
        self.assertEqual(engine.memory.read('TotalA'), 20000)
        self.assertEqual(engine.memory.read('AccumulatorA.SeenTimeout'), 1)
        self.assertEqual(engine.memory.read('AccumulatorA.SeenStatus'), 5)
        self.assertEqual(engine.memory.read('AccumulatorA.SeenOverlaps'), 1)

        line = logic.find('STContent/Line')
        for statement in ('SSV(Task,THIS,Status,SeenStatus);', 'GSV(Task,EventTask,Status,SeenStatus);'):
            with self.subTest(statement=statement):
                line.text = statement
                engine = self.engine(['EVENT(EventTask);'])
                self.assertTrue(any('AOI/harness' in blocker for blocker in engine.blockers), engine.blockers)

    def test_timing_this_reads_caller_snapshot_in_ladder_prescan_and_nested_st(self):
        self.root.find('Controller/Tasks/Task').set('DisableUpdateOutputs', 'false')
        fields = [('Program', 'LastScanTime', 'ProgramLast', 'DINT', 2, '<i'),
                  ('Program', 'MaxScanTime', 'ProgramMax', 'TIME32', 3, '<I'),
                  ('Task', 'LastScanTime', 'TaskLast', 'DINT', 8, '<i'),
                  ('Task', 'MaxScanTime', 'TaskMax', 'TIME32', 7, '<I'),
                  ('Task', 'StartTime', 'TaskStart', 'LINT', 13, '<q'),
                  ('Task', 'MinimumInterval', 'TaskMin', 'TIME', 14, '<Q'),
                  ('Task', 'MaximumInterval', 'TaskInterval', 'TIME', 15, '<Q')]
        for definition_name in ('LabAccumulator', 'LabScale'):
            locals_node = self.definition(definition_name).find('LocalTags')
            for _, _, tag, dtype, _, _ in fields:
                E.SubElement(locals_node, 'LocalTag', Name=tag, DataType=dtype)

        reads = [f'GSV({cls},THIS,{attribute},{tag})' for cls, attribute, tag, _, _, _ in fields]
        for mode in ('Logic', 'Prescan'):
            text = self.body(mode=mode)[0].find('Text')
            text.text = text.text.removesuffix(';') + ''.join(reads) + ';'
        logic = self.definition('LabScale').find('Routines/Routine[@Name="Logic"]')
        logic.remove(logic.find('RLLContent'))
        logic.set('Type', 'ST')
        E.SubElement(E.SubElement(logic, 'STContent'), 'Line', Number='0').text = (
            '; '.join(reads) + '; Result := Raw * Gain;')
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        self.assertEqual(engine.memory.read('AccumulatorA.TaskStart'), 0)
        engine.step()
        engine.step()

        sha = engine.project.sha256
        snapshot = {'Program': engine.program_timing_attributes('MainProgram', source_sha256=sha),
                    'Task': engine.task_scan_timing_attributes('MainTask', source_sha256=sha)}
        engine.step()
        for cls, _, tag, _, number, fmt in fields:
            expect = struct.unpack(fmt, snapshot[cls][number])[0]
            for instance in ('AccumulatorA', 'NestedScale.Core'):
                self.assertEqual(engine.memory.read(f'{instance}.{tag}', allow_time=True), expect)

    def test_timing_this_in_aoi_reads_an_ordinary_reset_and_restores_on_fault(self):
        self.root.find('Controller/Tasks/Task').set('DisableUpdateOutputs', 'false')
        E.SubElement(self.definition().find('LocalTags'), 'LocalTag', Name='TaskLast', DataType='DINT')
        self.body()[0].find('Text').text = 'GSV(Task,THIS,LastScanTime,TaskLast);'
        engine = self.engine([
            'XIC(EnableA)CLR(TotalB)SSV(Task,THIS,LastScanTime,TotalB);',
            'LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);',
            'CPT(TotalB,1/Truncated);',
        ])
        self.assertEqual(engine.blockers, [])
        engine.memory.write('EnableA', False)
        engine.memory.write('Truncated', 1)
        engine.step()
        engine.step()
        engine.memory.write('EnableA', True)
        engine.memory.write('Truncated', 0)
        before = copy.deepcopy(engine.memory.values), engine._task_measurements
        with self.assertRaisesRegex(ModelError, 'divide'):
            engine.step()
        self.assertEqual((engine.memory.values, engine._task_measurements), before)
        engine.memory.write('Truncated', 1)
        engine.step()
        self.assertEqual(engine.memory.read('AccumulatorA.TaskLast'), 0)

        self.body()[0].find('Text').text = 'SSV(Task,THIS,LastScanTime,TaskLast);'
        engine = self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);'])
        self.assertTrue(any('AOI/harness' in blocker for blocker in engine.blockers), engine.blockers)

    def test_aoi_program_disable_this_reads_live_self_disable_and_restores_after_fault(self):
        from test_gsv_configuration import scalar

        scalar(self.root.find('Controller/Tags'), 'DisableCommand', 'SINT', -1)
        locals_node = self.definition().find('LocalTags')
        E.SubElement(locals_node, 'LocalTag', Name='SeenDisable', DataType='SINT')
        E.SubElement(locals_node, 'LocalTag', Name='StartupDisable', DataType='SINT')
        self.body()[0].find('Text').text = 'GSV(Program,tHiS,DisableFlag,SeenDisable)MOV(SeenDisable,Total);'
        prescan = self.body(mode='Prescan')[0].find('Text')
        prescan.text = prescan.text.removesuffix(';') + 'GSV(Program,THIS,DisableFlag,StartupDisable);'

        scale = self.definition('LabScale')
        E.SubElement(scale.find('LocalTags'), 'LocalTag', Name='SeenDisable', DataType='DINT')
        logic = scale.find('Routines/Routine[@Name="Logic"]')
        logic.remove(logic.find('RLLContent'))
        logic.set('Type', 'ST')
        E.SubElement(E.SubElement(logic, 'STContent'), 'Line', Number='0').text = (
            'GSV(Program,THIS,DisableFlag,SeenDisable); Result := Raw * Gain;')

        engine = self.engine([
            'SSV(Program,THIS,DisableFlag,DisableCommand);',
            'LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);',
            'LabWrapper(NestedScale,RawValue,ScaledValue);',
            'CPT(TotalB,1/Truncated);',
        ])
        self.assertEqual(engine.blockers, [])
        self.assertEqual(engine.memory.read('AccumulatorA.StartupDisable'), 0)

        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError, 'divide'):
            engine.step()
        self.assertEqual(engine.memory.values, before)
        self.assertEqual(engine._disabled_programs, set())

        engine.memory.write('Truncated', 1)
        engine.step()
        self.assertEqual(engine.memory.read('TotalA'), 1)
        self.assertEqual(engine.memory.read('NestedScale.Core.SeenDisable'), 1)
        self.assertEqual(engine._disabled_programs, {'mainprogram'})

        engine.memory.write('DisableCommand', 0)
        engine.step()
        self.assertEqual(engine.memory.read('TotalA'), 1)
        self.assertEqual(engine._disabled_programs, {'mainprogram'})

    def test_aoi_program_disable_blocks_named_reads_and_setters(self):
        for statement in ('GSV(Program,MainProgram,DisableFlag,Total);',
                          'SSV(Program,THIS,DisableFlag,Total);'):
            with self.subTest(statement=statement):
                self.body()[0].find('Text').text = statement
                engine = self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);'])
                self.assertTrue(any('AOI/harness' in blocker for blocker in engine.blockers), engine.blockers)

    def test_definition_gsv_reads_own_metadata_in_ladder_and_nested_st(self):
        accumulator = self.definition()
        accumulator.attrib.update(Revision='7.002', RevisionExtension='production',
                                  Vendor='Demo Controls', EditedDate='2026-10-16T12:00:00.123456Z')
        fields = [('Name', 'DefName', 'STRING'), ('Vendor', 'DefVendor', 'STRING'),
                  ('RevisionExtendedText', 'DefExtension', 'STRING'), ('MajorRevision', 'DefMajor', 'DINT'),
                  ('MinorRevision', 'DefMinor', 'DINT'), ('LastEditDate', 'DefEdited', 'LINT')]
        for _, name, dtype in fields:
            E.SubElement(accumulator.find('LocalTags'), 'LocalTag', Name=name, DataType=dtype)
        self.body()[0].find('Text').text = ''.join(
            f'GSV(AddOnInstructionDefinition,THIS,{attribute},{name})'
            for attribute, name, _ in fields) + ';'

        scale = self.definition('LabScale')
        scale.set('Revision', '65535.4')
        E.SubElement(scale.find('LocalTags'), 'LocalTag', Name='DefName', DataType='STRING')
        E.SubElement(scale.find('LocalTags'), 'LocalTag', Name='DefMajor', DataType='DINT')
        logic = scale.find('Routines/Routine[@Name="Logic"]')
        logic.remove(logic.find('RLLContent'))
        logic.set('Type', 'ST')
        E.SubElement(E.SubElement(logic, 'STContent'), 'Line', Number='0').text = (
            'GSV(AddOnInstructionDefinition,this,Name,DefName); '
            'GSV(AddOnInstructionDefinition,this,MajorRevision,DefMajor); Result := Raw * Gain;')

        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        engine.step()
        self.assertEqual(engine.memory.string('AccumulatorA.DefName'), 'LabAccumulator')
        self.assertEqual(engine.memory.string('AccumulatorA.DefVendor'), 'Demo Controls')
        self.assertEqual(engine.memory.string('AccumulatorA.DefExtension'), 'production')
        self.assertEqual(engine.memory.read('AccumulatorA.DefMajor'), 7)
        self.assertEqual(engine.memory.read('AccumulatorA.DefMinor'), 2)
        self.assertEqual(engine.memory.read('AccumulatorA.DefEdited'), 1792152000123456)
        self.assertEqual(engine.memory.string('NestedScale.Core.DefName'), 'LabScale')
        self.assertEqual(engine.memory.read('NestedScale.Core.DefMajor'), 65535)

    def test_definition_gsv_rejects_wrong_context_operand_type_and_unknown_metadata(self):
        gsv = 'GSV(AddOnInstructionDefinition,THIS,MajorRevision,Total);'
        ordinary = self.engine([gsv.replace(',Total)', ',TotalA)')])
        self.assertTrue(any('requires a definition name' in b for b in ordinary.blockers))
        for logic, message in (
            (gsv.replace(',THIS,', ',LabAccumulator,'), 'requires THIS inside an AOI'),
            (gsv.replace('MajorRevision', 'SafetySignatureID'), 'Unsupported GSV AddOnInstructionDefinition'),
            (gsv.replace('MajorRevision', 'Name'), 'string tag'),
            (gsv.replace('MajorRevision', 'RevisionExtendedText'), 'is unavailable'),
            (gsv.replace('GSV', 'SSV'), 'SSV'),
        ):
            with self.subTest(logic=logic):
                self.body()[0].find('Text').text = logic
                engine = self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);'])
                self.assertTrue(any(message in b for b in engine.blockers), engine.blockers)
        E.SubElement(self.definition().find('LocalTags'), 'LocalTag', Name='DefEdited', DataType='LINT')
        self.body()[0].find('Text').text = gsv.replace('MajorRevision,Total', 'LastEditDate,DefEdited')
        for saved in ('2026-10-16T12:00:00', '2026-10-16T12:00:00.1234567Z', '2026-13-16T12:00:00Z'):
            with self.subTest(saved=saved):
                self.definition().set('EditedDate', saved)
                engine = self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);'])
                self.assertTrue(any('lasteditdate is unavailable' in b for b in engine.blockers), engine.blockers)

    def test_definition_gsv_reads_named_standard_headers_in_ladder_and_st(self):
        self.definition().set('Revision', '7.002')
        sections = self.root.find('Controller/AddOnInstructionDefinitions')
        sealed = E.SubElement(sections, 'EncodedData', EncodedType='AddOnInstructionDefinition',
                              Name='SealedLibrary', Class='Standard', Revision='5.1', SignatureID='A2345678')
        E.SubElement(sealed, 'Data').text = 'opaque-definition'
        reads = [
            'GSV(AddOnInstructionDefinition,lAbAcCuMuLaToR,MajorRevision,TotalA);',
            'GSV(AddOnInstructionDefinition,sealedlibrary,SignatureID,TotalB);',
        ]
        engine = self.engine(reads)
        self.assertEqual(engine.blockers, [])
        engine.step()
        self.assertEqual(engine.memory.read('TotalA'), 7)
        self.assertEqual(engine.memory.read('TotalB'), 0xA2345678 - (1 << 32))

        main = self.root.find('Controller/Programs/Program/Routines/Routine')
        main.remove(main.find('RLLContent'))
        main.set('Type', 'ST')
        body = E.SubElement(main, 'STContent')
        for number, text in enumerate(reads):
            E.SubElement(body, 'Line', Number=str(number)).text = text
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        engine.step()
        self.assertEqual(engine.memory.read('TotalA'), 7)
        self.assertEqual(engine.memory.read('TotalB'), 0xA2345678 - (1 << 32))

    def test_definition_gsv_named_read_rejects_instance_tag_and_harness(self):
        for name, reason in (('AccumulatorA', 'explicit Standard AOI definition'),
                             ('', 'requires a definition name')):
            with self.subTest(name=name):
                engine = self.engine([f'GSV(AddOnInstructionDefinition,{name},MajorRevision,TotalA);'])
                self.assertTrue(any(reason in b for b in engine.blockers), engine.blockers)
        engine = self.engine(['GSV(AddOnInstructionDefinition,LabAccumulator,MajorRevision,TotalA);'],
                             mode='routine', routine='MainProgram/MainRoutine')
        self.assertTrue(any('ordinary v35 5580 project' in b for b in engine.blockers), engine.blockers)

    def test_definition_gsv_signature_uses_only_unambiguous_header_value(self):
        definition = self.definition()
        history = E.SubElement(definition, 'SignatureHistory')
        E.SubElement(history, 'HistoryEntry', SignatureID='12345678')
        self.body()[0].find('Text').text = 'GSV(AddOnInstructionDefinition,THIS,SignatureID,Total);'
        calls = ['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);']
        for header in (None, '123456789', '16#ABCD', '12G45678'):
            with self.subTest(header=header):
                if header is not None:
                    definition.set('SignatureID', header)
                engine = self.engine(calls)
                self.assertTrue(any('signatureid is unavailable' in b for b in engine.blockers), engine.blockers)
        for header, expected in (('7f123456', 2131899478), ('FFFFFFFF', -1), ('00000000', 0)):
            with self.subTest(header=header):
                definition.set('SignatureID', header)
                engine = self.engine(calls)
                self.assertEqual(engine.blockers, [])
                engine.step()
                self.assertEqual(engine.memory.read('TotalA'), expected)
        definition.set('{urn:ambiguous}SignatureID', '7F123456')
        engine = self.engine(calls)
        self.assertTrue(any('signatureid is unavailable' in b for b in engine.blockers), engine.blockers)

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

    def test_output_requires_a_writable_compatible_reference(self):
        for target in ('4','EnableA','NestedScale'):
            with self.subTest(target=target):
                self.assertTrue(self.engine([f'LabAccumulator(AccumulatorA,StepA,{target},SharedA);']).blockers)

    def test_wrong_instance_type_and_operand_count_are_blocked(self):
        for rung in ('LabAccumulator(NestedScale,StepA,TotalA,SharedA);','LabAccumulator(AccumulatorA,StepA,TotalA);'):
            with self.subTest(rung=rung):self.assertTrue(self.engine([rung]).blockers)

    def test_same_instance_rebinds_inout_for_each_call(self):
        e=self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);','LabAccumulator(AccumulatorA,StepB,TotalB,SharedB);'])
        self.assertEqual(e.blockers, [])
        cache = e.memory._resolved
        address = e.memory.resolve('RawValue', 'MainProgram')
        e.step()
        self.assertEqual(e.memory.read('TotalA'),2);self.assertEqual(e.memory.read('TotalB'),5)
        self.assertEqual(e.memory.read('SharedA'),12);self.assertEqual(e.memory.read('SharedB'),23)
        self.assertIs(e.memory._resolved, cache)
        self.assertIs(e.memory.resolve('RawValue', 'MainProgram'), address)

    def test_unbound_frame_lookup_cannot_shadow_a_later_binding(self):
        e = self.engine()
        frame = '@AOI:unbound'
        memory = e.memory
        self.assertEqual(memory.read('SharedA', frame), 10)
        self.assertNotIn(('shareda', frame.lower()), memory._resolved)

        e.addons._set_frame(frame, {'shareda': ('SharedB', '')})
        self.assertEqual(memory.read('SharedA', frame), 20)
        e.addons._set_frame(frame, None)
        self.assertEqual(memory.read('SharedA', frame), 10)
        self.assertNotIn(('shareda', frame.lower()), memory._resolved)

    def test_failed_aoi_scan_retires_only_new_cached_addresses(self):
        self.set_dint_array('SharedA', (10, 20))
        e = self.engine([
            'LabAccumulator(AccumulatorA,StepA,TotalA,SharedA[Truncated]);',
            'CPT(ScaledValue,1/TotalB);',
        ])
        self.assertEqual(e.blockers, [])
        m = e.memory
        prior_address = m.resolve('SharedA[0]')
        m.write('Truncated', 1)
        m.write('TotalB', 0)
        cache = m._resolved
        before = cache.copy()
        binding = m.frames['@AOI:accumulatora']['shared']
        reached = ('shareda[1]', '')
        self.assertNotIn(reached, before)

        with self.assertRaisesRegex(ModelError, 'zero'):
            e.step()
        self.assertIs(m._resolved, cache)
        self.assertEqual(cache, before)
        self.assertIs(m.resolve('SharedA[0]'), prior_address)
        self.assertEqual(m.frames['@AOI:accumulatora']['shared'], binding)
        self.assertEqual(m.read('SharedA', mutable=False), [10, 20])

        m.write('TotalB', 1)
        e.step()
        self.assertIn(reached, cache)
        self.assertEqual(m.frames['@AOI:accumulatora']['shared'], ('SharedA[1]', ''))
        self.assertEqual(m.read('SharedA', mutable=False), [10, 22])

    def test_failed_scan_restores_rebound_frame_and_removes_new_instance(self):
        tag = self.root.find('./Controller/Tags/Tag[@Name="AccumulatorA"]')
        data = tag.find('Data')
        saved = data.find('Structure')
        E.SubElement(saved, 'DataValueMember', Name='Count', DataType='DINT', Value='0')
        tag.set('Dimensions', '2')
        data.remove(saved)
        array = E.SubElement(data, 'Array', DataType='LabAccumulator', Dimensions='2')
        for index in range(2):
            E.SubElement(array, 'Element', Index=f'[{index}]').append(copy.deepcopy(saved))
        self.set_dint_array('SharedA', (10, 20))
        e = self.engine([
            'LabAccumulator(AccumulatorA[0],StepA,TotalA,SharedA[Truncated]);',
            'LabAccumulator(AccumulatorA[Truncated],StepB,TotalB,SharedB);',
            'CPT(ScaledValue,1/StepB);',
        ])
        self.assertEqual(e.blockers, [])
        memory = e.memory
        memory.write('Truncated', 1)
        memory.write('StepB', 0)
        frames, instances = memory.frames, e.addons.instances
        frame = '@AOI:accumulatora[0]'
        original = frames[frame]
        values = copy.deepcopy(memory.values)
        self.assertEqual(set(instances), {'AccumulatorA[0]'})

        with self.assertRaisesRegex(ModelError, 'zero'):
            e.step()
        self.assertIs(memory.frames, frames)
        self.assertIs(e.addons.instances, instances)
        self.assertIs(frames[frame], original)
        self.assertNotIn('@AOI:accumulatora[1]', frames)
        self.assertEqual(set(instances), {'AccumulatorA[0]'})
        self.assertEqual(memory.values, values)

        memory.write('StepB', 3)
        e.step()
        self.assertEqual(frames[frame]['shared'], ('SharedA[1]', ''))
        self.assertEqual(frames['@AOI:accumulatora[1]']['shared'], ('SharedB', ''))
        self.assertEqual(set(instances), {'AccumulatorA[0]', 'AccumulatorA[1]'})
        self.assertEqual(memory.read('SharedA', mutable=False), [10, 22])
        self.assertEqual(memory.read('SharedB'), 23)

    def test_later_fault_rolls_back_local_output_inout_time_and_timer_metadata(self):
        e=self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);','CPT(TotalB,1/0);'])
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

    def bit_alias_accumulator(self, dtype, bit):
        definition = self.alias_accumulator()
        definition.set('ExecuteEnableInFalse','false')
        parameters = definition.find('Parameters')
        for name in ('Step','Total'):
            parameter = parameters.find(f'Parameter[@Name="{name}"]')
            parameter.set('DataType','BOOL')
            parameter.set('AliasFor',f'Flags[1].{bit}')
        E.SubElement(definition.find('LocalTags'),'LocalTag',Name='Flags',DataType=dtype,Dimensions='2')
        for name in ('AccumulatorA','AccumulatorB'):
            saved = self.root.find(f'Controller/Tags/Tag[@Name="{name}"]/Data/Structure')
            array = E.SubElement(saved,'ArrayMember',Name='Flags',DataType=dtype,Dimensions='2')
            E.SubElement(array,'Element',Index='[0]',Value='13')
            E.SubElement(array,'Element',Index='[1]',Value='5')
        self.body()[0].find('Text').text = 'XIC(Step)OTE(Total);'
        self.body(mode='Prescan')[0].find('Text').text = 'CLR(Count);'
        return definition

    def test_packed_aoi_aliases_preserve_sibling_bits_in_ladder_and_st(self):
        original = self.root
        for dtype,bit in (('SINT',7),('INT',15),('DINT',31)):
            with self.subTest(dtype=dtype):
                self.root = copy.deepcopy(original)
                definition = self.bit_alias_accumulator(dtype,bit)
                if dtype == 'INT':
                    logic = definition.find('Routines/Routine[@Name="Logic"]')
                    logic.remove(logic.find('RLLContent'))
                    logic.set('Type','ST')
                    E.SubElement(E.SubElement(logic,'STContent'),'Line',Number='0').text = 'Total := Step;'
                engine = self.engine(['LabAccumulator(AccumulatorA,EnableB,AReady,SharedA);'])
                self.assertEqual(engine.blockers, [])
                engine.step()
                self.assertTrue(engine.memory.read('AReady'))
                self.assertEqual(engine.memory.read('AccumulatorA.Flags'), [13,5-(1<<bit)])
                engine.memory.write('EnableB',False)
                engine.step()
                self.assertFalse(engine.memory.read('AReady'))
                self.assertEqual(engine.memory.read('AccumulatorA.Flags'), [13,5])
                engine.memory.write('AccumulatorA.Total',True)
                self.assertTrue(engine.memory.read('AccumulatorA.Step'))
                self.assertEqual(engine.memory.read('AccumulatorA.Flags'), [13,5-(1<<bit)])

    def test_saved_aoi_bit_alias_requires_agreement_and_a_complete_backing_word(self):
        self.bit_alias_accumulator('DINT',31)
        saved = self.root.find('Controller/Tags/Tag[@Name="AccumulatorA"]/Data/Structure')
        saved_bit = E.SubElement(saved,'DataValueMember',Name='Step',DataType='BOOL',Value='0')
        rung = ['LabAccumulator(AccumulatorA,EnableB,AReady,SharedA);']
        self.assertEqual(self.engine(rung).blockers, [])
        saved_bit.set('Value','1')
        self.assertTrue(any('Conflicting decorated AOI values for Flags[1].31' in value
                            for value in self.engine(rung).blockers))
        array = saved.find('ArrayMember[@Name="Flags"]')
        array.remove(array.find('Element[@Index="[1]"]'))
        self.assertTrue(any('requires its backing word' in value for value in self.engine(rung).blockers))

    def test_saved_full_word_alias_can_supply_bit_and_same_direction_overlap_is_rejected(self):
        definition = self.bit_alias_accumulator('DINT',31)
        parameters = definition.find('Parameters')
        output = parameters.find('Parameter[@Name="Total"]')
        output.set('DataType','DINT')
        output.set('AliasFor','Flags[1]')
        self.body()[0].find('Text').text = 'NOP();'
        saved = self.root.find('Controller/Tags/Tag[@Name="AccumulatorA"]/Data/Structure')
        array = saved.find('ArrayMember[@Name="Flags"]')
        array.remove(array.find('Element[@Index="[1]"]'))
        E.SubElement(saved,'DataValueMember',Name='Step',DataType='BOOL',Value='0')
        E.SubElement(saved,'DataValueMember',Name='Total',DataType='DINT',Value='5')
        rung = ['LabAccumulator(AccumulatorA,EnableB,TotalA,SharedA);']
        engine = self.engine(rung)
        self.assertEqual(engine.blockers, [])
        self.assertEqual(engine.project.initial['accumulatora']['Flags'], [13,5])
        parameter = E.SubElement(parameters,'Parameter',Name='WholeInput',Usage='Input',
                                 DataType='DINT',AliasFor='flags[01]')
        self.assertTrue(any('overlaps an existing target' in value for value in self.engine(rung).blockers))
        parameters.remove(parameter)
        parameters.find('Parameter[@Name="Step"]').set('AliasFor','Flags[1].32')
        self.assertTrue(any('bit must be within' in value for value in self.engine(rung).blockers))

    def named_bit_alias_record(self):
        definition = self.local_alias_record('State.Ready')
        definition.set('ExecuteEnableInFalse','false')
        for name in ('Step','Total'):
            definition.find(f'Parameters/Parameter[@Name="{name}"]').set('DataType','BOOL')
        members = self.root.find('Controller/DataTypes/DataType[@Name="AliasState"]/Members')
        E.SubElement(members,'Member',Name='HiddenFlags',DataType='SINT',Dimension='0',Hidden='true')
        for name,number in (('Ready','0'),('Fault','7')):
            E.SubElement(members,'Member',Name=name,DataType='BIT',Dimension='0',
                         Target='HiddenFlags',BitNumber=number)
        for name in ('AccumulatorA','AccumulatorB'):
            state = self.root.find(
                f'Controller/Tags/Tag[@Name="{name}"]/Data/Structure/StructureMember[@Name="State"]')
            E.SubElement(state,'DataValueMember',Name='Fault',DataType='BOOL',Value='1')
        self.body()[0].find('Text').text = 'XIC(Step)OTE(Total);'
        self.body(mode='Prescan')[0].find('Text').text = 'CLR(Count);'
        return members

    def test_named_bit_alias_shares_its_bool_and_preserves_other_fields(self):
        self.named_bit_alias_record()
        engine = self.engine(['LabAccumulator(AccumulatorA,EnableB,AReady,SharedA);'])
        self.assertEqual(engine.blockers, [])
        engine.step()
        self.assertTrue(all(engine.memory.read(ref) for ref in
                            ('AccumulatorA.Step','AccumulatorA.Total','AccumulatorA.State.Ready','AReady')))
        engine.memory.write('EnableB',False)
        engine.step()
        self.assertFalse(engine.memory.read('AccumulatorA.State.Ready'))
        self.assertFalse(engine.memory.read('AReady'))
        self.assertTrue(engine.memory.read('AccumulatorA.State.Fault'))
        self.assertEqual(engine.memory.read('AccumulatorA.State.Position'),21)
        engine.memory.write('AccumulatorA.Total',True)
        self.assertTrue(engine.memory.read('AccumulatorA.Step'))
        self.assertTrue(engine.memory.read('AccumulatorA.State.Ready'))
        self.assertNotIn('HiddenFlags',engine.memory.read('AccumulatorA.State'))

    def test_named_bit_alias_saved_value_needs_no_hidden_byte_and_rejects_conflicts(self):
        self.named_bit_alias_record()
        saved = self.root.find('Controller/Tags/Tag[@Name="AccumulatorA"]/Data/Structure')
        E.SubElement(saved,'DataValueMember',Name='Total',DataType='BOOL',Value='1')
        rung = ['LabAccumulator(AccumulatorA,EnableB,AReady,SharedA);']
        engine = self.engine(rung)
        self.assertEqual(engine.blockers, [])
        self.assertTrue(engine.project.initial['accumulatora']['State']['Ready'])
        E.SubElement(saved.find('StructureMember[@Name="State"]'),
                     'DataValueMember',Name='Ready',DataType='BOOL',Value='0')
        self.assertTrue(any('Conflicting decorated AOI values for State.Ready' in blocker
                            for blocker in self.engine(rung).blockers))

    def test_named_bit_alias_rejects_visible_hosts_and_overlapping_bits(self):
        members = self.named_bit_alias_record()
        host = members.find('Member[@Name="HiddenFlags"]')
        rung = ['LabAccumulator(AccumulatorA,EnableB,AReady,SharedA);']
        host.set('Hidden','false')
        self.assertTrue(any('hidden SINT host' in blocker for blocker in self.engine(rung).blockers))
        host.set('Hidden','true')
        members.find('Member[@Name="Fault"]').set('BitNumber','00')
        self.assertTrue(any('overlapping named BIT alias' in blocker for blocker in self.engine(rung).blockers))

    def set_dint_array(self, name, values):
        tag = self.root.find(f'Controller/Tags/Tag[@Name="{name}"]')
        length = str(len(values))
        tag.set('Dimensions', length)
        data = tag.find('Data')
        data.remove(data.find('DataValue'))
        array = E.SubElement(data, 'Array', DataType='DINT', Dimensions=length)
        for index, value in enumerate(values):
            E.SubElement(array, 'Element', Index=f'[{index}]', Value=str(value))
        return tag

    def larger_inout_array(self):
        parameter = self.definition().find('Parameters/Parameter[@Name="Shared"]')
        parameter.set('Dimensions', '2')
        return parameter, self.set_dint_array('SharedA', (10, 20, 30, 40))

    def test_larger_inout_array_exposes_actual_size_and_last_element_in_ladder_and_st(self):
        self.larger_inout_array()
        definition = self.definition()
        logic = definition.find('Routines/Routine[@Name="Logic"]')
        self.body()[0].find('Text').text = 'SIZE(Shared,0,Total)SUB(Total,1,Count)MOV(Step,Shared[Count]);'
        rung = ['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);']
        for language in ('RLL','ST'):
            with self.subTest(language=language):
                if language == 'ST':
                    logic.remove(logic.find('RLLContent'))
                    logic.set('Type','ST')
                    E.SubElement(E.SubElement(logic,'STContent'),'Line',Number='0').text = (
                        'SIZE(Shared,0,Total); Count := Total - 1; Shared[Count] := Step;')
                engine = self.engine(rung)
                self.assertEqual(engine.blockers, [])
                engine.step()
                self.assertEqual(engine.memory.read('TotalA'),4)
                self.assertEqual(engine.memory.read('SharedA'),[10,20,30,2])

    def test_larger_constant_inout_array_reports_actual_size(self):
        parameter,tag = self.larger_inout_array()
        parameter.set('Constant','true')
        tag.set('Constant','true')
        self.body()[0].find('Text').text = 'SIZE(Shared,0,Total);'
        engine = self.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);'])
        self.assertEqual(engine.blockers, [])
        engine.step()
        self.assertEqual(engine.memory.read('TotalA'),4)
        self.assertEqual(engine.memory.read('SharedA'),[10,20,30,40])

    def test_inout_extension_rejects_shorter_arrays_other_ranks_and_older_profiles(self):
        parameter,_ = self.larger_inout_array()
        rung = ['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);']
        for declared in ('5','2,2'):
            with self.subTest(declared=declared):
                parameter.set('Dimensions',declared)
                self.assertTrue(any('InOut dimensions' in blocker for blocker in self.engine(rung).blockers))
        parameter.set('Dimensions','2')
        self.root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(any('InOut dimensions' in blocker for blocker in self.engine(rung).blockers))

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

    def test_prescan_preview_rolls_back_instance_then_run_commits(self):
        tag = self.root.find('./Controller/Tags/Tag[@Name="AccumulatorA"]')
        data = tag.find('Data')
        saved = data.find('Structure')
        tag.set('Dimensions', '2')
        data.remove(saved)
        array = E.SubElement(data, 'Array', DataType='LabAccumulator', Dimensions='2')
        for index in range(2):
            E.SubElement(array, 'Element', Index=f'[{index}]').append(copy.deepcopy(saved))
        e = self.engine(['LabAccumulator(AccumulatorA[Truncated],StepA,TotalA,SharedA);'])
        self.assertEqual(e.blockers, [])
        m = e.memory
        m.write('Truncated', 1)
        m.write('TotalA', 47)
        values, frames, cache, instances = m.values, m.frames, m._resolved, e.addons.instances
        before = copy.deepcopy((values, frames, cache, instances))
        count = e.prescan_count

        e._apply_prescan(preview=True)
        self.assertEqual((m.values, m.frames, m._resolved, e.addons.instances), before)
        self.assertIs(m.values, values)
        self.assertIs(m.frames, frames)
        self.assertIs(m._resolved, cache)
        self.assertIs(e.addons.instances, instances)
        self.assertEqual(e.prescan_count, count)

        e.enter_run()
        self.assertEqual(m.read('AccumulatorA[1].Count'), 0)
        self.assertEqual(m.read('TotalA'), 0)
        self.assertIn('AccumulatorA[1]', instances)
        self.assertEqual(e.prescan_count, count + 1)

    def add_packed_output(self):
        """Add a copied flag that changes during each AOI scan mode."""
        E.SubElement(self.definition().find('Parameters'), 'Parameter', Name='Flag', DataType='BOOL',
                     Usage='Output', Required='true', Visible='true')
        for mode, text in (
            ('Logic', 'ADD(Count,Step,Count)MOV(Count,Total)ADD(Shared,Step,Shared)OTL(Flag);'),
            ('Prescan', 'CLR(Count)CLR(Total)OTU(Flag);'),
            ('EnableInFalse', 'MOV(-1,Total)OTU(Flag);'),
        ):
            self.body(mode=mode)[0].find('Text').text = text
        return self.root.find('./Controller/Tags')

    def test_bool_output_bit_preserves_signed_word_in_ladder_scan_modes(self):
        tags = self.add_packed_output()
        for dtype, width in (('SINT', 8), ('INT', 16), ('DINT', 32)):
            tag = E.SubElement(tags, 'Tag', Name='Packed'+dtype, DataType=dtype, TagType='Base')
            data = E.SubElement(tag, 'Data', Format='Decorated')
            E.SubElement(data, 'DataValue', DataType=dtype, Value=str(10 - (1 << (width - 1))))
        for dtype, width in (('SINT', 8), ('INT', 16), ('DINT', 32)):
            with self.subTest(dtype=dtype):
                word = 'Packed'+dtype
                engine = self.engine([
                    f'XIC(EnableA)LabAccumulator(AccumulatorA,StepA,TotalA,SharedA,{word}.{width-1});',
                ])
                self.assertEqual(engine.blockers, [])
                self.assertEqual(engine.memory.read(word), 10)
                engine.step()
                self.assertEqual(engine.memory.read(word), 10 - (1 << (width - 1)))
                engine.memory.write('EnableA', False)
                engine.step()
                self.assertEqual(engine.memory.read(word), 10)

    def test_st_bool_output_resolves_alias_and_indirect_bit(self):
        tags = self.add_packed_output()
        E.SubElement(tags, 'Tag', Name='PackedAlias', TagType='Alias', AliasFor='Truncated.1')
        main = self.root.find('./Controller/Programs/Program/Routines/Routine')
        main.remove(main.find('RLLContent'))
        main.set('Type', 'ST')
        content = E.SubElement(main, 'STContent')
        E.SubElement(content, 'Line', Number='0').text = (
            'LabAccumulator(AccumulatorA,StepA,TotalA,SharedA,PackedAlias);')
        E.SubElement(content, 'Line', Number='1').text = (
            'LabAccumulator(AccumulatorB,StepB,TotalB,SharedB,Truncated.[StepA]);')
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        engine.memory.write('Truncated', 8)
        engine.step()
        self.assertEqual(engine.memory.read('Truncated'), 14)
        engine.memory.write('StepA', 5)
        engine.step()
        self.assertEqual(engine.memory.read('Truncated'), 46)

    def test_bool_output_bit_keeps_destination_and_profile_guards(self):
        tags = self.add_packed_output()
        packed = tags.find('Tag[@Name="Truncated"]')
        packed.set('Constant', 'true')
        call = 'LabAccumulator(AccumulatorA,StepA,TotalA,SharedA,Truncated.2);'
        self.assertIn('Read-only destination', str(self.engine([call]).blockers))
        packed.set('Constant', 'false')
        self.assertIn('Output destination type must match exactly', str(self.engine([
            'LabAccumulator(AccumulatorA,StepA,Truncated.1,SharedA,Truncated.2);',
        ]).blockers))
        self.assertIn('InOut bit selections are unsupported', str(self.engine([
            'LabAccumulator(AccumulatorA,StepA,TotalA,Truncated.1,Truncated.2);',
        ]).blockers))
        self.root.find('Controller').set('MajorRev', '34')
        self.assertIn('Output bit selections require v35', str(self.engine([call]).blockers))

    def test_bool_output_bit_copy_rolls_back_after_later_fault(self):
        self.add_packed_output()
        engine = self.engine([
            'LabAccumulator(AccumulatorA,1,TotalA,SharedA,Truncated.2);',
            'CPT(TotalB,1/StepA);',
        ])
        self.assertEqual(engine.blockers, [])
        engine.memory.write('Truncated', 9)
        engine.memory.write('StepA', 0)
        with self.assertRaises(ModelError):
            engine.step()
        self.assertEqual(engine.memory.read('Truncated'), 9)
        self.assertEqual(engine.memory.read('AccumulatorA.Flag'), False)
        self.assertEqual(engine.memory.read('SharedA'), 10)
        engine.memory.write('StepA', 1)
        engine.step()
        self.assertEqual(engine.memory.read('Truncated'), 13)

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

    def test_array_instance_and_inout_shape_checks_do_not_snapshot_tags(self):
        tag = self.root.find('./Controller/Tags/Tag[@Name="AccumulatorA"]')
        data = tag.find('Data')
        saved = data.find('Structure')
        tag.set('Dimensions', '2')
        data.remove(saved)
        array = E.SubElement(data, 'Array', DataType='LabAccumulator', Dimensions='2')
        for index in range(2):
            E.SubElement(array, 'Element', Index=f'[{index}]').append(copy.deepcopy(saved))
        self.definition().set('ExecuteEnableInFalse', 'false')
        self.definition().find('./Parameters/Parameter[@Name="Shared"]').set('Dimensions', '2')
        self.body()[0].find('Text').text = 'ADD(Count,Step,Count)MOV(Count,Total)ADD(Shared[0],Step,Shared[0]);'
        self.set_dint_array('SharedA', (10, 20, 30))
        e = self.engine([
            'XIC(EnableA)LabAccumulator(AccumulatorA[1],StepA,TotalA,SharedA);',
            'CPT(TotalB,1/Truncated);',
        ])
        self.assertEqual(e.blockers, [])
        m = e.memory
        m.write('Truncated', 0)
        before = copy.deepcopy((m.values, m.frames, m._resolved, e.addons.instances, e.scan_count))
        with patch.object(m, '_remember', wraps=m._remember) as remember:
            with self.assertRaisesRegex(ModelError, 'zero'):
                e.step()
            self.assertEqual((m.values, m.frames, m._resolved, e.addons.instances, e.scan_count), before)
            m.write('Truncated', 1)
            e.step()
            m.write('EnableA', False)
            m.write('StepA', 7)
            e.step()
        self.assertFalse({'accumulatora', 'shareda'} & {call.args[0] for call in remember.call_args_list})
        self.assertEqual(m.read('AccumulatorA[1].Step'), 7)
        self.assertEqual(m.read('AccumulatorA[1].Count'), 2)
        self.assertEqual(m.read('TotalA'), 2)
        self.assertEqual(m.read('SharedA', mutable=False), [12, 20, 30])
        self.assertEqual(m.at('accumulatora', [0], mutable=False), before[0]['accumulatora'][0])

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
