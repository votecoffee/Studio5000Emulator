"""Matching PID copies, lazy selections, solver ownership and transactions."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_ladder_pid as fixtures
from logixlab.model import ModelError
from logixlab.numeric_fill import scalar_count


class PIDCopyTests(unittest.TestCase):
    setUp = fixtures.LadderPIDTests.setUp

    @staticmethod
    def fields(root):
        controller = root.find('Controller')
        tags = controller.find('Tags')
        source = tags.find('Tag[@Name="Loop"]/Data/Structure')
        for name, value in (('CopyIndex', 99), ('CopyCount', 1)):
            tag = E.SubElement(tags, 'Tag', Name=name, DataType='DINT', TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value=str(value))
        for name in ('Loops', 'CopiedLoops'):
            tag = E.SubElement(tags, 'Tag', Name=name, DataType='PID', TagType='Base', Dimensions='3')
            array = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType='PID', Dimensions='3')
            for i in range(3):
                obj = copy.deepcopy(source)
                obj.find('DataValueMember[@Name="SP"]').set('Value', str(10 * (i + 1)))
                E.SubElement(array, 'Element', Index=f'[{i}]').append(obj)
        E.SubElement(tags, 'Tag', Name='SelectedLoop', TagType='Alias', AliasFor='Loops[CopyIndex]')
        types = controller.find('DataTypes')
        definition = E.SubElement(types, 'DataType', Name='PIDBundle', Family='NoFamily', Class='User')
        members = E.SubElement(definition, 'Members')
        E.SubElement(members, 'Member', Name='Loop', DataType='PID', Dimension='0')
        E.SubElement(members, 'Member', Name='Guard', DataType='DINT', Dimension='0')
        for name, guard in (('SourceBundle', 71), ('DestBundle', 91)):
            tag = E.SubElement(tags, 'Tag', Name=name, DataType='PIDBundle', TagType='Base')
            obj = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Structure', DataType='PIDBundle')
            pid = copy.deepcopy(source);pid.tag = 'StructureMember';pid.set('Name', 'Loop');obj.append(pid)
            E.SubElement(obj, 'DataValueMember', Name='Guard', DataType='DINT', Value=str(guard))

    def engine(self, lines, *, mutate=None, st=False):
        def fields(root):
            self.fields(root)
            if st:
                routine = root.find('./Controller/Programs/Program/Routines/Routine')
                routine.set('Type', 'ST');routine.remove(routine.find('RLLContent'))
                content = E.SubElement(routine, 'STContent')
                for i, text in enumerate(lines):E.SubElement(content, 'Line', Number=str(i)).text = text
            if mutate:mutate(root)
        return fixtures.LadderPIDTests.engine(self, lines=lines, mutate=fields)

    def checked(self, *args, **kwargs):
        e = self.engine(*args, **kwargs);self.assertEqual(e.blockers, []);return e

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values, e.memory.frames, e.addons.instances, e.last_timer,
                              e.time_ms, e.scan_count, e.scheduler_description(), e.trace))

    def fault(self, e, pattern):
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, pattern):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_matching_scalar_copies_flags_data_unknowns_and_detached_storage(self):
        for op in ('COP', 'CPS'):
            e = self.checked([f'{op}(Loop,LoopSnapshot,1);'])
            e.memory.write('Loop.SWM', True);e.memory.write('Loop.DATA[16]', 123.5)
            e.memory.values['loop']['DATA'][5] = None
            e.memory.values['loopsnapshot']['KP'] = None
            expected = copy.deepcopy(e.memory.values['loop'])
            e.step()
            self.assertEqual(e.memory.values['loopsnapshot'], expected)
            self.assertTrue(e.memory.read('LoopSnapshot.SWM'))
            e.memory.write('Loop.DATA[16]', 77)
            self.assertEqual(e.memory.read('LoopSnapshot.DATA[16]'), 123.5)

    def test_false_and_prescan_skip_unknown_length_and_live_indices(self):
        e = self.checked(['XIC(LoadTuning)CPS(SelectedLoop,CopiedLoops[CopyIndex],CopyCount);'])
        e.memory.values['copycount'] = None
        e.step()
        e.memory.write('LoadTuning', True)
        self.fault(e, 'Unknown|outside bounds')
        e.memory.write('CopyCount', 1);e.memory.write('CopyIndex', 1);e.step()
        self.assertEqual(e.memory.read('CopiedLoops[1].SP'), 20)

    def test_forward_overlap_and_captured_length_retain_existing_copy_rules(self):
        for op in ('COP', 'CPS'):
            e = self.checked([f'{op}(Loops[0],Loops[1],Loops[1].CTL);'])
            e.memory.write('Loops[0].CTL', 7);e.memory.write('Loops[1].CTL', 2)
            e.step()
            self.assertEqual([obj['SP'] for obj in e.memory.read('Loops')], [10, 10, 10])
            self.assertEqual(e.memory.read('Loops[2].CTL'), 7)
            e.memory.write('Loops[1].DATA[0]', 99)
            self.assertNotEqual(e.memory.read('Loops[2].DATA[0]'), 99)

    def test_nested_pid_udt_records_copy_unknowns_and_guards(self):
        for op in ('COP', 'CPS'):
            e = self.checked([f'{op}(SourceBundle,DestBundle,1);'])
            e.memory.values['sourcebundle']['Loop']['SP'] = None
            e.memory.write('SourceBundle.Loop.DATA[16]', 45)
            e.step()
            self.assertEqual(e.memory.values['destbundle'], e.memory.values['sourcebundle'])
            e.memory.write('SourceBundle.Loop.DATA[16]', 77)
            self.assertEqual(e.memory.read('DestBundle.Loop.DATA[16]'), 45)
            self.assertEqual(e.memory.read('DestBundle.Guard'), 71)

    def test_zero_length_checks_addresses_and_oversized_regions_clip(self):
        e = self.checked(['COP(Loops[CopyIndex],CopiedLoops[2],CopyCount);'])
        e.memory.write('CopyCount', 0);self.fault(e, 'outside bounds')
        e.memory.write('CopyIndex', 0)
        before = copy.deepcopy(e.memory.values);e.step();self.assertEqual(e.memory.values, before)
        e.memory.write('CopyCount', 20);e.step()
        self.assertEqual([obj['SP'] for obj in e.memory.read('CopiedLoops')], [10, 20, 10])

    def test_budget_and_later_errors_roll_back_copies_and_solver_state(self):
        for budget in (False, True):
            e = self.checked(['CPS(Loop,LoopSnapshot,1);', 'DIV(1,FaultDivisor,Quotient);'])
            e.memory.write('Loop.KP', 7)
            if budget:e.instruction_limit = scalar_count(e.project.default('PID'))
            else:e.memory.write('FaultDivisor', 0)
            self.fault(e, 'budget' if budget else 'zero')

    def test_copy_does_not_transfer_solver_history_and_ini_controls_restart(self):
        e = self.checked(['XIC(Execute)PID(Loop,PV,0,CV,0,0,0);',
                          'XIC(IntExecute)PID(IntLoop,PV,0,RawCV,0,0,0);',
                          'XIC(CaptureLoop)COP(Loop,IntLoop,1);'])
        e.memory.write('IntLoop.SP', 50);e.memory.write('IntLoop.KI', 1)
        e.memory.write('IntLoop.UPD', 1)
        for name, value in [('MINI', 0), ('MAXI', 100), ('MINCV', 0), ('MAXCV', 100)]:
            e.memory.write('IntLoop.' + name, value)
        e.memory.write('Execute', True);e.memory.write('IntExecute', True);e.step()
        old = copy.deepcopy(e.last_timer)
        self.assertEqual(e.memory.read('Loop.DATA[0]'), 15)
        self.assertEqual(e.memory.read('IntLoop.DATA[0]'), 30)
        e.memory.write('Execute', False);e.memory.write('IntExecute', False);e.memory.write('CaptureLoop', True);e.step()
        self.assertEqual(e.last_timer, old)
        self.assertEqual(e.memory.read('IntLoop.DATA[0]'), 15)
        e.memory.write('CaptureLoop', False);e.memory.write('IntExecute', True);e.step()
        self.assertEqual(e.memory.read('IntLoop.DATA[0]'), 45)
        e.memory.write('IntLoop.INI', False);e.step()
        self.assertEqual(e.memory.read('IntLoop.DATA[0]'), 15)

    def test_sample_loads_preset_before_pid_and_captures_after_calculation(self):
        e = fixtures.LadderPIDTests.engine(self)
        self.assertEqual(e.blockers, [])
        e.memory.write('Execute', True);e.memory.write('LoadTuning', True);e.memory.write('CaptureLoop', True);e.step()
        self.assertEqual(e.memory.read('CV'), 90)
        self.assertEqual(e.memory.read('LoopSnapshot.DATA[14]'), 90)
        e.memory.write('LoadTuning', False);e.memory.write('CaptureLoop', False);e.step()
        self.assertEqual(e.memory.read('CV'), 100)
        self.assertEqual(e.memory.read('LoopSnapshot.DATA[14]'), 90)

    def test_existing_st_copy_calls_and_for_effect_protection(self):
        e = self.checked(['CPS(SourceBundle,DestBundle,1);'], st=True)
        e.step();self.assertEqual(e.memory.read('DestBundle.Guard'), 71)
        e = self.engine(['FOR CopyIndex := 0 TO DestBundle.Guard DO CPS(SourceBundle,DestBundle,1); END_FOR;'], st=True)
        self.assertTrue(e.blockers)

    @staticmethod
    def aoi(root):
        controller = root.find('Controller')
        definition = E.SubElement(controller.find('AddOnInstructionDefinitions'), 'AddOnInstructionDefinition',
                                  Name='CopyPID', Class='Standard', ExecutePrescan='false',
                                  ExecutePostscan='false', ExecuteEnableInFalse='false')
        params = E.SubElement(definition, 'Parameters')
        for name, dtype, usage, required in [('EnableIn', 'BOOL', 'Input', 'false'), ('EnableOut', 'BOOL', 'Output', 'false'),
                                            ('Source', 'PID', 'InOut', 'true'), ('Dest', 'PID', 'InOut', 'true')]:
            E.SubElement(params, 'Parameter', Name=name, DataType=dtype, Usage=usage, Required=required,
                         Visible=required, TagType='Base')
        E.SubElement(definition, 'LocalTags')
        routine = E.SubElement(E.SubElement(definition, 'Routines'), 'Routine', Name='Logic', Type='RLL')
        E.SubElement(E.SubElement(E.SubElement(routine, 'RLLContent'), 'Rung', Number='0', Type='N'), 'Text').text = 'CPS(Source,Dest,1);'
        tag = E.SubElement(controller.find('Tags'), 'Tag', Name='CopyInstance', DataType='CopyPID', TagType='Base')
        obj = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Structure', DataType='CopyPID')
        for name in ('EnableIn', 'EnableOut'):E.SubElement(obj, 'DataValueMember', Name=name, DataType='BOOL', Value='0')

    def test_aoi_inout_bindings_copy_records_and_roll_back_on_later_fault(self):
        e = self.checked(['CopyPID(CopyInstance,Loop,LoopSnapshot);', 'DIV(1,FaultDivisor,Quotient);'], mutate=self.aoi)
        e.memory.write('FaultDivisor', 0);self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1);e.memory.write('Loop.KP', 9);e.step()
        self.assertEqual(e.memory.read('LoopSnapshot.KP'), 9)
        e.memory.write('Loop.KP', 4);self.assertEqual(e.memory.read('LoopSnapshot.KP'), 9)

    def test_pid_fill_mixed_types_and_other_operational_schemas_stay_excluded(self):
        for text in ('FLL(0,SourceBundle,1);', 'COP(Loop,CV,1);', 'COP(Loop,SourceBundle,1);'):
            self.assertTrue(self.engine([text]).blockers)
        def other(root):root.find('./Controller/DataTypes/DataType[@Name="PIDBundle"]/Members/Member[@Name="Loop"]').set('DataType', 'MESSAGE')
        self.assertTrue(self.engine(['COP(SourceBundle,DestBundle,1);'], mutate=other).blockers)
        def redefine(root):E.SubElement(root.find('./Controller/DataTypes'), 'DataType', Name='PID', Family='NoFamily', Class='User')
        self.assertTrue(self.engine(['COP(Loop,LoopSnapshot,1);'], mutate=redefine).blockers)

    def test_report_names_public_copy_and_private_history_boundaries(self):
        report = self.checked(['COP(Loop,LoopSnapshot,1);']).report()['aggregate_copy']
        self.assertIn('PID', report['types'])
        self.assertIn('destination solver history', report['pid'])
        self.assertFalse(report['native_runtime_parity'])


if __name__ == '__main__':
    unittest.main()
