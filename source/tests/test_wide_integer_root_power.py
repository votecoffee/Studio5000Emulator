"""Exact homogeneous ladder integer roots/powers and transactional consumers."""
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from logixlab.expressions import Expression
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class WideIntegerRootPowerTests(unittest.TestCase):
    engine = fixtures.RadixExpressionTests.engine
    snapshot = staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault = fixtures.RadixExpressionTests.fault

    def test_roots_all_five_types_and_adjacent_values_beyond_float_precision(self):
        cases = [('USINT', 255, 16), ('UINT', 65535, 256), ('UDINT', 4294967295, 65536),
                 ('LINT', (1 << 63)-1, 3037000500), ('LINT', -(1 << 63), 3037000500),
                 ('ULINT', (1 << 64)-1, 4294967296),
                 ('ULINT', 16000000004000000000, 4000000000), ('ULINT', 16000000004000000001, 4000000001)]
        for dtype, value, expected in cases:
            e = self.engine(['CPT(Dest,SQR(Source));'], dtype=dtype, values=(value, 0, 0))
            e.memory.values['dest'] = None; e.step(); self.assertEqual(e.memory.read('Dest'), expected)
            self.assertEqual(e.memory.read('Source'), value)

    def test_powers_all_widths_signed_minimum_and_zero_exponents(self):
        for dtype, base, exponent, expected in [('USINT', 3, 5, 243), ('UINT', 3, 10, 59049),
                ('UDINT', 3, 20, 3486784401), ('LINT', 3, 34, 16677181699666569),
                ('ULINT', 2, 63, 1 << 63), ('LINT', -2, 63, -(1 << 63))]:
            e = self.engine(['CPT(Dest,Source**Mask);'], dtype=dtype, values=(base, exponent, 0))
            e.step(); self.assertEqual(e.memory.read('Dest'), expected)
        for dtype in ['USINT', 'UINT', 'UDINT', 'LINT', 'ULINT']:
            e = self.engine(['CPT(Dest,0**0);'], dtype=dtype); e.step(); self.assertEqual(e.memory.read('Dest'), 1)

    def test_typed_literals_nested_bcd_and_existing_operator_precedence(self):
        for dtype, text, expected in [('LINT', 'SQR(-9223372036854775808L)', 3037000500),
                ('ULINT', 'SQR(16000000004000000001UL)', 4000000001),
                ('LINT', '3L**34L', 16677181699666569), ('LINT', 'SQR(-16L)**2L', 16),
                ('LINT', 'SQR(TOD(99L))', 12), ('LINT', 'FRD(TOD(3L**4L))', 81),
                ('LINT', '-2L**2L', -4), ('LINT', '2L**3L**2L', 64)]:
            e = self.engine([f'CPT(Dest,{text});'], dtype=dtype); e.step(); self.assertEqual(e.memory.read('Dest'), expected, text)

    def test_cmp_relations_and_eager_boolean_unknown_and_zero_faults(self):
        for text in ['SQR(16000000004000000001UL)=4000000001UL', '3L**34L=16677181699666569L',
                     'SQR(-9223372036854775808L)>3037000499L']:
            e = self.engine([f'CMP({text})OTE(RunLatch);']); e.step(); self.assertTrue(e.memory.read('RunLatch'))
        for text in ['StartPB||(SQR(Source)=3L)', 'StartPB||(Source**2L/Mask=0L)']:
            e = self.engine([f'CMP({text})OTE(RunLatch);']); e.memory.write('StartPB', True)
            if 'SQR' in text:e.memory.values['source'] = None
            else:e.memory.write('Mask', 0)
            self.fault(e, 'Unknown|zero')

    def test_false_prescan_alias_selection_and_unknown_full_result(self):
        def fields(root):
            tags = root.find('./Controller/Tags'); tag = tags.find('Tag[@Name="Dest"]')
            tag.set('Dimensions', '3'); tag.remove(tag.find('Data'))
            arr = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType='LINT', Dimensions='3')
            E.SubElement(arr, 'Element', Index='[2]', Value='903')
            E.SubElement(tags, 'Tag', Name='Selected', DataType='LINT', TagType='Alias', AliasFor='Dest[SpeedCommand]')
        e = self.engine(['XIC(StartPB)CPT(Selected,SQR(Source)**2L);'], mutate=fields)
        e.memory.values['source'] = None; e.memory.write('SpeedCommand', 99); e.step()
        self.assertEqual(e.memory.read('Dest'), [None, None, 903])
        e.memory.write('StartPB', True); self.fault(e, 'Unknown|outside bounds')
        e.memory.write('Source', -16); e.memory.write('SpeedCommand', 1); e.step()
        self.assertEqual(e.memory.read('Dest'), [None, 16, 903])

    def test_exponent_limits_overflow_and_late_fault_restore_warm_state(self):
        for dtype, bits in [('USINT', 8), ('UINT', 16), ('UDINT', 32), ('LINT', 64), ('ULINT', 64)]:
            e = self.engine(['CPT(Dest,Source**Mask);'], dtype=dtype, values=(1, bits, 0)); self.fault(e, 'exponent')
            e = self.engine(['CPT(Dest,Source**Mask);'], dtype=dtype, values=(2, bits-1, 0))
            if dtype == 'LINT':self.fault(e, 'overflow')
            else:e.step(); self.assertEqual(e.memory.read('Dest'), 1 << (bits-1))
        e = self.engine(['CPT(Dest,Source**Mask);'], values=(2, -1, 0)); self.fault(e, 'exponent')
        e = self.engine(['CPT(Dest,SQR(Source)**2);'], dtype='USINT', values=(255, 0, 0)); self.fault(e, 'overflow')
        e = self.engine(['CPT(Dest,SQR(Source));', 'DIV(1,SpeedCommand,SpeedCommand);'])
        e.memory.write('SpeedCommand', 0); self.fault(e, 'zero'); e.memory.write('SpeedCommand', 1); e.step()
        self.assertEqual(e.memory.read('Dest'), 3)

    def test_mixed_types_permissions_profiles_st_and_index_paths_stay_guarded(self):
        for text in ['Source+SQR(Mask)', 'Source**(Mask+1)']:
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'], types=('LINT', 'DINT', 'LINT'), checked=False).blockers)
        for text in ['SQRT(Source)', 'LN(Source)', 'SQR(Source)+1.0', 'Source**2.5', 'SQR(StartPB)']:
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'], checked=False).blockers, text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()CPT(Dest,SQR(Source));'], mutate=constant, checked=False).blockers)
        for key, value in [('ProcessorType', '1756-L75'), ('MajorRev', '34')]:
            self.assertTrue(self.engine(['AFI()CPT(Dest,Source**2L);'], mutate=lambda root:root.find('Controller').set(key, value), checked=False).blockers)
        from logixlab.wide_st import analyze
        e = self.engine(['CPT(Dest,SQR(Source));'])
        for text, options in [('SQR(Source)', {}), ('Source**2', {'structured':True}), ('SQR(Source)', {'subscript':True})]:
            with self.assertRaises(ModelError):analyze(Expression(text, **options), e.memory, destination_type='LINT')

    def test_fal_all_exact_roots_and_powers_preserve_unselected_guard(self):
        e = self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],SQR(Queue[Ctl.POS]));'], file=True, dtype='ULINT',
                        queue=(16000000004000000000, 16000000004000000001, 0, (1 << 64)-1, 99))
        e.step(); self.assertEqual(e.memory.read('Queue'), [4000000000, 4000000001, 0, 4294967296, 99])
        e = self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]**2L);'], file=True, queue=(2, 3, 4, 5, 99))
        e.step(); self.assertEqual(e.memory.read('Queue'), [4, 9, 16, 25, 99]); self.assertTrue(e.memory.read('Ctl.DN'))

    def test_distributed_modes_unknown_retry_search_inhibit_and_mid_file_overflow(self):
        for mode in ['1', 'INC']:
            e = self.engine([f'XIC(StartPB)FAL(Ctl,?,?,{mode},Queue[Ctl.POS],Incoming**2L);'], file=True)
            e.memory.write('Incoming', 3); e.memory.write('StartPB', True); e.step()
            if mode == 'INC':
                e.memory.values['incoming'] = None; e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 0)
                e.memory.write('StartPB', False); e.step(); e.memory.write('StartPB', True)
            else:e.memory.write('StartPB', False); e.memory.values['incoming'] = None
            self.fault(e, 'Unknown'); e.memory.write('Incoming', 4); e.step(); self.assertEqual(e.memory.read('Queue')[:2], [9, 16])
        e = self.engine(['FSC(Ctl,?,?,ALL,SQR(Queue[Ctl.POS])>=3L);'], file=True, queue=(0, 4, 9, 16, 99))
        e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 2)
        e.memory.values['queue'][3] = None; e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 2)
        e.memory.write('Ctl.IN', False); self.fault(e, 'Unknown')
        e.memory.write('Queue[3]', 16); e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 3)
        e = self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]**2L);'], file=True, queue=(2, (1 << 63)-1, 4, 5, 99))
        self.fault(e, 'overflow'); e.memory.write('Queue[1]', 3); e.step(); self.assertEqual(e.memory.read('Queue'), [4, 9, 16, 25, 99])

    def test_warm_aoi_local_inout_and_file_bindings_share_rollback(self):
        import test_aoi_queues as queues
        import test_aoi_files as files
        import test_ladder_integer_literals as direct
        import test_file_integer_literals as integers
        h = queues.AOIQueueTests(); h.setUp(); self.addCleanup(h.doCleanups)
        def direct_fields(root):
            direct.LadderIntegerLiteralTests.aoi_fields(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text = text.text.replace('Value+2L', '(Value+2L)**2L')
        e = h.checked(direct_fields); e.memory.write('ValueA', 3); e.step(); self.assertEqual(e.memory.read('BufferA[1]'), 25)
        e.memory.write('FaultDivisor', 0); self.fault(e, 'zero'); e.memory.write('FaultDivisor', 1); e.step()
        h = files.AOIFileTests(); h.setUp(); self.addCleanup(h.doCleanups)
        def file_fields(root):
            integers.FileIntegerLiteralTests.aoi_fields(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text = text.text.replace('Input[Calc.POS]+9007199254740993L', '(Input[Calc.POS]+9007199254740993L)**1L')
                text.text = text.text.replace('Input[LocalCalc.POS]+1L', 'SQR(Input[LocalCalc.POS]+1L)')
        e = h.checked(file_fields, kind='1'); e.memory.write('Transform', True); e.memory.write('Search', True); e.step()
        self.assertEqual(e.memory.read('DriverA.Scratch')[0], 2)
        e.memory.write('Transform', False); e.memory.write('Search', False); e.memory.write('FaultDivisor', 0); self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1); e.step(); self.assertEqual(e.memory.read('OutputA')[:2], [9007199254740995, 9007199254740997])

    def test_public_sample_exact_values_report_and_fault_repair(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, []); e.step(); self.assertEqual(e.memory.read('RootPowerSelected'), [101, None, 999])
        e.memory.write('RootPowerEnabled', True); e.memory.write('RootPowerIndex', 1); e.step()
        for name, value in {'UnsignedRoot':4000000000, 'Power':16677181699666569, 'SignedRoot':4,
                            'Composed':16, 'Match':True, 'Selected':[101, 4000000000, 999]}.items():
            self.assertEqual(e.memory.read('RootPower'+name), value, name)
        e.memory.write('RootPowerUnsignedInput', 16000000004000000001); e.step()
        self.assertEqual(e.memory.read('RootPowerUnsignedRoot'), 4000000001)
        e.memory.write('RootPowerExponent', 64); self.fault(e, 'exponent')
        e.memory.write('RootPowerExponent', 34); e.step()
        e.memory.write('RootPowerLateDivisor', 0); self.fault(e, 'zero')
        e.memory.write('RootPowerEnabled', False); e.memory.write('RootPowerIndex', 99); e.step(); self.assertFalse(e.memory.read('RootPowerMatch'))
        report = e.report()['wide_ladder_expressions']['root_power']
        self.assertEqual(report['exponent_max']['ULINT'], 63); self.assertFalse(report['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
