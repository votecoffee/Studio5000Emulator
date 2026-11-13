"""Homogeneous wide ladder BCD calls retain exact width and scan semantics."""
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from logixlab.expressions import Expression
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine

TYPES = [('USINT', 255, 165, 99, 153), ('UINT', 65535, 16665, 9999, 39321),
         ('UDINT', 4294967295, 166666665, 99999999, 2576980377),
         ('LINT', -1, 16666666666666665, 9999999999999999, -7378697629483820647),
         ('ULINT', 18446744073709551615, 16666666666666665, 9999999999999999, 11068046444225730969)]


class WideBcdExpressionTests(unittest.TestCase):
    engine = fixtures.RadixExpressionTests.engine
    snapshot = staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault = fixtures.RadixExpressionTests.fault

    def test_five_selected_widths_decode_all_nibbles_and_pack_full_capacity(self):
        for dtype, pattern, decimal, maximum, packed in TYPES:
            for function, source, expected in [('FRD', pattern, decimal), ('TOD', maximum, packed)]:
                e = self.engine([f'CPT(Dest,{function}(Source));'], dtype=dtype, values=(source, 0, 0))
                e.memory.values['dest'] = None; e.step(); self.assertEqual(e.memory.read('Dest'), expected, dtype)
                self.assertEqual(e.memory.read('Source'), source)

    def test_nested_roundtrips_exact_literals_and_composed_integer_arithmetic(self):
        for dtype, _, _, maximum, _ in TYPES:
            e = self.engine(['CPT(Dest,FRD(TOD(Source)));'], dtype=dtype, values=(maximum, 0, 0))
            e.step(); self.assertEqual(e.memory.read('Dest'), maximum)
        for text, expected in [('FRD(16#FFFFFFFFFFFFFFFFL)', 16666666666666665),
                               ('FRD(TOD(9999999999999999L))', 9999999999999999),
                               ('FRD(16#0020000000000001L)+2L', 20000000000003),
                               ('(TOD(99L) AND 15L)+ABS(-1L)', 10),
                               ('FRD(TOD(Source+2L))/3L', 3)]:
            e = self.engine([f'CPT(Dest,{text});']); e.step(); self.assertEqual(e.memory.read('Dest'), expected, text)

    def test_cmp_exact_relations_and_eager_boolean_failures(self):
        for dtype, pattern, decimal, maximum, _ in TYPES:
            e = self.engine(['CMP(FRD(Source)=Mask)OTE(RunLatch);'], dtype=dtype, values=(pattern, decimal, 0))
            e.step(); self.assertTrue(e.memory.read('RunLatch'))
        for text in ['StartPB||(FRD(Source)=0L)', 'StartPB||(TOD(Source)/Mask=0L)']:
            e = self.engine([f'CMP({text})OTE(RunLatch);']); e.memory.write('StartPB', True)
            if 'FRD' in text:e.memory.values['source'] = None
            else:e.memory.write('Mask', 0)
            self.fault(e, 'Unknown|zero')

    def test_false_prescan_selected_alias_and_unknown_result_are_lazy(self):
        def fields(root):
            tags = root.find('./Controller/Tags'); tag = tags.find('Tag[@Name="Dest"]')
            tag.set('Dimensions', '3'); tag.remove(tag.find('Data'))
            arr = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType='LINT', Dimensions='3')
            E.SubElement(arr, 'Element', Index='[2]', Value='903')
            E.SubElement(tags, 'Tag', Name='Selected', DataType='LINT', TagType='Alias', AliasFor='Dest[SpeedCommand]')
        e = self.engine(['XIC(StartPB)CPT(Selected,TOD(Source));'], mutate=fields)
        e.memory.values['source'] = None; e.memory.write('SpeedCommand', 99); e.step()
        self.assertEqual(e.memory.read('Dest'), [None, None, 903])
        e.memory.write('StartPB', True); self.fault(e, 'Unknown|outside bounds')
        e.memory.write('Source', 9999999999999999); e.memory.write('SpeedCommand', 1); e.step()
        self.assertEqual(e.memory.read('Dest'), [None, -7378697629483820647, 903])

    def test_conversion_ranges_intermediate_overflow_and_late_fault_rollback(self):
        for dtype, _, _, maximum, _ in TYPES:
            for value in [maximum+1] + ([-1] if dtype == 'LINT' else []):
                e = self.engine(['MOV(77,SpeedCommand);', 'CPT(Dest,TOD(Source));'], dtype=dtype, values=(value, 0, 0))
                self.fault(e, 'range')
        e = self.engine(['CPT(Dest,FRD(Source+1L));'], values=((1 << 63)-1, 0, 0)); self.fault(e, 'overflow')
        e = self.engine(['CPT(Dest,TOD(Source));', 'DIV(1,SpeedCommand,SpeedCommand);'])
        e.memory.write('SpeedCommand', 0); self.fault(e, 'zero'); e.memory.write('SpeedCommand', 1); e.step()
        self.assertEqual(e.memory.read('Dest'), 7)

    def test_profile_mixed_types_real_bool_permissions_and_other_functions_stay_guarded(self):
        for types in [('LINT', 'DINT', 'LINT'), ('ULINT', 'UDINT', 'ULINT')]:
            self.assertTrue(self.engine(['AFI()CPT(Dest,FRD(Source)+Mask);'], types=types, checked=False).blockers)
        for text in ['FRD(Source)+1.0', 'TOD(Source)+1UL', 'LN(TOD(Source))', 'TOD(Source)**2.0', 'FRD(StartPB)']:
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'], checked=False).blockers, text)
        for dtype in ['REAL', 'LREAL']:
            self.assertTrue(self.engine(['AFI()CPT(Dest,FRD(Source));'], dtype=dtype, checked=False).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()CPT(Dest,TOD(Source));'], mutate=constant, checked=False).blockers)
        for key, value in [('ProcessorType', '1756-L75'), ('MajorRev', '34')]:
            self.assertTrue(self.engine(['AFI()CPT(Dest,TOD(Source));'], mutate=lambda root:root.find('Controller').set(key, value), checked=False).blockers)
        for options in [{}, {'structured':True}]:
            with self.assertRaises(ModelError):Expression('FRD(Source)', **options)
        index = Expression('FRD(Source)', subscript=True)
        self.assertFalse(index.bcd)
        from logixlab.wide_st import analyze
        e = self.engine(['CPT(Dest,TOD(Source));'])
        with self.assertRaises(ModelError):analyze(index, e.memory, destination_type='LINT')

    def test_fal_all_pack_decode_establish_unknown_results_and_guard(self):
        for dtype, _, _, maximum, packed in TYPES:
            e = self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],TOD(Incoming));'], file=True, dtype=dtype)
            e.memory.values['queue'][:4] = [None]*4; e.memory.write('Incoming', maximum); e.step()
            self.assertEqual(e.memory.read('Queue'), [packed]*4+[99]); self.assertTrue(e.memory.read('Ctl.DN'))
            e = self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],FRD(Queue[Ctl.POS]));'], file=True, dtype=dtype,
                            queue=(packed, packed, packed, packed, 99))
            e.step(); self.assertEqual(e.memory.read('Queue'), [maximum]*4+[99])

    def test_fal_numeric_and_inc_live_retry_preserve_prior_progress(self):
        for mode in ['1', 'INC']:
            e = self.engine([f'XIC(StartPB)FAL(Ctl,?,?,{mode},Queue[Ctl.POS],TOD(Incoming));'], file=True)
            e.memory.write('Incoming', 12); e.memory.write('StartPB', True); e.step()
            if mode == 'INC':
                e.memory.values['incoming'] = None; e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 0)
                e.memory.write('StartPB', False); e.step(); e.memory.write('StartPB', True)
            else:e.memory.write('StartPB', False); e.memory.values['incoming'] = None
            self.fault(e, 'Unknown'); e.memory.write('Incoming', 21); e.step()
            self.assertEqual(e.memory.read('Queue')[:2], [18, 33]); self.assertEqual(e.memory.read('Ctl.POS'), 1)

    def test_fsc_inhibit_resume_and_mid_file_conversion_range_rollback(self):
        e = self.engine(['FSC(Ctl,?,?,ALL,FRD(Queue[Ctl.POS])>=21L);'], file=True, queue=(0, 33, 34, 0, 99))
        e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 1); self.assertTrue(e.memory.read('Ctl.IN'))
        e.memory.values['queue'][2] = None; e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 1)
        e.memory.write('Ctl.IN', False); self.fault(e, 'Unknown')
        e.memory.write('Queue[2]', 34); e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 2)
        e = self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],TOD(Queue[Ctl.POS]));'], file=True, queue=(12, 10000000000000000, 21, 0, 99))
        self.fault(e, 'range'); e.memory.write('Queue[1]', 21); e.step(); self.assertEqual(e.memory.read('Queue'), [18, 33, 33, 0, 99])

    def test_warm_aoi_copied_inout_and_local_bindings_with_late_rollback(self):
        import test_aoi_queues as queues
        import test_aoi_files as files
        import test_ladder_integer_literals as direct
        import test_file_integer_literals as integers
        h = queues.AOIQueueTests(); h.setUp(); self.addCleanup(h.doCleanups)
        def direct_fields(root):
            direct.LadderIntegerLiteralTests.aoi_fields(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text = text.text.replace('Value+2L', 'FRD(TOD(Value+9007199254740993L))')
        e = h.checked(direct_fields); e.memory.write('ValueA', 3); e.step(); self.assertEqual(e.memory.read('BufferA[1]'), 9007199254740996)
        e.memory.write('FaultDivisor', 0); self.fault(e, 'zero'); e.memory.write('FaultDivisor', 1); e.step()
        h = files.AOIFileTests(); h.setUp(); self.addCleanup(h.doCleanups)
        def file_fields(root):
            integers.FileIntegerLiteralTests.aoi_fields(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text = text.text.replace('Input[Calc.POS]+9007199254740993L', 'FRD(TOD(Input[Calc.POS]+9007199254740993L))')
                text.text = text.text.replace('Input[Find.POS]>=6L', 'FRD(TOD(Input[Find.POS]))>=6L')
        e = h.checked(file_fields, kind='1'); e.memory.write('Transform', True); e.memory.write('Search', True); e.step()
        e.memory.write('Transform', False); e.memory.write('Search', False); e.memory.write('FaultDivisor', 0); self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1); e.step(); self.assertEqual(e.memory.read('OutputA')[:2], [9007199254740995, 9007199254740997])

    def test_public_sample_report_fault_repair_and_dormant_false_path(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, []); e.step(); self.assertEqual(e.memory.read('WideBcdSelected'), [101, None, 999])
        e.memory.write('WideBcdEnabled', True); e.memory.write('WideBcdIndex', 1); e.step()
        for name, value in {'Packed':-7378697629483820647, 'Roundtrip':9999999999999999,
                            'AllNibbles':16666666666666665, 'BytePacked':153, 'Match':True,
                            'Selected':[101, -7378697629483820647, 999]}.items():
            self.assertEqual(e.memory.read('WideBcd'+name), value, name)
        e.memory.write('WideBcdInput', 10000000000000000); self.fault(e, 'range')
        e.memory.write('WideBcdInput', 9999999999999999); e.step()
        e.memory.write('WideBcdLateDivisor', 0); self.fault(e, 'zero')
        e.memory.write('WideBcdEnabled', False); e.memory.write('WideBcdIndex', 99); e.step(); self.assertFalse(e.memory.read('WideBcdMatch'))
        report = e.report()['wide_ladder_expressions']['bcd']
        self.assertEqual(report['functions'], ['FRD', 'TOD']); self.assertFalse(report['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
