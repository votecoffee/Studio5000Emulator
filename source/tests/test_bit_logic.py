"""Contacts/coils, unknown values, one-shot state selection and rollback."""
import copy
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_bit_transfer as fixtures
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class BitLogicTests(unittest.TestCase):
    setUp = fixtures.BitTransferTests.setUp
    checked = fixtures.BitTransferTests.checked

    def engine(self, rungs=None, *, mutate=None, deferred=False):
        def fields(root):
            c = root.find('Controller');tags = c.find('Tags')
            members = E.SubElement(E.SubElement(c.find('DataTypes'), 'DataType', Name='LogicState', Family='NoFamily', Class='User'), 'Members')
            for name in ('Contact', 'Output', 'Latch', 'Storage', 'Pulse'):
                E.SubElement(members, 'Member', Name=name, DataType='BOOL', Dimension='0')
            E.SubElement(members, 'Member', Name='Guard', DataType='DINT', Dimension='0')
            node = E.SubElement(E.SubElement(E.SubElement(tags, 'Tag', Name='State', DataType='LogicState', TagType='Base'), 'Data', Format='Decorated'), 'Structure', DataType='LogicState')
            E.SubElement(node, 'DataValueMember', Name='Guard', DataType='DINT', Value='42')
            for name, kind, count in (('Flags', 'BOOL', 32), ('Words', 'DINT', 2)):
                tag = E.SubElement(tags, 'Tag', Name=name, DataType=kind, Dimensions=str(count), TagType='Base')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType=kind, Dimensions=str(count))
            tag = E.SubElement(tags, 'Tag', Name='Index', DataType='DINT', TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='0')
            if mutate:mutate(root)
        e = fixtures.BitTransferTests.engine(self, rungs or ['XIC(StartPB)OTE(State.Output);'], mutate=fields)
        return Engine(Project(e.project.path), defer_prescan=True) if deferred else e

    @staticmethod
    def snapshot(e):
        bindings = (e.memory.frames, e.memory._resolved, e.addons.instances) if e.project.aois else None
        return copy.deepcopy((e.memory.values, bindings, e.time_ms, e.scan_count, e.trace, e.scheduler_description()))

    def test_ote_establishes_unknown_bool_members_without_touching_siblings(self):
        e = self.checked();self.assertFalse(e.memory.read('State.Output'));self.assertIsNone(e.memory.values['state']['Latch'])
        e.memory.write('StartPB', True);e.step();self.assertTrue(e.memory.read('State.Output'))
        e.memory.write('StartPB', False);e.step();self.assertFalse(e.memory.read('State.Output'))
        self.assertEqual(e.memory.read('State.Guard'), 42);self.assertIsNone(e.memory.values['state']['Contact'])

    def test_import_preview_preserves_unknowns_then_run_prescan_establishes_output(self):
        e = self.checked(deferred=True);self.assertEqual(e.memory.values, e.project.initial)
        self.assertIsNone(e.memory.values['state']['Output']);self.assertEqual(e.prescan_count, 0)
        e.enter_run();self.assertFalse(e.memory.read('State.Output'));self.assertEqual(e.prescan_count, 1)

    def test_xic_and_xio_skip_false_unknowns_and_require_known_true_operands(self):
        for name in ('XIC', 'XIO'):
            e = self.checked([f'XIC(StartPB){name}(State.Contact)OTE(RunLatch);']);e.step()
            e.memory.write('StartPB', True);before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before)
            for value in (False, True):
                e.memory.write('State.Contact', value);e.step();self.assertEqual(e.memory.read('RunLatch'), value if name == 'XIC' else not value)

    def test_false_contacts_and_latches_do_not_sample_unknown_indices(self):
        for text in ('XIC(Flags[Index])OTE(RunLatch)', 'XIO(Flags[Index])OTE(RunLatch)', 'OTL(Flags[Index])', 'OTU(Flags[Index])'):
            e = self.checked(['XIC(StartPB)' + text + ';']);e.memory.write('Index', 999)
            reads = [];original = e.memory.read
            def read(ref, scope=''):
                if not e.memory.structural:reads.append(ref)
                return original(ref, scope)
            with patch.object(e.memory, 'read', side_effect=read):e.step()
            self.assertNotIn('Index', reads);self.assertNotIn('Flags[Index]', reads)

    def test_false_latches_retain_unknowns_true_latch_and_unlatch_establish_them(self):
        for name, expected in (('OTL', True), ('OTU', False)):
            e = self.checked([f'XIC(StartPB){name}(State.Latch);']);e.step()
            self.assertIsNone(e.memory.values['state']['Latch'])
            e.memory.write('StartPB', True);e.step();self.assertEqual(e.memory.read('State.Latch'), expected)
            e.memory.write('StartPB', False);e.step();self.assertEqual(e.memory.read('State.Latch'), expected)

    def test_ote_false_still_evaluates_and_writes_destination(self):
        e = self.checked(['XIC(StartPB)OTE(Flags[Index]);']);e.memory.write('Index', 999);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Index', 1);e.step();self.assertFalse(e.memory.read('Flags[1]'))

    def test_oneshot_prescan_initializes_unknown_storage_and_outputs(self):
        for name in ('ONS', 'OSR', 'OSF'):
            text = 'ONS(State.Storage)OTE(State.Pulse)' if name == 'ONS' else f'{name}(State.Storage,State.Pulse)'
            e = self.checked(['XIC(StartPB)' + text + ';'])
            self.assertEqual(e.memory.read('State.Storage'), name != 'OSF');self.assertFalse(e.memory.read('State.Pulse'))
            self.assertEqual(e.memory.read('State.Guard'), 42)

    def test_ons_osr_false_establish_new_unknown_storage_without_history(self):
        for name in ('ONS', 'OSR'):
            text = 'ONS(Flags[Index])OTE(State.Pulse)' if name == 'ONS' else 'OSR(Flags[Index],State.Pulse)'
            e = self.checked(['XIC(StartPB)' + text + ';']);e.memory.write('Index', 1);e.step()
            self.assertFalse(e.memory.read('Flags[1]'));self.assertFalse(e.memory.read('State.Pulse'))
            e.memory.write('StartPB', True);e.step();self.assertTrue(e.memory.read('State.Pulse'))
            e.step();self.assertFalse(e.memory.read('State.Pulse'))

    def test_osf_true_establishes_new_unknown_storage_then_pulses_on_fall(self):
        e = self.checked(['XIC(StartPB)OSF(Flags[Index],State.Pulse);']);e.memory.write('Index', 1);e.memory.write('StartPB', True);e.step()
        self.assertTrue(e.memory.read('Flags[1]'));self.assertFalse(e.memory.read('State.Pulse'))
        e.memory.write('StartPB', False);e.step();self.assertTrue(e.memory.read('State.Pulse'))
        e.step();self.assertFalse(e.memory.read('State.Pulse'))

    def test_edge_transitions_that_need_unknown_history_still_fault(self):
        for name in ('ONS', 'OSR', 'OSF'):
            text = 'ONS(Flags[Index])OTE(State.Pulse)' if name == 'ONS' else f'{name}(Flags[Index],State.Pulse)'
            e = self.checked(['MOV(99,SpeedCommand);', 'XIC(StartPB)' + text + ';'])
            e.memory.write('Index', 1);e.memory.write('StartPB', name != 'OSF');before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
            self.assertEqual(self.snapshot(e), before)

    def test_packed_integer_writes_preserve_neighbors_for_every_integer_type(self):
        for dtype, value in (('SINT', 85), ('INT', 21845), ('DINT', 0x55555555), ('LINT', 0x5555555555555555), ('USINT', 85), ('UINT', 21845), ('UDINT', 0x55555555), ('ULINT', 0x5555555555555555)):
            def typed(root):
                tag = root.find('./Controller/Tags/Tag[@Name="Source"]');tag.set('DataType', dtype)
                node = tag.find('Data/DataValue');node.set('DataType', dtype);node.set('Value', str(value))
            e = self.checked(['XIC(StartPB)OTE(Source.1);'], mutate=typed);e.step();self.assertEqual(e.memory.read('Source'), value)
            e.memory.write('StartPB', True);e.step();self.assertEqual(e.memory.read('Source'), value | 2)

    def test_unknown_packed_backing_is_not_filled_by_partial_writes(self):
        e = self.engine(['OTE(Words[0].3);']);self.assertTrue(any('Prescan:' in b and 'Unknown' in b for b in e.blockers))
        self.assertEqual(e.memory.values['words'], [None, None])
        e = self.checked(['OTL(Source.3);']);e.memory.values['source'] = None;before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown'):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_aliases_and_indirect_packed_bits_use_live_indices(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='AliasOutput', TagType='Alias', DataType='BOOL', AliasFor='State.Output')
        e = self.checked(['XIC(StartPB)OTE(AliasOutput);', 'XIC(StartPB)OTL(Source.[Index]);'], mutate=alias)
        e.memory.write('Index', 5);e.memory.write('StartPB', True);e.step()
        self.assertTrue(e.memory.read('State.Output'));self.assertEqual(e.memory.read('Source'), 32)
        e.memory.write('Index', 32);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'bit selection'):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_constants_types_whole_arrays_and_literal_destinations_are_rejected(self):
        for text in ('XIC(Source)', 'OTE(Source)', 'XIC(Flags)', 'OTE(Flags)', 'OTE(TRUE)', 'OSR(State.Storage,Source)'):
            self.assertTrue(self.engine([text + ';']).blockers, text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="State"]').set('Constant', 'true')
        for text in ('OTE(State.Output)', 'OTL(State.Latch)', 'OTU(State.Latch)', 'ONS(State.Storage)', 'OSR(State.Storage,PartPulse)'):
            self.assertTrue(self.engine(['AFI()' + text + ';'], mutate=constant).blockers, text)

    def test_s_fs_is_read_only_and_true_only_on_first_scan(self):
        e = self.checked(['XIC(S:FS)OTE(State.Output);']);e.step();self.assertTrue(e.memory.read('State.Output'))
        e.step();self.assertFalse(e.memory.read('State.Output'))
        self.assertTrue(self.engine(['OTE(S:FS);']).blockers)

    def test_later_fault_restores_coils_latches_edge_storage_and_scheduler(self):
        e = self.checked(['XIC(StartPB)OTE(State.Output)OTL(State.Latch)OSR(State.Storage,State.Pulse);', 'DIV(1,Mask,SpeedCommand);'])
        e.memory.write('StartPB', False);e.memory.write('Mask', 1);e.step()
        e.memory.write('StartPB', True);e.memory.write('Mask', 0);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'zero'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Mask', 1);e.step();self.assertTrue(e.memory.read('State.Pulse'))

    def test_run_reentry_resets_nonretentive_bits_and_retains_latches(self):
        e = self.checked(['XIC(StartPB)OTE(State.Output)OTL(State.Latch)ONS(State.Storage)OTE(State.Pulse);'])
        e.step();e.memory.write('StartPB', True);e.step();self.assertTrue(e.memory.read('State.Pulse'))
        e.enter_run();self.assertFalse(e.memory.read('State.Output'));self.assertTrue(e.memory.read('State.Latch'))
        e.step();self.assertFalse(e.memory.read('State.Pulse'))

    def test_aoi_inout_packed_local_bits_and_late_binding_rollback(self):
        import test_aoi_queues as queues
        f = queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        def logic(root):queues.logic(root, ['OTL(Buffer[Index].1)OTE(Stack[0].0)XIC(Buffer[Index].1)OTE(EnableOut);'])
        e = f.checked(logic);e.step();e.memory.write('IndexB', 999);before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('IndexB', 2);e.step();self.assertTrue(e.memory.read('BufferB[2].1'))

    def test_other_profiles_keep_legacy_and_report_lists_partial_boundaries(self):
        def old(root):root.find('Controller').set('ProcessorType', '1756-L75')
        e = self.checked(['XIC(StartPB)OTE(RunLatch);'], mutate=old);e.step();self.assertFalse(e.memory.read('RunLatch'))
        self.assertFalse(e.report()['bit_logic']['available'])
        report = self.checked().report()['bit_logic'];self.assertEqual(len(report['instructions']), 8);self.assertFalse(report['native_runtime_parity'])
