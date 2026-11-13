"""Declared radix widths, binary64 ordering, limits and lazy atomic recovery."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_lreal_comparison_literals as fixtures
from logixlab.model import Project, literal
from logixlab.runtime import Engine


class LrealComparisonRadixTests(unittest.TestCase):
    setUp = fixtures.LrealComparisonLiteralTests.setUp
    engine = fixtures.LrealComparisonLiteralTests.engine
    checked = fixtures.LrealComparisonLiteralTests.checked
    snapshot = staticmethod(fixtures.LrealComparisonLiteralTests.snapshot)
    fault = fixtures.LrealComparisonLiteralTests.fault

    def test_six_relations_three_bases_four_widths_both_operand_positions(self):
        for name, base, suffix, position, value in itertools.product(fixtures.RELATIONS, (2, 8, 16), ('', 'L', 'U', 'UL'), range(2), range(3)):
            word = f'{base}#1{suffix}'; args = 'Source,'+word if position == 0 else word+',Source'
            e = self.checked([name+'('+args+')OTE(RunLatch);'], value=value); before = e.memory.read('Source'); e.step()
            expected = fixtures.EXPECTED[value if position == 0 else 2-value][fixtures.RELATIONS.index(name)]
            self.assertIs(e.memory.read('RunLatch'), expected, (name, word, position, value))
            self.assertEqual(e.memory.read('Source'), before)

    def test_declared_sign_width_groups_and_large_integer_rounding(self):
        for word, value in [('16#FFFFFFFF', -1.0), ('8#37777777777', -1.0), ('2#'+'1'*32, -1.0),
                ('16#FFFFFFFFL', 4294967295.0), ('16#FFFFFFFFFFFFFFFFL', -1.0),
                ('16#FFFFFFFFFFFFFFFFUL', float(1<<64)), ('16#8000000000000000L', -float(1<<63)),
                ('16#0000 FFFFl', 65535.0), ('2#1_010uL', 10.0), ('16#0020000000000001L', 9007199254740992.0)]:
            e = self.checked([f'EQU(Source,{word})OTE(RunLatch);'], value=value); e.step(); self.assertTrue(e.memory.read('RunLatch'), word)
        e = self.checked(['EQU(16#0020000000000001L,9007199254740992.0L)OTE(RunLatch);']); e.step(); self.assertTrue(e.memory.read('RunLatch'))
        e = self.checked(['GRT(16#0020000000000001L,16#0020000000000000L)OTE(RunLatch);']); e.step(); self.assertTrue(e.memory.read('RunLatch'))

    def test_literal_selects_numeric_tags_and_constant_only_forms(self):
        for call, source, value, expected in [('EQU(16#FFFFFFFF,Source)', 'LREAL', -1, True),
                ('GRT(16#FFFFFFFFFFFFFFFFUL,0.0L)', 'DINT', 0, True),
                ('EQU(16#1000001U,Source)', 'LREAL', 16777217, True),
                ('EQU(16#1000001U,Source)', 'REAL', 16777217, True),
                ('EQU(16#1000001U,16777217.0L)', 'DINT', 0, True),
                ('EQU(16#1000001U,16777217.0)', 'LREAL', 0, False)]:
            e = self.engine([call+'OTE(RunLatch);'], source=source, value=value)
            # A REAL tag selects float32; constant-only REAL comparison stays separate.
            if call.endswith('16777217.0)'):
                self.assertTrue(e.blockers, call)
            else:
                self.assertEqual(e.blockers, []); e.step(); self.assertIs(e.memory.read('RunLatch'), expected)
        for dtype in ('SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'REAL', 'LREAL'):
            e = self.checked(['EQU(Source,1.0L)OTE(RunLatch);', 'EQU(16#1UL,1.0L)OTE(RunLatch);'], source=dtype, value=1)
            e.step(); self.assertTrue(e.memory.read('RunLatch'))

    def test_lim_all_positions_normal_reversed_and_collapsed_bounds(self):
        for base, suffix, position in itertools.product((2, 8, 16), ('', 'L', 'U', 'UL'), range(3)):
            args = ['Source', 'Mask', 'High']; args[position] = f'{base}#1{suffix}'
            e = self.checked(['LIM('+','.join(args)+')OTE(RunLatch);'], other='LREAL', high='LREAL', value=1, high_value=1)
            e.memory.write('Mask', 1); e.step(); self.assertTrue(e.memory.read('RunLatch'))
        for value, expected in [(-2, True), (-1, True), (0, False), (1, True), (2, True)]:
            e = self.checked(['LIM(16#1U,Source,8#37777777777)OTE(RunLatch);'], value=value)
            e.step(); self.assertIs(e.memory.read('RunLatch'), expected)
        e = self.checked(['LIM(16#0020000000000001L,9007199254740992.0L,16#0020000000000000UL)OTE(RunLatch);'])
        e.step(); self.assertTrue(e.memory.read('RunLatch'))

    def test_false_prescan_and_reached_unknowns_or_indices_are_lazy(self):
        e = self.checked(['XIC(StartPB)EQU(Inputs[Index],16#FFFFFFFF)OTE(RunLatch);'])
        e.memory.write('Index', 99); e.memory.write('RunLatch', True); e.step(); self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('StartPB', True); self.fault(e, 'outside bounds')
        e.memory.write('Index', 1); self.fault(e, 'Unknown')
        e.memory.write('Inputs[1]', -1); e.step(); self.assertTrue(e.memory.read('RunLatch'))
        for call in ('EQU(0.0L,Inputs[1])', 'LIM(16#1UL,Inputs[1],0.0L)', 'LIM(Inputs[1],0.0L,16#0U)'):
            e = self.checked([call+'OTE(RunLatch);']); self.fault(e, 'Unknown')

    def test_malformed_words_and_unsupported_profiles_block_false_calls(self):
        for word in ('16#100000000', '16#100000000U', '16#10000000000000000UL', '2#2UL', '8#8L', '16#FF_L', '16#FF L', '-16#1L', '(16#1L)', '16#1L+1L'):
            for call in (f'EQU(Source,{word})', f'LIM(0.0L,{word},1.0L)'):
                self.assertTrue(self.engine(['AFI()'+call+'OTE(RunLatch);']).blockers, call)
        for call in ('EQU(Source,TRUE)', 'LIM(0.0L,Inputs,16#1U)', 'MEQ(Source,16#1UL,Source)'):
            self.assertTrue(self.engine(['AFI()'+call+'OTE(RunLatch);']).blockers, call)
        for key, value in [('ProcessorType', '1756-L75'), ('MajorRev', '34')]:
            self.assertTrue(self.engine(['AFI()EQU(Source,16#1L)OTE(RunLatch);'], mutate=lambda root:root.find('Controller').set(key,value)).blockers)

    def test_real_integer_temporal_and_default_helpers_remain_separate(self):
        for call in ('EQU(Source,16#1L)', 'LIM(16#0UL,Source,16#2U)'):
            e=self.checked([call+'OTE(RunLatch);'], source='REAL', value=1);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e = self.checked(['GRT(16#0020000000000001L,16#0020000000000000L)OTE(RunLatch);']); e.step(); self.assertTrue(e.memory.read('RunLatch'))
        self.assertTrue(self.engine(['LIM(0L,16#1UL,2L)OTE(RunLatch);']).blockers)
        from logixlab.numeric_storage import lreal_math_source
        from logixlab.model import ModelError
        with self.assertRaises(ModelError):lreal_math_source(e.memory, '16#FFFFFFFF', 'MainProgram')
        self.assertEqual(literal('16#FFFFFFFF'), 4294967295)

    def test_alias_member_sources_and_late_fault_remain_atomic(self):
        def fields(root):
            tags = root.find('./Controller/Tags'); E.SubElement(tags, 'Tag', Name='Selected', DataType='LREAL', TagType='Alias', AliasFor='Inputs[Index]')
            root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant', 'true')
        e = self.checked(['EQU(Source,16#FFFFFFFF)OTE(RunLatch);', 'EQU(Selected,16#FFFFFFFF)OTE(RunLatch);', 'DIV(1,Mask,SpeedCommand);'], value=-1, mutate=fields)
        e.memory.write('Inputs[0]', -1); e.memory.write('Mask', 1); e.step(); before = e.memory.read('Source')
        e.memory.write('RunLatch', False); e.memory.write('Mask', 0); self.fault(e, 'zero')
        e.memory.write('Mask', 1); e.step(); self.assertEqual(e.memory.read('Source'), before)

    def test_warm_aoi_copied_inout_local_and_false_execution(self):
        h = fixtures.LrealComparisonLiteralTests(); h.setUp(); self.addCleanup(h.doCleanups); old = h.aoi(); root = E.parse(old.project.path).getroot()
        import test_aoi_queues as queues
        queues.logic(root, ['GRT(Value,0.0L)OTE(Latched);', 'LIM(16#FFFFFFFF,Buffer[Index],1.0L)OTE(CompareEqual);', 'GRT(Stack[0],16#0U)OTE(LiteralLocalResult);'])
        queues.logic(root, ['AFI()EQU(Buffer[Index],16#0L)OTE(LiteralLocalResult);'], name='EnableInFalse')
        E.ElementTree(root).write(old.project.path, encoding='utf8', xml_declaration=True); e = Engine(Project(old.project.path)); self.assertEqual(e.blockers, [])
        e.step(); self.assertTrue(e.memory.read('DriverA.Latched')); self.assertTrue(e.memory.read('DriverA.CompareEqual'))
        e.memory.write('BufferA[1]', 2); e.memory.write('FaultDivisor', 0); self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1); e.step(); self.assertFalse(e.memory.read('DriverA.CompareEqual'))
        e.memory.write('EnabledA', False); e.memory.write('IndexA', 99); e.step()

    def test_public_sample_thresholds_unknowns_and_rollback_retry(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X')); self.assertEqual(e.blockers, []); e.step()
        e.memory.write('RadixCompareEnabled', True); e.step()
        for name in ('Signed', 'Unsigned', 'Rounded', 'Normal', 'Reversed', 'Collapsed', 'ConstantOnly', 'Selected'):self.assertTrue(e.memory.read('RadixCompare'+name), name)
        e.memory.write('RadixCompareIndex', 1); self.fault(e, 'Unknown')
        e.memory.write('RadixCompareInputs[1]', -1); e.step(); self.assertTrue(e.memory.read('RadixCompareSelected'))
        e.memory.write('RadixCompareValue', 0); e.memory.write('RadixCompareLateDivisor', 0); self.fault(e, 'zero')
        e.memory.write('RadixCompareLateDivisor', 1); e.step(); self.assertFalse(e.memory.read('RadixCompareSigned')); self.assertFalse(e.memory.read('RadixCompareReversed'))
        e.memory.write('RadixCompareEnabled', False); e.memory.write('RadixCompareIndex', 99); e.step(); self.assertFalse(e.memory.read('RadixCompareSelected'))
        profile = e.report()['numeric_comparisons']['lreal_ordering']['radix_sources']
        self.assertEqual(profile['bases'], [2,8,16]); self.assertFalse(profile['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
