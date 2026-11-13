"""Exact wide-integer FAL/FSC across modes, bindings and scan rollback."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_file_arithmetic as fixtures
from logixlab.model import ModelError


class IntegerFileTests(unittest.TestCase):
    setUp = fixtures.FileArithmeticTests.setUp

    def engine(self, rungs, *, dtype='LINT', queue=(2, 4, 6, 8, 99), **kwargs):
        return fixtures.FileArithmeticTests.engine(self, rungs, dtype=dtype, queue=queue, **kwargs)

    def checked(self, *args, **kwargs):
        e = self.engine(*args, **kwargs); self.assertEqual(e.blockers, []); return e

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values, e.memory.frames, e.addons.instances, e._file_incremental,
                              e.scan_count, e.time_ms, e.scheduler_description(), e.trace, e.last_timer))

    def test_all_transforms_for_all_five_new_integer_types(self):
        for dtype in ('LINT', 'USINT', 'UINT', 'UDINT', 'ULINT'):
            e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]*2+1);'], dtype=dtype); e.step()
            self.assertEqual(e.memory.read('Queue'), [5, 9, 13, 17, 99]); self.assertEqual(e.memory.read('Ctl.POS'), 3); self.assertTrue(e.memory.read('Ctl.DN'))

    def test_adjacent_64_bit_values_and_unsigned_maximum_keep_exact_bits(self):
        e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+1);'], queue=(9007199254740993, 9007199254740994, 0, 1, 99)); e.step()
        self.assertEqual(e.memory.read('Queue')[:2], [9007199254740994, 9007199254740995])
        e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS] XOR 1);'], dtype='ULINT', queue=(18446744073709551615, 9007199254740993, 0, 1, 99)); e.step()
        self.assertEqual(e.memory.read('Queue')[:2], [18446744073709551614, 9007199254740992])

    def test_destination_context_allows_representable_literal_only_results(self):
        for dtype in ('LINT', 'USINT', 'UINT', 'UDINT', 'ULINT'):
            e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],1+2*3);'], dtype=dtype); e.step(); self.assertEqual(e.memory.read('Queue'), [7, 7, 7, 7, 99])

    def test_signed_64_bit_quotient_remainder_and_absolute_value_are_exact(self):
        for expression, expected in [('Queue[Ctl.POS]/3', [-3074457345618258602, -2, 2]), ('Queue[Ctl.POS] MOD 3', [-2, -1, 1])]:
            e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],' + expression + ');'], length=3, queue=(-9223372036854775808, -7, 7, 99)); e.step(); self.assertEqual(e.memory.read('Queue')[:3], expected)
        e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],ABS(Queue[Ctl.POS]));'], queue=(-9007199254740993, -7, 7, 0, 99)); e.step(); self.assertEqual(e.memory.read('Queue')[0], 9007199254740993)

    def test_numeric_mode_continues_when_false_and_rolls_back_required_unknown(self):
        e = self.checked(['XIC(StartPB)FAL(Ctl,?,?,2,Queue[Ctl.POS],Incoming);']); e.step()
        e.memory.write('Incoming', 9007199254740993); e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('Queue')[:2], [9007199254740993] * 2); e.memory.write('StartPB', False); e.memory.values['incoming'] = None; before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('Incoming', 9007199254740995); e.step()
        self.assertEqual(e.memory.read('Queue')[2:4], [9007199254740995] * 2); self.assertTrue(e.memory.read('Ctl.DN'))

    def test_incremental_edges_hold_unknown_operands_and_resume_both_consumers(self):
        e = self.checked(['XIC(StartPB)FAL(Ctl,?,?,INC,Queue[Ctl.POS],Incoming);'], length=2); e.step()
        e.memory.write('Incoming', 9007199254740993); e.memory.write('StartPB', True); e.step(); e.memory.values['incoming'] = None; e.step()
        self.assertEqual(e.memory.read('Ctl.POS'), 0); e.memory.write('StartPB', False); e.step(); e.memory.write('Incoming', 9007199254740995); e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('Queue')[:2], [9007199254740993, 9007199254740995]); self.assertTrue(e.memory.read('Ctl.DN'))
        e = self.checked(['XIC(StartPB)FSC(Ctl,?,?,INC,Queue[Ctl.POS]>=Incoming);'], queue=(9007199254740993, 9007199254740994, 0, 1, 99)); e.memory.write('Incoming', 9007199254740994); e.memory.write('StartPB', True); e.step()
        self.assertFalse(e.memory.read('Ctl.FD')); e.memory.write('StartPB', False); e.step(); e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('Ctl.POS'), 1); self.assertTrue(e.memory.read('Ctl.IN'))

    def test_wide_search_uses_exact_values_and_eager_bool_composition(self):
        for dtype, values, threshold in [('LINT', (9007199254740993, 9007199254740994, 0, 1, 99), 9007199254740994),
                                          ('ULINT', (9007199254740993, 18446744073709551615, 0, 1, 99), 18446744073709551615)]:
            e = self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=Incoming&&BitIn);'], dtype=dtype, queue=values); e.memory.write('Incoming', threshold); e.step()
            self.assertEqual(e.memory.read('Ctl.POS'), 1); self.assertTrue(e.memory.read('Ctl.FD')); self.assertTrue(e.memory.read('Ctl.IN'))

    def test_search_shares_existing_range_preserving_mixed_cmp_profile(self):
        def small(root):
            tag = E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='Small', DataType='UDINT', TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='UDINT', Value='3')
        e = self.checked(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Small);'], dtype='ULINT', mutate=small); e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 1)

    def test_search_all_five_types_keeps_numeric_false_scan_continuation(self):
        for dtype in ('LINT', 'USINT', 'UINT', 'UDINT', 'ULINT'):
            e = self.checked(['XIC(StartPB)FSC(Ctl,?,?,2,Queue[Ctl.POS]>=Incoming);'], dtype=dtype)
            e.memory.write('Incoming', 7); e.memory.write('StartPB', True); e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 1)
            e.memory.write('StartPB', False); e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 3)
            self.assertTrue(e.memory.read('Ctl.FD')); self.assertTrue(e.memory.read('Ctl.IN')); self.assertFalse(e.memory.read('Ctl.EN'))

    def test_completed_or_inhibited_calls_skip_required_unknown_wide_values(self):
        for kind in ('FAL', 'FSC'):
            text = 'FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Incoming)' if kind == 'FAL' else 'FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>=Incoming)'
            e = self.checked([text + ';']); e.memory.write('Incoming', 5); e.step(); e.memory.values['incoming'] = None
            before = copy.deepcopy(e.memory.values); e.step(); self.assertEqual(e.memory.values, before)
            e.memory.write('Ctl.ER', True); e.step(); self.assertIsNone(e.memory.values['incoming'])

    def test_alias_and_indirect_destinations_retain_lazy_selection(self):
        def aliases(root):
            tags = root.find('./Controller/Tags')
            tag = E.SubElement(tags, 'Tag', Name='Offset', DataType='DINT', TagType='Base'); E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='99')
            E.SubElement(tags, 'Tag', Name='SelectedValue', TagType='Alias', AliasFor='Queue[Ctl.POS+Offset]')
        e = self.checked(['XIC(StartPB)FAL(Ctl,?,?,ALL,SelectedValue,SelectedValue+1);'], length=3, mutate=aliases); e.step()
        e.memory.write('Offset', 1); e.memory.write('StartPB', True); e.step(); self.assertEqual(e.memory.read('Queue'), [2, 5, 7, 9, 99])

    def test_unknown_destinations_and_sequential_overlap_keep_exact_values(self):
        e = self.checked(['XIC(StartPB)FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Incoming);']); e.memory.values['queue'][:4] = [None] * 4; e.step()
        e.memory.write('Incoming', 9007199254740993); e.memory.write('StartPB', True); e.step(); self.assertEqual(e.memory.read('Queue'), [9007199254740993] * 4 + [99])
        e = self.checked(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS+1],Queue[Ctl.POS]);'], queue=(9007199254740993, 0, 0, 0, 99)); e.step(); self.assertEqual(e.memory.read('Queue'), [9007199254740993] * 5)

    def test_overflow_underflow_division_and_later_faults_rollback(self):
        cases = [('LINT', (9223372036854775807, 0, 0, 0, 99), 'Queue[Ctl.POS]+1'), ('USINT', (255, 0, 0, 0, 99), 'Queue[Ctl.POS]+1'),
                 ('ULINT', (0, 0, 0, 0, 99), 'Queue[Ctl.POS]-1'), ('LINT', (0, 0, 0, 0, 99), 'Queue[Ctl.POS]/0'),
                 ('LINT', (-9223372036854775808, 0, 0, 0, 99), 'ABS(Queue[Ctl.POS])')]
        for dtype, queue, expr in cases:
            e = self.checked(['XIC(StartPB)FAL(Ctl,?,?,ALL,Queue[Ctl.POS],' + expr + ');'], dtype=dtype, queue=queue); e.step(); e.memory.write('StartPB', True); before = self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e), before)
        e = self.checked(['XIC(StartPB)FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Incoming);', 'XIC(StartPB)DIV(1,0,SpeedCommand);']); e.step(); e.memory.write('StartPB', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'zero'):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_existing_aoi_file_bindings_and_local_arrays_accept_exact_matching_types(self):
        import test_aoi_files as aoi
        helper = aoi.AOIFileTests(); helper.setUp(); self.addCleanup(helper.doCleanups)
        def types(root):
            for node in root.iter():
                if node.get('DataType') == 'DINT' and node.get('Name') not in ('LEN', 'POS', 'Position'):node.set('DataType', 'LINT')
        for kind, pulses in [('ALL', 1), ('2', 2), ('INC', 4)]:
            e = helper.engine(types, kind=kind); self.assertEqual(e.blockers, []); e.memory.write('InputA[0]', 9007199254740993)
            for _ in range(pulses):helper.pulse(e)
            self.assertEqual(e.memory.read('OutputA')[0], 18014398509481987); self.assertEqual(e.memory.read('DriverA.Scratch')[0], 9007199254740994)

    def test_unqualified_mixtures_functions_literals_and_destinations_are_guarded(self):
        for expr in ('Queue[Ctl.POS]+Result', 'SQRT(Queue[Ctl.POS])', 'Queue[Ctl.POS]**2.0', 'Queue[Ctl.POS]+2147483648'):
            self.assertTrue(self.engine(['AFI()FAL(Ctl,?,?,ALL,Outgoing,' + expr + ');']).blockers)
        self.assertTrue(self.engine(['AFI()FAL(Ctl,?,?,ALL,Result,Queue[Ctl.POS]);']).blockers)
        self.assertTrue(self.engine(['AFI()FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>Result);']).blockers)


if __name__ == '__main__':unittest.main()
