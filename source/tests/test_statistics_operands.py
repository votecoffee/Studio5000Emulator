"""AVE/STD indirect result selection, unknown full writes and rollback."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_array_statistics as fixtures
import test_aoi_statistics as aoi
from logixlab.model import ModelError


class StatisticsOperandTests(unittest.TestCase):
    setUp = fixtures.ArrayStatisticsTests.setUp

    def engine(self, rungs, *, mutate=None, **kwargs):
        def fields(root):
            tags = root.find('./Controller/Tags')
            for name in ('SourceIndex', 'ResultIndex', 'ControlIndex'):
                tag = E.SubElement(tags, 'Tag', Name=name, DataType='DINT', TagType='Base')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='99')
            for name, kind in [('Results', 'REAL'), ('IntegerResults', 'DINT'), ('Controls', 'CONTROL')]:
                tag = E.SubElement(tags, 'Tag', Name=name, DataType=kind, TagType='Base', Dimensions='3')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType=kind, Dimensions='3')
            if mutate:mutate(root)
        return fixtures.ArrayStatisticsTests.engine(self, rungs, mutate=fields, **kwargs)

    def checked(self, *args, **kwargs):
        e = self.engine(*args, **kwargs); self.assertEqual(e.blockers, []); self.assertFalse(e.memory.structural); return e

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values, e.memory.frames, e.memory._resolved if e.project.aois else None,
                              e.addons.instances, e.scan_count, e.time_ms, e.scheduler_description(), e.trace, e.last_timer))

    def test_false_and_prescan_skip_unknown_or_invalid_result_indices(self):
        for op in ('AVE', 'STD'):
            e = self.checked([f'XIC(StartPB){op}(Queue[SourceIndex],0,Results[ResultIndex],Ctl,?,?);'])
            e.step(); self.assertEqual(e.memory.read('ResultIndex'), 99); self.assertIsNone(e.memory.read('Results')[0])
            e.memory.values['sourceindex'] = None; e.memory.values['resultindex'] = None; e.step()
            self.assertIsNone(e.memory.values['resultindex']); self.assertIsNone(e.memory.read('Results')[1])

    def test_fresh_calculation_requires_source_then_result_addresses_and_recovers(self):
        for op, expected in [('AVE', 4), ('STD', 2)]:
            e = self.checked([f'XIC(StartPB){op}(Queue[SourceIndex],0,Results[ResultIndex],Ctl,?,?);'], length=3)
            e.step(); e.memory.write('StartPB', True)
            for writes in ([], [('SourceIndex', 0)]):
                for ref, value in writes:e.memory.write(ref, value)
                before = self.snapshot(e)
                with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
                self.assertEqual(self.snapshot(e), before)
            e.memory.write('ResultIndex', 1); e.step(); self.assertEqual(e.memory.read('Results')[1], expected)
            self.assertIs(type(e.memory.read('Results')[1]), float); self.assertIsNone(e.memory.read('Results')[0])

    def test_enable_done_and_error_inhibit_without_consuming_result_indices(self):
        for op in ('AVE', 'STD'):
            for flag in ('EN', 'DN', 'ER'):
                e = self.checked([f'{op}(Queue[SourceIndex],0,Results[ResultIndex],Ctl,?,?);'])
                e.memory.write('Ctl.' + flag, True); e.memory.values['sourceindex'] = None; e.memory.values['resultindex'] = None
                e.step(); self.assertIsNone(e.memory.read('Results')[0]); self.assertTrue(e.memory.read('Ctl.' + flag))

    def test_held_results_skip_changed_indices_and_false_rearms_for_next_window(self):
        for op, first, second in [('AVE', 4, 6), ('STD', 2, 2)]:
            e = self.checked([f'XIC(StartPB){op}(Queue[SourceIndex],0,Results[ResultIndex],Ctl,?,?);'], length=3)
            for ref, value in [('SourceIndex', 0), ('ResultIndex', 1), ('StartPB', True)]:e.memory.write(ref, value)
            e.step(); e.memory.write('SourceIndex', 99); e.memory.write('ResultIndex', 99); e.step()
            self.assertEqual(e.memory.read('Results')[1], first); e.memory.write('StartPB', False); e.step()
            e.memory.write('StartPB', True); before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e), before); e.memory.write('SourceIndex', 1); e.memory.write('ResultIndex', 2); e.step()
            self.assertEqual(e.memory.read('Results')[1:], [first, second])

    def test_required_unknown_samples_still_fault_and_full_writes_establish_unknown_results(self):
        for op, expected in [('AVE', 4), ('STD', 2)]:
            e = self.checked([f'{op}(Queue[0],0,Results[ResultIndex],Ctl,?,?);'], length=3)
            e.memory.write('ResultIndex', 1); e.memory.values['queue'][0] = None; before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before); e.memory.write('Queue[0]', 2); e.step()
            self.assertEqual(e.memory.read('Results')[1], expected); self.assertIsNone(e.memory.read('Results')[2])

    def test_indexed_integer_averages_keep_rounding_and_range_rollback(self):
        for kind in ('SINT', 'INT', 'DINT'):
            def typed(root):
                tag = root.find('./Controller/Tags/Tag[@Name="IntegerResults"]'); tag.set('DataType', kind); tag.find('./Data/Array').set('DataType', kind)
            e = self.checked(['AVE(Queue[0],0,IntegerResults[ResultIndex],Ctl,?,?);'], queue=(1, 2, 3, 4, 999), mutate=typed)
            e.memory.write('ResultIndex', 1); e.step(); self.assertEqual(e.memory.read('IntegerResults')[1], 2)
            self.assertIs(type(e.memory.read('IntegerResults')[1]), int); self.assertIsNone(e.memory.read('IntegerResults')[0])
        def byte(root):
            tag = root.find('./Controller/Tags/Tag[@Name="IntegerResults"]'); tag.set('DataType', 'SINT'); tag.find('./Data/Array').set('DataType', 'SINT')
        e = self.checked(['AVE(Queue[0],0,IntegerResults[ResultIndex],Ctl,?,?);'], length=2, queue=(127, 128, 999), mutate=byte)
        e.memory.write('ResultIndex', 1); before = self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('Queue[1]', 127); e.step(); self.assertEqual(e.memory.read('IntegerResults')[1], 127)

    def test_alias_results_and_constant_sources_keep_canonical_storage(self):
        def aliases(root):
            tags = root.find('./Controller/Tags'); tags.find('Tag[@Name="Queue"]').set('Constant', 'true')
            E.SubElement(tags, 'Tag', Name='InputView', TagType='Alias', AliasFor='Queue[SourceIndex]')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'), 'Tag', Name='ResultView', TagType='Alias', AliasFor='Results[ResultIndex]')
        e = self.checked(['XIC(StartPB)AVE(InputView,0,ResultView,Ctl,?,?);'], length=3, mutate=aliases)
        e.step(); e.memory.write('SourceIndex', 0); e.memory.write('ResultIndex', 1); e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('Results')[1], 4); self.assertEqual(e.memory.read('Queue'), [2, 4, 6, 8, 999])

    def test_late_fault_restores_results_control_flags_time_and_scheduler(self):
        e = self.checked(['XIC(StartPB)AVE(Queue[0],0,Results[ResultIndex],Ctl,?,?);', 'XIC(StartPB)DIV(1,SpeedSetpoint,SpeedCommand);'], length=3)
        e.step(); e.memory.write('ResultIndex', 1); e.memory.write('StartPB', True); e.memory.write('SpeedSetpoint', 0); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'zero'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('SpeedSetpoint', 1); e.step()
        self.assertEqual(e.memory.read('Results')[1], 4); self.assertTrue(e.memory.read('Ctl.DN'))

    def test_prescan_still_requires_actual_controls_and_existing_ave_error_history(self):
        for op in ('AVE', 'STD'):
            e = self.engine([f'AFI(){op}(Queue[0],0,Results[ResultIndex],Controls[ControlIndex],?,?);'])
            self.assertTrue(any('Prescan' in b for b in e.blockers))
        self.assertTrue(any('CONTROL.ER' in b for b in self.engine(['AFI()AVE(Queue[0],0,Results[ResultIndex],Controls[0],?,?);']).blockers))

    def test_literal_bounds_permissions_shapes_and_overlap_guards_remain(self):
        for text in ('AVE(Queue[0],0,Results[99],Ctl,?,?);', 'STD(Queue[0],0,IntegerResults[ResultIndex],Ctl,?,?);', 'AVE(Queue[0],0,Results,Ctl,?,?);', 'AVE(Queue[0],0,Queue[1],Ctl,?,?);', 'AVE(Queue[0],0,Ctl.LEN,Ctl,?,?);'):
            self.assertTrue(self.engine(['AFI()' + text]).blockers, text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()AVE(Queue[0],0,Results[ResultIndex],Ctl,?,?);'], mutate=constant).blockers)
        def older(root):root.find('Controller').set('ProcessorType', '1756-L75')
        self.assertTrue(self.engine(['AFI()AVE(Queue[0],0,Results[ResultIndex],Ctl,?,?);'], mutate=older).blockers)

    @staticmethod
    def aoi_results(root):
        d = root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition')
        for name, kind, size in [('ResultIndex', 'DINT', 0), ('Computed', 'REAL', 3), ('Deviations', 'REAL', 3)]:
            tag = E.SubElement(d.find('LocalTags'), 'LocalTag', Name=name, DataType=kind)
            if size:tag.set('Dimensions', str(size))
        for record in root.findall('./Controller/Tags/Tag[@DataType="LabStatsDriver"]/Data/Structure'):
            E.SubElement(record, 'DataValueMember', Name='ResultIndex', DataType='DINT', Value='99')
            for name in ('Computed', 'Deviations'):E.SubElement(record, 'ArrayMember', Name=name, DataType='REAL', Dimensions='3')
        texts = d.findall('./Routines/Routine[@Name="Logic"]/RLLContent/Rung/Text')
        texts[0].text = texts[0].text.replace(',Mean,', ',Computed[ResultIndex],')
        texts[1].text = texts[1].text.replace(',Deviation,', ',Deviations[ResultIndex],')

    def test_aoi_local_result_indices_are_independent_and_restore_bindings(self):
        fixture = aoi.AOIStatisticsTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        e = fixture.checked(self.aoi_results); e.step(); e.memory.write('DriverA.ResultIndex', 1); e.memory.write('Calculate', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('DriverB.ResultIndex', 2); e.step()
        self.assertEqual((e.memory.read('DriverA.Computed')[1], e.memory.read('DriverB.Computed')[2]), (4, 20))
        self.assertEqual((e.memory.read('DriverA.Deviations')[1], e.memory.read('DriverB.Deviations')[2]), (2, 10))
        e.memory.write('DriverA.ResultIndex', 99); e.memory.write('DriverB.ResultIndex', 99); e.memory.write('IndexA', 999); e.step()
        self.assertEqual(e.memory.read('DriverA.Computed')[1], 4); e.memory.write('Calculate', False); e.step(); e.memory.write('Calculate', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)


if __name__ == '__main__':unittest.main()
