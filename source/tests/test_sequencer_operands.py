"""Sequencer mask/payload selection, held data, unknowns and rollback."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_control_operations as fixtures
import test_aoi_sequencers as aoi
from logixlab.model import ModelError


class SequencerOperandTests(unittest.TestCase):
    setUp = fixtures.ControlOperationTests.setUp

    def engine(self, rungs, *, mutate=None, **kwargs):
        def fields(root):
            tags = root.find('./Controller/Tags')
            for name in ('MaskIndex', 'PayloadIndex', 'OutputIndex'):
                tag = E.SubElement(tags, 'Tag', Name=name, DataType='DINT', TagType='Base')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='99')
            for name, kind in [('Masks', 'DINT'), ('Samples', 'DINT'), ('Outputs', 'DINT'), ('Controls', 'CONTROL')]:
                tag = E.SubElement(tags, 'Tag', Name=name, DataType=kind, TagType='Base', Dimensions='3')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType=kind, Dimensions='3')
            if mutate:mutate(root)
        return fixtures.ControlOperationTests.engine(self, rungs, mutate=fields, **kwargs)

    def checked(self, *args, **kwargs):
        e = self.engine(*args, **kwargs); self.assertEqual(e.blockers, []); self.assertFalse(e.memory.structural); return e

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values, e.memory.frames, e.memory._resolved if e.project.aois else None,
                              e.addons.instances, e.scan_count, e.time_ms, e.scheduler_description(), e.trace, e.last_timer))

    def test_sqo_false_skips_mask_and_destination_then_true_requires_each(self):
        e = self.checked(['XIC(StartPB)SQO(Queue[0],Masks[MaskIndex],Outputs[OutputIndex],Ctl,?,?);'], length=2, queue=(10, 20, 30, 999))
        e.step(); self.assertIsNone(e.memory.read('Outputs')[0]); e.memory.write('StartPB', True)
        for expected, writes in [('outside bounds', []), ('Unknown', [('MaskIndex', 0)]), ('outside bounds', [('Masks[0]', -1)])]:
            for ref, value in writes:e.memory.write(ref, value)
            before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, expected):e.step()
            self.assertEqual(self.snapshot(e), before)
        e.memory.write('OutputIndex', 1); e.step(); self.assertEqual(e.memory.read('Outputs')[1], 20)
        self.assertEqual(e.memory.read('Ctl.POS'), 1); self.assertIsNone(e.memory.read('Outputs')[0])

    def test_sqo_held_true_reselects_mask_and_destination_without_advancing(self):
        e = self.checked(['SQO(Queue[0],Masks[MaskIndex],Outputs[OutputIndex],Ctl,?,?);'], length=2, queue=(10, 20, 30, 999))
        e.memory.write('MaskIndex', 0); e.memory.write('Masks[0]', -1); e.memory.write('OutputIndex', 0); e.step()
        e.memory.write('Queue[0]', 55); e.memory.write('OutputIndex', 1); e.step()
        self.assertEqual(e.memory.read('Outputs')[:2], [10, 55]); self.assertEqual(e.memory.read('Ctl.POS'), 0)
        e.memory.write('MaskIndex', 99); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_sqi_false_and_zero_mask_skip_compared_source_but_nonzero_consumes_it(self):
        e = self.checked(['XIC(StartPB)SQI(Queue[0],Masks[MaskIndex],Samples[PayloadIndex],Ctl,?,?)OTE(RunLatch);'], length=2, queue=(10, 20, 30, 999))
        e.step(); self.assertFalse(e.memory.read('RunLatch')); e.memory.write('StartPB', True); e.memory.write('MaskIndex', 0); e.memory.write('Masks[0]', 0)
        e.step(); self.assertTrue(e.memory.read('RunLatch')); self.assertEqual(e.memory.read('PayloadIndex'), 99)
        e.memory.write('Masks[0]', -1); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('PayloadIndex', 0); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('Samples[0]', 10); e.step(); self.assertTrue(e.memory.read('RunLatch'))
        e.memory.write('Samples[0]', 11); e.step(); self.assertFalse(e.memory.read('RunLatch')); self.assertEqual(e.memory.read('Ctl.POS'), 0)

    def test_sql_false_skips_source_and_held_true_reloads_selected_live_value(self):
        e = self.checked(['XIC(StartPB)SQL(Queue[0],Samples[PayloadIndex],Ctl,?,?);'], length=2, queue=(10, 0, 0, 999))
        e.step(); e.memory.write('StartPB', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('PayloadIndex', 0); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('Samples[0]', -41); e.step()
        e.memory.write('PayloadIndex', 1); e.memory.write('Samples[1]', 55); e.step()
        self.assertEqual(e.memory.read('Queue'), [10, 55, 0, 999]); self.assertEqual(e.memory.read('Ctl.POS'), 1)
        e.memory.write('PayloadIndex', 99); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_invalid_control_paths_skip_live_masks_and_payloads(self):
        for text in ('SQO(Queue[0],Masks[MaskIndex],Outputs[OutputIndex],Ctl,?,?);',
                     'SQI(Queue[0],Masks[MaskIndex],Samples[PayloadIndex],Ctl,?,?)OTE(RunLatch);',
                     'SQL(Queue[0],Samples[PayloadIndex],Ctl,?,?);'):
            e = self.checked([text], length=0); before = copy.deepcopy(e.memory.read('Queue')); e.step()
            self.assertTrue(e.memory.read('Ctl.ER')); self.assertEqual(e.memory.read('Queue'), before)
            self.assertIsNone(e.memory.read('Outputs')[0]); self.assertEqual(e.memory.read('MaskIndex'), 99)

    def test_zero_mask_skips_live_output_and_row_values_but_still_checks_table(self):
        e = self.checked(['SQO(Queue[0],0,Outputs[OutputIndex],Ctl,?,?);'], length=2)
        e.memory.values['queue'][0] = None; e.step(); self.assertIsNone(e.memory.read('Outputs')[0])
        e = self.checked(['SQO(Queue[PayloadIndex],0,Outputs[OutputIndex],Ctl,?,?);'], length=2)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e = self.checked(['SQI(Queue[0],Masks[MaskIndex],Samples[PayloadIndex],Ctl,?,?)OTE(RunLatch);'], length=4, position=4)
        e.step(); self.assertTrue(e.memory.read('Ctl.ER')); self.assertFalse(e.memory.read('RunLatch'))

    def test_full_mask_establishes_unknown_output_partial_mask_requires_old_bits(self):
        for mask in (-1, 255):
            e = self.checked([f'SQO(Queue[0],{mask},Outputs[OutputIndex],Ctl,?,?);'], length=2, queue=(10, 20, 30, 999))
            e.memory.write('OutputIndex', 1)
            if mask == -1:e.step(); self.assertEqual(e.memory.read('Outputs')[1], 10)
            else:
                before = self.snapshot(e)
                with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
                self.assertEqual(self.snapshot(e), before); e.memory.write('Outputs[1]', 0x120000); e.step()
                self.assertEqual(e.memory.read('Outputs')[1], 0x12000a)

    def test_runtime_checks_control_addresses_after_prescan(self):
        for text in ('SQO(Queue[0],0,Outgoing,Controls[PayloadIndex],?,?);',
                     'SQI(Queue[0],0,Incoming,Controls[PayloadIndex],?,?);'):
            with self.subTest(instruction=text):
                engine = self.checked(['AFI()' + text])
                before = self.snapshot(engine)
                with self.assertRaisesRegex(ModelError, 'outside bounds'):
                    engine.step()
                self.assertEqual(self.snapshot(engine), before)

    def test_alias_constant_mask_and_input_sources_resolve_canonical_values(self):
        def setup(root):
            tags = root.find('./Controller/Tags'); tags.find('Tag[@Name="Masks"]').set('Constant', 'true'); tags.find('Tag[@Name="Samples"]').set('Constant', 'true')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'), 'Tag', Name='MaskView', TagType='Alias', AliasFor='Masks[MaskIndex]')
            E.SubElement(tags, 'Tag', Name='InputView', TagType='Alias', AliasFor='Samples[PayloadIndex]')
        e = self.checked(['XIC(StartPB)SQL(Queue[0],InputView,Ctl,?,?);', 'XIC(PartSensor)SQI(Queue[0],MaskView,InputView,Ctl,?,?)OTE(RunLatch);'], length=2, mutate=setup)
        e.step(); e.memory.values['masks'][0] = -1; e.memory.values['samples'][1] = 73
        e.memory.write('MaskIndex', 0); e.memory.write('PayloadIndex', 1); e.memory.write('StartPB', True); e.memory.write('PartSensor', True); e.step()
        self.assertEqual(e.memory.read('Queue[1]'), 73); self.assertTrue(e.memory.read('RunLatch'))

    def test_later_fault_restores_output_table_flags_and_scheduler(self):
        e = self.checked(['XIC(StartPB)SQO(Queue[0],-1,Outputs[OutputIndex],Ctl,?,?);', 'XIC(StartPB)SQL(Queue[0],Samples[PayloadIndex],Ctl,?,?);', 'XIC(StartPB)DIV(1,SpeedSetpoint,SpeedCommand);'], length=2, queue=(10, 20, 30, 999))
        e.step(); e.memory.write('OutputIndex', 1); e.memory.write('PayloadIndex', 1); e.memory.write('Samples[1]', 77); e.memory.write('SpeedSetpoint', 0); e.memory.write('StartPB', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'zero'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('SpeedSetpoint', 1); e.step()
        self.assertEqual(e.memory.read('Outputs')[1], 20); self.assertEqual(e.memory.read('Queue[1]'), 77)

    @staticmethod
    def aoi_operands(root):
        d = root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition')
        for name, kind, size in [('Pick', 'DINT', 0), ('Masks', 'DINT', 3), ('Values', 'DINT', 3)]:
            tag = E.SubElement(d.find('LocalTags'), 'LocalTag', Name=name, DataType=kind)
            if size:tag.set('Dimensions', str(size))
        for record in root.findall('./Controller/Tags/Tag[@DataType="LabSequencer"]/Data/Structure'):
            E.SubElement(record, 'DataValueMember', Name='Pick', DataType='DINT', Value='99')
            for name in ('Masks', 'Values'):E.SubElement(record, 'ArrayMember', Name=name, DataType='DINT', Dimensions='3')
        for text in d.findall('./Routines/Routine[@Name="Logic"]/RLLContent/Rung/Text'):
            text.text = text.text.replace('16#FF', 'Masks[Pick]').replace(',Value,', ',Values[Pick],')

    def test_aoi_local_operands_are_lazy_independent_and_restore_bindings(self):
        fixture = aoi.AOISequencerTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        e = fixture.checked(self.aoi_operands); e.step()
        for tag, value in [('DriverA.Pick', 1), ('DriverA.Masks[1]', -1), ('DriverA.Values[1]', 61), ('DriverB.Masks[2]', -1), ('DriverB.Values[2]', 71), ('Step', True), ('Teach', True)]:e.memory.write(tag, value)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('DriverB.Pick', 2); e.step()
        self.assertEqual((e.memory.read('OutputsA'), e.memory.read('OutputsB')), (1, 8))
        self.assertEqual((e.memory.read('LearnedA[2]'), e.memory.read('LearnedB[3]')), (61, 71))
        e.memory.write('DriverA.Values[1]', 81); e.step(); self.assertEqual(e.memory.read('LearnedA[2]'), 81); self.assertEqual(e.memory.read('TeachA.POS'), 1)

    def test_structural_type_bounds_permissions_and_profile_guards_remain(self):
        for text in ('SQO(Queue[0],Masks[99],Outgoing,Ctl,?,?);', 'SQO(Queue[0],0,Outputs[99],Ctl,?,?);', 'SQL(Queue[0],Samples[99],Ctl,?,?);', 'SQO(Queue[0],TRUE,Outgoing,Ctl,?,?);', 'SQL(Queue[0],BitIn,Ctl,?,?);'):
            self.assertTrue(self.engine(['AFI()' + text], length=2).blockers, text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Outputs"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()SQO(Queue[0],0,Outputs[OutputIndex],Ctl,?,?);'], mutate=constant).blockers)
        def older(root):root.find('Controller').set('ProcessorType', '1756-L75')
        self.assertTrue(self.engine(['AFI()SQL(Queue[0],Samples[PayloadIndex],Ctl,?,?);'], mutate=older).blockers)


if __name__ == '__main__':unittest.main()
