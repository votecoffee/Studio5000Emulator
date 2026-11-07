"""CONTROL reset and shift/queue payload selection without dormant reads."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_control_operations as fixtures
import test_aoi_queues as aoi
from logixlab import file_incremental
from logixlab.control_operations import FLAGS
from logixlab.model import ModelError


class ControlOperandTests(unittest.TestCase):
    setUp = fixtures.ControlOperationTests.setUp

    def engine(self, rungs, *, mutate=None, **kwargs):
        def fields(root):
            tags = root.find('./Controller/Tags')
            for name in ('SourceIndex', 'DestIndex', 'ControlIndex'):
                tag = E.SubElement(tags, 'Tag', Name=name, DataType='DINT', TagType='Base')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='99')
            for name, dtype in [('Inputs', 'DINT'), ('Outputs', 'DINT'), ('Bits', 'BOOL'), ('Controls', 'CONTROL')]:
                tag = E.SubElement(tags, 'Tag', Name=name, DataType=dtype, TagType='Base', Dimensions='3')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType=dtype, Dimensions='3')
            if mutate:mutate(root)
        return fixtures.ControlOperationTests.engine(self, rungs, mutate=fields, **kwargs)

    def checked(self, *args, **kwargs):
        e = self.engine(*args, **kwargs); self.assertEqual(e.blockers, []); self.assertFalse(e.memory.structural); return e

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values, e.memory.frames, e.memory._resolved if e.project.aois else None, e.addons.instances,
                              e._file_incremental, e.scan_count, e.time_ms, e.scheduler_description(), e.trace, e.last_timer))

    def test_shift_false_and_held_skip_source_index_then_reached_source_faults_and_recovers(self):
        for op in ('BSL', 'BSR'):
            e = self.checked([f'XIC(StartPB){op}(Words[0],Ctl,Bits[SourceIndex],?);'], length=1)
            e.step(); e.memory.write('StartPB', True); before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('SourceIndex', 0); before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('Bits[0]', True); e.step(); words = copy.deepcopy(e.memory.read('Words'))
            e.memory.write('SourceIndex', 99); e.step(); self.assertEqual(e.memory.read('Words'), words)
            e.memory.write('StartPB', False); e.step(); self.assertFalse(e.memory.read('Ctl.EN'))

    def test_load_false_held_and_full_skip_payload_but_each_moving_edge_reads_it(self):
        for op in ('FFL', 'LFL'):
            e = self.checked([f'XIC(StartPB){op}(Inputs[SourceIndex],Queue[0],Ctl,?,?);'], length=1)
            e.step(); e.memory.write('StartPB', True); before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('SourceIndex', 0); before = self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('Inputs[0]', 41); e.step(); self.assertEqual(e.memory.read('Queue[0]'), 41)
            e.memory.write('SourceIndex', 99); e.step(); self.assertEqual(e.memory.read('Ctl.POS'), 1)
            e.memory.write('StartPB', False); e.step(); e.memory.write('StartPB', True); e.step()
            self.assertEqual(e.memory.read('Ctl.POS'), 1); self.assertTrue(e.memory.read('Ctl.DN'))

    def test_unload_false_held_and_empty_write_destination_selection(self):
        for op in ('FFU', 'LFU'):
            e = self.checked([f'XIC(StartPB){op}(Queue[0],Outputs[DestIndex],Ctl,?,?);'], length=2, position=1, queue=(31, 0, 0, 999))
            e.step(); e.memory.write('StartPB', True); before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('DestIndex', 1); e.step(); self.assertEqual(e.memory.read('Outputs')[1], 31)
            self.assertIsNone(e.memory.read('Outputs')[0]); e.memory.write('DestIndex', 99); e.step()
            e.memory.write('StartPB', False); e.step(); e.memory.write('StartPB', True); before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
            self.assertEqual(self.snapshot(e), before)
            e.memory.write('DestIndex', 1); e.step(); self.assertEqual(e.memory.read('Outputs')[1], 0)

    def test_control_reset_false_prescan_and_true_unknown_record_initialization(self):
        e = self.checked(['XIC(StartPB)RES(Controls[ControlIndex]);'])
        before = copy.deepcopy(e.memory.values); e.step(); self.assertEqual(e.memory.values, before)
        e.memory.write('StartPB', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('ControlIndex', 1); e.step(); obj = e.memory.read('Controls')[1]
        self.assertIsNone(obj['LEN']); self.assertEqual(obj['POS'], 0)
        self.assertTrue(all(obj[flag] is False for flag in FLAGS)); self.assertIsNone(e.memory.read('Controls')[0]['POS'])

    def test_reset_preserves_known_length_and_removes_only_resolved_incremental_identity(self):
        def aliases(root):E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='View', TagType='Alias', AliasFor='Controls[ControlIndex]')
        e = self.checked(['XIC(StartPB)RES(View);'], mutate=aliases)
        e.memory.write('ControlIndex', 1); e.memory.write('Controls[1].LEN', -17); e.memory.write('Controls[1].POS', 5)
        for flag in FLAGS:e.memory.write('Controls[1].' + flag, True)
        first = file_incremental.identity(e, 'Controls[1]', ''); other = file_incremental.identity(e, 'Controls[2]', '')
        e._file_incremental.update((first, other)); e.step(); self.assertIn(first, e._file_incremental)
        e.memory.write('StartPB', True); e.step(); obj = e.memory.read('Controls')[1]
        self.assertEqual((obj['LEN'], obj['POS']), (-17, 0)); self.assertTrue(all(obj[flag] is False for flag in FLAGS))
        self.assertEqual(e._file_incremental, {other})

    def test_reset_and_queue_late_faults_restore_flags_payloads_and_incremental_state(self):
        for text in ('RES(Controls[ControlIndex]);', 'FFL(Inputs[SourceIndex],Queue[0],Ctl,?,?);'):
            e = self.checked(['XIC(StartPB)' + text, 'XIC(StartPB)DIV(1,SpeedSetpoint,SpeedCommand);'], length=2)
            e.step(); e.memory.write('ControlIndex', 1); e.memory.write('SourceIndex', 1); e.memory.write('Inputs[1]', 47)
            e.memory.write('Controls[1].POS', 9); e.memory.write('Controls[1].EN', True)
            key = file_incremental.identity(e, 'Controls[1]', ''); e._file_incremental.add(key)
            e.memory.write('StartPB', True); e.memory.write('SpeedSetpoint', 0); before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'zero'):e.step()
            self.assertEqual(self.snapshot(e), before); e.memory.write('SpeedSetpoint', 1); e.step()
            if text.startswith('RES'):self.assertEqual(e.memory.read('Controls')[1]['POS'], 0); self.assertNotIn(key, e._file_incremental)
            else:self.assertEqual(e.memory.read('Queue[0]'), 47)

    def test_alias_payload_indices_and_constant_inputs_use_canonical_storage(self):
        def aliases(root):
            tags = root.find('./Controller/Tags'); tags.find('Tag[@Name="Inputs"]').set('Constant', 'true')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'), 'Tag', Name='View', TagType='Alias', AliasFor='Inputs[SourceIndex]')
        e = self.checked(['XIC(StartPB)FFL(View,Queue[0],Ctl,?,?);'], length=1, mutate=aliases)
        e.step(); e.memory.values['inputs'][1] = 53; e.memory.write('SourceIndex', 1); e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('Queue[0]'), 53); self.assertEqual(e.memory.read('Inputs')[1], 53)

    def test_prescan_skips_bad_control_addresses_but_requires_known_indices_and_queue_state(self):
        for text in ('BSL(Words[0],Controls[ControlIndex],BitIn,?);', 'FFL(Incoming,Queue[0],Controls[ControlIndex],?,?);'):
            engine = self.checked(['AFI()' + text])
            before = self.snapshot(engine)
            with self.assertRaisesRegex(ModelError, 'outside bounds'):
                engine.step()
            self.assertEqual(self.snapshot(engine), before)
        unknown = self.engine(['AFI()BSL(Words[0],Controls[Inputs[0]],BitIn,?);'])
        self.assertTrue(any('Prescan' in b and 'Unknown' in b for b in unknown.blockers))
        self.assertTrue(any('CONTROL.LEN' in b for b in self.engine(['AFI()FFL(Incoming,Queue[0],Controls[0],?,?);']).blockers))

    def test_structural_errors_permissions_literal_bounds_and_older_profiles_stay_blocked(self):
        for text in ('FFL(Inputs[99],Queue[0],Ctl,?,?);', 'FFU(Queue[0],Outputs[99],Ctl,?,?);', 'BSL(Words[0],Ctl,Inputs[SourceIndex],?);', 'FFL(Bits[SourceIndex],Queue[0],Ctl,?,?);', 'RES(Controls[99]);', 'RES(Controls);'):
            self.assertTrue(self.engine(['AFI()' + text]).blockers, text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Controls"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()RES(Controls[ControlIndex]);'], mutate=constant).blockers)
        def read_only(root):root.find('./Controller/Tags/Tag[@Name="Outputs"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()FFU(Queue[0],Outputs[DestIndex],Ctl,?,?);'], mutate=read_only).blockers)
        def older(root):root.find('Controller').set('ProcessorType', '1756-L75')
        self.assertTrue(self.engine(['AFI()RES(Controls[ControlIndex]);'], mutate=older).blockers)
        self.assertTrue(self.engine(['AFI()FFL(Inputs[SourceIndex],Queue[0],Ctl,?,?);'], mutate=older).blockers)

    @staticmethod
    def aoi_payloads(root):
        definition = root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition')
        E.SubElement(definition.find('LocalTags'), 'LocalTag', Name='Values', DataType='DINT', Dimensions='3')
        for tag in root.findall('./Controller/Tags/Tag[@DataType="LabQueueDriver"]/Data/Structure'):
            E.SubElement(tag, 'ArrayMember', Name='Values', DataType='DINT', Dimensions='3')
        node = definition.find('./Routines/Routine[@Name="Logic"]/RLLContent/Rung[@Number="0"]/Text')
        node.text = node.text.replace('FFL(Value,', 'FFL(Values[Index],')

    def test_aoi_local_payload_indices_keep_instance_scope_and_rollback_bindings(self):
        fixture = aoi.AOIQueueTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        e = fixture.checked(self.aoi_payloads); e.step()
        e.memory.write('DriverA.Values[1]', 61); e.memory.write('DriverB.Values[2]', 71)
        e.memory.write('Load', True); e.step(); self.assertEqual((e.memory.read('BufferA')[1], e.memory.read('BufferB')[2]), (61, 71))
        e.memory.write('IndexB', 99); e.step(); e.memory.write('Load', False); e.step(); e.memory.write('Load', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('IndexB', 2); e.step(); self.assertEqual(e.memory.read('StateA.POS'), 2)

    def test_aoi_local_and_inout_resets_preserve_length_and_restore_bindings_on_later_fault(self):
        def setup(root):
            definition = root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition')
            E.SubElement(definition.find('LocalTags'), 'LocalTag', Name='Controls', DataType='CONTROL', Dimensions='3')
            for tag in root.findall('./Controller/Tags/Tag[@DataType="LabQueueDriver"]/Data/Structure'):
                E.SubElement(tag, 'ArrayMember', Name='Controls', DataType='CONTROL', Dimensions='3')
            aoi.logic(root, ['XIC(Load)RES(State);', 'XIC(Load)RES(Controls[Index]);'])
        fixture = aoi.AOIQueueTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        e = fixture.checked(setup); e.step(); saved_length = e.memory.read('StateA.LEN'); e.memory.write('StateA.POS', 5); e.memory.write('StateB.POS', 7)
        first = file_incremental.identity(e, 'StateA', ''); second = file_incremental.identity(e, 'StateB', '')
        e._file_incremental.update((first, second)); e.memory.write('IndexB', 99); e.memory.write('Load', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('IndexB', 2); e.step()
        self.assertEqual((e.memory.read('StateA.POS'), e.memory.read('StateB.POS')), (0, 0))
        self.assertEqual(e.memory.read('StateA.LEN'), saved_length); self.assertFalse(e._file_incremental)
        for name, index in [('DriverA', 1), ('DriverB', 2)]:
            obj = e.memory.read(name + '.Controls')[index]
            self.assertIsNone(obj['LEN']); self.assertEqual(obj['POS'], 0); self.assertTrue(all(obj[flag] is False for flag in FLAGS))
            self.assertIsNone(e.memory.read(name + '.Controls')[0]['POS'])


if __name__ == '__main__':unittest.main()
