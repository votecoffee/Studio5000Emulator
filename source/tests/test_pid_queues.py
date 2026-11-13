"""Logical PID FIFO/LIFO payloads, nested schemas, snapshots and rollback."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_control_operations as base
import test_fifo_records as records
import test_numeric_queues as numeric
from logixlab.ladder_pid import default as pid_default
from logixlab.model import ModelError


def record(kind, value, member=None):
    obj = E.Element('StructureMember' if member else 'Structure', DataType=kind)
    if member:obj.set('Name', member)
    if kind == 'PIDBundle':
        E.SubElement(obj, 'DataValueMember', Name='Id', DataType='DINT', Value=str(value))
        obj.append(record('PID', value, 'Tuning'))
        array = E.SubElement(obj, 'ArrayMember', Name='Loops', DataType='PID', Dimensions='2')
        for i in range(2):E.SubElement(array, 'Element', Index=f'[{i}]').append(record('PID', value + i))
        return obj
    fields = pid_default() | dict(CTL=(1 << 26) | (1 << 15), SP=float(value), KP=1.5, DATA=[value + i + .25 for i in range(17)])
    for name, item in fields.items():
        if name == 'DATA':
            array = E.SubElement(obj, 'ArrayMember', Name=name, DataType='REAL', Dimensions='17')
            for i, number in enumerate(item):E.SubElement(array, 'Element', Index=f'[{i}]', Value=str(number))
        else:E.SubElement(obj, 'DataValueMember', Name=name, DataType='DINT' if name == 'CTL' else 'REAL', Value=str(item))
    return obj


class PIDQueueTests(unittest.TestCase):
    setUp = base.ControlOperationTests.setUp
    checked = base.ControlOperationTests.checked
    snapshot = staticmethod(numeric.NumericQueueTests.snapshot)

    def engine(self, logic=None, *, kind='PID', mutate=None, length=2, position=0):
        def payloads(root):
            tags = root.find('./Controller/Tags')
            if kind == 'PIDBundle':
                members = E.SubElement(E.SubElement(root.find('./Controller/DataTypes'), 'DataType', Name=kind, Class='User'), 'Members')
                for name, dtype, size in [('Id', 'DINT', 0), ('Tuning', 'PID', 0), ('Loops', 'PID', 2)]:
                    E.SubElement(members, 'Member', Name=name, DataType=dtype, Dimension=str(size))
            for name, value in [('Incoming', 11), ('Outgoing', 99)]:
                data = tags.find(f'Tag[@Name="{name}"]/Data');data.clear();data.set('Format', 'Decorated');data.append(record(kind, value))
            for node, value in zip(tags.find('Tag[@Name="Queue"]/Data/Array'), (11, 22, 33, 999)):
                node.attrib.pop('Value', None);node.append(record(kind, value))
            if mutate:mutate(root)
        logic = logic if logic is not None else ['XIC(StartPB)FFL(Incoming,Queue[0],Ctl,?,?);',
                                                 'XIC(PartSensor)FFU(Queue[0],Outgoing,Ctl,?,?);']
        return base.ControlOperationTests.engine(self, logic, dtype=kind, mutate=payloads, length=length, position=position)

    @staticmethod
    def pulse(e, gate):
        e.memory.write(gate, False);e.step();e.memory.write(gate, True);e.step()

    def fault(self, e, pattern):
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, pattern):e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_fifo_keeps_pid_order_ctl_data_flags_and_guard(self):
        e = self.checked();e.step();saved = []
        for value in (41, 52):
            e.memory.write('Incoming.SP', value);saved.append(copy.deepcopy(e.memory.read('Incoming')))
            self.pulse(e, 'StartPB')
        self.assertTrue(e.memory.read('Ctl.DN'));e.memory.write('StartPB', False)
        for expected in saved:
            self.pulse(e, 'PartSensor');self.assertEqual(e.memory.read('Outgoing'), expected)
            self.assertTrue(e.memory.read('Outgoing.SWM'));self.assertTrue(e.memory.read('Outgoing.INI'))
        self.assertEqual(e.memory.read('Queue[3].SP'), 999)
        self.assertEqual(e.memory.read('Queue[1]'), pid_default())

    def test_lifo_returns_pid_records_in_reverse_order_and_clears_selected_slot(self):
        e = self.checked(['XIC(StartPB)LFL(Incoming,Queue[0],Ctl,?,?);', 'XIC(PartSensor)LFU(Queue[0],Outgoing,Ctl,?,?);'])
        e.step()
        for value in (41, 52):e.memory.write('Incoming.SP', value);self.pulse(e, 'StartPB')
        self.pulse(e, 'PartSensor');self.assertEqual(e.memory.read('Outgoing.SP'), 52)
        self.assertEqual(e.memory.read('Queue[0].SP'), 41)
        self.assertEqual(e.memory.read('Queue[1]'), pid_default())
        self.pulse(e, 'PartSensor');self.assertEqual(e.memory.read('Outgoing.SP'), 41)
        self.assertEqual(e.memory.read('Queue[3].SP'), 999)

    def test_nested_pid_records_and_arrays_are_detached_in_both_directions(self):
        e = self.checked(kind='PIDBundle');e.step()
        e.memory.write('Incoming.Loops[1].DATA[16]', 123.5)
        expected = copy.deepcopy(e.memory.read('Incoming'));self.pulse(e, 'StartPB')
        e.memory.write('Incoming.Loops[1].DATA[16]', 456.5)
        self.assertEqual(e.memory.read('Queue[0]'), expected)
        self.pulse(e, 'PartSensor');self.assertEqual(e.memory.read('Outgoing'), expected)
        e.memory.write('Queue[0].Tuning.DATA[0]', 42)
        self.assertEqual(e.memory.read('Outgoing.Tuning.DATA[0]'), 11.25)

    def test_unknown_pid_members_are_preserved_and_empty_unload_establishes_zero(self):
        e = self.checked();e.step()
        e.memory.values['incoming']['SP'] = None;e.memory.values['incoming']['DATA'][7] = None
        self.pulse(e, 'StartPB');self.pulse(e, 'PartSensor')
        self.assertIsNone(e.memory.values['outgoing']['SP']);self.assertIsNone(e.memory.values['outgoing']['DATA'][7])
        self.pulse(e, 'PartSensor');self.assertEqual(e.memory.read('Outgoing'), pid_default())
        self.assertIs(type(e.memory.read('Outgoing.DATA[7]')), float)

    def test_load_is_edge_triggered_and_full_or_held_paths_skip_whole_unknown_sources(self):
        e = self.checked(length=1);e.step();self.pulse(e, 'StartPB')
        e.memory.values['incoming'] = None;e.step();self.assertEqual(e.memory.read('Ctl.POS'), 1)
        self.pulse(e, 'StartPB');self.assertEqual(e.memory.read('Ctl.POS'), 1)
        self.pulse(e, 'PartSensor');e.memory.write('StartPB', False);e.step();e.memory.write('StartPB', True)
        self.fault(e, 'Unknown|represented logical record')

    def test_alias_and_indirect_starts_skip_false_then_move_selected_pid(self):
        def aliases(root):
            tags = root.find('./Controller/Tags')
            tag = E.SubElement(tags, 'Tag', Name='Index', DataType='DINT', TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='99')
            E.SubElement(tags, 'Tag', Name='SelectedQueue', TagType='Alias', AliasFor='Queue[Index]')
        e = self.checked(['XIC(StartPB)FFL(Incoming,SelectedQueue,Ctl,?,?);'], mutate=aliases, length=1)
        e.step();e.memory.write('StartPB', True);self.fault(e, 'outside bounds')
        e.memory.write('Index', 1);e.step()
        self.assertEqual(e.memory.read('Queue[1].SP'), 11);self.assertEqual(e.memory.read('Queue[0].SP'), 11)
        self.assertEqual(e.memory.read('Queue[3].SP'), 999)

    def test_payload_movement_and_zeroing_do_not_transfer_or_reset_private_pid_history(self):
        e = self.checked();e.step()
        identities = [('RLL-PID', 'incoming', ()), ('RLL-PID', 'outgoing', ()), ('RLL-PID', 'queue', (0,))]
        for index, identity in enumerate(identities):e.last_timer[identity] = dict(integral=10 + index)
        before = copy.deepcopy(e.last_timer)
        self.pulse(e, 'StartPB');self.pulse(e, 'PartSensor');self.pulse(e, 'PartSensor')
        self.assertEqual(e.last_timer, before);self.assertEqual(e.memory.read('Outgoing.CTL'), 0)

    def test_later_fault_restores_pid_records_control_trace_time_and_scheduler(self):
        e = self.checked(['XIC(StartPB)FFL(Incoming,Queue[0],Ctl,?,?);', 'DIV(1,SpeedSetpoint,SpeedCommand);'])
        e.step();e.memory.write('StartPB', True);e.memory.write('SpeedSetpoint', 0)
        self.fault(e, 'zero')
        e.memory.write('SpeedSetpoint', 1);e.step()
        self.assertEqual(e.memory.read('Ctl.POS'), 1)

    @staticmethod
    def aoi(root):
        controller = root.find('Controller');tags = controller.find('Tags')
        definition = E.SubElement(controller.find('AddOnInstructionDefinitions'), 'AddOnInstructionDefinition',
                                  Name='PIDQueue', Class='Standard', ExecutePrescan='false', ExecutePostscan='false', ExecuteEnableInFalse='false')
        params = E.SubElement(definition, 'Parameters')
        for name, dtype, dims, usage, required in [('EnableIn', 'BOOL', '0', 'Input', 'false'), ('EnableOut', 'BOOL', '0', 'Output', 'false'),
                ('Source', 'PID', '0', 'InOut', 'true'), ('Buffer', 'PID', '4', 'InOut', 'true'), ('State', 'CONTROL', '0', 'InOut', 'true')]:
            E.SubElement(params, 'Parameter', Name=name, DataType=dtype, Dimensions=dims, Usage=usage,
                         Required=required, Visible=required, TagType='Base')
        E.SubElement(definition, 'LocalTags')
        routine = E.SubElement(E.SubElement(definition, 'Routines'), 'Routine', Name='Logic', Type='RLL')
        E.SubElement(E.SubElement(E.SubElement(routine, 'RLLContent'), 'Rung', Number='0', Type='N'), 'Text').text = 'FFL(Source,Buffer[0],State,?,?);'
        tag = E.SubElement(tags, 'Tag', Name='Instance', DataType='PIDQueue', TagType='Base')
        obj = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Structure', DataType='PIDQueue')
        for name in ('EnableIn', 'EnableOut'):E.SubElement(obj, 'DataValueMember', Name=name, DataType='BOOL', Value='0')

    def test_aoi_inout_pid_array_binding_and_late_fault_rollback(self):
        e = self.checked(['XIC(StartPB)PIDQueue(Instance,Incoming,Queue,Ctl);', 'DIV(1,SpeedSetpoint,SpeedCommand);'], mutate=self.aoi)
        e.step();e.memory.write('StartPB', True);e.memory.write('SpeedSetpoint', 0);self.fault(e, 'zero')
        e.memory.write('SpeedSetpoint', 1);e.step();self.assertEqual(e.memory.read('Queue[0].DATA[16]'), 27.25)

    def test_pid_redefinitions_mismatched_types_and_other_operational_payloads_are_blocked(self):
        def redefine(root):E.SubElement(root.find('./Controller/DataTypes'), 'DataType', Name='PID', Class='User')
        self.assertTrue(self.engine(mutate=redefine).blockers)
        def mismatch(root):root.find('./Controller/Tags/Tag[@Name="Incoming"]').set('DataType', 'TIMER')
        self.assertTrue(self.engine(mutate=mismatch).blockers)
        def other(root):root.find('./Controller/DataTypes/DataType[@Name="PIDBundle"]/Members/Member[@Name="Tuning"]').set('DataType', 'MESSAGE')
        self.assertTrue(self.engine(kind='PIDBundle', mutate=other).blockers)

    def test_record_lab_pid_member_moves_with_fifo_lifo_and_clears_on_empty_unload(self):
        e = records.RecordQueueTests.engine(self)
        self.assertEqual(e.blockers, []);e.step()
        e.memory.write('IncomingPart.Tuning.SP', 75);self.pulse(e, 'LoadPart')
        e.memory.write('IncomingPart.Tuning.SP', 85);self.pulse(e, 'PushPart')
        self.pulse(e, 'UnloadPart');self.assertEqual(e.memory.read('OutgoingPart.Tuning.SP'), 75)
        self.pulse(e, 'PopPart');self.assertEqual(e.memory.read('PoppedPart.Tuning.SP'), 85)
        self.pulse(e, 'UnloadPart');self.assertEqual(e.memory.read('OutgoingPart.Tuning'), pid_default())

    def test_report_identifies_pid_snapshots_and_native_boundary(self):
        report = self.checked().report()['control_operations']
        self.assertIn('PID', report['fifo']);self.assertTrue(report['pid_payloads']['nested_udts'])
        self.assertIn('private solver history', report['pid_payloads']['history'])
        self.assertFalse(report['pid_payloads']['native_runtime_parity'])


if __name__ == '__main__':
    unittest.main()
