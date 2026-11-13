"""Declared radix integer words use the explicit binary64 ladder profile."""
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from logixlab.conditions import Condition
from logixlab.expressions import Expression
from logixlab.model import ModelError, Project, literal
from logixlab.runtime import Engine


class LrealRadixExpressionTests(unittest.TestCase):
    engine = fixtures.RadixExpressionTests.engine
    snapshot = staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault = fixtures.RadixExpressionTests.fault

    def test_three_bases_declared_widths_signedness_zero_fill_and_groups(self):
        for base in [2, 8, 16]:
            for suffix, bits, value in [('', 32, -1), ('L', 64, -1), ('U', 32, 4294967295), ('UL', 64, (1 << 64)-1)]:
                token = f'{base}#{format((1 << bits)-1, {2:"b",8:"o",16:"x"}[base])}{suffix}'
                e = self.engine([f'CPT(Dest,{token});'], dtype='LREAL'); e.memory.values['dest'] = None; e.step()
                self.assertEqual(e.memory.read('Dest'), float(value), token)
        for token, expected in [('16#FFFFFFFFL', 4294967295.0), ('16#80000000', -2147483648.0),
                ('16#8000000000000000L', -9223372036854775808.0), ('16#0000 FFFFl', 65535.0),
                ('2#1_010uL', 10.0), ('8#000377U', 255.0)]:
            e = self.engine([f'CPT(Dest,{token});'], dtype='LREAL'); e.step(); self.assertEqual(e.memory.read('Dest'), expected)

    def test_rounding_precedes_arithmetic_functions_and_comparisons(self):
        for text, expected in [('16#0020000000000001L-9007199254740992L', 0.0),
                ('16#3L/2#10U', 1.5), ('2#10U**-16#1L', .5), ('8#1777777777777777777777UL', 18446744073709551616.0),
                ('ABS(16#8000000000000000L)', 9223372036854775808.0), ('-16#FFFFFFFFFFFFFFFFL', 1.0),
                ('-16#FFFFFFFF', 1.0), ('SQR(16#9U)', 3.0), ('16#FFFFFFF9 MOD 2#11UL', -1.0)]:
            e = self.engine([f'CPT(Dest,{text});'], dtype='LREAL'); e.step(); self.assertEqual(e.memory.read('Dest'), expected, text)
        e = self.engine(['CMP(16#0020000000000001L=9007199254740992L+0.0L)OTE(RunLatch);'])
        e.step(); self.assertTrue(e.memory.read('RunLatch'))

    def test_selection_all_numeric_destinations_and_exact_integer_context_stay_distinct(self):
        for dtype in ['SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'REAL', 'LREAL']:
            e = self.engine(['CPT(Dest,16#3L/2#10U+0.0L);'], dtype=dtype); e.step()
            self.assertEqual(e.memory.read('Dest'), 1.5 if dtype in ('REAL', 'LREAL') else 2)
        e = self.engine(['CPT(Dest,16#0020000000000001L);']); e.step(); self.assertEqual(e.memory.read('Dest'), 9007199254740993)
        e = self.engine(['CPT(Dest,16#0020000000000001L+0.0L);']); e.step(); self.assertEqual(e.memory.read('Dest'), 9007199254740992)
        self.assertTrue(self.engine(['AFI()CPT(Dest,16#3L/2#10U);'], checked=False).blockers)

    def test_declared_range_and_destination_rounding_overflow_before_later_fault_recovery(self):
        for dtype, text in [('ULINT', '16#FFFFFFFFFFFFFFFFUL+0.0L'), ('LINT', '16#7FFFFFFFFFFFFFFFL+0.0L'),
                             ('SINT', '16#80U+0.0L')]:
            e = self.engine([f'CPT(Dest,{text});'], dtype=dtype); self.fault(e, 'overflow')
        e = self.engine(['CPT(Dest,16#FFFFFFFFFFFFF800UL+0.0L);'], dtype='ULINT'); e.step()
        self.assertEqual(e.memory.read('Dest'), 18446744073709549568)
        e = self.engine(['CPT(Dest,16#3L/2#10U);', 'DIV(1,SpeedCommand,SpeedCommand);'], dtype='LREAL')
        e.memory.write('SpeedCommand', 0); self.fault(e, 'zero'); e.memory.write('SpeedCommand', 1); e.step()
        self.assertEqual(e.memory.read('Dest'), 1.5)

    def test_invalid_digits_widths_unary_ranges_functions_and_profiles_block_false_calls(self):
        for text in ['16#100000000', '16#100000000U', '16#10000000000000000L', '2#2UL', '8#8L',
                     '16#FF_L', '16#FF L', '-16#8000000000000000L', '-16#80000000', '-16#1U',
                     'FRD(16#1L)', 'TOD(16#1U)', '16#1L AND 16#1UL']:
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'], dtype='LREAL', checked=False).blockers, text)
        for key, value in [('ProcessorType', '1756-L75'), ('MajorRev', '34')]:
            self.assertTrue(self.engine(['AFI()CPT(Dest,16#1L);'], dtype='LREAL',
                                        mutate=lambda root:root.find('Controller').set(key, value), checked=False).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()CPT(Dest,16#1L);'], dtype='LREAL', mutate=constant, checked=False).blockers)

    def test_default_st_index_parsing_and_real_only_integer_guards_do_not_expand(self):
        for create in [Expression, Condition, lambda text:Expression(text, structured=True), lambda text:Expression(text, subscript=True)]:
            with self.assertRaises(ModelError):create('16#1L')
        self.assertEqual(literal('16#FFFFFFFF'), 4294967295)
        self.assertEqual(Expression('16#FFFFFFFF').tree, ('literal', 4294967295))
        for dtype, text in [('REAL', '16#100000000'), ('REAL', '16#10000000000000000L'), ('DINT', '16#100000000+1.0')]:
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'], dtype=dtype, checked=False).blockers)

    def test_false_prescan_alias_indices_and_unknown_full_destinations(self):
        def fields(root):
            tags = root.find('./Controller/Tags'); tag = tags.find('Tag[@Name="Dest"]')
            tag.set('Dimensions', '3'); tag.remove(tag.find('Data'))
            arr = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType='LREAL', Dimensions='3')
            E.SubElement(arr, 'Element', Index='[2]', Value='903')
            E.SubElement(tags, 'Tag', Name='Selected', DataType='LREAL', TagType='Alias', AliasFor='Dest[SpeedCommand]')
        e = self.engine(['XIC(StartPB)CPT(Selected,Source+16#1L);'], dtype='LREAL', mutate=fields)
        e.memory.values['source'] = None; e.memory.write('SpeedCommand', 99); e.step()
        self.assertEqual(e.memory.read('Dest'), [None, None, 903.0])
        e.memory.write('StartPB', True); self.fault(e, 'Unknown|outside bounds')
        e.memory.write('Source', 2); e.memory.write('SpeedCommand', 1); e.step()
        self.assertEqual(e.memory.read('Dest'), [None, 3.0, 903.0])

    def test_cmp_relations_and_eager_boolean_sides_consume_required_values(self):
        for op, expected in [('=', False), ('<>', True), ('<', True), ('<=', True), ('>', False), ('>=', False)]:
            e = self.engine([f'CMP(16#3L{op}8#4UL+0.0L)OTE(RunLatch);']); e.step(); self.assertEqual(e.memory.read('RunLatch'), expected)
        for text in ['StartPB||(Source>16#1L)', 'StartPB||(16#1L/2#0U=0.0L)']:
            e = self.engine([f'CMP({text})OTE(RunLatch);'], dtype='LREAL'); e.memory.write('StartPB', True)
            if 'Source' in text:e.memory.values['source'] = None
            self.fault(e, 'Unknown|zero')

    def test_fal_modes_unknown_retry_and_fsc_inhibit_resume(self):
        e = self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],16#0020000000000001L);'], file=True, dtype='LREAL')
        e.memory.values['queue'][:4] = [None]*4; e.step(); self.assertEqual(e.memory.read('Queue'), [9007199254740992.0]*4+[99.0])
        for mode in ['1', 'INC']:
            e = self.engine([f'XIC(StartPB)FAL(Ctl,?,?,{mode},Queue[Ctl.POS],Incoming+16#1L);'], file=True, dtype='LREAL')
            e.memory.write('Incoming', 3); e.memory.write('StartPB', True); e.step()
            if mode == 'INC':
                e.memory.values['incoming'] = None; e.step(); e.memory.write('StartPB', False); e.step(); e.memory.write('StartPB', True)
            else:e.memory.write('StartPB', False); e.memory.values['incoming'] = None
            self.fault(e, 'Unknown'); e.memory.write('Incoming', 5); e.step(); self.assertEqual(e.memory.read('Queue')[:2], [4.0, 6.0])
        e = self.engine(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=16#0020000000000001L);'], file=True, dtype='LREAL',
                        queue=(0, 9007199254740992, 9007199254740994, 0, 99))
        e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 1); self.assertTrue(e.memory.read('Ctl.IN'))
        e.memory.values['queue'][2] = None; e.step(); e.memory.write('Ctl.IN', False); self.fault(e, 'Unknown')
        e.memory.write('Queue[2]', 9007199254740994); e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 2)

    def test_warm_aoi_copied_inout_and_local_values_and_numeric_false_continuation(self):
        import test_aoi_queues as queues
        import test_aoi_files as files
        import test_lreal_integer_literals as integers
        h = queues.AOIQueueTests(); h.setUp(); self.addCleanup(h.doCleanups)
        def direct_fields(root):
            integers.LrealIntegerLiteralTests.aoi_fields(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text = text.text.replace('9007199254740993L', '16#0020000000000001L').replace('+2UL', '+2#10UL').replace('+1U', '+8#1U')
        e = h.checked(direct_fields); e.memory.write('ValueA', 3); e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 5); self.assertEqual(e.memory.read('DriverA.Stack[1]'), 9007199254740996.0)
        e.memory.write('FaultDivisor', 0); self.fault(e, 'zero'); e.memory.write('FaultDivisor', 1); e.step()
        h = files.AOIFileTests(); h.setUp(); self.addCleanup(h.doCleanups)
        def file_fields(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                if 'FAL(' in text.text:text.text = text.text.replace('+Bias', '+Bias+16#1L/2#10U+0.0L')
                text.text = text.text.replace('Input[Find.POS]>=Threshold', 'Input[Find.POS]>=16#3U+0.0L')
        e = h.checked(file_fields, kind='1'); e.memory.write('Transform', True); e.memory.write('Search', True); e.step()
        self.assertEqual(e.memory.read('OutputA')[0], 6); self.assertEqual(e.memory.read('DriverA.Scratch')[0], 4)
        e.memory.write('Transform', False); e.memory.write('Search', False); e.memory.write('FaultDivisor', 0); self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1); e.step(); self.assertEqual(e.memory.read('OutputA')[:2], [6, 10])

    def test_public_sample_results_report_and_late_fault_recovery(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, []); e.step(); self.assertEqual(e.memory.read('BinaryRadixSelected'), [101.0, None, 999.0])
        e.memory.write('BinaryRadixIndex', 1); e.memory.write('BinaryRadixEnabled', True); e.step()
        for name, value in {'Value':9007199254740992.0, 'Unsigned':18446744073709551616.0,
                            'Signed':-9223372036854775808.0, 'Dint':-1.0, 'Rounded':0.0, 'Mixed':2.5,
                            'Match':True, 'Selected':[101.0, 4294967296.0, 999.0]}.items():
            self.assertEqual(e.memory.read('BinaryRadix'+name), value, name)
        e.memory.write('BinaryRadixSource', 2); e.memory.write('BinaryRadixLateDivisor', 0); self.fault(e, 'zero')
        e.memory.write('BinaryRadixLateDivisor', 1); e.step(); self.assertEqual(e.memory.read('BinaryRadixMixed'), 3.5)
        self.assertEqual(e.memory.read('BinaryRadixSelected')[1], 4294967297.0)
        profile = e.report()['lreal_expression_execution']['radix_literals']
        self.assertEqual(profile['bases'], [2, 8, 16]); self.assertEqual(profile['types'], ['DINT', 'LINT', 'UDINT', 'ULINT'])
        self.assertFalse(profile['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
