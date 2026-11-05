"""Exact typed integer constants in FAL/FSC, including distributed progress."""
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_integer_files as fixtures
import test_file_bcd as snapshots
import test_ladder_integer_literals as integers
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class FileIntegerLiteralTests(unittest.TestCase):
    setUp = fixtures.IntegerFileTests.setUp
    engine = fixtures.IntegerFileTests.engine
    checked = fixtures.IntegerFileTests.checked
    snapshot = staticmethod(snapshots.FileBcdTests.snapshot)
    fault = snapshots.FileBcdTests.fault

    def test_full_width_constants_establish_unknown_files_and_keep_guard(self):
        for dtype, text, value in integers.CASES:
            e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],' + text + ');'], dtype=dtype)
            e.memory.values['queue'][:4] = [None]*4; e.step()
            self.assertEqual(e.memory.read('Queue'), [value]*4+[99])
            self.assertTrue(e.memory.read('Ctl.DN'))
            self.assertEqual(e.memory.read('Ctl.POS'), 3)

    def test_case_signs_exact_quotients_and_bitwise_forms(self):
        for dtype, text, value in [('LINT', '-(9223372036854775808l)', -(1 << 63)),
                                   ('LINT', '9007199254740993L+2L', 9007199254740995),
                                   ('UDINT', '00042u', 42), ('ULINT', '42Ul', 42),
                                   ('ULINT', '18446744073709551615uL/3UL', 6148914691236517205),
                                   ('LINT', '-9223372036854775808L MOD 3L', -2),
                                   ('ULINT', 'NOT 0ul', (1 << 64)-1), ('UDINT', '-0U', 0)]:
            e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],' + text + ');'], dtype=dtype)
            e.step(); self.assertEqual(e.memory.read('Queue'), [value]*4+[99])

    def test_matching_tag_and_literal_forms_keep_declared_width(self):
        for dtype, suffix in [('LINT', 'L'), ('UDINT', 'U'), ('ULINT', 'UL')]:
            e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+2' + suffix + ');'], dtype=dtype)
            e.step(); self.assertEqual(e.memory.read('Queue'), [4, 6, 8, 10, 99])

    def test_numeric_false_continuation_consumes_live_sources_and_keeps_prior_commits(self):
        e = self.checked(['XIC(StartPB)FAL(Ctl,?,?,1,Queue[Ctl.POS],Incoming+9007199254740993L);'])
        e.memory.write('Incoming', 0); e.memory.write('StartPB', True); e.step()
        e.memory.write('StartPB', False); e.memory.values['incoming'] = None
        self.fault(e, 'Unknown')
        self.assertEqual(e.memory.read('Queue')[0], 9007199254740993)
        self.assertEqual(e.memory.read('Ctl.POS'), 0)
        e.memory.write('Incoming', 2); e.step()
        self.assertEqual(e.memory.read('Queue')[:2], [9007199254740993, 9007199254740995])

    def test_incremental_hold_skips_unknown_values_and_retry_preserves_pending_edge(self):
        e = self.checked(['XIC(StartPB)FAL(Ctl,?,?,INC,Queue[Ctl.POS],Incoming+9007199254740993L);'])
        e.memory.write('Incoming', 0); e.memory.write('StartPB', True); e.step()
        e.memory.values['incoming'] = None; e.step()
        self.assertEqual(e.memory.read('Ctl.POS'), 0)
        e.memory.write('StartPB', False); e.step(); e.memory.write('StartPB', True)
        self.fault(e, 'Unknown')
        e.memory.write('Incoming', 2); e.step()
        self.assertEqual(e.memory.read('Queue')[:2], [9007199254740993, 9007199254740995])
        self.assertEqual(e.memory.read('Ctl.POS'), 1)

    def test_search_exact_64_bit_values_all_relations_and_matching_suffixes(self):
        for dtype, text, value in integers.CASES:
            e = self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]=' + text + ');'], dtype=dtype,
                             queue=(0, value, 0, 0, 99))
            e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 1); self.assertTrue(e.memory.read('Ctl.IN'))
        for dtype, suffix in [('LINT', 'L'), ('UDINT', 'U'), ('ULINT', 'UL')]:
            for op, position, found in [('=', 3, False), ('<>', 0, True), ('<', 0, True),
                                        ('<=', 0, True), ('>', 2, True), ('>=', 2, True)]:
                e = self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]' + op + '5' + suffix + ');'], dtype=dtype)
                e.step(); self.assertEqual(e.memory.read('Ctl.POS'), position)
                self.assertEqual(e.memory.read('Ctl.FD'), found)

    def test_literal_only_search_and_eager_boolean_failure(self):
        e = self.checked(['FSC(Ctl,?,?,ALL,9007199254740993L>9007199254740992L&&BitIn);'])
        e.step(); self.assertTrue(e.memory.read('Ctl.FD')); self.assertEqual(e.memory.read('Ctl.POS'), 0)
        for text in ['(1L=1L)||(1L/0L>0)', '(0L=1L)&&(1L/0L>0)']:
            self.fault(self.checked(['FSC(Ctl,?,?,ALL,' + text + ');']), 'zero')

    def test_numeric_search_continues_false_and_incremental_search_requires_edges(self):
        for mode in ['1', 'INC']:
            e = self.checked(['XIC(StartPB)FSC(Ctl,?,?,' + mode + ',Queue[Ctl.POS]>=6L);'])
            e.memory.write('StartPB', True); e.step()
            self.assertEqual(e.memory.read('Ctl.POS'), 0)
            if mode == 'INC':
                e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 0)
            e.memory.write('StartPB', False); e.step()
            if mode == 'INC': e.memory.write('StartPB', True); e.step()
            self.assertEqual(e.memory.read('Ctl.POS'), 1)
            if mode == 'INC': e.memory.write('StartPB', False); e.step(); e.memory.write('StartPB', True)
            e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 2); self.assertTrue(e.memory.read('Ctl.IN'))

    def test_search_resume_after_inhibit_retains_exact_threshold(self):
        e = self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=9007199254740993L);'],
                         queue=(0, 9007199254740993, 9007199254740994, 0, 99))
        e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 1)
        e.memory.values['queue'][2] = None; e.step()
        e.memory.write('Ctl.IN', False); self.fault(e, 'Unknown')
        e.memory.write('Queue[2]', 9007199254740994); e.step()
        self.assertEqual(e.memory.read('Ctl.POS'), 2); self.assertTrue(e.memory.read('Ctl.IN'))

    def test_incremental_inhibit_must_clear_before_an_observed_false_rearms_enable(self):
        e = self.checked(['XIC(StartPB)FSC(Ctl,?,?,INC,1UL=1UL);'])
        e.memory.write('StartPB', True); e.step()
        e.memory.write('StartPB', False); e.step()
        self.assertTrue(e.memory.read('Ctl.EN'))
        e.memory.write('Ctl.IN', False); e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('Ctl.POS'), 0)
        e.memory.write('StartPB', False); e.step()
        e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('Ctl.POS'), 1); self.assertTrue(e.memory.read('Ctl.IN'))

    def test_literal_range_errors_block_false_calls_for_both_consumers(self):
        for dtype, text in integers.BAD:
            for rung in ['AFI()FAL(Ctl,?,?,ALL,Queue[Ctl.POS],' + text + ');',
                         'AFI()FSC(Ctl,?,?,ALL,Queue[Ctl.POS]=' + text + ');']:
                self.assertTrue(self.engine([rung], dtype=dtype).blockers, rung)

    def test_narrow_mixed_floating_radix_and_other_arguments_remain_guarded(self):
        for dtype, text in [('LINT', '1U'), ('ULINT', '1L'), ('DINT', '1L'), ('REAL', '1L'),
                            ('LINT', '1L+1U'), ('LINT', '1L+0.5'), ('LINT', '1e999L'),
                            ('LINT', '16#FFL'), ('LINT', '1_000L'), ('LINT', 'SQR(1L)')]:
            self.assertTrue(self.engine(['AFI()FAL(Ctl,?,?,ALL,Queue[Ctl.POS],' + text + ');'], dtype=dtype).blockers)
        for mode in ['1L', '1U', '1UL']:
            self.assertTrue(self.engine(['FAL(Ctl,?,?,' + mode + ',Queue[Ctl.POS],1L);']).blockers)
        for key, value in [('ProcessorType', '1756-L75'), ('MajorRev', '34')]:
            self.assertTrue(self.engine(['AFI()FSC(Ctl,?,?,ALL,1L=1L);'],
                                       mutate=lambda root: root.find('Controller').set(key, value)).blockers)

    def test_mid_file_overflow_and_later_fault_restore_earlier_writes_and_controls(self):
        e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+1L);'],
                         queue=(0, (1 << 63)-1, 0, 0, 99))
        self.fault(e, 'overflow')
        e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],9007199254740993L);', 'DIV(1,0,SpeedCommand);'])
        self.fault(e, 'zero')

    def test_false_done_inhibited_and_error_paths_do_not_read_required_unknowns(self):
        for rung in ['XIC(StartPB)FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Incoming+1L);',
                     'XIC(StartPB)FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Incoming+1L);']:
            e = self.checked([rung]); e.memory.values['incoming'] = None; e.step()
            e.memory.write('StartPB', True); self.fault(e, 'Unknown')
            e.memory.write('Ctl.ER', True); e.step()
        e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],9007199254740993L);'])
        e.step(); before = e.memory.read('Queue'); e.step(); self.assertEqual(e.memory.read('Queue'), before)

    def test_cache_modes_and_generic_index_parsers_remain_isolated(self):
        from logixlab.expressions import Expression
        from logixlab.conditions import Condition
        e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],1L);', 'FSC(Ctl,?,?,ALL,1L=1L);'])
        self.assertIn(('1L', True, True, True), e.extensions.expressions)
        self.assertIn(('1L=1L', True, True, False, True), e.extensions.conditions)
        with self.assertRaises(ModelError): e.extensions.condition('1L=1L', allow_wide=True, bcd=True)
        for create in [Expression, Condition, lambda text: Expression(text, subscript=True)]:
            with self.assertRaises(ModelError): create('1UL')

    @staticmethod
    def aoi_fields(root):
        fields = {'Gain', 'Bias', 'Threshold', 'Input', 'Output', 'Total', 'Scratch',
                  'GainA', 'GainB', 'BiasA', 'BiasB', 'ThresholdA', 'ThresholdB',
                  'InputA', 'InputB', 'OutputA', 'OutputB'}
        for node in root.iter():
            if node.get('Name') in fields:
                for child in node.iter():
                    if child.get('DataType') == 'DINT': child.set('DataType', 'LINT')
        for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
            text.text = text.text.replace('Input[Calc.POS]*Gain+Bias', 'Input[Calc.POS]+9007199254740993L')
            text.text = text.text.replace('Input[Find.POS]>=Threshold', 'Input[Find.POS]>=6L')
            text.text = text.text.replace('Input[LocalCalc.POS]+Bias', 'Input[LocalCalc.POS]+1L')

    def test_warm_aoi_inout_local_and_numeric_false_continuation_rollback(self):
        import test_aoi_files as aois
        f = aois.AOIFileTests(); f.setUp(); self.addCleanup(f.doCleanups)
        e = f.checked(self.aoi_fields, kind='1')
        e.memory.write('Transform', True); e.memory.write('Search', True); e.step()
        self.assertEqual(e.memory.read('OutputA')[0], 9007199254740995)
        self.assertEqual(e.memory.read('DriverA.Scratch')[0], 3)
        e.memory.write('Transform', False); e.memory.write('Search', False)
        e.memory.write('FaultDivisor', 0); self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1); e.step()
        self.assertEqual(e.memory.read('OutputA')[:2], [9007199254740995, 9007199254740997])
        self.assertEqual(e.memory.read('CalcA.POS'), 1)

    def test_warm_aoi_incremental_progress_is_separate_per_instance_and_control(self):
        import test_aoi_files as aois
        f = aois.AOIFileTests(); f.setUp(); self.addCleanup(f.doCleanups)
        e = f.checked(self.aoi_fields)
        f.pulse(e); f.pulse(e)
        self.assertEqual(e.memory.read('OutputA')[:2], [9007199254740995, 9007199254740997])
        self.assertEqual(e.memory.read('OutputB')[:2], [9007199254740994, 9007199254740996])
        e.memory.write('InputA[2]', (1 << 63)-1); e.memory.write('Transform', False); e.step()
        e.memory.write('Transform', True); self.fault(e, 'overflow')
        e.memory.write('InputA[2]', 6); e.step(); self.assertEqual(e.memory.read('CalcA.POS'), 2)

    def test_report_states_checked_literals_without_native_parity(self):
        row = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],1L);']).report()
        for name in ['file_arithmetic', 'file_search']:
            self.assertEqual(row[name]['typed_integer_literals']['types'], ['LINT', 'UDINT', 'ULINT'])
            self.assertFalse(row[name]['typed_integer_literals']['native_runtime_parity'])

    def test_sample_full_width_progress_fault_retry_and_selected_unknowns(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, []); e.step()
        self.assertEqual(e.memory.read('FILitValues'), [None, None, None, 903])
        e.memory.write('FILitEnabled', True); e.memory.write('FILitLateDivisor', 0)
        self.fault(e, 'zero'); e.memory.write('FILitLateDivisor', 1); e.step()
        self.assertEqual(e.memory.read('FILitValues'), [9007199254740993]*3+[903])
        self.assertEqual(e.memory.read('FILitUnsigned'), [(1 << 64)-1]*3+[905])
        self.assertTrue(e.memory.read('FILitFind.IN'))
        e.memory.write('FILitNumericStart', True); e.step()
        e.memory.write('FILitNumericStart', False); e.memory.write('FILitOffset', 2); e.step()
        self.assertEqual(e.memory.read('FILitNumeric'), [9007199254740993, 9007199254740995, None, 906])
        e.memory.write('FILitIncrement', True); e.step(); e.step()
        self.assertEqual(e.memory.read('FILitIncrementCalc.POS'), 0)
        e.memory.write('FILitIncrementFind.IN', False); e.memory.write('FILitIncrement', False); e.step()
        e.memory.write('FILitIncrement', True); e.step()
        self.assertEqual(e.memory.read('FILitIncrements')[:2], [(1 << 64)-1]*2)
        self.assertEqual(e.memory.read('FILitIncrementFind.POS'), 1)
