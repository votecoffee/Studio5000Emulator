"""Lazy ladder comparison operands, masks, limits and scan rollback."""
import copy
from unittest.mock import patch
import unittest
from xml.etree import ElementTree as E

import test_bit_transfer as fixtures
from logixlab.model import ModelError


class NumericComparisonTests(unittest.TestCase):
    setUp = fixtures.BitTransferTests.setUp
    checked = fixtures.BitTransferTests.checked

    def engine(self, rungs=None, *, types=('DINT', 'DINT', 'DINT'), values=(7, 15, 7), mutate=None):
        def fields(root):
            tags = root.find('./Controller/Tags')
            tag = E.SubElement(tags, 'Tag', Name='Values', DataType=types[0], Dimensions='3', TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType=types[0], Dimensions='3')
            tag = E.SubElement(tags, 'Tag', Name='Index', DataType='DINT', TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='999')
            if mutate:mutate(root)
        return fixtures.BitTransferTests.engine(self, rungs or ['MEQ(Source,Mask,Dest)OTE(RunLatch);'],
                                               types=types, values=values, mutate=fields)

    @staticmethod
    def snapshot(e):
        bindings = (e.memory.frames, e.memory._resolved, e.addons.instances) if e.project.aois else None
        return copy.deepcopy((e.memory.values, bindings, e.time_ms, e.scan_count, e.trace, e.scheduler_description()))

    def test_all_six_relations_import_unknown_elements_and_read_only_when_enabled(self):
        for name, expected in (('EQU', True), ('NEQ', False), ('LES', False), ('LEQ', True), ('GRT', False), ('GEQ', True)):
            e = self.checked([f'XIC(StartPB){name}(Values[Index],7)OTE(RunLatch);'])
            e.memory.write('RunLatch', True);e.step();self.assertFalse(e.memory.read('RunLatch'))
            e.memory.write('StartPB', True);before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('Index', 0);before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('Values[0]', 7);e.step();self.assertEqual(e.memory.read('RunLatch'), expected)

    def test_false_comparisons_do_not_sample_live_index_values(self):
        for text in ('EQU(Values[Index],7)', 'LIM(0,Values[Index],10)', 'MEQ(Values[Index],15,7)'):
            e = self.checked(['XIC(StartPB)' + text + 'OTE(RunLatch);'])
            reads = [];original = e.memory.read
            def observed(ref, scope=''):
                if not e.memory.structural:reads.append(ref)
                return original(ref, scope)
            with patch.object(e.memory, 'read', side_effect=observed):e.step()
            self.assertNotIn('Index', reads);self.assertNotIn('Values[Index]', reads)
            self.assertFalse(e.memory.structural)

    def test_prescan_skips_unknown_meq_and_lim_operands(self):
        e = self.checked(['MEQ(Values[Index],Mask,Dest)OTE(RunLatch);', 'LIM(0,Values[Index],10)OTE(BatchComplete);'])
        self.assertEqual(e.scan_count, 0);self.assertFalse(e.memory.read('RunLatch'))
        self.assertFalse(e.memory.read('BatchComplete'));self.assertEqual(e.memory.read('Values'), [None] * 3)

    def test_meq_each_unknown_operand_faults_only_when_reached(self):
        for position in range(3):
            args = ['7', '15', '7'];args[position] = 'Values[0]'
            e = self.checked(['XIC(StartPB)MEQ(' + ','.join(args) + ')OTE(RunLatch);']);e.step()
            e.memory.write('StartPB', True);before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('Values[0]', 15 if position == 1 else 7);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_zero_meq_mask_still_consumes_unknown_source_and_compare(self):
        for text in ('MEQ(Values[0],0,7)', 'MEQ(7,0,Values[0])'):
            e = self.checked([text + 'OTE(RunLatch);']);before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('Values[0]', -123);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_meq_narrow_zero_fill_and_radix_patterns_are_preserved(self):
        for dtype, expected in (('SINT', 255), ('INT', 65535), ('DINT', 4294967295)):
            e = self.checked([f'MEQ(Source,16#FFFF_FFFF,16#{expected:X})OTE(RunLatch);'],
                             types=(dtype, 'DINT', 'DINT'), values=(-1, 0, 0));e.step()
            self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Source'), -1)
        for mask in ('2#1111', '8#17', '16#F', '-1'):
            e = self.checked([f'MEQ(Source,{mask},Dest)OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_meq_wide_unknowns_and_exact_high_bits_for_all_five_types(self):
        for dtype, value in (('LINT', -9223372036854775808), ('ULINT', 1 << 63), ('USINT', 255), ('UINT', 65535), ('UDINT', 1 << 31)):
            e = self.checked(['XIC(StartPB)MEQ(Values[0],Mask,Dest)OTE(RunLatch);'],
                             types=(dtype,) * 3, values=(0, value, value));e.step()
            e.memory.write('StartPB', True);before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('Values[0]', value);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_lim_each_operand_is_lazy_and_required_when_true(self):
        for position in range(3):
            args = ['0', '5', '10'];args[position] = 'Values[0]'
            e = self.checked(['XIC(StartPB)LIM(' + ','.join(args) + ')OTE(RunLatch);']);e.step()
            e.memory.write('StartPB', True);before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('Values[0]', (0, 5, 10)[position]);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_lim_inclusive_reversed_equal_and_real_bounds(self):
        for low, high, rows in ((2, 8, ((1, False), (2, True), (5, True), (8, True), (9, False))),
                                (8, 2, ((1, True), (2, True), (5, False), (8, True), (9, True))),
                                (2, 2, ((1, False), (2, True), (3, False)))):
            for value, expected in rows:
                e = self.checked([f'LIM({low},Source,{high})OTE(RunLatch);'], values=(value, 0, 0));e.step()
                self.assertEqual(e.memory.read('RunLatch'), expected)
        e = self.checked(['LIM(2.0,Source,3.0)OTE(RunLatch);'], types=('REAL', 'DINT', 'DINT'), values=(2.5, 0, 0));e.step()
        self.assertTrue(e.memory.read('RunLatch'))

    def test_wide_relations_and_limits_preserve_adjacent_64_bit_values(self):
        for dtype in ('LINT', 'ULINT'):
            e = self.checked(['GRT(Source,Dest)OTE(RunLatch);', 'LIM(Dest,Source,Mask)OTE(BatchComplete);'],
                             types=(dtype,) * 3, values=(9007199254740993, 9007199254740994, 9007199254740992));e.step()
            self.assertTrue(e.memory.read('RunLatch'));self.assertTrue(e.memory.read('BatchComplete'))

    def test_program_local_alias_array_references(self):
        def alias(root):
            tags = root.find('./Controller/Programs/Program/Tags')
            E.SubElement(tags, 'Tag', Name='View', DataType='DINT', TagType='Alias', AliasFor='Values')
        e = self.checked(['XIC(StartPB)MEQ(View[Index],15,7)OTE(RunLatch);'], mutate=alias)
        e.step();e.memory.write('StartPB', True);e.memory.write('Index', 0);e.memory.write('Values[0]', 7)
        e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_comparison_operands_remain_read_only_and_downstream_contacts_work(self):
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant', 'true')
        e = self.checked(['MEQ(Source,Mask,Dest)GEQ(Source,Dest)LIM(0,Source,10)OTE(RunLatch);'], mutate=constant)
        before = tuple(e.memory.read(t) for t in ('Source', 'Mask', 'Dest'));e.step()
        self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(tuple(e.memory.read(t) for t in ('Source', 'Mask', 'Dest')), before)
        e.memory.write('Dest', 8);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_type_shape_bad_indices_and_wide_profile_rejection(self):
        for text in ('MEQ(TRUE,1,1)', 'MEQ(1.0,1,1)', 'MEQ(Values,1,1)', 'MEQ(16#100000000,1,1)',
                     'LIM(0,StartPB,10)', 'EQU(Values,7)', 'EQU(Values[999],7)'):
            self.assertTrue(self.engine(['AFI()' + text + 'OTE(RunLatch);']).blockers, text)
        for types in (('LINT', 'REAL', 'LINT'), ('USINT', 'BOOL', 'USINT')):
            self.assertTrue(self.engine(types=types).blockers)

    def test_later_unknown_comparison_rolls_back_prior_writes_coils_and_time(self):
        e = self.checked(['MOV(99,SpeedCommand);', 'MEQ(Source,Mask,Dest)OTE(RunLatch);', 'LIM(0,Values[0],10)OTE(BatchComplete);'])
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Values[0]', 5);e.step();self.assertTrue(e.memory.read('BatchComplete'))

    def test_aoi_inout_local_comparisons_and_binding_rollback(self):
        import test_aoi_queues as queues
        fixture = queues.AOIQueueTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        def logic(root):
            queues.logic(root, ['MEQ(Buffer[Index],0,Stack[0])LIM(0,Stack[1],10)OTE(EnableOut);'])
            queues.logic(root, ['AFI()MEQ(Buffer[Index],0,Stack[0])LIM(0,Stack[1],10)OTE(EnableOut);'], name='EnableInFalse')
        e = fixture.checked(logic);e.step();e.memory.write('EnabledB', False);e.memory.write('IndexB', 999);e.step()
        e.memory.write('EnabledB', True);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('IndexB', 2);e.step()

    def test_other_profiles_and_string_comparisons_keep_their_paths(self):
        def old(root):root.find('Controller').set('ProcessorType', '1756-L75')
        e = self.checked(mutate=old);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertFalse(e.report()['numeric_comparisons']['available'])
        report = self.checked().report()['numeric_comparisons'];self.assertEqual(len(report['instructions']), 8)
        self.assertFalse(report['native_runtime_parity'])
