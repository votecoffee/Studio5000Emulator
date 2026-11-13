"""Full DINT word constants in the qualified ladder expression consumers."""
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from logixlab.conditions import Condition
from logixlab.expressions import Expression
from logixlab.model import ModelError, Project, literal
from logixlab.runtime import Engine

WORDS = ['16#FFFF_FFFF', '8#37777777777', '2#' + '1'*32]


class DintRadixExpressionTests(unittest.TestCase):
    engine = fixtures.RadixExpressionTests.engine
    snapshot = staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault = fixtures.RadixExpressionTests.fault

    def test_three_bases_sign_zero_fill_boundaries_and_unary_order(self):
        for token in WORDS:
            for text, want in [(token, -1), ('Source+'+token, 6), ('-'+token, 1), ('ABS('+token+')', 1)]:
                e = self.engine([f'CPT(Dest,{text});'], dtype='DINT')
                e.memory.values['dest'] = None; e.step(); self.assertEqual(e.memory.read('Dest'), want)
        for text, want in [('16#80000000', -(1 << 31)), ('16#7FFFFFFF', (1 << 31)-1),
                           ('16#FFFF', 65535), ('8#377', 255), ('2#1_010', 10)]:
            e = self.engine([f'CPT(Dest,{text});'], dtype='DINT'); e.step(); self.assertEqual(e.memory.read('Dest'), want)

    def test_narrow_division_remainder_bitwise_functions_and_power(self):
        for text, want in [('16#FFFFFFF9/2', -3), ('16#FFFFFFF9 MOD 2', -1),
                           ('NOT 16#FFFFFFFF', 0), ('16#FFFFFFFF AND 3', 3),
                           ('16#FFFFFFFF XOR 1', -2), ('16#80000000 OR 1', -2147483647),
                           ('FRD(16#FFFFFFFF)', 166666665), ('SQR(16#FFFFFFF7)', 3),
                           ('16#FFFFFFFE**2', 4)]:
            e = self.engine([f'CPT(Dest,{text});'], dtype='DINT'); e.step(); self.assertEqual(e.memory.read('Dest'), want)

    def test_wide_exact_and_matching_typed_constants_keep_existing_ranges(self):
        for text in ['9007199254740993L+16#FFFFFFFF', '16#0020000000000001L+16#FFFFFFFF']:
            e = self.engine([f'CPT(Dest,{text});']); e.step(); self.assertEqual(e.memory.read('Dest'), 9007199254740992)
        for dtype in ['UDINT', 'ULINT']:
            self.assertTrue(self.engine(['AFI()CPT(Dest,16#FFFFFFFF);'], dtype=dtype, checked=False).blockers)
        e = self.engine(['CPT(Dest,Source+Mask+16#FFFFFFFF);'],
                        types=('LINT', 'DINT', 'LINT'), values=(9007199254740993, 3, 0))
        e.step(); self.assertEqual(e.memory.read('Dest'), 9007199254740995)

    def test_cmp_literal_only_and_eager_boolean_unknown_and_zero_failures(self):
        for text in ['16#FFFFFFFF=-1', '16#80000000<0', 'FRD(16#FFFFFFFF)=166666665', 'SQR(16#FFFFFFF7)=3']:
            e = self.engine([f'CMP({text})OTE(RunLatch);'], dtype='DINT'); e.step(); self.assertTrue(e.memory.read('RunLatch'))
        for text in ['StartPB||(Source+16#FFFFFFFF=6)', 'StartPB||(16#FFFFFFFF/Mask=0)']:
            e = self.engine([f'CMP({text})OTE(RunLatch);'], dtype='DINT'); e.memory.write('StartPB', True)
            if 'Source' in text:e.memory.values['source'] = None
            else:e.memory.write('Mask', 0)
            self.fault(e, 'Unknown|zero')

    def test_false_prescan_alias_indices_and_unknown_selected_destination(self):
        def array(root):
            tags = root.find('./Controller/Tags'); dest = tags.find('Tag[@Name="Dest"]')
            dest.set('Dimensions', '3'); dest.remove(dest.find('Data'))
            obj = E.SubElement(E.SubElement(dest, 'Data', Format='Decorated'), 'Array', DataType='DINT', Dimensions='3')
            E.SubElement(obj, 'Element', Index='[2]', Value='903')
            E.SubElement(tags, 'Tag', Name='Selected', DataType='DINT', TagType='Alias', AliasFor='Dest[SpeedCommand]')
        e = self.engine(['XIC(StartPB)CPT(Selected,Source+16#FFFFFFFF);'], dtype='DINT', mutate=array)
        e.memory.write('SpeedCommand', 99); e.memory.values['source'] = None; e.step()
        self.assertEqual(e.memory.read('Dest'), [None, None, 903])
        e.memory.write('StartPB', True); self.fault(e, 'Unknown|outside bounds')
        e.memory.write('Source', 7); e.memory.write('SpeedCommand', 1); e.step()
        self.assertEqual(e.memory.read('Dest'), [None, 6, 903])

    def test_overflow_divide_by_zero_and_late_fault_restore_warm_scan(self):
        for text in ['-16#80000000', '16#80000000-1', '16#FFFFFFFF/0', 'ABS(16#80000000)']:
            e = self.engine(['MOV(77,SpeedCommand);', f'CPT(Dest,{text});'], dtype='DINT'); self.fault(e, 'overflow|zero')
        e = self.engine(['CPT(Dest,Source+16#FFFFFFFF);', 'DIV(1,SpeedCommand,SpeedCommand);'], dtype='DINT')
        e.memory.write('SpeedCommand', 0); self.fault(e, 'zero')
        e.memory.write('SpeedCommand', 1); e.step(); self.assertEqual(e.memory.read('Dest'), 6)

    def test_invalid_digits_width_permissions_real_mixes_and_profiles_block_false_calls(self):
        for word in ['16#100000000', '8#40000000000', '2#'+'1'*33, '8#8', '2#2']:
            for code, file in [(f'AFI()CPT(Dest,{word});', False), (f'AFI()FSC(Ctl,?,?,ALL,Queue[Ctl.POS]={word});', True)]:
                self.assertTrue(self.engine([code], dtype='DINT', file=file, checked=False).blockers, word)
        for dtype, text in [('REAL', '16#100000000'), ('LREAL', 'FRD(16#FFFFFFFF)'),
                            ('DINT', '16#100000000+1.0'), ('DINT', 'SIN(16#FFFFFFFF)')]:
            self.assertTrue(self.engine([f'AFI()CPT(Dest,{text});'], dtype=dtype, checked=False).blockers)
        for dtype in ['REAL', 'LREAL']:
            self.assertTrue(self.engine(['AFI()CMP(Source>FRD(16#FFFFFFFF))OTE(RunLatch);'], dtype=dtype, checked=False).blockers)
            self.assertTrue(self.engine(['AFI()FAL(Ctl,?,?,ALL,Queue[Ctl.POS],FRD(16#FFFFFFFF));'], file=True, dtype=dtype, checked=False).blockers)
            self.assertTrue(self.engine(['AFI()FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>FRD(16#FFFFFFFF));'], file=True, dtype=dtype, checked=False).blockers)
        for key, value in [('ProcessorType', '1756-L75'), ('MajorRev', '34')]:
            for code in ['AFI()CPT(Dest,16#FFFFFFFF);', 'AFI()CMP(16#FFFFFFFF<0)OTE(RunLatch);']:
                self.assertTrue(self.engine([code], dtype='DINT', mutate=lambda root:root.find('Controller').set(key, value), checked=False).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()CPT(Dest,16#FFFFFFFF);'], dtype='DINT', mutate=constant, checked=False).blockers)

    def test_default_st_index_parsers_and_caches_retain_legacy_words(self):
        for options in [{}, {'structured':True}, {'subscript':True}, {'integer_literals':True}]:
            expr = Expression('16#FFFFFFFF', **options)
            self.assertEqual(expr.tree, ('literal', 4294967295)); self.assertEqual(expr.radix_types, set())
        self.assertEqual(literal('16#FFFFFFFF'), 4294967295)
        self.assertEqual(Condition('16#FFFFFFFF=1').tree[2], ('literal', 4294967295))
        e = self.engine(['CPT(Dest,16#FFFFFFFF);'], dtype='DINT')
        plain = e.extensions.expression('16#FFFFFFFF', integer_literals=True)
        enabled = e.extensions.expression('16#FFFFFFFF', integer_literals=True, radix_literals=True)
        self.assertIsNot(plain, enabled); self.assertEqual(enabled.tree, ('literal', -1))
        self.assertEqual(enabled.typed_types, set()); self.assertEqual(enabled.radix_types, {'DINT'})

    def test_fal_all_establishes_unknowns_and_preserves_guard_and_completed_hold(self):
        e = self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],16#FFFFFFFF);'], file=True, dtype='DINT')
        e.memory.values['queue'][:4] = [None]*4; e.step()
        self.assertEqual(e.memory.read('Queue'), [-1]*4+[99]); self.assertTrue(e.memory.read('Ctl.DN'))
        e.memory.write('Ctl.POS', 99); e.step(); self.assertEqual(e.memory.read('Queue'), [-1]*4+[99])

    def test_fal_numeric_incremental_live_retry_and_prior_progress(self):
        for mode in ['1', 'INC']:
            e = self.engine([f'XIC(StartPB)FAL(Ctl,?,?,{mode},Queue[Ctl.POS],Incoming+16#FFFFFFFF);'], file=True, dtype='DINT')
            e.memory.write('Incoming', 7); e.memory.write('StartPB', True); e.step()
            if mode == 'INC':
                e.memory.values['incoming'] = None; e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 0)
                e.memory.write('StartPB', False); e.step(); e.memory.write('StartPB', True)
            else:e.memory.write('StartPB', False); e.memory.values['incoming'] = None
            self.fault(e, 'Unknown'); e.memory.write('Incoming', 3); e.step()
            self.assertEqual(e.memory.read('Queue')[:2], [6, 2]); self.assertEqual(e.memory.read('Ctl.POS'), 1)

    def test_fsc_inhibit_resume_and_file_late_fault_rollback(self):
        e = self.engine(['FSC(Ctl,?,?,ALL,Queue[Ctl.POS]>16#FFFFFFFF);'], file=True, dtype='DINT', queue=(-2, 0, 2, -3, 99))
        e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 1); self.assertTrue(e.memory.read('Ctl.IN'))
        e.memory.values['queue'][2] = None; e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 1)
        e.memory.write('Ctl.IN', False); self.fault(e, 'Unknown')
        e.memory.write('Queue[2]', 2); e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 2)
        e = self.engine(['FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Queue[Ctl.POS]+16#FFFFFFFF);',
                         'DIV(1,0,SpeedCommand);'], file=True, dtype='DINT')
        self.fault(e, 'zero')

    def test_warm_aoi_direct_and_file_bindings(self):
        import test_aoi_queues as queues
        import test_aoi_files as files
        import test_ladder_integer_literals as direct
        import test_file_integer_literals as literals
        h = queues.AOIQueueTests(); h.setUp(); self.addCleanup(h.doCleanups)
        def direct_fields(root):
            direct.LadderIntegerLiteralTests.aoi_fields(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text = text.text.replace('+2L', '+16#FFFFFFFF')
        e = h.checked(direct_fields); e.memory.write('ValueA', 3); e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 2)
        self.assertEqual(e.memory.read('DriverA.Stack[1]'), 9007199254740996)
        e.memory.write('FaultDivisor', 0); self.fault(e, 'zero'); e.memory.write('FaultDivisor', 1); e.step()
        self.assertEqual(e.memory.read('BufferA[1]'), 2)
        h = files.AOIFileTests(); h.setUp(); self.addCleanup(h.doCleanups)
        def file_fields(root):
            literals.FileIntegerLiteralTests.aoi_fields(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text = text.text.replace('+1L', '-16#FFFFFFFF')
        e = h.checked(file_fields, kind='1'); e.memory.write('Transform', True); e.memory.write('Search', True); e.step()
        e.memory.write('Transform', False); e.memory.write('Search', False); e.memory.write('FaultDivisor', 0); self.fault(e, 'zero')
        e.memory.write('FaultDivisor', 1); e.step(); self.assertEqual(e.memory.read('OutputA')[:2], [9007199254740995, 9007199254740997])

    def test_public_sample_results_rollback_recovery_and_report(self):
        e = Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers, []); e.step(); self.assertEqual(e.memory.read('DintExprSelected'), [101, None, 999])
        e.memory.write('DintExprIndex', 1); e.memory.write('DintExprEnabled', True); e.step()
        expected = {'Value':6, 'Quotient':-3, 'Remainder':-1, 'Bcd':166666665, 'Root':3, 'Power':4,
                    'Wide':9007199254740992, 'Match':True, 'Negative':True, 'Selected':[101, 6, 999]}
        for name, value in expected.items():self.assertEqual(e.memory.read('DintExpr'+name), value, name)
        for name in ['DintExprDivisor', 'DintExprLateDivisor']:
            previous = e.memory.read(name); e.memory.write(name, 0); self.fault(e, 'zero')
            e.memory.write(name, previous); e.step()
        from logixlab.wide_st import ladder_description
        report = ladder_description(e.project)['signed_dint_radix_expressions']
        self.assertEqual(report['instructions'], ['CPT', 'CMP', 'FAL', 'FSC']); self.assertFalse(report['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
