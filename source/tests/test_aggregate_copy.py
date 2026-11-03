"""Matching record copies, lazy references, overlap and atomic recovery."""
import copy
import unittest
from xml.etree import ElementTree as E

from logixlab.model import ModelError
import test_aggregate_fill as fill
from test_numeric_copy import logic


class AggregateCopyTests(unittest.TestCase):
    setUp = fill.AggregateFillTests.setUp
    engine = fill.AggregateFillTests.engine
    checked = fill.AggregateFillTests.checked
    snapshot = staticmethod(fill.AggregateFillTests.snapshot)

    @staticmethod
    def fields(root):
        fill.AggregateFillTests.fields(root)
        tags = root.find('./Controller/Tags')
        for name in ('Records', 'Timers', 'Counters', 'Controls', 'Texts', 'CustomTexts'):
            tag = copy.deepcopy(tags.find('./Tag[@Name="' + name + '"]'))
            tag.set('Name', 'Copy' + name)
            tags.append(tag)

    def test_false_and_prescan_skip_saved_length_and_both_live_indices(self):
        e = self.checked(['XIC(StartPB)COP(Records[SourceIndex],CopyRecords[Index],Lengths[0]);'])
        before = copy.deepcopy(e.memory.values); e.step(); self.assertEqual(e.memory.values, before)
        e.memory.write('StartPB', True)
        for expected, writes in [('Unknown', []), ('outside bounds', [('Lengths[0]', 1)]),
                                 ('outside bounds', [('SourceIndex', 2)])]:
            for ref, value in writes:e.memory.write(ref, value)
            before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, expected):e.step()
            self.assertEqual(self.snapshot(e), before)
        e.memory.write('Index', 0); e.step()
        self.assertEqual(e.memory.read('CopyRecords')[0], e.memory.read('Records')[2])
        self.assertEqual(e.memory.read('CopyRecords')[0]['Count'], 777)

    def test_full_records_copy_unknowns_without_consuming_them_and_own_storage(self):
        for op in ('COP', 'CPS'):
            e = self.checked([f'{op}(Records[0],CopyRecords[1],1);'])
            e.memory.write('Records[0].Enabled', True); e.memory.write('Records[0].Flags[0]', True)
            e.memory.write('CopyRecords[1].Count', 123); guard = copy.deepcopy(e.memory.read('CopyRecords')[2])
            e.step(); self.assertEqual(e.memory.read('Records')[0], e.memory.read('CopyRecords')[1])
            self.assertIsNone(e.memory.read('CopyRecords')[1]['Count'])
            self.assertEqual(e.memory.read('CopyRecords')[2], guard)
            e.memory.write('Records[0].Flags[0]', False)
            self.assertIs(e.memory.read('CopyRecords')[1]['Flags'][0], True)
            self.assertIsNot(e.memory.read('Records')[0], e.memory.read('CopyRecords')[1])

    def test_all_basic_records_and_custom_strings_copy_complete_saved_values(self):
        for name in ('Timers', 'Counters', 'Controls', 'Texts', 'CustomTexts'):
            e = self.checked([f'CPS({name}[0],Copy{name}[1],1);'])
            field = 'DATA[0]' if 'Texts' in name else 'ACC' if name in ('Timers', 'Counters') else 'POS'
            e.memory.write(name + '[0].' + field, 65 if 'Texts' in name else 17)
            if 'Texts' in name:e.memory.write(name + '[0].LEN', 0)
            e.step(); self.assertEqual(e.memory.read(name)[0], e.memory.read('Copy' + name)[1])
            self.assertIsNone(e.memory.read('Copy' + name)[0]['LEN' if 'Texts' in name or name == 'Controls' else 'ACC'])
            if 'Texts' in name:self.assertEqual(e.memory.read('Copy' + name)[1]['DATA'][0], 65)

    def test_forward_and_backward_overlap_retain_sequential_logical_behavior(self):
        for op in ('COP', 'CPS'):
            for source, dest, expected in [(0, 1, [10, 10, 10]), (1, 0, [20, 30, 30])]:
                e = self.checked([f'{op}(Records[{source}],Records[{dest}],2);'])
                for i, value in enumerate((10, 20, 30)):e.memory.write(f'Records[{i}].Count', value)
                e.step(); self.assertEqual([row['Count'] for row in e.memory.read('Records')], expected)
                e.memory.write('Records[1].Count', 99); self.assertEqual(e.memory.read('Records')[2]['Count'], expected[2])

    def test_source_destination_windows_and_length_are_captured_before_writes(self):
        e = self.checked(['COP(Records[0],Records[1],Records[1].Count);'])
        e.memory.write('Records[0].Count', 7); e.memory.write('Records[1].Count', 2)
        e.step(); self.assertEqual([row['Count'] for row in e.memory.read('Records')], [7, 7, 7])
        e = self.checked(['CPS(Records[0],Records[Records[1].Count],2);'])
        e.memory.write('Records[0].Count', 7); e.memory.write('Records[1].Count', 1)
        e.step(); self.assertEqual([row['Count'] for row in e.memory.read('Records')], [7, 7, 7])

    def test_zero_length_still_resolves_both_live_addresses_without_values(self):
        e = self.checked(['COP(Records[SourceIndex],CopyRecords[Index],0);'])
        for writes in ([], [('SourceIndex', 0)]):
            for ref, value in writes:e.memory.write(ref, value)
            before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e), before)
        e.memory.write('Index', 0); before = copy.deepcopy(e.memory.values); e.step()
        self.assertEqual(e.memory.values, before)

    def test_complete_regions_are_strict_and_dynamic_lengths_are_checked_when_reached(self):
        for ref in ('Records[0],CopyRecords[Index]', 'Records[Index],CopyRecords[0]'):
            e = self.checked(['MOV(55,SpeedCommand);', f'COP({ref},Lengths[0]);'])
            e.memory.write('Index', 2); e.memory.write('Lengths[0]', 2); before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'boundary'):e.step()
            self.assertEqual(self.snapshot(e), before)
            for length in (-1, 100001):
                e.memory.write('Lengths[0]', length); before = self.snapshot(e)
                with self.assertRaisesRegex(ModelError, 'length'):e.step()
                self.assertEqual(self.snapshot(e), before)
            e.memory.write('Lengths[0]', 1); e.step(); self.assertEqual(e.memory.read('SpeedCommand'), 55)

    def test_budget_and_later_fault_restore_records_time_scheduler_and_bindings(self):
        for tail, expected in [([], 'scalar-member budget'), (['DIV(1,SpeedSetpoint,SpeedCommand);'], 'zero')]:
            e = self.checked(['MOV(55,SpeedCommand);', 'CPS(Records[2],CopyRecords[0],1);'] + tail)
            e.memory.write('SpeedSetpoint', 0)
            if not tail:e.instruction_limit = 10
            before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, expected):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.instruction_limit = 1000; e.memory.write('SpeedSetpoint', 1); e.step()
            self.assertEqual(e.memory.read('CopyRecords')[0]['Count'], 777)

    def test_alias_constant_source_and_multidimensional_member_windows(self):
        def setup(root):
            tags = root.find('./Controller/Tags')
            grid = E.SubElement(tags, 'Tag', Name='Grid', DataType='FillCell', TagType='Base', Dimensions='2,2')
            E.SubElement(E.SubElement(grid, 'Data', Format='Decorated'), 'Array', DataType='FillCell', Dimensions='2,2')
            members = E.SubElement(E.SubElement(root.find('./Controller/DataTypes'), 'DataType', Name='Box'), 'Members')
            E.SubElement(members, 'Member', Name='Cells', DataType='FillCell', Dimension='3')
            boxed = E.SubElement(tags, 'Tag', Name='Boxed', DataType='Box', TagType='Base')
            record = E.SubElement(E.SubElement(boxed, 'Data', Format='Decorated'), 'Structure', DataType='Box')
            E.SubElement(record, 'ArrayMember', Name='Cells', DataType='FillCell', Dimensions='3')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'), 'Tag', Name='View', TagType='Alias', AliasFor='Grid')
            tags.find('./Tag[@Name="Records"]').set('Constant', 'true')
        e = self.checked(['COP(Records[1],View[0,1],2);', 'CPS(View[1,0],Boxed.Cells[1],1);'], setup)
        e.step(); self.assertIsNone(e.memory.read('Grid')[0][0]['Count'])
        self.assertEqual(e.memory.read('Grid')[1][0]['Count'], 777)
        self.assertEqual(e.memory.read('Boxed.Cells')[1]['Count'], 777)
        self.assertIsNone(e.memory.read('Boxed.Cells')[2]['Count'])

    @staticmethod
    def aoi_logic(root):
        fill.AggregateFillTests.aoi_logic(root)
        texts = root.findall('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name="FillWorker"]/Routines/Routine/RLLContent/Rung/Text')
        for node, text in zip(texts, ['COP(Buffer[Position],LocalCells[Position],1);', 'CPS(LocalCells[Position],Buffer[Position],1);']):node.text = text

    def test_aoi_local_and_inout_copies_have_independent_storage_and_binding_rollback(self):
        e = self.checked(['XIC(EnabledA)FillWorker(First,Records,IndexA);', 'XIC(EnabledB)FillWorker(Second,Records,IndexB);'], self.aoi_logic)
        e.memory.write('Records[0].Count', 17); e.memory.write('Records[1].Count', 27); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('IndexB', 1); e.step()
        self.assertEqual((e.memory.read('First.LocalCells')[0]['Count'], e.memory.read('Second.LocalCells')[1]['Count']), (17, 27))
        e.memory.write('Records[0].Count', 19); self.assertEqual(e.memory.read('First.LocalCells')[0]['Count'], 17)
        e.memory.write('EnabledB', False); e.memory.write('IndexB', 99); e.step()
        e.memory.write('EnabledB', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_existing_st_calls_share_selection_and_for_protects_nested_bound_members(self):
        def st(root):
            routine = root.find('./Controller/Programs/Program/Routines/Routine')
            routine.remove(routine.find('RLLContent')); routine.set('Type', 'ST')
            logic(routine, ['IF StartPB THEN CPS(Records[SourceIndex],CopyRecords[Index],Lengths[0]); END_IF;'])
        e = self.checked([], st); e.step(); e.memory.write('Lengths[0]', 1); e.memory.write('SourceIndex', 2); e.memory.write('Index', 1); e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('CopyRecords')[1]['Count'], 777)
        def loop(root):
            st(root); routine = root.find('./Controller/Programs/Program/Routines/Routine')
            routine.remove(routine.find('STContent')); logic(routine, ['FOR SpeedCommand:=0 TO CopyRecords[1].Count DO COP(Records[0],CopyRecords[0],2); END_FOR;'])
        self.assertTrue(any('bounds/step' in b for b in self.engine([], loop).blockers))

    def test_structural_errors_constants_and_excluded_schemas_stay_blocked(self):
        for instruction in ('COP', 'CPS'):
            for args in ('Records[99],CopyRecords[0],0', 'Records[0],CopyRecords[0],4', 'Records[0],CopyRecords[0],-1', 'Records[0],CopyRecords[0],1.0', 'Records[0],CopyTimers[0],1', 'Records[0],CopyRecords[0],StartPB', 'Records[0],CopyRecords[0],Records[0].Wide'):
                self.assertTrue(self.engine([f'AFI(){instruction}({args});']).blockers, args)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="CopyRecords"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()COP(Records[0],CopyRecords[0],1);'], constant).blockers)
        def operational(root):root.find('./Controller/DataTypes/DataType[@Name="FillCell"]/Members/Member[@Name="Timer"]').set('DataType', 'PID')
        self.assertTrue(self.engine(['AFI()COP(Records[0],CopyRecords[0],1);'], operational).blockers)
        def older(root):root.find('Controller').set('ProcessorType', '1756-L75')
        self.assertTrue(self.engine(['AFI()COP(Records[SourceIndex],CopyRecords[Index],Lengths[0]);'], older).blockers)
        report = self.checked(['AFI()COP(Records[0],CopyRecords[0],1);']).report()['aggregate_copy']
        self.assertTrue(report['available']); self.assertFalse(report['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
