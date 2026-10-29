"""Execution boundaries for typed integer ladder operations."""
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class IntegerMathTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def engine(self, rungs, dtype='LINT', a=0, b=1, dest=0, *, types=None,
               processor='1756-L85E', revision='35'):
        source = Path(__file__).resolve().parents[1] / 'samples/ConveyorDemo.L5X'
        root = ET.parse(source).getroot()
        controller = root.find('Controller')
        controller.set('ProcessorType', processor)
        controller.set('MajorRev', revision)
        tags = controller.find('Tags')
        for name, value, kind in zip(('WideA', 'WideB', 'WideDest', 'Result'),
                                    (a, b, dest, 0), (*(types or (dtype,) * 3), 'BOOL')):
            tag = ET.SubElement(tags, 'Tag', Name=name, DataType=kind, TagType='Base')
            data = ET.SubElement(tag, 'Data', Format='Decorated')
            ET.SubElement(data, 'DataValue', DataType=kind, Value=str(value))
        content = controller.find('./Programs/Program/Routines/Routine/RLLContent')
        content.clear()
        for number, text in enumerate(rungs):
            rung = ET.SubElement(content, 'Rung', Number=str(number), Type='N')
            ET.SubElement(rung, 'Text').text = text
        path = Path(self.tmp.name) / 'project.L5X'
        ET.ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)
        return Engine(Project(path))

    def run_value(self, instruction, dtype, a, b, expected):
        engine = self.engine([f'{instruction}(WideA,WideB,WideDest);'], dtype, a, b)
        self.assertEqual(engine.blockers, [])
        engine.step()
        self.assertEqual(engine.memory.read('WideDest'), expected)

    def test_add_subtract_multiply_all_wide_types(self):
        for dtype in ('LINT', 'USINT', 'UINT', 'UDINT', 'ULINT'):
            for instruction, a, b, expected in (('ADD', 200, 3, 203), ('SUB', 200, 3, 197), ('MUL', 40, 6, 240)):
                with self.subTest(dtype=dtype, instruction=instruction):
                    self.run_value(instruction, dtype, a, b, expected)

    def test_64_bit_math_does_not_round_through_float(self):
        for dtype in ('LINT', 'ULINT'):
            self.run_value('ADD', dtype, 9007199254740993, 2, 9007199254740995)
            self.run_value('MUL', dtype, 3002399751580331, 3, 9007199254740993)
        self.run_value('ADD', 'ULINT', 18446744073709551614, 1, 18446744073709551615)

    def test_division_truncates_exact_integer_quotient_toward_zero(self):
        for dtype in ('LINT', 'USINT', 'UINT', 'UDINT', 'ULINT'):
            self.run_value('DIV', dtype, 7, 2, 3)
        for a, b, expected in ((-7, 2, -3), (7, -2, -3), (-7, -2, 3),
                               (-9223372036854775808, 3, -3074457345618258602)):
            self.run_value('DIV', 'LINT', a, b, expected)
        self.run_value('DIV', 'ULINT', 18446744073709551615, 3, 6148914691236517205)

    def test_modulo_keeps_dividend_sign_and_full_width(self):
        for a, b, expected in ((-7, 3, -1), (7, -3, 1), (-7, -3, -1),
                               (-9223372036854775808, 3, -2)):
            self.run_value('MOD', 'LINT', a, b, expected)
        self.run_value('MOD', 'ULINT', 18446744073709551615, 7, 1)

    def test_comparisons_keep_exact_64_bit_values(self):
        for dtype in ('LINT', 'ULINT'):
            for instruction, expected in (('EQU', False), ('NEQ', True), ('LES', True),
                                           ('LEQ', True), ('GRT', False), ('GEQ', False)):
                with self.subTest(dtype=dtype, instruction=instruction):
                    e = self.engine([f'{instruction}(WideA,WideB)OTE(Result);'], dtype,
                                    9007199254740992, 9007199254740993)
                    self.assertEqual(e.blockers, []); e.step()
                    self.assertEqual(e.memory.read('Result'), expected)

    def test_limit_supports_normal_and_wrapped_ranges(self):
        for low, value, high, expected in ((3, 5, 7, True), (3, 8, 7, False),
                                            (7, 8, 3, True), (7, 5, 3, False)):
            e = self.engine(['LIM(WideA,WideDest,WideB)OTE(Result);'], 'ULINT', low, high, value)
            self.assertEqual(e.blockers, []); e.step()
            self.assertEqual(e.memory.read('Result'), expected)

    def test_bitwise_width_includes_unsigned_complement_and_signed_top_bit(self):
        for dtype, bits in (('LINT', 64), ('USINT', 8), ('UINT', 16), ('UDINT', 32), ('ULINT', 64)):
            maximum = (1 << (bits - 1)) - 1 if dtype == 'LINT' else (1 << bits) - 1
            e = self.engine(['NOT(WideA,WideDest);'], dtype)
            self.assertEqual(e.blockers, []); e.step()
            self.assertEqual(e.memory.read('WideDest'), -1 if dtype == 'LINT' else maximum)
            for instruction, expected in (('AND', 0), ('OR', maximum), ('XOR', maximum)):
                self.run_value(instruction, dtype, maximum, 0, expected)
        self.run_value('XOR', 'LINT', -9223372036854775808, 1, -9223372036854775807)

    def test_negate_absolute_move_clear_and_bounded_immediates(self):
        for instruction, source, expected in (('NEG', -9, 9), ('ABS', -9, 9), ('MOV', -9, -9)):
            e = self.engine([f'{instruction}(WideA,WideDest);'], a=source)
            self.assertEqual(e.blockers, []); e.step()
            self.assertEqual(e.memory.read('WideDest'), expected)
        e = self.engine(['MOV(7,WideDest);', 'ADD(WideDest,2,WideDest);', 'CLR(WideA);'], a=100)
        self.assertEqual(e.blockers, []); e.step()
        self.assertEqual(e.memory.read('WideDest'), 9); self.assertEqual(e.memory.read('WideA'), 0)

    def test_overflow_and_unsigned_underflow_roll_back_complete_scan(self):
        cases = (('LINT', 'ADD', 9223372036854775807, 1), ('LINT', 'SUB', -9223372036854775808, 1),
                 ('ULINT', 'ADD', 18446744073709551615, 1), ('USINT', 'SUB', 0, 1),
                 ('UINT', 'MUL', 65535, 2), ('UDINT', 'ADD', 4294967295, 1),
                 ('LINT', 'DIV', -9223372036854775808, -1))
        for dtype, instruction, a, b in cases:
            with self.subTest(dtype=dtype, instruction=instruction):
                e = self.engine(['MOV(99,SpeedCommand);', f'{instruction}(WideA,WideB,WideDest);'], dtype, a, b, 13)
                self.assertEqual(e.blockers, [])
                with self.assertRaisesRegex(ModelError, 'overflow'): e.step()
                self.assertEqual(e.memory.read('WideDest'), 13)
                self.assertEqual(e.memory.read('SpeedCommand'), 0)
                self.assertEqual((e.scan_count, e.time_ms), (0, 0))

    def test_false_rung_skips_arithmetic_faults_and_destination_changes(self):
        e = self.engine(['AFI()DIV(WideA,WideB,WideDest);'], a=7, b=0, dest=13)
        self.assertEqual(e.blockers, []); e.step()
        self.assertEqual(e.memory.read('WideDest'), 13)

    def test_divide_by_zero_rolls_back_and_does_not_claim_native_minor_fault(self):
        e = self.engine(['MOV(99,SpeedCommand);', 'DIV(WideA,WideB,WideDest);'], a=7, b=0, dest=13)
        self.assertEqual(e.blockers, [])
        with self.assertRaisesRegex(ModelError, 'divide by zero'): e.step()
        self.assertEqual(e.memory.read('WideDest'), 13)
        self.assertEqual(e.memory.read('SpeedCommand'), 0)

    def test_mixed_types_real_bool_and_unbounded_immediates_stay_blocked(self):
        for types in (('LINT', 'DINT', 'LINT'), ('LINT', 'ULINT', 'LINT'),
                      ('LINT', 'LINT', 'DINT'), ('LINT', 'REAL', 'LINT'), ('LINT', 'BOOL', 'LINT')):
            with self.subTest(types=types):
                self.assertTrue(self.engine(['ADD(WideA,WideB,WideDest);'], types=types).blockers)
        for operand in ('1.0', 'TRUE', '2147483648'):
            self.assertTrue(self.engine([f'ADD(WideA,{operand},WideDest);']).blockers)
        self.assertTrue(self.engine(['ADD(WideA,-1,WideDest);'], 'ULINT').blockers)

    def test_new_operations_require_explicit_v35_5580_profile(self):
        for processor, revision in (('1756-L75', '35'), ('1756-L85E', '34'), ('Unknown', '35')):
            with self.subTest(processor=processor, revision=revision):
                self.assertTrue(self.engine(['ADD(WideA,WideB,WideDest);'], processor=processor, revision=revision).blockers)
        # Previously available storage moves remain usable independently.
        e = self.engine(['MOV(WideA,WideDest);', 'CLR(WideB);'], processor='1756-L75', a=42)
        self.assertEqual(e.blockers, []); e.step()
        self.assertEqual(e.memory.read('WideDest'), 42)

    def test_writes_establish_unknown_destination_without_reading_old_value(self):
        for rung, expected in (('ADD(WideA,WideB,WideDest);', 10), ('MOV(WideA,WideDest);', 7),
                               ('NEG(WideA,WideDest);', -7), ('CLR(WideDest);', 0)):
            with self.subTest(rung=rung):
                e = self.engine([rung], a=7, b=3)
                e.memory.values['widedest'] = None
                e.step()
                self.assertEqual(e.memory.read('WideDest'), expected)

    def test_unknown_reached_source_faults_and_preserves_state(self):
        e = self.engine(['MOV(99,SpeedCommand);', 'ADD(WideA,WideB,WideDest);'], a=7, dest=13)
        e.memory.values['widea'] = None
        with self.assertRaisesRegex(ModelError, 'Unknown'): e.step()
        self.assertIsNone(e.memory.values['widea'])
        self.assertEqual(e.memory.read('WideDest'), 13)
        self.assertEqual(e.memory.read('SpeedCommand'), 0)

    def test_integer_division_differs_from_real_to_integer_rounding(self):
        for a, b, expected in ((7, 2, 3), (-7, 2, -3), (7, -2, -3), (-7, -2, 3)):
            e = self.engine([f'DIV({a},{b},SpeedCommand);'])
            self.assertEqual(e.blockers, []); e.step()
            self.assertEqual(e.memory.read('SpeedCommand'), expected)
        e = self.engine(['DIV(7.0,2,SpeedCommand);'])
        self.assertEqual(e.blockers, []); e.step()
        self.assertEqual(e.memory.read('SpeedCommand'), 4)

    def test_bundled_integer_lab_runs_with_exact_watched_values(self):
        from logixlab.server import SAMPLES
        self.assertIn('IntegerLab', SAMPLES)
        source = Path(__file__).resolve().parents[1] / 'samples/IntegerLab.L5X'
        e = Engine(Project(source))
        self.assertEqual(e.blockers, [])
        for _ in range(2): e.step()
        wanted = dict(SignedSum=9007199254740995, SignedQuotient=3002399751580331,
                      SignedRemainder=0, UnsignedSum=18446744073709551615,
                      UnsignedComplement=1, ByteSum=203, WordSum=60123,
                      DwordSum=4000000042, ExactComparison=True)
        for tag, value in wanted.items(): self.assertEqual(e.memory.read(tag), value)
        rows = {row['name']: row for row in e.memory.leaves()}
        self.assertEqual(rows['UnsignedSum']['value'], '18446744073709551615')
        self.assertTrue(e.report()['integer_execution']['arithmetic_available'])


if __name__ == '__main__':
    unittest.main()
