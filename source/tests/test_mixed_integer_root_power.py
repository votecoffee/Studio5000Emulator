"""Common-range mixed roots/powers keep type, subtree and transaction guards."""
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class MixedIntegerRootPowerTests(unittest.TestCase):
    engine = fixtures.RadixExpressionTests.engine
    snapshot = staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault = fixtures.RadixExpressionTests.fault

    def file_engine(self, *args, checked=True, **kwargs):
        import test_mixed_integer_files as files
        h = files.MixedIntegerFileTests(); h.setUp(); self.addCleanup(h.doCleanups)
        return (h.checked if checked else h.engine)(*args, **kwargs)

    def test_compatible_source_pairs_use_actual_common_type_for_roots_and_powers(self):
        pairs = [('LINT', 'SINT'), ('LINT', 'DINT'), ('LINT', 'UINT'), ('LINT', 'UDINT'),
                 ('ULINT', 'USINT'), ('ULINT', 'UINT'), ('ULINT', 'UDINT'),
                 ('UDINT', 'USINT'), ('UDINT', 'UINT'), ('UINT', 'USINT'), ('INT', 'USINT'), ('DINT', 'UINT')]
        for common, smaller in pairs:
            for text, expected in [('Source**Mask', 9), ('SQR(Source)+Mask', 4), ('SQR(Source+Mask)', 2)]:
                e = self.engine([f'CPT(Dest,{text});'], types=(common, smaller, common), values=(3, 2, 0))
                e.memory.values['dest'] = None; e.step(); self.assertEqual(e.memory.read('Dest'), expected, (common, smaller, text))

    def test_exact_large_values_matching_constants_and_negative_root(self):
        e = self.engine(['CPT(Dest,Source**Mask+16#0L);', 'CMP(Source**Mask=Dest)OTE(RunLatch);'],
                        types=('LINT', 'DINT', 'LINT'), values=(3, 34, 0))
        e.step(); self.assertEqual(e.memory.read('Dest'), 16677181699666569); self.assertTrue(e.memory.read('RunLatch'))
        for source, expected in [(16000000004000000000, 4000000001), (16000000004000000001, 4000000002)]:
            e = self.engine(['CPT(Dest,SQR(Source)+Mask);'], types=('ULINT', 'UDINT', 'ULINT'), values=(source, 1, 0))
            e.step(); self.assertEqual(e.memory.read('Dest'), expected)
        e = self.engine(['CPT(Dest,SQR(Source+Mask));'], types=('LINT', 'DINT', 'LINT'), values=(-17, 1, 0))
        e.step(); self.assertEqual(e.memory.read('Dest'), 4)

    def test_complete_source_ranges_subtrees_bcd_and_destinations_stay_guarded(self):
        for common, smaller in [('UINT', 'INT'), ('UDINT', 'DINT'), ('ULINT', 'LINT'), ('LINT', 'ULINT'), ('INT', 'UINT')]:
            self.assertTrue(self.engine(['AFI()CPT(Dest,Source**Mask);'], types=(common, smaller, common), values=(3, 2, 0), checked=False).blockers)
        for text in ['Source+SQR(Mask)', 'Source**(Mask+1)', 'Source+FRD(Mask)',
                     'TOD(Source)+Mask', 'Source AND Mask', 'Source**Mask+1U', 'Source**Mask+0.5']:
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'], types=('LINT', 'DINT', 'LINT'), checked=False).blockers, text)
        self.assertTrue(self.engine(['AFI()CPT(Dest,Source**Mask);'], types=('DINT', 'UINT', 'LINT'), checked=False).blockers)
        for key, value in [('ProcessorType', '1756-L75'), ('MajorRev', '34')]:
            self.assertTrue(self.engine(['AFI()CPT(Dest,SQR(Source)+Mask);'], types=('LINT', 'DINT', 'LINT'),
                                        mutate=lambda root:root.find('Controller').set(key, value), checked=False).blockers)

    def test_false_prescan_alias_and_program_local_exponent_establish_selected_unknown(self):
        def fields(root):
            tags = root.find('./Controller/Tags'); tag = tags.find('Tag[@Name="Dest"]')
            tag.set('Dimensions', '3'); tag.remove(tag.find('Data'))
            arr = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType='LINT', Dimensions='3')
            E.SubElement(arr, 'Element', Index='[2]', Value='903')
            E.SubElement(tags, 'Tag', Name='Selected', DataType='LINT', TagType='Alias', AliasFor='Dest[SpeedCommand]')
            E.SubElement(tags, 'Tag', Name='SourceAlias', DataType='LINT', TagType='Alias', AliasFor='Source')
            program = root.find('./Controller/Programs/Program'); local = program.find('Tags')
            if local is None:local = E.SubElement(program, 'Tags')
            tag = E.SubElement(local, 'Tag', Name='LocalExponent', DataType='DINT', TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='2')
        e = self.engine(['XIC(StartPB)CPT(Selected,SourceAlias**LocalExponent);'], mutate=fields)
        e.memory.values['source'] = None; e.memory.write('SpeedCommand', 99); e.step()
        self.assertEqual(e.memory.read('Dest'), [None, None, 903])
        e.memory.write('StartPB', True); self.fault(e, 'Unknown|outside bounds')
        e.memory.write('Source', 3); e.memory.write('SpeedCommand', 1); e.step(); self.assertEqual(e.memory.read('Dest'), [None, 9, 903])
        e.memory.write('LocalExponent', 3, 'MainProgram'); e.step(); self.assertEqual(e.memory.read('Dest'), [None, 27, 903])

    def test_common_width_exponent_limits_overflow_and_late_fault_rollback(self):
        for common, smaller, exponent in [('INT', 'USINT', 16), ('DINT', 'UINT', 32), ('LINT', 'DINT', 64), ('ULINT', 'UDINT', 64)]:
            e = self.engine(['CPT(Dest,Source**Mask);'], types=(common, smaller, common), values=(1, exponent, 0)); self.fault(e, 'exponent')
        for common, smaller, exponent in [('INT', 'USINT', 15), ('DINT', 'UINT', 31), ('LINT', 'DINT', 63)]:
            e = self.engine(['CPT(Dest,Source**Mask);'], types=(common, smaller, common), values=(2, exponent, 0)); self.fault(e, 'overflow')
        e = self.engine(['CPT(Dest,Source**Mask);'], types=('LINT', 'DINT', 'LINT'), values=(-2, 63, 0))
        e.step(); self.assertEqual(e.memory.read('Dest'), -(1 << 63))
        e.memory.write('Mask', -1); self.fault(e, 'exponent'); e.memory.write('Mask', 2147483647); self.fault(e, 'exponent')
        e = self.engine(['CPT(Dest,SQR(Source)+Mask);', 'DIV(1,SpeedCommand,SpeedCommand);'], types=('LINT', 'DINT', 'LINT'))
        e.memory.write('SpeedCommand', 0); self.fault(e, 'zero'); e.memory.write('SpeedCommand', 1); e.step(); self.assertEqual(e.memory.read('Dest'), 6)

    def test_cmp_eager_boolean_sides_consume_unknown_and_zero_divisor(self):
        for text in ['StartPB||(SQR(Source)+Mask=7L)', 'StartPB||(Source**Mask/0L=0L)']:
            e = self.engine([f'CMP({text})OTE(RunLatch);'], types=('LINT', 'DINT', 'LINT'), values=(3, 2, 0))
            e.memory.write('StartPB', True)
            if 'SQR' in text:e.memory.values['source'] = None
            self.fault(e, 'Unknown|zero')

    def test_fal_all_and_fsc_mixed_roots_powers_and_selected_narrow_common_type(self):
        e = self.file_engine('Queue[Ctl.POS]**Small', small=2); e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('Queue'), [4, 16, 36, 64, 99])
        e = self.file_engine('SQR(Queue[Ctl.POS])+Small'); e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('Queue'), [4, 5, 5, 6, 99])
        e = self.file_engine('Queue[Ctl.POS]**Small', dtype='INT', small_type='USINT', small=3, queue=(2, 3, 4, 5, 99))
        e.memory.write('StartPB', True); e.step(); self.assertEqual(e.memory.read('Queue'), [8, 27, 64, 125, 99])
        e = self.file_engine(rungs=['XIC(StartPB)FSC(Ctl,?,?,ALL,SQR(Queue[Ctl.POS])>=Small);'], queue=(1, 9, 16, 25, 99))
        e.memory.write('StartPB', True); e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 1); self.assertTrue(e.memory.read('Ctl.IN'))
        e.memory.values['queue'][2] = None; e.step(); e.memory.write('Ctl.IN', False); self.fault(e, 'Unknown')
        e.memory.write('Queue[2]', 16); e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 2)

    def test_distributed_file_live_retry_preserves_progress_and_mid_file_overflow(self):
        for mode in ['1', 'INC']:
            e = self.file_engine('Queue[Ctl.POS]**Small', mode=mode, small=2); e.memory.write('StartPB', True); e.step()
            if mode == 'INC':
                e.memory.values['small'] = None; e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 0)
                e.memory.write('StartPB', False); e.step(); e.memory.write('StartPB', True)
            else:e.memory.write('StartPB', False); e.memory.values['small'] = None
            self.fault(e, 'Unknown'); e.memory.write('Small', 3); e.step()
            self.assertEqual(e.memory.read('Queue')[:2], [4, 64]); self.assertEqual(e.memory.read('Ctl.POS'), 1)
        e = self.file_engine('Queue[Ctl.POS]**Small', small=2, queue=(2, (1 << 63)-1, 6, 8, 99))
        e.memory.write('StartPB', True); self.fault(e, 'overflow')
        e.memory.write('Queue[1]', 3); e.step(); self.assertEqual(e.memory.read('Queue'), [4, 9, 36, 64, 99])

    def test_warm_aoi_mixed_inputs_inout_locals_and_false_continuation(self):
        import test_aoi_queues as queues
        import test_aoi_files as files
        import test_ladder_integer_literals as direct
        import test_mixed_integer_files as mixed
        h = queues.AOIQueueTests(); h.setUp(); self.addCleanup(h.doCleanups)
        def direct_fields(root):
            direct.LadderIntegerLiteralTests.aoi_fields(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text = text.text.replace('Value+2L', 'Value**Index')
        e = h.checked(direct_fields); e.memory.write('ValueA', 3); e.step(); self.assertEqual(e.memory.read('BufferA[1]'), 3)
        e.memory.write('IndexA', 2); e.step(); self.assertEqual(e.memory.read('BufferA[2]'), 9)
        e.memory.write('FaultDivisor', 0); self.fault(e, 'zero'); e.memory.write('FaultDivisor', 1); e.step()
        h = files.AOIFileTests(); h.setUp(); self.addCleanup(h.doCleanups)
        def file_fields(root):
            mixed.MixedIntegerFileTests.aoi_types(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text = text.text.replace('Input[Calc.POS]*Gain+Bias', 'Input[Calc.POS]**Gain+Bias')
                text.text = text.text.replace('Input[LocalCalc.POS]+Bias', 'SQR(Input[LocalCalc.POS]+Bias)')
                text.text = text.text.replace('Input[Find.POS]>=Threshold', 'SQR(Input[Find.POS])>=Threshold')
        e = h.checked(file_fields, kind='1'); e.memory.write('Transform', True); e.memory.write('Search', True); e.step()
        self.assertEqual(e.memory.read('OutputA')[0], 5); self.assertEqual(e.memory.read('DriverA.Scratch')[0], 2)
        e.memory.write('Transform', False); e.memory.write('Search', False); e.memory.write('FaultDivisor', 0); self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1); e.step(); self.assertEqual(e.memory.read('OutputA')[:2], [5, 17])

    def test_public_sample_mixed_values_metadata_and_fault_recovery(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, []); e.step(); self.assertEqual(e.memory.resolve('RootPowerExponent')[2], 'DINT')
        e.memory.write('RootPowerIndex', 1); e.memory.write('RootPowerEnabled', True); e.step()
        self.assertEqual(e.memory.read('RootPowerPower'), 16677181699666569)
        self.assertEqual((e.memory.read('RootPowerShifted'), e.memory.read('RootPowerScaled'), e.memory.read('RootPowerMixedMatch')), (5, 4, True))
        e.memory.write('RootPowerOffset', 100); e.step(); self.assertEqual((e.memory.read('RootPowerShifted'), e.memory.read('RootPowerScaled')), (104, 9))
        e.memory.write('RootPowerLateDivisor', 0); self.fault(e, 'zero'); e.memory.write('RootPowerLateDivisor', 1); e.step()
        e.memory.write('RootPowerExponent', 64); self.fault(e, 'exponent')
        e.memory.write('RootPowerEnabled', False); e.memory.write('RootPowerIndex', 99); e.step(); self.assertFalse(e.memory.read('RootPowerMixedMatch'))
        report = e.report(); profile = report['wide_ladder_expressions']['root_power']
        self.assertTrue(profile['mixed_numeric_types']); self.assertEqual(profile['mixed_exponent_max']['INT'], 15)
        self.assertIn('SQR', report['file_arithmetic']['mixed_integer_arithmetic']['operators']); self.assertFalse(profile['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
