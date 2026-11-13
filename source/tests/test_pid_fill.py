"""Typed zero PID FLL, bounded windows, lifecycle and transactional effects."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_pid_copies as copies
import test_ladder_pid as fixtures
from logixlab.numeric_fill import scalar_count


class PIDFillTests(unittest.TestCase):
    setUp = copies.PIDCopyTests.setUp
    fields = staticmethod(copies.PIDCopyTests.fields)
    engine = copies.PIDCopyTests.engine
    checked = copies.PIDCopyTests.checked
    snapshot = staticmethod(copies.PIDCopyTests.snapshot)
    fault = copies.PIDCopyTests.fault

    def assert_zero(self, e, ref):
        actual = e.memory.read(ref)
        self.assertEqual(actual, e.project.default('PID'))
        self.assertIs(type(actual['CTL']), int)
        self.assertTrue(all(type(value) is float for name, value in actual.items() if name not in ('CTL', 'DATA')))
        self.assertTrue(all(type(value) is float for value in actual['DATA']))

    def test_zero_establishes_unknown_fields_and_all_real_data_with_typed_values(self):
        e = self.checked(['FLL(0,Loop,1);'])
        e.memory.values['loop'] = {name: [None] * 17 if name == 'DATA' else None
                                   for name in e.project.default('PID')}
        other = copy.deepcopy(e.memory.values['intloop'])
        e.step()
        self.assert_zero(e, 'Loop')
        self.assertFalse(e.memory.read('Loop.INI'))
        self.assertEqual(e.memory.values['intloop'], other)

    def test_selected_array_fills_clip_preserve_guards_and_detach_data(self):
        e = self.checked(['FLL(0,Loops[1],100);'])
        guard = copy.deepcopy(e.memory.values['loops'][0])
        e.step()
        self.assert_zero(e, 'Loops[1]');self.assert_zero(e, 'Loops[2]')
        self.assertEqual(e.memory.values['loops'][0], guard)
        e.memory.write('Loops[1].DATA[0]', 15)
        self.assertEqual(e.memory.read('Loops[2].DATA[0]'), 0.0)

    def test_nested_udt_whole_and_member_fills_retain_unselected_members(self):
        for ref in ('SourceBundle', 'SourceBundle.Loop'):
            e = self.checked([f'FLL(0,{ref},1);'])
            e.step();self.assert_zero(e, 'SourceBundle.Loop')
            self.assertEqual(e.memory.read('SourceBundle.Guard'), 0 if ref == 'SourceBundle' else 71)
            self.assertEqual(e.memory.read('DestBundle.Guard'), 91)

    def test_dynamic_source_is_lazy_when_false_or_zero_length_and_retries_after_invalid_pattern(self):
        e = self.checked(['XIC(LoadTuning)FLL(FaultDivisor,SelectedLoop,CopyCount);'])
        e.memory.values['faultdivisor'] = None
        e.step()
        e.memory.write('LoadTuning', True);e.memory.write('CopyIndex', 1);e.memory.write('CopyCount', 0)
        e.step();self.assertEqual(e.memory.read('Loops[1].SP'), 20)
        e.memory.write('CopyCount', 1);self.fault(e, 'Unknown')
        e.memory.write('FaultDivisor', -1);self.fault(e, 'All-ones FLL excludes PID')
        e.memory.write('CopyCount', 0);e.step()
        e.memory.write('CopyCount', 1);e.memory.write('FaultDivisor', 0);e.step()
        self.assert_zero(e, 'Loops[1]')

    def test_live_selected_addresses_lengths_and_unknown_indices_still_fault(self):
        e = self.checked(['XIC(LoadTuning)FLL(0,SelectedLoop,CopyCount);'])
        e.step();e.memory.write('LoadTuning', True)
        self.fault(e, 'outside bounds')
        e.memory.write('CopyIndex', 0)
        for value in (-1, 100001):
            e.memory.write('CopyCount', value);self.fault(e, 'length')
        e.memory.values['copycount'] = None;self.fault(e, 'Unknown')
        e.memory.write('CopyCount', 1);e.step();self.assert_zero(e, 'Loops[0]')

    def test_count_stored_inside_the_filled_record_is_captured_before_writes(self):
        e = self.checked(['FLL(0,Loops[0],Loops[0].CTL);'])
        e.memory.write('Loops[0].CTL', 2)
        e.step();self.assert_zero(e, 'Loops[0]');self.assert_zero(e, 'Loops[1]')
        self.assertEqual(e.memory.read('Loops[2].SP'), 30)

    def test_budget_and_later_faults_restore_fills_time_and_scheduler(self):
        for budget in (True, False):
            e = self.checked(['FLL(0,SourceBundle,1);', 'DIV(1,FaultDivisor,Quotient);'])
            if budget:e.instruction_limit = scalar_count(e.project.default('PID'))
            else:e.memory.write('FaultDivisor', 0)
            self.fault(e, 'budget' if budget else 'zero')

    def test_private_history_is_retained_until_the_next_ini_initialization(self):
        e = fixtures.LadderPIDTests.engine(self)
        self.assertEqual(e.blockers, [])
        e.memory.write('Execute', True);e.step()
        previous = copy.deepcopy(e.last_timer)
        self.assertEqual(e.memory.read('Loop.DATA[0]'), 15)
        e.memory.write('Execute', False);e.memory.write('ClearLoop', True);e.step()
        self.assert_zero(e, 'Loop')
        self.assertEqual(e.memory.read('CV'), 45)
        self.assertEqual(e.last_timer, previous)
        e.memory.write('ClearLoop', False);e.memory.write('LoadTuning', True);e.memory.write('Execute', True);e.step()
        self.assertEqual(e.memory.read('Loop.DATA[0]'), 10)
        self.assertEqual(e.memory.read('CV'), 90)

    @staticmethod
    def aoi(root):
        copies.PIDCopyTests.aoi(root)
        root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text').text = 'FLL(0,Dest,1);'

    def test_aoi_inout_pid_clear_and_bindings_roll_back_after_later_fault(self):
        e = self.checked(['CopyPID(CopyInstance,Loop,LoopSnapshot);', 'DIV(1,FaultDivisor,Quotient);'], mutate=self.aoi)
        e.memory.write('FaultDivisor', 0);self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1);e.step();self.assert_zero(e, 'LoopSnapshot')
        self.assertEqual(e.memory.read('Loop.KP'), 1)

    def test_existing_st_fill_calls_and_for_write_protection(self):
        e = self.checked(['FLL(0,SourceBundle.Loop,1);'], st=True)
        e.step();self.assert_zero(e, 'SourceBundle.Loop')
        e = self.engine(['FOR CopyIndex := 0 TO SourceBundle.Guard DO FLL(0,SourceBundle,1); END_FOR;'], st=True)
        self.assertTrue(e.blockers)

    def test_invalid_patterns_permissions_redefinitions_and_other_records_are_excluded(self):
        for source in ('-1', '1', '0.0', 'TRUE', '18446744073709551615UL'):
            self.assertTrue(self.engine([f'AFI()FLL({source},Loop,1);']).blockers, source)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Loop"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()FLL(0,Loop,1);'], mutate=constant).blockers)
        def redefine(root):E.SubElement(root.find('./Controller/DataTypes'), 'DataType', Name='PID', Family='NoFamily', Class='User')
        self.assertTrue(self.engine(['FLL(0,Loop,1);'], mutate=redefine).blockers)
        def other(root):root.find('./Controller/DataTypes/DataType[@Name="PIDBundle"]/Members/Member[@Name="Loop"]').set('DataType', 'MESSAGE')
        self.assertTrue(self.engine(['FLL(0,SourceBundle,1);'], mutate=other).blockers)

    def test_sample_clear_before_load_and_reported_lifecycle_boundaries(self):
        e = fixtures.LadderPIDTests.engine(self)
        self.assertEqual(e.blockers, [])
        e.memory.write('ClearLoop', True);e.memory.write('LoadTuning', True)
        e.memory.write('Execute', True);e.memory.write('CaptureLoop', True);e.step()
        self.assertEqual(e.memory.read('CV'), 90)
        self.assertEqual(e.memory.read('LoopSnapshot.DATA[14]'), 90)
        e.memory.write('LoadTuning', False)
        self.fault(e, 'UPD|scaling')
        e.memory.write('LoadTuning', True);e.step();self.assertEqual(e.memory.read('CV'), 90)
        report = e.report()['aggregate_fill']['pid']
        self.assertIn('Zero only', report['pattern'])
        self.assertIn('INI', report['history'])
        self.assertFalse(report['native_runtime_parity'])


if __name__ == '__main__':
    unittest.main()
