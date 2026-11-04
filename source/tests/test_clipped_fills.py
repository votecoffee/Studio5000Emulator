"""Clipped numeric FLL windows, capture, scope and conservative ST effects."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_numeric_fill as fixtures
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class ClippedFillTests(unittest.TestCase):
    setUp = fixtures.NumericFillTests.setUp
    engine = fixtures.NumericFillTests.engine
    checked = fixtures.NumericFillTests.checked
    snapshot = staticmethod(fixtures.NumericFillTests.snapshot)
    aoi = fixtures.NumericFillTests.aoi

    def st(self, text, **kwargs):
        extra = kwargs.pop('mutate', None)
        def source(root):
            routine = root.find('./Controller/Programs/Program/Routines/Routine'); routine.set('Type', 'ST'); routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine, 'STContent'), 'Line', Number='0').text = text
            if extra:extra(root)
        return self.engine(['NOP();'], mutate=source, **kwargs)

    def clipped_aoi(self):
        e = self.aoi(typed=True); root = E.parse(e.project.path).getroot()
        for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
            text.text = text.text.replace('FLL(Value,Buffer[Index],2)', 'FLL(Value,Buffer[Index],100000)').replace('FLL(Value,Stack[0],2)', 'FLL(Value,Stack[0],100000)')
        E.ElementTree(root).write(e.project.path, encoding='utf8', xml_declaration=True); e = Engine(Project(e.project.path)); self.assertEqual(e.blockers, []); return e

    def test_all_sixteen_type_pairs_clip_without_changing_conversion(self):
        for source in ('SINT', 'INT', 'DINT', 'REAL'):
            for dest in ('SINT', 'INT', 'DINT', 'REAL'):
                value = 3.5 if source == 'REAL' else 3
                result = 3.5 if source == dest == 'REAL' else 4 if source == 'REAL' else 3
                e = self.checked(['FLL(Source,Fills[3],Mask);'], source_type=source, dest_type=dest, value=value, count=100000); e.step()
                self.assertEqual(e.memory.read('Fills'), [11, 22, 33, result, result]); self.assertEqual(e.memory.read('Source'), value)

    def test_whole_array_and_scalar_destinations_clip_at_their_own_ends(self):
        e = self.checked(['FLL(Source,Fills,100000)FLL(Source,Dest,100000);'], source_type='REAL', dest_type='INT', value=3.5); e.step()
        self.assertEqual(e.memory.read('Fills'), [4] * 5); self.assertEqual(e.memory.read('Dest'), 4)

    def test_source_and_length_are_captured_before_clipped_overlap_stores(self):
        e = self.checked(['FLL(Fills[1],Fills[0],Fills[0]);'], dest_type='DINT'); e.memory.write('Fills[0]', 100000); e.step()
        self.assertEqual(e.memory.read('Fills'), [22] * 5)

    def test_zero_length_skips_unknown_source_and_still_checks_destination(self):
        e = self.checked(['FLL(Source,Fills[Dest],0);']); e.memory.values['source'] = None; e.step()
        self.assertEqual(e.memory.read('Fills'), [11, 22, 33, 44, 55]); e.memory.write('Dest', 99); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_false_call_keeps_invalid_destination_and_length_dormant(self):
        e = self.checked(['XIC(StartPB)FLL(Source,Fills[Dest],Mask);'], value=4660, count=100000); e.memory.write('Dest', 99); e.step()
        e.memory.write('StartPB', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('Dest', 3); e.step(); self.assertEqual(e.memory.read('Fills'), [11, 22, 33, 52, 52])
        e.memory.write('StartPB', False); e.memory.write('Mask', -1); e.step()

    def test_partial_unknown_array_source_and_destinations_are_not_zero_assumed(self):
        def unknown(root):
            for name, dtype in [('Inputs', 'DINT'), ('Fills', 'SINT')]:
                node = root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Array'); dimensions = node.get('Dimensions'); node.clear(); node.attrib.update(DataType=dtype, Dimensions=dimensions)
        e = self.checked(['XIC(StartPB)FLL(Inputs[0],Fills[3],Mask);'], count=100000, mutate=unknown); e.step(); e.memory.write('StartPB', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('Inputs[0]', 4660); e.step(); self.assertEqual(e.memory.read('Fills'), [None, None, None, 52, 52])

    def test_multidimensional_tail_is_row_major_and_bounded(self):
        def matrix(root):
            tag = root.find('./Controller/Tags/Tag[@Name="Fills"]'); tag.set('Dimensions', '2,3'); array = tag.find('Data/Array'); array.clear(); array.attrib.update(DataType='SINT', Dimensions='2,3')
            for i in range(6):E.SubElement(array, 'Element', Index=f'[{i//3},{i%3}]', Value=str(i))
        e = self.checked(['FLL(Source,Fills[0,2],100000);'], value=128, mutate=matrix); e.step(); self.assertEqual(e.memory.read('Fills'), [[0, 1, -128], [-128, -128, -128]])

    def test_member_array_stops_before_sibling_and_alias_keeps_that_boundary(self):
        def member(root):
            controller = root.find('Controller'); types = controller.find('DataTypes'); dtype = E.SubElement(types, 'DataType', Name='Packet', Family='NoFamily', Class='User'); members = E.SubElement(dtype, 'Members')
            E.SubElement(members, 'Member', Name='Values', DataType='SINT', Dimension='3'); E.SubElement(members, 'Member', Name='Guard', DataType='DINT', Dimension='0')
            tag = E.SubElement(controller.find('Tags'), 'Tag', Name='Packet1', DataType='Packet', TagType='Base'); record = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Structure', DataType='Packet'); array = E.SubElement(record, 'ArrayMember', Name='Values', DataType='SINT', Dimensions='3')
            for i, value in enumerate((11, 22, 33)):E.SubElement(array, 'Element', Index=f'[{i}]', Value=str(value))
            E.SubElement(record, 'DataValueMember', Name='Guard', DataType='DINT', Value='777'); E.SubElement(controller.find('Tags'), 'Tag', Name='View', TagType='Alias', AliasFor='Packet1.Values')
        e = self.checked(['FLL(Source,View[1],100000);'], value=128, mutate=member); e.step()
        self.assertEqual(e.memory.read('Packet1.Values'), [11, -128, -128]); self.assertEqual(e.memory.read('Packet1.Guard'), 777)

    def test_bad_lengths_conversion_ranges_and_later_faults_are_atomic(self):
        for count in (-1, 100001):
            e = self.checked(['XIC(StartPB)FLL(Source,Fills[3],Mask);'], count=count); e.step(); e.memory.write('StartPB', True); before = self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e), before)
        e = self.checked(['XIC(StartPB)FLL(Source,Fills[3],Mask);'], source_type='REAL', dest_type='DINT', value=3.4e38, count=100000); e.step(); e.memory.write('StartPB', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'overflow'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e = self.checked(['XIC(StartPB)FLL(Source,Fills[3],Mask)DIV(1,Dest,SpeedCommand);'], value=4660, count=100000); e.step(); e.memory.write('StartPB', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'zero'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('Dest', 1); e.step(); self.assertEqual(e.memory.read('Fills')[3:], [52, 52])

    def test_existing_aoi_inout_and_typed_local_arrays_clip_independently(self):
        e = self.clipped_aoi(); e.step()
        self.assertEqual(e.memory.read('BufferA'), [101] + [22136] * 5); self.assertEqual(e.memory.read('BufferB')[2:], [-129] * 4)
        self.assertEqual(e.memory.read('DriverA.Stack'), [120] * 4); self.assertEqual(e.memory.read('DriverB.Stack'), [127] * 4)
        e = self.clipped_aoi(); e.memory.write('FaultDivisor', 0); before = self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_emulator_st_extension_clips_and_protects_the_complete_for_window(self):
        e = self.st('FLL(Source,Fills[3],100000);', value=4660); self.assertEqual(e.blockers, []); e.step(); self.assertEqual(e.memory.read('Fills'), [11, 22, 33, 52, 52])
        e = self.st('FOR Dest:=0 TO Fills[0] DO FLL(Source,Fills[3],100000); END_FOR;', dest_type='DINT', value=3); self.assertEqual(e.blockers, []); e.step(); self.assertEqual(e.memory.read('Fills'), [11, 22, 33, 3, 3])
        e = self.st('FOR Dest:=0 TO Fills[4] DO FLL(Source,Fills[3],100000); END_FOR;', dest_type='DINT'); self.assertTrue(e.blockers)

    def test_st_dynamic_alias_effects_are_conservative_and_zero_literal_is_empty(self):
        def view(root):E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='View', TagType='Alias', AliasFor='Fills[Mask]')
        e = self.st('FOR Dest:=0 TO Fills[0] DO FLL(Source,View,1); END_FOR;', dest_type='DINT', count=3, mutate=view); self.assertTrue(e.blockers)
        e = self.st('FOR Dest:=0 TO Fills[0] DO FLL(Source,View,0); END_FOR;', dest_type='DINT', count=3, mutate=view); self.assertEqual(e.blockers, []); e.step(); self.assertEqual(e.memory.read('Fills'), [11, 22, 33, 44, 55])

    def test_aggregate_strict_bounds_other_profiles_and_wide_types_stay_separate(self):
        import test_aggregate_fill as aggregate
        helper = aggregate.AggregateFillTests(); helper.setUp(); self.addCleanup(helper.doCleanups)
        self.assertTrue(helper.engine(['AFI()FLL(0,Records[0],4);']).blockers)
        for source in ('LINT', 'USINT', 'ULINT'):self.assertTrue(self.engine(source_type=source).blockers)
        def old(root):root.find('Controller').set('ProcessorType', '1756-L75')
        self.assertTrue(self.engine(count=100000, mutate=old).blockers)
        e = self.checked(); self.assertTrue(e.report()['numeric_fill']['clipping']); self.assertFalse(e.report()['numeric_fill']['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
