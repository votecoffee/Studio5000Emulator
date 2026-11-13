"""Matching typed constants in bounded mixed CPT/CMP/FAL/FSC expressions."""
import unittest
from xml.etree import ElementTree as E

import test_mixed_expression_math as direct
import test_mixed_integer_files as files
import test_aoi_files as aoi
from logixlab.model import ModelError


class MixedIntegerLiteralTests(unittest.TestCase):
    setUp = files.MixedIntegerFileTests.setUp
    engine = files.MixedIntegerFileTests.engine
    checked = files.MixedIntegerFileTests.checked
    snapshot = staticmethod(files.MixedIntegerFileTests.snapshot)
    fault = files.MixedIntegerFileTests.fault

    def direct_engine(self, text, *, checked=True, **kwargs):
        helper = direct.MixedExpressionMathTests();helper.setUp();self.addCleanup(helper.doCleanups)
        return (helper.checked if checked else helper.engine)([text], **kwargs)

    def test_cpt_keeps_full_width_matching_l_u_and_ul_constants_exact(self):
        for types, values, constant, expected in [
                (('LINT', 'DINT', 'LINT'), (9007199254740993, 3, 0), '9007199254740993L', 18014398509481989),
                (('UDINT', 'UINT', 'UDINT'), (0, 0, 0), '4294967295u', 4294967295),
                (('ULINT', 'UDINT', 'ULINT'), (0, 0, 0), '18446744073709551615uL', 18446744073709551615)]:
            e = self.direct_engine('CPT(Dest,Source+Mask+' + constant + ');', types=types, values=values)
            e.step();self.assertEqual(e.memory.read('Dest'), expected)

    def test_cmp_matching_literals_keep_exact_arithmetic_and_eager_boolean_reads(self):
        e = self.direct_engine('CMP(Source+Mask=9007199254740996L)OTE(RunLatch);', values=(9007199254740993, 3, 0))
        e.step();self.assertTrue(e.memory.read('RunLatch'))
        e = self.direct_engine('CMP(StartPB||(Source+Mask>0L))OTE(RunLatch);')
        e.memory.write('StartPB', True);e.memory.values['mask'] = None;self.fault(e, 'Unknown')

    def test_immediate_unary_sign_checks_allow_lint_minimum_and_unsigned_negative_zero(self):
        e = self.direct_engine('CPT(Dest,Source+Mask+(-9223372036854775808L));', values=(0, 0, 0))
        e.step();self.assertEqual(e.memory.read('Dest'), -9223372036854775808)
        e = self.direct_engine('CPT(Dest,Source+Mask+(-0UL));', types=('ULINT', 'UDINT', 'ULINT'), values=(7, 3, 0))
        e.step();self.assertEqual(e.memory.read('Dest'), 10)
        for constant in ('9223372036854775808L', '-9223372036854775809L', '18446744073709551616UL'):
            self.assertTrue(self.direct_engine('AFI()CPT(Dest,Source+Mask+' + constant + ');', checked=False).blockers)

    def test_literal_type_cannot_promote_tags_or_replace_a_common_tag_in_a_subtree(self):
        for expression in ('Source+Mask+1U', 'Source+Mask+0UL', 'Source+(Mask+1L)',
                           'Source+ABS(Mask+0L)', 'Source+Mask+(1L+2L)', 'Source AND Mask+1L'):
            self.assertTrue(self.direct_engine('AFI()CPT(Dest,' + expression + ');', checked=False).blockers, expression)
        self.assertTrue(self.direct_engine('CPT(Dest,Source+Mask+0UL);', checked=False,
                        types=('UDINT', 'UINT', 'ULINT'), values=(0, 0, 0)).blockers)

    def test_fal_all_numeric_and_inc_modes_preserve_typed_exact_results(self):
        for mode, advances in [('ALL', 1), ('2', 2), ('INC', 4)]:
            e = self.checked('Queue[Ctl.POS]+Small+9007199254740993L', mode=mode)
            e.step()
            for _ in range(advances):
                if mode == 'INC':e.memory.write('StartPB', False);e.step()
                e.memory.write('StartPB', True);e.step()
            self.assertEqual(e.memory.read('Queue'), [9007199254740998, 9007199254741000, 9007199254741002, 9007199254741004, 99])
            self.assertTrue(e.memory.read('Ctl.DN'))

    def test_fsc_all_numeric_and_inc_conditions_share_matching_literal_rules(self):
        for mode in ('ALL', '1', 'INC'):
            e = self.checked(rungs=[f'XIC(StartPB)FSC(Ctl,?,?,{mode},Queue[Ctl.POS]+Small>=9007199254740997L);'],
                             length=2, queue=(9007199254740993, 9007199254740994, 99))
            e.step();e.memory.write('StartPB', True);e.step()
            if mode != 'ALL':
                e.memory.write('StartPB', False);e.step()
                if mode == 'INC':e.memory.write('StartPB', True);e.step()
            self.assertEqual(e.memory.read('Ctl.POS'), 1)
            self.assertTrue(e.memory.read('Ctl.FD'));self.assertTrue(e.memory.read('Ctl.IN'))

    def test_false_calls_skip_unknown_sources_but_matching_literal_ranges_are_preflight_checks(self):
        e = self.checked('Queue[Ctl.POS]+Small+3L')
        e.memory.values['small'] = None;e.step();e.memory.write('StartPB', True);self.fault(e, 'Unknown')
        e.memory.write('Small', 3);e.step();self.assertEqual(e.memory.read('Queue')[0], 8)
        self.assertTrue(self.engine('Queue[Ctl.POS]+Small+9223372036854775808L').blockers)
        self.assertTrue(self.engine('Queue[Ctl.POS]+Small+1U').blockers)

    def test_overflow_of_any_typed_intermediate_restores_destinations_and_file_progress(self):
        e = self.direct_engine('CPT(Dest,Source+Mask+9223372036854775807L-9223372036854775807L);', values=(1, 0, 17))
        self.fault(e, 'overflow')
        e = self.checked('Queue[Ctl.POS]+Small+9223372036854775807L', length=1, queue=(1, 99), small=0)
        e.memory.write('StartPB', True);self.fault(e, 'overflow')
        self.assertFalse(e.memory.read('Ctl.ER'))

    def test_later_fault_rolls_back_completed_mixed_typed_file_writes(self):
        e = self.checked(rungs=['XIC(StartPB)FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+Small+1L);',
                                'XIC(StartPB)DIV(1,0,SpeedCommand);'])
        e.step();e.memory.write('StartPB', True);self.fault(e, 'zero')

    @staticmethod
    def aoi_types(root):
        files.MixedIntegerFileTests.aoi_types(root)
        for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
            if 'FAL(' in text.text:
                text.text = text.text.replace('*Gain+Bias', '*Gain+Bias+1L').replace('Input[LocalCalc.POS]+Bias', 'Input[LocalCalc.POS]+Bias+1L')

    def test_aoi_mixed_parameter_and_local_array_literals_keep_precise_values(self):
        helper = aoi.AOIFileTests();helper.setUp();self.addCleanup(helper.doCleanups)
        for mode, advances in [('ALL', 1), ('2', 2), ('INC', 4)]:
            e = helper.checked(self.aoi_types, kind=mode);e.memory.write('InputA[0]', 9007199254740993)
            for _ in range(advances):helper.pulse(e)
            self.assertEqual(e.memory.read('OutputA[0]'), 18014398509481988)
            self.assertEqual(e.memory.read('DriverA.Scratch[0]'), 9007199254740995)

    def test_st_and_other_controller_profiles_keep_existing_limits(self):
        def st(root):
            routine = root.find('./Controller/Programs/Program/Routines/Routine')
            routine.set('Type', 'ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine, 'STContent'), 'Line', Number='0').text = 'Queue[0] := Queue[0]+Small+1L;'
        self.assertTrue(self.engine(mutate=st).blockers)
        for processor, revision in [('1756-L75', '35'), ('1756-L85E', '34')]:
            def target(root):root.find('Controller').set('ProcessorType', processor);root.find('Controller').set('MajorRev', revision)
            self.assertTrue(self.engine('Queue[Ctl.POS]+Small+1L', mutate=target).blockers)

    def test_reports_identify_matching_common_types_without_claiming_native_parity(self):
        report = self.checked('Queue[Ctl.POS]+Small+1L').report()
        typed = report['wide_ladder_expressions']['mixed_integer_arithmetic']['typed_constants']
        self.assertTrue(typed['matching_common_source_type']);self.assertTrue(typed['no_source_promotion'])
        self.assertEqual(typed['types'], ['LINT', 'UDINT', 'ULINT'])
        self.assertIn('FSC', report['wide_ladder_expressions']['file_consumers'])
        self.assertFalse(report['file_arithmetic']['typed_integer_literals']['native_runtime_parity'])


if __name__ == '__main__':
    unittest.main()
