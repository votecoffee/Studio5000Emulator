"""Typed MOV sources preserve declared precision and existing conversion rules."""
import itertools
import struct
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_numeric_storage as fixtures
import test_file_bcd as snapshots
import test_ladder_integer_literals as integers
from logixlab.model import ModelError, Project
from logixlab.numeric_storage import typed_literal
from logixlab.runtime import Engine

TYPES = ('SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'REAL', 'LREAL')


class MovLiteralTests(unittest.TestCase):
    setUp = fixtures.NumericStorageTests.setUp
    engine = fixtures.NumericStorageTests.engine
    checked = fixtures.NumericStorageTests.checked
    snapshot = staticmethod(snapshots.FileBcdTests.snapshot)
    fault = snapshots.FileBcdTests.fault

    def test_full_integer_ranges_establish_unknown_destinations_exactly(self):
        for dtype, text, value in integers.CASES:
            e = self.checked(['MOV(' + text + ',Results[1]);'], dest=dtype)
            e.step(); self.assertEqual(e.memory.read('Results'), [None, value, None])
            self.assertIs(type(e.memory.read('Results[1]')), int)

    def test_all_typed_integer_and_floating_forms_match_declared_source_tags(self):
        cases = [*integers.CASES, ('LREAL', '0.1L', .1), ('LREAL', '3.5L', 3.5)]
        for (source, text, value), dest in itertools.product(cases, TYPES):
            with self.subTest(source=source, text=text, dest=dest):
                e = self.checked(['MOV(Source,Results[0]);', 'MOV(' + text + ',Results[1]);'],
                                 source=source, dest=dest, value=value)
                e.step(); results = e.memory.read('Results')
                self.assertEqual(results[0], results[1]); self.assertIsNone(results[2])

    def test_integer_patterns_widening_and_narrowing_use_literal_type(self):
        for text, dest, expected in [('4294967295U', 'LINT', 4294967295),
                                     ('4294967295U', 'SINT', -1), ('4294967295U', 'DINT', -1),
                                     ('18446744073709551615UL', 'LINT', -1), ('-1L', 'ULINT', (1 << 64)-1),
                                     ('-9223372036854775808L', 'DINT', 0), ('-1L', 'UINT', 65535)]:
            e = self.checked(['MOV(' + text + ',Results[1]);'], dest=dest)
            e.step(); self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_case_leading_zero_sign_and_standalone_operand_boundaries(self):
        for text, dtype, expected in [('00042l', 'LINT', 42), ('+42L', 'LINT', 42),
                                      ('-0u', 'UDINT', 0), ('42ul', 'ULINT', 42),
                                      ('42Ul', 'ULINT', 42), ('42uL', 'ULINT', 42),
                                      (' .5l ', 'LREAL', .5), ('1.L', 'LREAL', 1.0), ('1E+2l', 'LREAL', 100.0)]:
            self.assertEqual(typed_literal(text), (dtype, expected))
            e = self.checked(['MOV(' + text + ',Results[1]);'], dest=dtype)
            e.step(); self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_floating_suffix_retains_binary64_range_precision_and_sign(self):
        for text, expected in [('0.1L', .1), ('1.0000000000000002L', 1.0000000000000002),
                               ('1e308L', 1e308), ('5e-324l', 5e-324), ('-0.0L', -0.0),
                               ('-1e308L', -1e308), ('1e-400L', 0.0)]:
            e = self.checked(['MOV(' + text + ',Results[1]);'], dest='LREAL')
            e.step(); self.assertEqual(struct.pack('<d', e.memory.read('Results[1]')), struct.pack('<d', expected))
        e = self.checked(['MOV(0.1,Results[0]);', 'MOV(0.1L,Results[1]);'], dest='LREAL')
        e.step(); self.assertEqual(e.memory.read('Results'), [.10000000149011612, .1, None])

    def test_lreal_to_real_precision_and_checked_nearest_even_integer_conversion(self):
        for text, dest, expected in [('1.0000000000000002L', 'REAL', 1.0), ('2.5L', 'DINT', 2),
                                     ('3.5L', 'DINT', 4), ('-2.5L', 'INT', -2), ('-3.5L', 'INT', -4)]:
            e = self.checked(['MOV(' + text + ',Results[1]);'], dest=dest)
            e.step(); self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_integer_to_double_conversion_rounds_after_source_range_check(self):
        for text, expected in [('9007199254740993L', 9007199254740992.0),
                               ('18446744073709551615UL', float(1 << 64)),
                               ('9223372036854775807L', float(1 << 63))]:
            e = self.checked(['MOV(' + text + ',Results[1]);'], dest='LREAL')
            e.step(); self.assertEqual(e.memory.read('Results[1]'), expected)

    def test_invalid_declared_ranges_and_nonfinite_literals_block_false_calls(self):
        for _, text in integers.BAD:
            self.assertTrue(self.engine(['AFI()MOV(' + text + ',Results[1]);'], dest='LREAL').blockers, text)
        for text in ['1e309L', '-1e309L', '1e999L']:
            self.assertTrue(self.engine(['AFI()MOV(' + text + ',Results[1]);'], dest='LREAL').blockers)

    def test_malformed_expression_radix_and_other_typed_forms_remain_blocked(self):
        for text in ['1LU', '1ULL', '1ULgarbage', '1L2', '1 UL', '- 1L', '1_000L',
                     '16#FFLU', 'LINT#1', '1.0UL', '1e3U', '(1L)', '1L+1L', 'ABS(1L)',
                     'TRUE', '2147483648', '16#1_0000_0000']:
            self.assertTrue(self.engine(['AFI()MOV(' + text + ',Results[1]);']).blockers, text)

    def test_false_and_prescan_skip_live_destination_index_and_required_values(self):
        e = self.checked(['XIC(StartPB)MOV(9007199254740993L,Results[Index]);'], dest='LINT')
        e.memory.values['source'] = None; e.memory.write('Index', 999); e.step()
        self.assertEqual(e.memory.read('Results'), [None]*3)
        e.memory.write('StartPB', True); self.fault(e, 'outside bounds')
        e.memory.write('Index', 1); e.step()
        self.assertEqual(e.memory.read('Results'), [None, 9007199254740993, None])

    def test_floating_destination_range_and_late_faults_restore_earlier_writes(self):
        for text, dest, match in [('128.0L', 'SINT', 'overflow'), ('-1.0L', 'ULINT', 'overflow'),
                                 ('1e308L', 'REAL', 'float|overflow'), ('9223372036854775808.0L', 'LINT', 'overflow')]:
            e = self.checked(['MOV(99,SpeedCommand);', 'MOV(' + text + ',Results[1]);'], dest=dest)
            self.fault(e, match)
        self.fault(self.checked(['MOV(18446744073709551615UL,Results[1]);',
                                 'DIV(1,0,SpeedCommand);'], dest='ULINT'), 'zero')

    def test_complete_literals_do_not_read_old_destination_or_unrelated_source(self):
        e = self.checked(['MOV(18446744073709551615UL,Results[1]);'], dest='ULINT')
        e.memory.values['source'] = None; e.step()
        self.assertEqual(e.memory.read('Results'), [None, (1 << 64)-1, None])

    def test_alias_udt_and_names_ending_in_literal_text_preserve_identity(self):
        def fields(root):
            c = root.find('Controller')
            members = E.SubElement(E.SubElement(c.find('DataTypes'), 'DataType', Name='Packet', Class='User'), 'Members')
            for name in ['Value', 'Guard']: E.SubElement(members, 'Member', Name=name, DataType='LINT', Dimension='0')
            record = E.SubElement(E.SubElement(E.SubElement(c.find('Tags'), 'Tag', Name='Packet1', DataType='Packet', TagType='Base'), 'Data', Format='Decorated'), 'Structure', DataType='Packet')
            E.SubElement(record, 'DataValueMember', Name='Guard', DataType='LINT', Value='777')
            E.SubElement(c.find('Tags'), 'Tag', Name='AliasValue', DataType='LINT', TagType='Alias', AliasFor='Packet1.Value')
            E.SubElement(c.find('Tags'), 'Tag', Name='Source1L', DataType='DINT', TagType='Alias', AliasFor='Source')
        e = self.checked(['MOV(9007199254740993L,AliasValue);', 'MOV(Source1L,Results[1]);'], mutate=fields)
        e.step(); self.assertEqual(e.memory.read('Packet1.Value'), 9007199254740993)
        self.assertEqual(e.memory.read('Packet1.Guard'), 777); self.assertEqual(e.memory.read('Results[1]'), 3)

    @staticmethod
    def aoi_fields(root):
        import test_aoi_queues as queues
        import test_lreal_results as results
        results.LrealResultTests.aoi_fields(root, 'LINT')
        queues.logic(root, ['MOV(9007199254740993L,Buffer[Index]);', 'MOV(3.5L,Item);',
                            'MOV(0.1L,Stack[Index]);'])
        queues.logic(root, ['AFI()MOV(1e308L,Stack[Index]);'], name='EnableInFalse')

    def test_warm_aoi_outputs_inout_local_precision_and_late_rollback(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests(); f.setUp(); self.addCleanup(f.doCleanups)
        e = f.checked(self.aoi_fields); e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 9007199254740993)
        self.assertEqual(e.memory.read('ItemA'), 4); self.assertEqual(e.memory.read('DriverA.Stack[1]'), .1)
        e.memory.write('IndexA', 2); e.memory.write('FaultDivisor', 0); self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1); e.step(); self.assertEqual(e.memory.read('BufferA[2]'), 9007199254740993)
        e.memory.write('EnabledA', False); e.memory.write('IndexA', 999); e.step()

    def test_old_profiles_dest_permissions_and_non_mov_arguments_do_not_widen(self):
        for key, value in [('ProcessorType', '1756-L75'), ('MajorRev', '34')]:
            self.assertTrue(self.engine(['AFI()MOV(1L,Results[1]);'],
                                       mutate=lambda root: root.find('Controller').set(key, value)).blockers)
        def constant(root): root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()MOV(1L,Results[1]);'], mutate=constant).blockers)
        for rung in ['ADD(1L,1L,Results[1]);', 'FLL(1L,Results[0],1);', 'CLR(1L);',
                     'MOV(1L,Results[1L]);', 'MOV(1L,StartPB);']:
            self.assertTrue(self.engine([rung]).blockers, rung)

    def test_report_states_source_precision_and_separate_scope(self):
        row = self.checked(['MOV(0.1L,Results[1]);'], dest='LREAL').report()['numeric_storage']['typed_mov_literals']
        self.assertEqual(row['integer_types'], ['LINT', 'UDINT', 'ULINT'])
        self.assertEqual(row['floating_type'], 'LREAL'); self.assertFalse(row['native_runtime_parity'])

    def test_sample_precision_guards_and_fault_retry(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, []); e.step()
        self.assertEqual(e.memory.read('MovLitSelected'), [None, None, 903])
        e.memory.write('MovLitEnabled', True); e.step()
        for name, expected in [('MovLitSigned', -(1 << 63)), ('MovLitUnsigned', (1 << 64)-1),
                               ('MovLitDword', (1 << 32)-1), ('MovLitWrapped', -1),
                               ('MovLitZeroExtended', (1 << 32)-1), ('MovLitDouble', .1),
                               ('MovLitDefault', .10000000149011612), ('MovLitRounded', 4),
                               ('MovLitLarge', 1e308), ('MovLitTiny', 5e-324)]:
            self.assertEqual(e.memory.read(name), expected)
        self.assertEqual(struct.pack('<d', e.memory.read('MovLitNegativeZero')), struct.pack('<d', -0.0))
        for name in ['MovLitRangeFault', 'MovLitFloatRangeFault']:
            e.memory.write(name, True); self.fault(e, 'overflow|float'); e.memory.write(name, False); e.step()
        e.memory.write('MovLitIndex', 1); e.memory.write('MovLitLateDivisor', 0); self.fault(e, 'zero')
        self.assertEqual(e.memory.read('MovLitSelected'), [9007199254740993, None, 903])
        e.memory.write('MovLitLateDivisor', 1); e.step()
        self.assertEqual(e.memory.read('MovLitSelected'), [9007199254740993]*2+[903])
        e.memory.write('MovLitEnabled', False); e.memory.write('MovLitIndex', 999); e.step()
