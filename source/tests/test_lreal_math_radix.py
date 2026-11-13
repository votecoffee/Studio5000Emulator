"""Radix source decoding is scoped to standalone binary64 ladder math."""
import itertools
import math
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_lreal_math_literals as fixtures
from logixlab.model import ModelError, Project, literal
from logixlab.runtime import Engine


class LrealMathRadixTests(unittest.TestCase):
    setUp = fixtures.LrealMathLiteralTests.setUp
    engine = fixtures.LrealMathLiteralTests.engine
    checked = fixtures.LrealMathLiteralTests.checked
    snapshot = staticmethod(fixtures.LrealMathLiteralTests.snapshot)
    fault = fixtures.LrealMathLiteralTests.fault

    def test_nineteen_forms_accept_three_bases_and_four_declared_word_types(self):
        expected = {**fixtures.BINARY, **fixtures.UNARY}
        for name, base, suffix in itertools.product(expected, (2, 8, 16), ('', 'L', 'U', 'UL')):
            word = f'{base}#1{suffix}'; args = word+','+word if name in fixtures.BINARY else word
            e = self.checked([f'{name}({args},Results[1]);']); e.step()
            self.assertEqual(e.memory.read('Results'), [None, expected[name], None], (name, word))

    def test_sign_width_zero_fill_grouping_and_binary64_promotion(self):
        for word, expected in [('16#FFFFFFFF', -1.0), ('8#37777777777', -1.0),
                ('2#'+'1'*32, -1.0), ('16#FFFFFFFFL', 4294967295.0),
                ('16#FFFFFFFFFFFFFFFFL', -1.0), ('16#FFFFFFFFFFFFFFFFUL', 18446744073709551616.0),
                ('16#8000000000000000L', -9223372036854775808.0), ('16#0000 FFFFl', 65535.0),
                ('2#1_010uL', 10.0)]:
            e = self.checked([f'ADD({word},0.0L,Results[1]);']); e.step(); self.assertEqual(e.memory.read('Results[1]'), expected)
        e = self.checked(['SUB(16#0020000000000001L,9007199254740992L,Results[1]);']); e.step()
        self.assertEqual(e.memory.read('Results[1]'), 0.0)
        e = self.checked(['SQR(16#1000001U,Results[1]);']); e.step(); self.assertEqual(e.memory.read('Results[1]'), math.sqrt(16777217))

    def test_lreal_tag_selection_with_radix_in_both_binary_positions(self):
        expected = {'ADD':(4, 4), 'SUB':(2, -2), 'MUL':(3, 3), 'DIV':(3, 0), 'MOD':(0, 1), 'XPY':(3, 1)}
        for name, position in itertools.product(expected, range(2)):
            args = 'Source,16#1UL' if position == 0 else '16#1UL,Source'
            e = self.checked([f'{name}({args},Results[1]);'], source='LREAL', dest='DINT', value=3)
            e.step(); self.assertEqual(e.memory.read('Results[1]'), expected[name][position], (name, position))
        e = self.checked(['ADD(16#FFFFFFFF,Source,Results[1]);'], source='LREAL', dest='REAL', value=3)
        e.step(); self.assertEqual(e.memory.read('Results[1]'), 2.0)

    def test_all_numeric_results_convert_after_binary64_calculation(self):
        for dtype in ['SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'REAL', 'LREAL']:
            e = self.checked(['DIV(16#3U,2.0L,Results[1]);'], dest=dtype); e.step()
            self.assertEqual(e.memory.read('Results[1]'), 1.5 if dtype in ('REAL', 'LREAL') else 2)
        e = self.checked(['SUB(16#1000001U,0.0L,Results[1]);'], dest='REAL'); e.step()
        self.assertEqual(e.memory.read('Results[1]'), 16777216.0)
        e = self.checked(['XPY(16#4U,0.5L,Results[1]);'], dest='SINT'); e.step(); self.assertEqual(e.memory.read('Results[1]'), 2)

    def test_real_integer_comparison_bitwise_and_default_helpers_keep_their_scope(self):
        for call in ['ADD(16#1U,1U,Results[1]);', 'SQR(16#1U,Results[1]);', 'LN(16#1U,Results[1]);']:
            self.assertTrue(self.engine(['AFI()'+call], dest='REAL').blockers, call)
        self.assertTrue(self.engine(['AFI()SQR(16#1L,Results[1]);'], dest='LINT').blockers)
        self.assertTrue(self.engine(['AFI()EQU(Source,16#1L)OTE(RunLatch);'], source='LREAL').blockers)
        e = self.checked(['ADD(1L,1L,Results[1]);'])
        from logixlab.numeric_storage import lreal_math_source, math_source_type
        for helper in [lreal_math_source, math_source_type]:
            with self.assertRaises(ModelError):helper(e.memory, '16#1L', 'MainProgram')
        self.assertEqual(literal('16#FFFFFFFF'), 4294967295)

    def test_bad_words_expressions_permissions_and_target_profiles_block_false_calls(self):
        for word in ['16#100000000', '16#100000000U', '16#10000000000000000UL', '2#2UL', '8#8L',
                     '16#FF_L', '16#FF L', '-16#1L', '(16#1L)', '16#1L+1L']:
            for name in ['ADD', 'XPY', 'SQR']:
                args = word+',1L' if name != 'SQR' else word
                self.assertTrue(self.engine([f'AFI(){name}({args},Results[1]);']).blockers, (name, word))
        for key, value in [('ProcessorType', '1756-L75'), ('MajorRev', '34')]:
            def target(root):root.find('Controller').set(key, value)
            self.assertTrue(self.engine(['AFI()ADD(16#1L,1L,Results[1]);'], mutate=target).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()SQR(16#1U,Results[1]);'], mutate=constant).blockers)

    def test_false_prescan_dynamic_alias_unknown_sources_and_complete_writes(self):
        def fields(root):
            tags = root.find('./Controller/Tags'); tag = E.SubElement(tags, 'Tag', Name='AddressIndex', DataType='DINT', TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='99')
            E.SubElement(tags, 'Tag', Name='Selected', DataType='LREAL', TagType='Alias', AliasFor='Results[AddressIndex]')
        e = self.checked(['XIC(StartPB)ADD(Source,16#1U,Selected);'], source='LREAL', mutate=fields)
        e.memory.values['source'] = None; e.step(); self.assertEqual(e.memory.read('Results'), [None, None, None])
        e.memory.write('StartPB', True); self.fault(e, 'Unknown|outside bounds')
        e.memory.write('Source', 3); e.memory.write('AddressIndex', 1); e.step()
        self.assertEqual(e.memory.read('Results'), [None, 4.0, None])

    def test_zero_domain_conversion_overflow_and_later_fault_restore_warm_state(self):
        for call, dest, error in [('DIV(16#1L,16#0U,Results[1]);', 'LREAL', 'zero'),
                ('LN(16#FFFFFFFFFFFFFFFFL,Results[1]);', 'LREAL', 'finite'),
                ('XPY(16#2U,1025L,Results[1]);', 'LREAL', 'finite'),
                ('ADD(16#FFFFFFFFFFFFFFFFUL,0.0L,Results[1]);', 'ULINT', 'overflow'),
                ('XPY(16#FFFFFFFFFFFFFFFFUL,2.0L,Results[1]);', 'REAL', 'finite REAL')]:
            e = self.checked([call], dest=dest); self.fault(e, error)
        e = self.checked(['ADD(Source,16#1U,Results[1]);', 'DIV(1,Mask,Mask);'], source='LREAL')
        e.memory.write('Mask', 0); self.fault(e, 'zero'); e.memory.write('Mask', 1); e.step()
        self.assertEqual(e.memory.read('Results[1]'), 4.0)

    def test_warm_aoi_inputs_outputs_inout_and_local_state_remain_atomic(self):
        import test_aoi_queues as queues
        h = queues.AOIQueueTests(); h.setUp(); self.addCleanup(h.doCleanups)
        def fields(root):
            fixtures.LrealMathLiteralTests.aoi_fields(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text = text.text.replace('0.1L', '16#1U').replace('SQR(4U,', 'SQR(16#4U,').replace('0.5L,1L,', '0.5L,2#1UL,')
        e = h.checked(fields); value = e.memory.read('ValueA'); e.step()
        self.assertEqual((e.memory.read('BufferA[1]'), e.memory.read('ItemA'), e.memory.read('DriverA.Stack[1]')), (value+1, 2.0, .5))
        e.memory.write('IndexA', 2); e.memory.write('FaultDivisor', 0); self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1); e.step(); self.assertEqual(e.memory.read('BufferA[2]'), value+1)
        e.memory.write('EnabledA', False); e.memory.write('IndexA', 999); e.step()

    def test_public_sample_exact_values_metadata_and_recovery(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, []); e.step(); self.assertEqual(e.memory.read('RadixMathSelected'), [101.0, None, 999.0])
        e.memory.write('RadixMathEnabled', True); e.memory.write('RadixMathIndex', 1); e.step()
        for name, value in {'Sum':4.0, 'Unsigned':18446744073709551616.0, 'Signed':9223372036854775808.0,
                            'Loss':0.0, 'Root':math.sqrt(16777217), 'Power':2, 'Quotient':1.5,
                            'Match':True, 'Selected':[101.0, 2.0, 999.0]}.items():
            self.assertEqual(e.memory.read('RadixMath'+name), value, name)
        e.memory.write('RadixMathSource', 5); e.memory.write('RadixMathLateDivisor', 0); self.fault(e, 'zero')
        e.memory.write('RadixMathLateDivisor', 1); e.step(); self.assertEqual(e.memory.read('RadixMathSum'), 6.0)
        self.assertEqual(e.memory.read('RadixMathSelected'), [101.0, 4.0, 999.0]); self.assertFalse(e.memory.read('RadixMathMatch'))
        profile = e.report()['scalar_math']['lreal_arithmetic']['radix_sources']
        self.assertEqual(profile['bases'], [2, 8, 16]); self.assertFalse(profile['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
