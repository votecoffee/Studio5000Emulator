"""Array metadata reads and finite REAL truncation with lazy runtime operands."""
import copy
from xml.etree import ElementTree as E
import unittest

import test_bit_transfer as fixtures
from logixlab.model import ModelError


class SizeTruncateTests(unittest.TestCase):
    setUp = fixtures.BitTransferTests.setUp
    checked = fixtures.BitTransferTests.checked

    def engine(self, rungs=None, *, source='REAL', dest='DINT', value=3.9, dimension=0, mutate=None):
        def fields(root):
            tags = root.find('./Controller/Tags')
            for name, kind, dims in (('Grid', 'DINT', '2,3'), ('Results', 'DINT', '3'), ('Reals', 'REAL', '2')):
                tag = E.SubElement(tags, 'Tag', Name=name, DataType=kind, Dimensions=dims, TagType='Base')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType=kind, Dimensions=dims)
            banner = E.SubElement(tags, 'Tag', Name='Banner', DataType='STRING', TagType='Base')
            E.SubElement(banner, 'Data', Format='L5K').text = "[0,'" + '$00' * 82 + "']"
            if mutate:mutate(root)
        return fixtures.BitTransferTests.engine(self, rungs or ['TRN(Source,Dest);'],
                                               types=(source, 'DINT', dest), values=(value, dimension, 0), mutate=fields)

    @staticmethod
    def snapshot(e):
        bindings = (e.memory.frames, e.memory._resolved, e.addons.instances) if e.project.aois else None
        return copy.deepcopy((e.memory.values, bindings, e.time_ms, e.scan_count, e.trace, e.scheduler_description()))

    def test_size_unknown_array_leaves_are_metadata_not_values(self):
        e = self.checked(['SIZE(Grid,0,Results[0])SIZE(Grid[1,2],1,Results[1]);'])
        e.step()
        self.assertEqual(e.memory.read('Results'), [2, 3, None])
        self.assertEqual(e.memory.read('Grid'), [[None] * 3] * 2)

    def test_size_all_supported_destinations(self):
        for dtype in ('SINT', 'INT', 'DINT', 'REAL'):
            e = self.checked(['SIZE(Grid[0,0],1,Dest);'], dest=dtype)
            e.memory.values['dest'] = None
            e.step();self.assertEqual(e.memory.read('Dest'), 3)
            self.assertEqual(type(e.memory.read('Dest')), float if dtype == 'REAL' else int)

    def test_size_partial_subscript_keeps_declared_dimensions(self):
        e = self.checked(['SIZE(Grid[1],0,Dest);']);e.step()
        self.assertEqual(e.memory.read('Dest'), 2)

    def test_size_string_data_capacity_ignores_unknown_len_and_bytes(self):
        e = self.checked(['SIZE(Banner.DATA[0],0,Dest);'])
        e.memory.values['banner'] = {'LEN': None, 'DATA': [None] * 82};e.step()
        self.assertEqual(e.memory.read('Dest'), 82)
        self.assertIsNone(e.memory.values['banner']['LEN'])

    def test_size_member_arrays_choose_closest_array(self):
        def strings(root):
            tags = root.find('./Controller/Tags')
            labels = E.SubElement(tags, 'Tag', Name='Labels', DataType='STRING', Dimensions='2', TagType='Base')
            array = E.SubElement(E.SubElement(labels, 'Data', Format='Decorated'), 'Array', DataType='STRING', Dimensions='2')
            for index in range(2):
                obj = E.SubElement(E.SubElement(array, 'Element', Index=f'[{index}]'), 'Structure', DataType='STRING')
                E.SubElement(obj, 'DataValueMember', Name='LEN', DataType='DINT', Value='0')
                data = E.SubElement(obj, 'ArrayMember', Name='DATA', DataType='SINT', Dimensions='82')
                for byte in range(82):E.SubElement(data, 'Element', Index=f'[{byte}]', Value='0')
        for ref in ('Labels[1].DATA', 'Labels[1].DATA[12]'):
            e = self.checked([f'SIZE({ref},0,Dest);'], mutate=strings);e.step()
            self.assertEqual(e.memory.read('Dest'), 82)
        self.assertTrue(self.engine(['SIZE(Labels[1].LEN,0,Dest);'], mutate=strings).blockers)

    def test_size_aliases_and_three_dimensional_arrays(self):
        def cube(root):
            tag = root.find('./Controller/Tags/Tag[@Name="Grid"]');tag.set('Dimensions', '2,3,4')
            tag.find('Data/Array').set('Dimensions', '2,3,4')
            E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='View', DataType='DINT', Dimensions='2,3,4', TagType='Alias', AliasFor='Grid')
        e = self.checked(['SIZE(View[1,2,3],2,Dest);'], mutate=cube);e.step()
        self.assertEqual(e.memory.read('Dest'), 4)

    def test_size_false_and_prescan_skip_unknown_dynamic_operands(self):
        e = self.checked(['XIC(StartPB)SIZE(Grid[Mask,0],Mask,Results[Mask]);'])
        e.memory.values['mask'] = None;e.step()
        e.memory.write('StartPB', True);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Mask', 1);e.step();self.assertEqual(e.memory.read('Results[1]'), 3)

    def test_size_changed_dimensions_indices_and_late_faults_roll_back(self):
        e = self.checked(['MOV(99,Dest);', 'SIZE(Grid[Mask,0],Mask,Results[0]);'])
        for index in (-1, 2, 999):
            e.memory.write('Mask', index);before = self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e), before)
        e.memory.write('Mask', 1);e.step();self.assertEqual(e.memory.read('Results[0]'), 3)

    def test_size_dimension_output_overlap_samples_before_store(self):
        e = self.checked(['SIZE(Grid,Mask,Mask);'], dimension=1);e.step()
        self.assertEqual(e.memory.read('Mask'), 3)

    def test_size_static_bad_forms_are_blocked(self):
        for text in ('SIZE(Grid,2,Dest);', 'SIZE(Grid,-1,Dest);', 'SIZE(Grid,1.0,Dest);',
                     'SIZE(Grid,TRUE,Dest);', 'SIZE(Source,0,Dest);', 'SIZE(Dest.0,0,Mask);',
                     'SIZE(Grid,0,StartPB);', 'SIZE(Grid,0,Results);'):
            self.assertTrue(self.engine([text]).blockers, text)

    def test_size_dynamic_rank_checked_on_execution(self):
        e = self.checked(['SIZE(Grid,Mask,Dest);'], dimension=2);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'rank'):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_trn_each_signed_unsigned_and_real_destination(self):
        for dtype in ('SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'REAL'):
            e = self.checked(dest=dtype);e.memory.values['dest'] = None;e.step()
            self.assertEqual(e.memory.read('Dest'), 3)
        for value, expected in ((-3.9, -3), (-0.9, 0), (3.5, 3), (-3.5, -3)):
            e = self.checked(value=value);e.step();self.assertEqual(e.memory.read('Dest'), expected)

    def test_trn_float32_precision_before_truncation_and_same_tag(self):
        e = self.checked(['TRN(Source,Source);'], value=16777217);e.step()
        self.assertEqual(e.memory.read('Source'), 16777216.0)
        e = self.checked(['TRN(-2.9,Dest);']);e.step();self.assertEqual(e.memory.read('Dest'), -2)

    def test_trn_wide_results_and_boundaries(self):
        for dest, value in (('LINT', 2**62), ('ULINT', 2**63), ('UDINT', 2**31)):
            e = self.checked(dest=dest, value=value);e.step();self.assertEqual(e.memory.read('Dest'), value)
        for dest, value in (('SINT', 128.0), ('USINT', -1.0), ('LINT', 2**63), ('ULINT', 2**64)):
            e = self.checked(dest=dest, value=value);before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'overflow'):e.step()
            self.assertEqual(self.snapshot(e), before)

    def test_trn_unknown_source_and_destination_indices_are_lazy(self):
        e = self.checked(['XIC(StartPB)TRN(Reals[Mask],Results[Mask]);'], dimension=999);e.step()
        e.memory.write('StartPB', True);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Mask', 1);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Reals[1]', -3.9);e.step();self.assertEqual(e.memory.read('Results'), [None, -3, None])

    def test_trn_bad_types_constants_and_nonfinite_values(self):
        for dtype in ('DINT', 'LINT', 'USINT', 'BOOL'):
            self.assertTrue(self.engine(source=dtype, value=1).blockers)
        for text in ('TRN(Source,StartPB);', 'TRN(TRUE,Dest);', 'TRN(Reals,Dest);', 'TRN(2147483648,Dest);'):
            self.assertTrue(self.engine([text]).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant', 'true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        e = self.checked();e.memory.values['source'] = float('inf');before = self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        # NaN equality is unsuitable here; infinity retains ordinary equality.
        self.assertEqual(self.snapshot(e), before)

    def test_trn_late_fault_rolls_back_size_and_wide_results(self):
        e = self.checked(['SIZE(Grid,0,Results[0]);', 'TRN(Source,Dest);', 'DIV(1,Mask,SpeedCommand);'], dest='LINT')
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'zero'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Mask', 1);e.step();self.assertEqual(e.memory.read('Dest'), 3)

    def test_size_st_call_and_trunc_expression_remain_separate(self):
        def st(root):
            routine = root.find('.//Program/Routines/Routine');routine.set('Type', 'ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine, 'STContent'), 'Line', Number='0').text = 'SIZE(Grid[1,2],1,Dest); Source:=TRUNC(-3.9);'
        e = self.checked(mutate=st);e.step()
        self.assertEqual((e.memory.read('Dest'), e.memory.read('Source')), (3, -3.0))

    def test_size_aoi_inout_local_arrays_and_binding_rollback(self):
        import test_aoi_queues as queues
        fixture = queues.AOIQueueTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        def logic(root):queues.logic(root, ['SIZE(Buffer[Index],0,Stack[0])SIZE(Stack[0],0,Stack[1]);'])
        e = fixture.checked(logic);e.step()
        self.assertEqual((e.memory.read('DriverA.Stack[0]'), e.memory.read('DriverB.Stack[1]')), (6, 4))
        e.memory.write('IndexB', 999);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('IndexB', 2);e.step();self.assertEqual(e.memory.read('DriverB.Stack[0]'), 6)

    def test_other_profiles_retain_legacy_and_report_marks_boundaries(self):
        def old(root):root.find('Controller').set('ProcessorType', '1756-L75')
        e = self.checked(value=3.9, mutate=old);e.step();self.assertEqual(e.memory.read('Dest'), 3)
        self.assertFalse(e.report()['size_truncate']['available'])
        report = self.checked().report()['size_truncate']
        self.assertIn('ULINT', report['trn_destinations']);self.assertFalse(report['native_runtime_parity'])
