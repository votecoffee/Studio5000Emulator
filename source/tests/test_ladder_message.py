"""Bounded THIS message lifecycle, simulated transfers and scan rollback."""
import copy
import math
import tempfile
import unittest
from itertools import product
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine

SAMPLE = Path(__file__).resolve().parents[1] / 'samples/MessageLab.L5X'


def add_message_burst(root):
    root.getroot().set('TargetName', 'MessageBurstLab')
    controller = root.find('./Controller')
    controller.set('Name', 'MessageBurstLab')
    tags = controller.find('Tags')
    trigger = ET.SubElement(tags, 'Tag', Name='SendBurst', TagType='Base', DataType='BOOL')
    ET.SubElement(ET.SubElement(trigger, 'Data', Format='Decorated'), 'DataValue', DataType='BOOL', Value='0')
    destination = ET.SubElement(tags, 'Tag', Name='BurstValues', TagType='Base', DataType='DINT', Dimensions='17')
    values = ET.SubElement(ET.SubElement(destination, 'Data', Format='Decorated'), 'Array',
                           DataType='DINT', Dimensions='17')
    content = controller.find('.//RLLContent')
    for index in range(17):
        name = f'BurstControl{index + 1}'
        ET.SubElement(values, 'Element', Index=f'[{index}]', Value='0')
        tag = ET.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType='MESSAGE', ExternalAccess='None')
        ET.SubElement(ET.SubElement(tag, 'Data', Format='Message'), 'MessageParameters',
                      MessageType='CIP Data Table Read', LocalElement=f'BurstValues[{index}]',
                      RemoteElement='VirtualValue', RequestedLength='1', ConnectedFlag='0',
                      ConnectionPath='THIS', CommTypeCode='0')
        rung = ET.SubElement(content, 'Rung', Number=str(21 + index), Type='N')
        ET.SubElement(rung, 'Text').text = f'XIC(SendBurst)MSG({name});'


class MessageTests(unittest.TestCase):
    def engine(self, mutate=None, **options):
        path = SAMPLE
        if mutate:
            fixture = ET.parse(SAMPLE)
            mutate(fixture)
            directory = tempfile.TemporaryDirectory()
            self.addCleanup(directory.cleanup)
            path = Path(directory.name) / SAMPLE.name
            fixture.write(path, encoding='utf-8')
        return Engine(Project(path), **options)

    def assert_flags(self, engine, control, **expected):
        for member, value in expected.items():
            self.assertEqual(engine.memory.read(f'{control}.{member}'), value, member)

    def test_read_edges_false_while_busy_and_write(self):
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        self.assertFalse(engine.project.message_catalog.empty)
        memory = engine.memory
        memory.write('SendRead', True)
        engine.step()
        self.assert_flags(engine, 'ReadControl', EN=True, EW=True, ST=False, DN=False, ER=False)
        self.assertEqual(memory.read('ReadValue'), 0)
        memory.write('SendRead', False)
        engine.step()
        self.assert_flags(engine, 'ReadControl', EN=True, EW=False, ST=True, DN=False)
        engine.step()
        self.assert_flags(engine, 'ReadControl', EN=False, ST=False, DN=True, ER=False, REQ_LEN=2, DN_LEN=2)
        self.assertEqual(memory.read('ReadValue'), 17)

        memory.write('SendWrite', True)
        engine.step()
        engine.step()
        self.assertEqual(memory.read('VirtualValue'), 17)
        engine.step()
        self.assert_flags(engine, 'WriteControl', EN=True, ST=False, DN=True, ER=False)
        self.assertEqual(memory.read('VirtualValue'), 42)
        memory.write('WriteValue', 86)
        for _ in range(3):
            engine.step()
        self.assertEqual(memory.read('VirtualValue'), 42)
        memory.write('SendWrite', False)
        engine.step()
        self.assert_flags(engine, 'WriteControl', EN=False, DN=True)
        memory.write('SendWrite', True)
        engine.step()
        self.assert_flags(engine, 'WriteControl', EN=True, EW=True, DN=False)
        engine.step()
        engine.step()
        self.assertEqual(memory.read('VirtualValue'), 86)

    def test_cancel_without_transfer_and_reset_pending_on_prescan(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('SendRead', True)
        memory.write('CancelRead', True)
        engine.step()
        memory.write('CancelRead', False)
        engine.step()
        self.assert_flags(engine, 'ReadControl', EN=True, EW=False, ST=False, DN=False, ER=True, TO=False, ERR=0xFE)
        self.assertEqual(memory.read('ReadValue'), 0)
        memory.write('SendRead', False)
        engine.step()
        self.assert_flags(engine, 'ReadControl', EN=False, ER=True)
        memory.write('SendRead', True)
        engine.step()
        self.assert_flags(engine, 'ReadControl', EW=True, ER=False, ERR=0)
        engine.enter_run()
        self.assert_flags(engine, 'ReadControl', EN=False, EW=False, ST=False, ER=False)
        memory.write('SendRead', False)
        for _ in range(3):
            engine.step()
        self.assertEqual(memory.read('ReadValue'), 0)

    def test_flags_word_and_named_status_share_ladder_lifecycle(self):
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        self.assertEqual(memory.resolve('ReadControl.FLAGS')[2], 'INT')
        self.assertEqual(memory.resolve('ReadControl.EN_CC')[2], 'BOOL')
        memory.write('CaptureReadFlags', True)
        memory.write('SendRead', True)
        for word, member, bit in ((0x84, 'EW', 2), (0xC0, 'ST', 6), (0xA0, 'DN', 5)):
            engine.step()
            self.assertEqual(memory.read('ReadFlagsSnapshot'), word)
            self.assert_flags(engine, 'ReadControl', FLAGS=word, EN=True, EN_CC=False, **{member: True})
            self.assertTrue(memory.read(f'ReadControl.FLAGS.{bit}'))
            self.assertTrue(memory.read('ReadControl')[member])
        memory.write('SendRead', False)
        engine.step()
        self.assertEqual(memory.read('ReadFlagsSnapshot'), 0x20)
        leaves = {row['name']: row['value'] for row in memory.leaves()}
        self.assertEqual((leaves['ReadControl.FLAGS'], leaves['ReadControl.EN'], leaves['ReadControl.DN']),
                         (0x20, False, True))
        engine.enter_run()
        self.assert_flags(engine, 'ReadControl', FLAGS=0, DN=False)

    def test_status_writes_preserve_engine_bits_and_share_timeout_bit(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('SendRead', True)
        memory.write('CancelRead', True)
        engine.step()
        self.assert_flags(engine, 'ReadControl', FLAGS=0x184, TO=True, EW=True, DN=False)
        memory.write('ReadControl.TO', False)
        self.assertFalse(memory.read('ReadControl.FLAGS.8'))
        memory.write('ReadControl.FLAGS', -1)
        memory.write('ReadControl.EW', False)
        memory.write('ReadControl.FLAGS.5', True)
        memory.write('ReadControl.EN_CC', True)
        self.assert_flags(engine, 'ReadControl', FLAGS=0x184, EW=True, DN=False, TO=True, EN_CC=False)
        memory.write('CancelRead', False)
        engine.step()
        self.assert_flags(engine, 'ReadControl', FLAGS=0x90, ER=True, TO=False, ERR=0xFE)
        self.assertEqual(memory.read('ReadValue'), 0)

    def test_copy_into_flags_keeps_the_in_progress_status(self):
        def configure(root):
            rung = ET.SubElement(root.find('.//RLLContent'), 'Rung', Number='21', Type='N')
            ET.SubElement(rung, 'Text').text = 'XIC(CaptureReadFlags)COP(IdentityAttribute,ReadControl.FLAGS,1);'

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('SendRead', True)
        engine.memory.write('CaptureReadFlags', True)
        engine.step()
        self.assert_flags(engine, 'ReadControl', FLAGS=0x84, EW=True, TO=False)
        engine.step()
        self.assert_flags(engine, 'ReadControl', FLAGS=0xC0, ST=True, TO=False)

    def test_timeout_at_exact_deadline_and_retry_with_new_setting(self):
        engine = self.engine()
        memory = engine.memory
        self.assert_flags(engine, 'ReadControl', UnconnectedTimeout=30_000_000)
        memory.write('ApplyReadTimeout', True)
        engine.step()
        self.assert_flags(engine, 'ReadControl', UnconnectedTimeout=10_000)
        self.assertEqual(memory.read('ReadTimeoutEcho', allow_time=True), 10_000)
        memory.write('SendRead', True)
        engine.step()
        self.assert_flags(engine, 'ReadControl', EN=True, EW=True)

        memory.write('ReadTimeoutUs', 10_001)
        engine.step()
        self.assert_flags(engine, 'ReadControl', ST=True, UnconnectedTimeout=10_001)
        self.assertEqual(memory.read('ReadTimeoutEcho', allow_time=True), 10_001)
        engine.step()
        self.assert_flags(engine, 'ReadControl', EN=True, ST=False, ER=True, ERR=0xFE, DN=False, DN_LEN=0, TO=False)
        self.assertEqual(memory.read('ReadValue'), 0)
        engine.step()
        self.assert_flags(engine, 'ReadControl', ER=True, EW=False)

        memory.write('SendRead', False)
        engine.step()
        self.assert_flags(engine, 'ReadControl', EN=False, ER=True)
        memory.write('SendRead', True)
        for _ in range(3):
            engine.step()
        self.assert_flags(engine, 'ReadControl', DN=True, ER=False, ERR=0)
        self.assertEqual(memory.read('ReadValue'), 17)

    def test_variable_step_timeout_preserves_the_write_destination(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('WriteControl.UnconnectedTimeout', 30_000)
        memory.write('SendWrite', True)
        engine.step(7)
        engine.step(42)
        self.assert_flags(engine, 'WriteControl', ST=True, ER=False)
        self.assertEqual(engine.time_ms, 49)
        engine.step(1)
        self.assert_flags(engine, 'WriteControl', ST=False, ER=True, ERR=0xFE, DN=False)
        self.assertEqual(memory.read('VirtualValue'), 17)

    def test_nonpositive_timeout_reports_invalid_value_without_queuing(self):
        for timeout in (0, -1):
            with self.subTest(timeout=timeout):
                engine = self.engine()
                engine.memory.write('ReadControl.UnconnectedTimeout', timeout)
                engine.memory.write('SendRead', True)
                engine.step()
                self.assert_flags(engine, 'ReadControl', EN=True, EW=False, ST=False, ER=True, ERR=0x03)
                self.assertEqual(engine._messages, {})

    def test_prescan_preserves_live_timeout_and_new_engine_uses_default(self):
        engine = self.engine()
        engine.memory.write('ReadControl.UnconnectedTimeout', 4_000_000)
        engine.enter_run()
        self.assert_flags(engine, 'ReadControl', UnconnectedTimeout=4_000_000)
        self.assert_flags(Engine(engine.project), 'ReadControl', UnconnectedTimeout=30_000_000)

    def test_message_timeout_ssv_accepts_time32_and_gsv_returns_exact_dint(self):
        def configure(root):
            for name, dtype in [('ReadTimeoutUs', 'TIME32'), ('ReadTimeoutEcho', 'DINT')]:
                tag = root.find(f'.//Tag[@Name="{name}"]')
                tag.set('DataType', dtype)
                tag.find('Data/DataValue').set('DataType', dtype)
            root.find('.//Rung[@Number="7"]/Text').text = (
                'XIC(ApplyReadTimeout)SSV(message,readcontrol,unconnectedtimeout,ReadTimeoutUs)'
                'GSV(MESSAGE,READCONTROL,UNCONNECTEDTIMEOUT,ReadTimeoutEcho);')

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('ReadTimeoutUs', 'T32#20ms')
        engine.memory.write('ApplyReadTimeout', True)
        engine.step()
        self.assert_flags(engine, 'ReadControl', UnconnectedTimeout=20_000)
        self.assertEqual(engine.memory.read('ReadTimeoutEcho'), 20_000)

    def test_message_timeout_attribute_defers_live_indices_and_establishes_unknown_output(self):
        def configure(root):
            tags = root.find('./Controller/Tags')
            for name, dtype in [('TimeoutSources', 'TIME32'), ('TimeoutDestinations', 'DINT')]:
                tag = ET.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType=dtype, Dimensions='2')
                data = ET.SubElement(ET.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType=dtype, Dimensions='2')
                ET.SubElement(data, 'Element', Index='[0]' if dtype == 'TIME32' else '[1]', Value='21000')
            root.find('.//Tag[@Name="ReadLocalIndex"]/Data/DataValue').set('Value', '99')
            root.find('.//Rung[@Number="7"]/Text').text = (
                'XIC(ApplyReadTimeout)SSV(Message,ReadControl,UnconnectedTimeout,TimeoutSources[ReadLocalIndex])'
                'GSV(Message,ReadControl,UnconnectedTimeout,TimeoutDestinations[ReadLocalIndex]);')

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        engine.step()
        self.assert_flags(engine, 'ReadControl', UnconnectedTimeout=30_000_000)
        engine.memory.write('ApplyReadTimeout', True)
        engine.memory.write('ReadLocalIndex', 0)
        engine.step()
        self.assertEqual(engine.memory.read('TimeoutDestinations[0]'), 21_000)
        engine.memory.write('ReadLocalIndex', 1)
        with self.assertRaisesRegex(ModelError, 'requires a known positive value'):
            engine.step()
        self.assert_flags(engine, 'ReadControl', UnconnectedTimeout=21_000)

    def test_message_timeout_ssv_and_readback_roll_back_with_later_fault(self):
        def configure(root):
            rung = ET.SubElement(root.find('.//RLLContent'), 'Rung', Number='21', Type='N')
            ET.SubElement(rung, 'Text').text = 'XIC(CancelRead)DIV(1,0,ReadValue);'

        engine = self.engine(configure)
        engine.memory.write('ApplyReadTimeout', True)
        engine.memory.write('CancelRead', True)
        with self.assertRaisesRegex(ModelError, 'Scan rolled back'):
            engine.step()
        self.assert_flags(engine, 'ReadControl', UnconnectedTimeout=30_000_000)
        self.assertEqual(engine.memory.read('ReadTimeoutEcho', allow_time=True), 0)

    def test_message_timeout_attribute_blocks_unqualified_instances_and_types(self):
        for call in ('SSV(Message,,UnconnectedTimeout,ReadTimeoutUs)',
                     'GSV(Message,ReadValue,UnconnectedTimeout,ReadTimeoutEcho)',
                     'GSV(Message,ReadControl,UnconnectedTimeout,SendRead)',
                     'SSV(Message,ReadControl,UnconnectedTimeout,10000)',
                     'SSV(Message,ReadControl,ConnectionRate,ReadTimeoutUs)'):
            with self.subTest(call=call):
                def configure(root):
                    root.find('.//Rung[@Number="7"]/Text').text = f'XIC(ApplyReadTimeout){call};'

                self.assertTrue(self.engine(configure).blockers)

    def test_message_timeout_attribute_remains_ladder_only(self):
        def configure(root):
            routine = root.find('.//Routine')
            routine.set('Type', 'ST')
            routine.remove(routine.find('RLLContent'))
            content = ET.SubElement(routine, 'STContent')
            ET.SubElement(content, 'Line', Number='0').text = 'GSV(Message,ReadControl,UnconnectedTimeout,ReadTimeoutEcho);'
            ET.SubElement(content, 'Line', Number='1').text = 'SSV(Message,ReadControl,UnconnectedTimeout,ReadTimeoutUs);'

        blockers = self.engine(configure).blockers
        self.assertTrue(any('GSV' in problem and 'whole-project ladder scan' in problem for problem in blockers))
        self.assertTrue(any('SSV' in problem and 'whole-project ladder scan' in problem for problem in blockers))

    def test_generic_identity_read_uses_the_message_queue_and_preserves_neighbors(self):
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        engine.memory.write('SendIdentityRead', True)
        engine.step()
        self.assert_flags(engine, 'IdentityControl', EN=True, EW=True, REQ_LEN=0, DN_LEN=0)
        engine.step()
        self.assert_flags(engine, 'IdentityControl', ST=True, DN=False)
        self.assertEqual(engine.memory.read('IdentityReply'), [-9, 0, 0, -9])
        engine.step()
        self.assertEqual(engine.memory.read('IdentityReply'), [-9, 35, 11, -9])
        self.assert_flags(engine, 'IdentityControl', ST=False, DN=True, ER=False, DN_LEN=2)

    def test_generic_identity_reads_exact_byte_payloads(self):
        for attribute, payload in [(1, b'\x01\x00'), (2, b'\x0e\x00'), (3, b'\xa8\x00'),
                                   (4, b'\x23\x0b'), (5, b'\x70\x30'), (6, b'\x01\x00LL'), (7, b'\x0b1756-L85E/B')]:
            with self.subTest(attribute=attribute):
                def configure(root):
                    control = root.find('.//Tag[@Name="IdentityControl"]//MessageParameters')
                    control.set('AttributeNumber', str(attribute))
                    tag = root.find('.//Tag[@Name="IdentityReply"]')
                    tag.set('Dimensions', '16')
                    tag.find('Data/Array').set('Dimensions', '16')

                engine = self.engine(configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write('SendIdentityRead', True)
                for _ in range(3):
                    engine.step()
                reply = engine.memory.read('IdentityReply')
                self.assertEqual(bytes(value & 255 for value in reply[1:1 + len(payload)]), payload)
                self.assertEqual(reply[0], -9)
                self.assert_flags(engine, 'IdentityControl', DN=True, DN_LEN=len(payload))

    def test_generic_identity_attribute_written_by_ladder_applies_to_next_request(self):
        engine = self.engine()
        memory = engine.memory
        self.assertEqual(engine.blockers, [])
        self.assertEqual(memory.resolve('IdentityControl.Attribute')[2], 'INT')
        self.assertEqual(memory.resolve('IdentityControl.Class')[2], 'INT')
        self.assertEqual(memory.resolve('IdentityControl.Instance')[2], 'DINT')
        self.assert_flags(engine, 'IdentityControl', Class=1, Instance=1, Attribute=4)
        memory.write('SendIdentityRead', True)
        engine.step()
        memory.write('ApplyIdentityAttribute', True)
        engine.step()
        self.assert_flags(engine, 'IdentityControl', ST=True, Attribute=3)
        engine.step()
        self.assertEqual(memory.read('IdentityReply'), [-9, 35, 11, -9])
        memory.write('SendIdentityRead', False)
        engine.step()
        memory.write('SendIdentityRead', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(memory.read('IdentityReply'), [-9, -88, 0, -9])
        self.assert_flags(engine, 'IdentityControl', DN=True, ER=False, DN_LEN=2)

    def test_generic_identity_captures_address_errors_and_preserves_reply(self):
        for control, gate, reply, member, value, error in (
            ('IdentityControl', 'SendIdentityRead', 'IdentityReply', 'Class', 2, 0x05),
            ('IdentityControl', 'SendIdentityRead', 'IdentityReply', 'Instance', 2, 0x05),
            ('IdentityControl', 'SendIdentityRead', 'IdentityReply', 'Attribute', -1, 0x14),
            ('IdentityAllControl', 'SendIdentityAll', 'IdentityAllReply', 'Instance', 2, 0x05),
        ):
            with self.subTest(control=control, member=member):
                engine = self.engine()
                memory = engine.memory
                before = list(memory.read(reply))
                ref = f'{control}.{member}'
                configured = memory.read(ref)
                memory.write(ref, value)
                memory.write(gate, True)
                engine.step()
                memory.write(ref, configured)
                engine.step()
                engine.step()
                self.assertEqual(memory.read(reply), before)
                self.assertEqual(engine.fault, '')
                self.assert_flags(engine, control, DN=False, ER=True, ERR=error, DN_LEN=0)

    def test_generic_identity_prescan_keeps_live_address_fields_and_reset_restores_them(self):
        engine = self.engine()
        for name, value in [('Class', 2), ('Instance', 3), ('Attribute', 5)]:
            engine.memory.write('IdentityControl.' + name, value)
        engine.enter_run()
        self.assert_flags(engine, 'IdentityControl', Class=2, Instance=3, Attribute=5)
        self.assert_flags(Engine(engine.project), 'IdentityControl', Class=1, Instance=1, Attribute=4)

    def test_generic_identity_short_destination_and_timeout_preserve_all_bytes(self):
        def long_reply(root):
            root.find('.//Tag[@Name="IdentityControl"]//MessageParameters').set('AttributeNumber', '7')

        for configure, timeout, error in [(long_reply, 30_000_000, 0x11), (None, 10_000, 0xFE)]:
            with self.subTest(error=error):
                engine = self.engine(configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write('IdentityControl.UnconnectedTimeout', timeout)
                engine.memory.write('SendIdentityRead', True)
                for _ in range(3):
                    engine.step()
                self.assertEqual(engine.memory.read('IdentityReply'), [-9, 0, 0, -9])
                self.assert_flags(engine, 'IdentityControl', DN=False, ER=True, ERR=error, DN_LEN=0)

    def test_generic_identity_all_returns_complete_reply_with_completion_mode(self):
        for running, low_status in [(False, 0x70), (True, 0x60)]:
            with self.subTest(running=running):
                def configure(root):
                    control = root.find('.//Tag[@Name="IdentityAllControl"]//MessageParameters')
                    if running:
                        del control.attrib['AttributeNumber']
                    else:
                        control.set('AttributeNumber', '16#FFFF')  # Custom service placeholder.

                engine = self.engine(configure)
                self.assertEqual(engine.blockers, [])
                self.assert_flags(engine, 'IdentityAllControl', Attribute=0 if running else -1)
                engine.memory.write('IdentityAllControl.Attribute', 32767)
                engine.memory.write('SendIdentityAll', True)
                engine.step()
                engine.step()
                self.assert_flags(engine, 'IdentityAllControl', ST=True, DN=False)
                engine.step(running=running)

                reply = engine.memory.read('IdentityAllReply')
                expected = bytes((1, 0, 14, 0, 168, 0, 35, 11, low_status, 0x30, 1, 0, 0x4c, 0x4c, 11))
                self.assertEqual(bytes(value & 255 for value in reply[1:-1]), expected + b'1756-L85E/B')
                self.assertEqual((reply[0], reply[-1]), (-9, -9))
                self.assert_flags(engine, 'IdentityAllControl', ST=False, DN=True, ER=False, REQ_LEN=0, DN_LEN=26)

    def test_generic_identity_all_short_buffer_errors_without_partial_data(self):
        def configure(root):
            control = root.find('.//Tag[@Name="IdentityAllControl"]//MessageParameters')
            control.set('DestinationTag', 'IdentityReply[1]')

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('SendIdentityAll', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(engine.memory.read('IdentityReply'), [-9, 0, 0, -9])
        self.assert_flags(engine, 'IdentityAllControl', DN=False, ER=True, ERR=0x11, DN_LEN=0)

    def test_generic_identity_all_rolls_back_response_and_queue_after_later_fault(self):
        def configure(root):
            rung = ET.SubElement(root.find('.//RLLContent'), 'Rung', Number='21', Type='N')
            ET.SubElement(rung, 'Text').text = 'XIC(CancelRead)DIV(1,0,ReadValue);'

        engine = self.engine(configure)
        engine.memory.write('SendIdentityAll', True)
        engine.step()
        engine.step()
        original = list(engine.memory.read('IdentityAllReply'))
        pending = engine._messages['identityallcontrol']
        engine.memory.write('CancelRead', True)
        with self.assertRaisesRegex(ModelError, 'Scan rolled back'):
            engine.step(running=True)
        self.assertEqual(engine.memory.read('IdentityAllReply'), original)
        self.assertEqual(engine._messages['identityallcontrol'], pending)
        self.assert_flags(engine, 'IdentityAllControl', ST=True, DN=False, ER=False, DN_LEN=0)

    def test_generic_identity_rejects_unqualified_services_and_destinations(self):
        for name, value in [('ServiceCode', '16#10'), ('ObjectType', '2'), ('TargetObject', '2'),
                            ('AttributeNumber', '8'), ('RequestedLength', '1'),
                            ('DestinationTag', 'ReadValue'), ('DestinationTag', 'IdentityReply[*]'),
                            ('ConnectionPath', '2,192.0.2.20')]:
            with self.subTest(name=name, value=value):
                def configure(root):
                    root.find('.//Tag[@Name="IdentityControl"]//MessageParameters').set(name, value)

                self.assertTrue(any('MSG:' in problem for problem in self.engine(configure).blockers))

    def test_array_offsets_and_overlapping_source_snapshot(self):
        def configure(root):
            tag = root.find('.//Tag[@Name="VirtualValue"]')
            tag.set('Dimensions', '4')
            data = tag.find('Data')
            data.remove(data[0])
            values = ET.SubElement(data, 'Array', DataType='DINT', Dimensions='4')
            for index, value in enumerate((11, 22, -33, 44)):
                ET.SubElement(values, 'Element', Index=f'[{index}]', Value=str(value))
            write = root.find('.//Tag[@Name="WriteControl"]//MessageParameters')
            write.attrib.update(LocalElement='VirtualValue[0]', RemoteElement='VirtualValue',
                                RemoteIndex='1', RequestedLength='3')

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('WriteControl.LocalIndex', 2)
        engine.memory.write('WriteControl.RemoteIndex', -1)
        engine.memory.write('SendWrite', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(engine.memory.read('VirtualValue'), [11, 11, 22, -33])
        self.assert_flags(engine, 'WriteControl', REQ_LEN=6, DN_LEN=6, DN=True, ER=False)

    def test_matching_numeric_types_read_and_write_without_conversion(self):
        for dtype, incoming, outgoing, words in (
            ('SINT', -128, 127, 1), ('INT', -32768, 32767, 1),
            ('DINT', -2147483648, 2147483647, 2), ('LINT', -9223372036854775808, 9007199254740993, 4),
            ('REAL', -0.0, 1.25, 2),
        ):
            with self.subTest(dtype=dtype):
                def configure(root):
                    for name, value in [('ReadValue', 0), ('VirtualValue', incoming), ('WriteValue', outgoing)]:
                        tag = root.find(f'.//Tag[@Name="{name}"]')
                        tag.set('DataType', dtype)
                        tag.find('./Data/DataValue').attrib.update(DataType=dtype, Value=str(value))
                    # Configuration can precede both data endpoints in a saved export.
                    tags = root.find('./Controller/Tags')
                    read_control = tags.find('Tag[@Name="ReadControl"]')
                    tags.remove(read_control)
                    tags.insert(0, read_control)

                engine = self.engine(configure, defer_prescan=True)
                self.assertEqual(engine.blockers, [])
                self.assert_flags(engine, 'ReadControl', REQ_LEN=words, DN_LEN=0)
                engine.memory.write('SendRead', True)
                engine.memory.write('SendWrite', True)
                for _ in range(3):
                    engine.step()
                value = engine.memory.read('ReadValue')
                self.assertEqual(value, incoming)
                if dtype == 'REAL':
                    self.assertEqual(math.copysign(1, value), -1)
                self.assertEqual(engine.memory.read('VirtualValue'), outgoing)
                for control in ('ReadControl', 'WriteControl'):
                    self.assert_flags(engine, control, REQ_LEN=words, DN_LEN=words, DN=True, ER=False)

    def test_star_indices_program_scope_and_exact_lint_in_bundled_sample(self):
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        engine.memory.write('SendTyped', True)
        engine.step()
        self.assert_flags(engine, 'RealReadControl', EW=True, REQ_LEN=4, DN_LEN=0)
        for _ in range(2):
            engine.step()
        self.assertEqual(engine.memory.read('RealReadback'), [2.5, -7.25, 0.0])
        self.assertEqual(engine.memory.read('Program:MainProgram.WideTarget'), 9007199254740993)
        self.assert_flags(engine, 'RealReadControl', DN=True, DN_LEN=4)
        self.assert_flags(engine, 'WideWriteControl', DN=True, DN_LEN=4)

    def test_ladder_index_writes_are_captured_at_queue_time(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('SetReadIndices', True)
        memory.write('ReadLocalIndex', 1)
        memory.write('ReadRemoteIndex', 0)
        memory.write('SendTyped', True)
        engine.step()
        self.assert_flags(engine, 'RealReadControl', EW=True, LocalIndex=1, RemoteIndex=0)

        memory.write('ReadLocalIndex', 0)
        memory.write('ReadRemoteIndex', 1)
        engine.step()
        self.assert_flags(engine, 'RealReadControl', ST=True, LocalIndex=0, RemoteIndex=1)
        engine.step()
        self.assertEqual(memory.read('RealReadback'), [0.0, 100.0, 2.5])
        self.assert_flags(engine, 'RealReadControl', DN=True, ER=False)

        memory.write('SendTyped', False)
        engine.step()
        memory.write('SendTyped', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(memory.read('RealReadback'), [2.5, -7.25, 2.5])

    def test_prescan_preserves_index_edits_and_reset_loads_authored_indices(self):
        def configure(root):
            control = root.find('.//Tag[@Name="RealReadControl"]//MessageParameters')
            control.set('LocalIndex', '99')

        engine = self.engine(configure, defer_prescan=True)
        self.assertEqual(engine.blockers, [])
        self.assert_flags(engine, 'RealReadControl', LocalIndex=99, RemoteIndex=1)
        engine.memory.write('RealReadControl.LocalIndex', 1)
        engine.memory.write('RealReadControl.RemoteIndex', 0)
        engine.memory.write('SendTyped', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(engine.memory.read('RealReadback'), [0.0, 100.0, 2.5])
        self.assert_flags(engine, 'RealReadControl', DN=True, LocalIndex=1, RemoteIndex=0)
        fresh = Engine(engine.project, defer_prescan=True)
        self.assert_flags(fresh, 'RealReadControl', DN=False, LocalIndex=99, RemoteIndex=1)

    def test_invalid_live_index_sets_message_error_and_never_wraps(self):
        for member, value in [('LocalIndex', -1), ('LocalIndex', 2),
                              ('RemoteIndex', -1), ('RemoteIndex', 2147483647)]:
            with self.subTest(member=member, value=value):
                engine = self.engine()
                engine.memory.write('RealReadControl.' + member, value)
                engine.memory.write('SendTyped', True)
                for _ in range(3):
                    engine.step()
                self.assertEqual(engine.fault, '')
                self.assertEqual(engine.memory.read('RealReadback'), [0.0, 0.0, 0.0])
                self.assert_flags(engine, 'RealReadControl', ER=True, ERR=0x05, DN=False, DN_LEN=0)

    def test_ladder_string_move_retargets_only_the_next_read(self):
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        field = 'ReadControl.RemoteElement'
        self.assertEqual(memory.string(field), 'VirtualValue')
        memory.write('SendRead', True)
        engine.step()
        memory.write('UseAlternateRead', True)
        engine.step()
        self.assertEqual(memory.string(field), 'AlternateValue')
        self.assert_flags(engine, 'ReadControl', ST=True)
        engine.step()
        self.assertEqual(memory.read('ReadValue'), 17)

        memory.write('SendRead', False)
        engine.step()
        memory.write('SendRead', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(memory.read('ReadValue'), 64)
        self.assert_flags(engine, 'ReadControl', DN=True, ER=False)
        watch = next(row for row in memory.leaves() if row['name'] == field)
        self.assertEqual((watch['kind'], watch['type'], watch['value']), ('string', 'STRING', 'AlternateValue'))

    def test_write_target_is_captured_and_prescan_keeps_live_text(self):
        engine = self.engine()
        memory = engine.memory
        field = 'WriteControl.RemoteElement'
        memory.write('SendWrite', True)
        engine.step()
        memory.write(field, 'AlternateValue')
        for _ in range(2):
            engine.step()
        self.assertEqual((memory.read('VirtualValue'), memory.read('AlternateValue')), (42, 64))

        engine.enter_run()
        self.assertEqual(memory.string(field), 'AlternateValue')
        memory.write('WriteValue', 71)
        for _ in range(3):
            engine.step()
        self.assertEqual((memory.read('VirtualValue'), memory.read('AlternateValue')), (42, 71))
        self.assertEqual(Engine(engine.project).memory.string(field), 'VirtualValue')

    def test_retargeted_literal_does_not_inherit_the_authored_wildcard_index(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('RealReadControl.RemoteElement', 'Program:MainProgram.Samples[0]')
        memory.write('SendTyped', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(memory.read('RealReadback'), [100.0, 2.5, 0.0])
        self.assert_flags(engine, 'RealReadControl', RemoteIndex=1, DN=True, ER=False)

    def test_invalid_remote_string_and_wrong_type_complete_with_errors(self):
        field = 'ReadControl.RemoteElement'
        for ref, value, error in [(field, '', 0x05), (field, '2,192.0.2.20', 0x05),
                                  (field, 'VirtualValue\u00a0', 0x05), (field, 'Missing', 0x05),
                                  (field + '.LEN', 83, 0x05), (field, 'SendRead', 0xFC),
                                  (field, 'RecordSource.Missing', 0x05), (field, 'RecordSource[*].Batch', 0x05),
                                  (field, 'RecordSource.Quality.Value', 0xFC)]:
            with self.subTest(ref=ref, value=value):
                engine = self.engine()
                engine.memory.write(ref, value)
                engine.memory.write('SendRead', True)
                for _ in range(3):
                    engine.step()
                self.assertEqual(engine.fault, '')
                self.assertEqual(engine.memory.read('ReadValue'), 0)
                self.assert_flags(engine, 'ReadControl', DN=False, ER=True, ERR=error)

    def test_long_authored_address_keeps_existing_transfer_support(self):
        program_name, tag_name = 'P' * 40, 'T' * 40

        def configure(root):
            program = root.find('.//Program')
            program.set('Name', program_name)
            root.find('.//ScheduledProgram').set('Name', program_name)
            for parameters in root.findall('.//MessageParameters[@RemoteElement]'):
                remote = parameters.get('RemoteElement')
                parameters.set('RemoteElement', remote.replace('Program:MainProgram.', f'Program:{program_name}.'))
            tag = ET.SubElement(program.find('Tags'), 'Tag', Name=tag_name, TagType='Base', DataType='DINT')
            ET.SubElement(ET.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType='DINT', Value='109')
            root.find('.//Tag[@Name="ReadControl"]//MessageParameters').set('RemoteElement', f'Program:{program_name}.{tag_name}')
            # The bundled MOV requires the optional writable STRING field, so remove that rung for this profile.
            content = program.find('.//RLLContent')
            content.remove(content.find('Rung[@Number="0"]'))

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        self.assertNotIn('RemoteElement', engine.memory.read('ReadControl'))
        engine.memory.write('SendRead', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(engine.memory.read('ReadValue'), 109)

    def test_scoped_errors_and_unknown_source_leave_all_destination_elements_intact(self):
        for case, expected in [('none', 0x0F), ('mismatch', 0xFC), ('unknown', 0x03), ('bounds', 0x05)]:
            with self.subTest(case=case):
                def configure(root):
                    tag = root.find('.//Tag[@Name="Samples"]')
                    data = tag.find('Data/Array')
                    if case == 'none':
                        tag.set('ExternalAccess', 'None')
                    elif case == 'mismatch':
                        tag.set('DataType', 'DINT')
                        data.set('DataType', 'DINT')
                        for i, item in enumerate(data):
                            item.set('Value', str(i))
                    elif case == 'unknown':
                        data.remove(data[2])
                    else:
                        control = root.find('.//Tag[@Name="RealReadControl"]//MessageParameters')
                        control.set('RemoteIndex', '2')

                engine = self.engine(configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write('SendTyped', True)
                for _ in range(3):
                    engine.step()
                self.assertEqual(engine.memory.read('RealReadback'), [0.0, 0.0, 0.0])
                self.assert_flags(engine, 'RealReadControl', DN=False, ER=True, ERR=expected, DN_LEN=0)

    def test_odd_sint_transfer_reports_whole_words(self):
        def configure(root):
            control = root.find('.//Tag[@Name="RealReadControl"]//MessageParameters')
            control.attrib.update(LocalIndex='1', RemoteIndex='0', RequestedLength='3')
            for name in ('Samples', 'RealReadback'):
                tag = root.find(f'.//Tag[@Name="{name}"]')
                tag.attrib.update(DataType='SINT', Dimensions='4')
                data = tag.find('Data/Array')
                data.attrib.update(DataType='SINT', Dimensions='4')
                data[:] = [ET.Element('Element', Index=f'[{i}]', Value=str(value))
                           for i, value in enumerate((10, -9, 8, -7))]

        engine = self.engine(configure)
        engine.memory.write('SendTyped', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(engine.memory.read('RealReadback'), [10, 10, -9, 8])
        self.assert_flags(engine, 'RealReadControl', REQ_LEN=2, DN_LEN=2, DN=True, ER=False)

    def test_read_crosses_a_row_and_captures_full_remote_coordinates(self):
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        memory.write('SendGridRead', True)
        engine.step()
        memory.write('GridReadControl.RemoteElement', 'Program:MainProgram.Grid[0, 1]')
        memory.write('GridReadControl.LocalIndex', 2)
        memory.write('GridReadControl.RemoteIndex', 2)
        engine.step()
        self.assertEqual(memory.read('GridReadback'), [[-1, -1, 0], [0, 0, -1]])
        engine.step()
        self.assertEqual(memory.read('GridReadback'), [[-1, -1, 30], [40, 50, -1]])
        self.assert_flags(engine, 'GridReadControl', DN=True, ER=False, REQ_LEN=6, DN_LEN=6)
        memory.write('SendGridRead', False)
        engine.step()
        memory.write('SendGridRead', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(memory.read('GridReadback'), [[-1, -1, 20], [30, 40, -1]])

    def test_write_crosses_a_plane_and_snapshots_the_overlapping_source(self):
        def configure(root):
            tags = root.find('./Controller/Tags')
            cube = ET.SubElement(tags, 'Tag', Name='Cube', TagType='Base', DataType='DINT',
                                 Dimensions='2,2,2', ExternalAccess='Read/Write')
            data = ET.SubElement(ET.SubElement(cube, 'Data', Format='Decorated'), 'Array',
                                 DataType='DINT', Dimensions='2,2,2')
            for value, (i, j, k) in enumerate(product(range(2), repeat=3)):
                ET.SubElement(data, 'Element', Index=f'[{i},{j},{k}]', Value=str(value))
            root.find('.//Tag[@Name="WriteControl"]//MessageParameters').attrib.update(
                LocalElement='Cube[0,1,0]', RemoteElement='Cube[0,1,1]', RequestedLength='4')

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('SendWrite', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(engine.memory.read('Cube'), [[[0, 1], [2, 2]], [[3, 4], [5, 7]]])
        self.assert_flags(engine, 'WriteControl', DN=True, ER=False, REQ_LEN=8, DN_LEN=8)

    def test_incomplete_or_overrun_grid_address_preserves_destination(self):
        for subscript in ('', '[1]', '[*]', '[0,3]', '[1,1]', '[0,0,0]', '[0,*]'):
            with self.subTest(subscript=subscript):
                engine = self.engine()
                memory = engine.memory
                memory.write('GridReadControl.RemoteElement', 'Program:MainProgram.Grid' + subscript)
                memory.write('SendGridRead', True)
                for _ in range(3):
                    engine.step()
                self.assertEqual(engine.fault, '')
                self.assertEqual(memory.read('GridReadback'), [[-1, -1, 0], [0, 0, -1]])
                self.assert_flags(engine, 'GridReadControl', DN=False, ER=True, ERR=5, DN_LEN=0)

    def test_multidimensional_local_address_requires_full_start_and_zero_offset(self):
        for attributes in ({'LocalElement': 'GridReadback[0]'}, {'LocalIndex': '1'},
                           {'LocalElement': 'GridReadback[1,1]'}):
            with self.subTest(attributes=attributes):
                def configure(root):
                    root.find('.//Tag[@Name="GridReadControl"]//MessageParameters').attrib.update(attributes)

                self.assertTrue(any('MSG' in item for item in self.engine(configure).blockers))

    def test_missing_wrong_type_and_denied_remote_transfers(self):
        for remote, access, expected in [('Missing', 'Read/Write', 0x05), ('VirtualValue[2]', 'Read/Write', 0x05),
                                         ('CancelRead', 'Read/Write', 0xFC), ('VirtualValue', 'Read Only', 0x0F)]:
            with self.subTest(remote=remote, access=access):
                def configure(root):
                    root.find('.//Tag[@Name="WriteControl"]//MessageParameters').set('RemoteElement', remote)
                    root.find('.//Tag[@Name="VirtualValue"]').set('ExternalAccess', access)

                engine = self.engine(configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write('SendWrite', True)
                for _ in range(3):
                    engine.step()
                self.assert_flags(engine, 'WriteControl', EN=True, ER=True, DN=False, ERR=expected, DN_LEN=0)
                self.assertEqual(engine.memory.read('VirtualValue'), 17)

    def test_completion_and_queue_roll_back_with_later_fault(self):
        def configure(root):
            content = root.find('.//RLLContent')
            rung = ET.SubElement(content, 'Rung', Number='21', Type='N')
            ET.SubElement(rung, 'Text').text = 'XIC(CancelRead)DIV(1,0,ReadValue);'

        for timeout in (30_000_000, 10_000):
            with self.subTest(timeout=timeout):
                engine = self.engine(configure)
                memory = engine.memory
                memory.write('WriteControl.UnconnectedTimeout', timeout)
                memory.write('SendWrite', True)
                engine.step()
                engine.step()
                pending = engine._messages['writecontrol']
                memory.write('CancelRead', True)
                with self.assertRaisesRegex(ModelError, 'Scan rolled back'):
                    engine.step()
                self.assertEqual((engine.scan_count, engine.time_ms), (2, 20))
                self.assertEqual(memory.read('VirtualValue'), 17)
                self.assert_flags(engine, 'WriteControl', FLAGS=0xC0, EN=True, ST=True, DN=False, ER=False)
                self.assertEqual(engine._messages['writecontrol'], pending)

    def test_decorated_only_message_fields_remain_readable_without_execution(self):
        def configure(root):
            tags = root.find('./Controller/Tags')
            tag = ET.SubElement(tags, 'Tag', Name='SavedMessage', TagType='Base', DataType='MESSAGE')
            data = ET.SubElement(tag, 'Data', Format='Decorated')
            record = ET.SubElement(data, 'Structure', DataType='MESSAGE')
            ET.SubElement(record, 'DataValueMember', Name='LegacyStatus', DataType='INT', Value='19')

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        self.assertEqual(engine.memory.read('SavedMessage.LegacyStatus'), 19)
        self.assertEqual(engine.memory.read('ReadControl.DN'), False)

        def use_as_control(root):
            configure(root)
            root.find('.//Rung[@Number="1"]/Text').text = 'XIC(SendRead)MSG(SavedMessage);'

        self.assertTrue(any('directly named controller or program-local MESSAGE' in item
                            for item in self.engine(use_as_control).blockers))

    def test_program_local_controls_read_and_write_private_local_data(self):
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        program = 'Program:MainProgram.'
        memory.write('SendLocalMessages', True)
        engine.step()
        self.assert_flags(engine, program + 'LocalReadControl', FLAGS=0x84, REQ_LEN=2)
        self.assert_flags(engine, program + 'LocalWriteControl', FLAGS=0x84, REQ_LEN=2)
        memory.write(program + 'LocalOutbox', 91)
        engine.step()
        self.assertEqual(memory.read(program + 'LocalInbox'), [-1, -1])
        self.assertEqual(memory.read('LocalEcho'), 0)
        engine.step()
        self.assertEqual(memory.read(program + 'LocalInbox'), [-1, 17])
        self.assertEqual(memory.read('LocalEcho'), 91)
        self.assert_flags(engine, program + 'LocalReadControl', DN=True, DN_LEN=2)
        self.assert_flags(engine, program + 'LocalWriteControl', DN=True, DN_LEN=2)

    def test_same_named_controls_and_local_data_stay_in_each_program(self):
        def configure(root):
            controller_tags = root.find('./Controller/Tags')
            programs = root.find('./Controller/Programs')
            main = programs.find('Program')
            second = ET.SubElement(programs, 'Program', Name='Second', MainRoutineName='Main', Class='Standard')
            second_tags = ET.SubElement(second, 'Tags')
            for name in ('ReadValue', 'ReadControl'):
                tag = controller_tags.find(f'Tag[@Name="{name}"]')
                main.find('Tags').append(copy.deepcopy(tag))
                second_tags.append(copy.deepcopy(tag))
            second_tags.find('Tag[@Name="ReadControl"]//MessageParameters').set('RemoteElement', 'AlternateValue')
            routines = ET.SubElement(second, 'Routines')
            routine = ET.SubElement(routines, 'Routine', Name='Main', Type='RLL')
            ET.SubElement(routine, 'RLLContent').append(copy.deepcopy(main.find('.//Rung[@Number="1"]')))
            ET.SubElement(root.find('.//ScheduledPrograms'), 'ScheduledProgram', Name='Second')

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        memory.write('SendRead', True)
        engine.step()
        self.assertEqual(list(engine._messages), ['program:mainprogram.readcontrol', 'program:second.readcontrol'])
        engine.step()
        engine.step()
        self.assertEqual([memory.read(ref) for ref in ('Program:MainProgram.ReadValue',
                                                       'Program:Second.ReadValue', 'ReadValue')], [17, 64, 0])
        self.assert_flags(engine, 'ReadControl', FLAGS=0)
        memory.write('ApplyReadTimeout', True)
        engine.step()
        self.assertEqual(memory.read('ReadTimeoutEcho', allow_time=True), 10_000)
        self.assert_flags(engine, 'Program:MainProgram.ReadControl', UnconnectedTimeout=10_000)
        self.assert_flags(engine, 'Program:Second.ReadControl', UnconnectedTimeout=30_000_000)
        self.assert_flags(engine, 'ReadControl', UnconnectedTimeout=30_000_000)

    def test_controller_message_can_explicitly_address_calling_program_data(self):
        def configure(root):
            read = root.find('.//Tag[@Name="ReadControl"]//MessageParameters')
            read.set('LocalElement', 'Program:MainProgram.LocalInbox[0]')

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('SendRead', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(engine.memory.read('Program:MainProgram.LocalInbox'), [17, -1])
        self.assertEqual(engine.memory.read('ReadValue'), 0)
        self.assert_flags(engine, 'ReadControl', DN=True, REQ_LEN=2, DN_LEN=2)

    def test_local_generic_identity_uses_the_program_reply_buffer(self):
        def configure(root):
            controller_tags = root.find('./Controller/Tags')
            program_tags = root.find('./Controller/Programs/Program/Tags')
            for name in ('IdentityReply', 'IdentityControl'):
                tag = controller_tags.find(f'Tag[@Name="{name}"]')
                controller_tags.remove(tag)
                program_tags.append(tag)

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('SendIdentityRead', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(engine.memory.read('Program:MainProgram.IdentityReply'), [-9, 35, 11, -9])
        self.assert_flags(engine, 'Program:MainProgram.IdentityControl', DN=True, DN_LEN=2)

    def test_scope_validation_rejects_foreign_data_and_nonlocal_control_usage(self):
        def foreign(root):
            read = root.find('.//Tag[@Name="LocalReadControl"]//MessageParameters')
            read.set('LocalElement', 'Program:Second.LocalInbox[0]')

        def public(root):
            root.find('.//Tag[@Name="LocalReadControl"]').set('Usage', 'Public')

        self.assertTrue(any('local data must belong to the program' in item for item in self.engine(foreign).blockers))
        self.assertTrue(any('must be Local tags' in item for item in self.engine(public).blockers))

    def test_matching_record_transfers_preserve_typed_members_and_report_words(self):
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        memory.write('SendRecord', True)
        engine.step()
        self.assert_flags(engine, 'RecordWriteControl', EW=True, REQ_LEN=16)
        self.assert_flags(engine, 'Program:MainProgram.RecordReadControl', EW=True, REQ_LEN=16)
        memory.write('RecordSource.Lot', 9007199254740997)
        engine.step()
        self.assertEqual(memory.read('RecordEcho.Batch'), 0)
        engine.step()
        expected = {'Batch': 73, 'Lot': 9007199254740997, 'Ready': True,
                    'Samples': [12, -3], 'Quality': {'Value': 2.5, 'Code': 7}}
        self.assertEqual(memory.read('RecordEcho'), expected)
        self.assertEqual(memory.read('Program:MainProgram.RecordInbox'), expected)
        self.assert_flags(engine, 'RecordWriteControl', DN=True, ER=False, DN_LEN=16)
        self.assert_flags(engine, 'Program:MainProgram.RecordReadControl', DN=True, ER=False, DN_LEN=16)
        memory.write('RecordSource.Quality.Value', 1.25)
        self.assertEqual(memory.read('RecordEcho.Quality.Value'), 2.5)
        self.assertEqual(memory.read('Program:MainProgram.RecordInbox.Quality.Value'), 2.5)

    def test_record_array_transfer_snapshots_overlap_and_rejects_unknown_source_atomically(self):
        for unknown in (False, True):
            with self.subTest(unknown=unknown):
                def configure(root):
                    tag = root.find('.//Tag[@Name="RecordSource"]')
                    tag.set('Dimensions', '3')
                    data = tag.find('Data')
                    example = data[0]
                    data.remove(example)
                    array = ET.SubElement(data, 'Array', DataType='MessageRecord', Dimensions='3')
                    for index in range(3):
                        record = copy.deepcopy(example)
                        record.find('DataValueMember[@Name="Batch"]').set('Value', str(10 * (index + 1)))
                        if unknown and index == 1:
                            quality = record.find('StructureMember[@Name="Quality"]')
                            quality.remove(quality.find('DataValueMember[@Name="Value"]'))
                        ET.SubElement(array, 'Element', Index=f'[{index}]').append(record)
                    config = root.find('.//Tag[@Name="RecordWriteControl"]//MessageParameters')
                    config.attrib.update(LocalElement='RecordSource[0]', RemoteElement='RecordSource[1]', RequestedLength='2')
                    member = root.find('.//Tag[@Name="MemberWriteControl"]//MessageParameters')
                    member.set('LocalElement', 'RecordSource[0].Quality.Value')

                engine = self.engine(configure)
                self.assertEqual(engine.blockers, [])
                memory = engine.memory
                before = copy.deepcopy(memory.read('RecordSource'))
                memory.write('SendRecord', True)
                for _ in range(3):
                    engine.step()
                if unknown:
                    self.assertEqual(memory.read('RecordSource'), before)
                    self.assert_flags(engine, 'RecordWriteControl', DN=False, ER=True, ERR=3, DN_LEN=0)
                else:
                    self.assertEqual(memory.read('RecordSource'), [before[0], before[0], before[1]])
                    self.assert_flags(engine, 'RecordWriteControl', DN=True, ER=False, DN_LEN=32)

    def test_record_write_checks_nested_access_and_exact_declared_type(self):
        for different_type in (False, True):
            with self.subTest(different_type=different_type):
                def configure(root):
                    if different_type:
                        source_type = root.find('.//DataType[@Name="MessageRecord"]')
                        other = copy.deepcopy(source_type)
                        other.set('Name', 'OtherRecord')
                        root.find('.//DataTypes').append(other)
                        echo = root.find('.//Tag[@Name="RecordEcho"]')
                        echo.set('DataType', 'OtherRecord')
                        echo.find('Data/Structure').set('DataType', 'OtherRecord')
                    else:
                        member = root.find('.//DataType[@Name="MessageQuality"]//Member[@Name="Code"]')
                        member.set('ExternalAccess', 'Read Only')

                engine = self.engine(configure)
                self.assertEqual(engine.blockers, [])
                memory = engine.memory
                before = copy.deepcopy(memory.read('RecordEcho'))
                memory.write('SendRecord', True)
                for _ in range(3):
                    engine.step()
                self.assertEqual(memory.read('RecordEcho'), before)
                self.assert_flags(engine, 'RecordWriteControl', DN=False, ER=True, ERR=0xFC if different_type else 0x0F)
                self.assert_flags(engine, 'Program:MainProgram.RecordReadControl', DN=True, ER=False)

    def test_record_payload_cap_blocks_before_queueing(self):
        def configure(root):
            root.find('.//DataType[@Name="MessageRecord"]//Member[@Name="Samples"]').set('Dimension', '4096')
            root.find('.//Tag[@Name="RecordWriteControl"]//MessageParameters').set('RequestedLength', '5')

        engine = self.engine(configure)
        self.assertTrue(any('record transfer exceeds 32768' in item for item in engine.blockers))
        self.assert_flags(engine, 'RecordWriteControl', REQ_LEN=0)

    def test_member_messages_capture_addresses_and_change_only_selected_fields(self):
        engine = self.engine()
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        prefix = 'Program:MainProgram.'
        control = prefix + 'MemberReadControl'
        memory.write('SendMembers', True)
        engine.step()
        self.assert_flags(engine, control, EW=True, REQ_LEN=2)
        self.assert_flags(engine, 'MemberWriteControl', EW=True, REQ_LEN=2)
        memory.write(control + '.LocalIndex', 1)
        memory.write(control + '.RemoteElement', 'RecordEcho.Samples[0]')
        memory.write('RecordSource.Quality.Value', 3.25)
        engine.step()
        engine.step()
        self.assertEqual(memory.read(prefix + 'RecordInbox.Samples'), [12, -3])
        self.assertEqual(memory.read(prefix + 'RecordInbox.Batch'), 0)
        self.assertEqual(memory.read('RecordEcho.Quality'), {'Value': 3.25, 'Code': 0})
        self.assert_flags(engine, control, DN=True, ER=False, DN_LEN=2)
        self.assert_flags(engine, 'MemberWriteControl', DN=True, ER=False, DN_LEN=2)

        memory.write('SendMembers', False)
        memory.write(control + '.LocalIndex', 0)
        engine.step()
        memory.write('SendMembers', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(memory.read(prefix + 'RecordInbox.Samples'), [0, 0])
        self.assert_flags(engine, control, DN=True, ER=False)

    def test_member_span_stays_inside_selected_record_array_element(self):
        def configure(root):
            tag = root.find('.//Tag[@Name="RecordSource"]')
            tag.set('Dimensions', '2')
            data = tag.find('Data')
            example = data[0]
            data.remove(example)
            array = ET.SubElement(data, 'Array', DataType='MessageRecord', Dimensions='2')
            for index in range(2):
                record = copy.deepcopy(example)
                record.find('StructureMember/DataValueMember[@Name="Value"]').set('Value', str(2.5 + index))
                ET.SubElement(array, 'Element', Index=f'[{index}]').append(record)
            write = root.find('.//Tag[@Name="MemberWriteControl"]//MessageParameters')
            write.set('LocalElement', 'RecordSource[1].Quality.Value')
            read = root.find('.//Tag[@Name="MemberReadControl"]//MessageParameters')
            read.set('RemoteElement', 'RecordSource[1].Samples[1]')

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        memory.write('SendMembers', True)
        for _ in range(3):
            engine.step()
        self.assertEqual(memory.read('RecordEcho.Quality.Value'), 3.5)
        self.assertEqual(memory.read('Program:MainProgram.RecordInbox.Samples'), [0, 0])
        self.assert_flags(engine, 'Program:MainProgram.MemberReadControl', DN=False, ER=True, ERR=5, DN_LEN=0)

    def test_remote_member_access_applies_to_selected_members_and_ancestors(self):
        for access in ('Read Only', 'None'):
            with self.subTest(access=access):
                def configure(root):
                    quality = root.find('.//DataType[@Name="MessageRecord"]//Member[@Name="Quality"]')
                    quality.set('ExternalAccess', access)
                    read = root.find('.//Tag[@Name="MemberReadControl"]//MessageParameters')
                    read.attrib.update(LocalElement='RecordInbox.Quality.Value',
                                       RemoteElement='RecordSource.Quality.Value', RequestedLength='1')
                    content = root.find('.//RLLContent')
                    for number in ('15', '16'):
                        content.remove(content.find(f'Rung[@Number="{number}"]'))

                engine = self.engine(configure)
                self.assertEqual(engine.blockers, [])
                memory = engine.memory
                memory.write('SendMembers', True)
                for _ in range(3):
                    engine.step()
                readable = access == 'Read Only'
                self.assertEqual(memory.read('Program:MainProgram.RecordInbox.Quality.Value'), 2.5 if readable else 0.0)
                self.assertEqual(memory.read('RecordEcho.Quality.Value'), 0.0)
                self.assert_flags(engine, 'Program:MainProgram.MemberReadControl',
                                  DN=readable, ERR=0 if readable else 0x0F)
                self.assert_flags(engine, 'MemberWriteControl', DN=False, ER=True, ERR=0x0F)

    def test_string_format_and_msg_preserve_escaped_bytes_and_report_full_length(self):
        def configure(root):
            root.find('.//Tag[@Name="TextSource"]/Data').text = "'GO$FF$00!'"

        engine = self.engine(configure)
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        expected = {'LEN': 5, 'DATA': [71, 79, -1, 0, 33] + [0] * 77}
        self.assertEqual(memory.read('TextSource'), expected)
        memory.write('SendText', True)
        engine.step()
        self.assert_flags(engine, 'TextWriteControl', EW=True, REQ_LEN=44)
        self.assert_flags(engine, 'Program:MainProgram.TextReadControl', EW=True, REQ_LEN=44)
        engine.step()
        self.assertEqual(memory.string('TextEcho'), '')
        engine.step()
        self.assertEqual(memory.read('TextEcho'), expected)
        self.assertEqual(memory.read('Program:MainProgram.TextInbox'), expected)
        self.assert_flags(engine, 'TextWriteControl', DN=True, ER=False, DN_LEN=44)
        self.assert_flags(engine, 'Program:MainProgram.TextReadControl', DN=True, ER=False, DN_LEN=44)

    def test_string_format_rejects_inconsistent_length(self):
        def configure(root):
            root.find('.//Tag[@Name="TextSource"]/Data').set('Length', '4')

        self.assertTrue(any('String data does not match its Length' in item for item in self.engine(configure).blockers))

    def test_string_array_copies_unknown_tail_but_rejects_unknown_active_bytes(self):
        for unknown_active in (False, True):
            with self.subTest(unknown_active=unknown_active):
                def configure(root):
                    tag = root.find('.//Tag[@Name="TextSource"]')
                    tag.set('Dimensions', '3')
                    data = tag.find('Data')
                    data.clear()
                    data.set('Format', 'Decorated')
                    array = ET.SubElement(data, 'Array', DataType='STRING', Dimensions='3')
                    for index, byte in enumerate((65, 66, 67)):
                        element = ET.SubElement(array, 'Element', Index=f'[{index}]')
                        string = ET.SubElement(element, 'Structure', DataType='STRING')
                        length = 2 if unknown_active and index == 1 else 1
                        ET.SubElement(string, 'DataValueMember', Name='LEN', DataType='DINT', Value=str(length))
                        backing = ET.SubElement(string, 'ArrayMember', Name='DATA', DataType='SINT', Dimensions='82')
                        ET.SubElement(backing, 'Element', Index='[0]', Value=str(byte))
                        ET.SubElement(backing, 'Element', Index='[81]', Value=str(-index - 1))
                    config = root.find('.//Tag[@Name="TextWriteControl"]//MessageParameters')
                    config.attrib.update(LocalElement='TextSource[0]', RemoteElement='TextSource[1]', RequestedLength='2')

                engine = self.engine(configure)
                self.assertEqual(engine.blockers, [])
                memory = engine.memory
                before = copy.deepcopy(memory.read('TextSource'))
                memory.write('SendText', True)
                for _ in range(3):
                    engine.step()
                if unknown_active:
                    self.assertEqual(memory.read('TextSource'), before)
                    self.assert_flags(engine, 'TextWriteControl', DN=False, ER=True, ERR=3, DN_LEN=0)
                else:
                    self.assertEqual(memory.read('TextSource'), [before[0], before[0], before[1]])
                    self.assertEqual(memory.string('TextSource[2]'), 'B')
                    self.assert_flags(engine, 'TextWriteControl', DN=True, ER=False, DN_LEN=88)

    def test_string_family_uses_declared_capacity_type_and_member_access(self):
        for case in ('matching', 'different', 'read_only'):
            with self.subTest(case=case):
                def configure(root):
                    types = root.find('./Controller/DataTypes')
                    label = ET.SubElement(types, 'DataType', Name='Label16', Family='StringFamily', Class='User')
                    members = ET.SubElement(label, 'Members')
                    ET.SubElement(members, 'Member', Name='LEN', DataType='DINT', Dimension='0')
                    data = ET.SubElement(members, 'Member', Name='DATA', DataType='SINT', Dimension='16')
                    if case == 'read_only':
                        data.set('ExternalAccess', 'Read Only')
                    for name in ('TextSource', 'TextInbox', 'TextEcho'):
                        root.find(f'.//Tag[@Name="{name}"]').set('DataType', 'Label16')
                    if case == 'different':
                        other = copy.deepcopy(label)
                        other.set('Name', 'OtherLabel16')
                        types.append(other)
                        root.find('.//Tag[@Name="TextEcho"]').set('DataType', 'OtherLabel16')

                engine = self.engine(configure)
                self.assertEqual(engine.blockers, [])
                memory = engine.memory
                memory.write('SendText', True)
                for _ in range(3):
                    engine.step()
                self.assertEqual(memory.string('Program:MainProgram.TextInbox'), 'READY')
                self.assertEqual(len(memory.read('Program:MainProgram.TextInbox.DATA')), 16)
                self.assert_flags(engine, 'Program:MainProgram.TextReadControl', DN=True, REQ_LEN=10, DN_LEN=10)
                if case == 'matching':
                    self.assertEqual(memory.string('TextEcho'), 'READY')
                    self.assert_flags(engine, 'TextWriteControl', DN=True, DN_LEN=10)
                else:
                    self.assertEqual(memory.string('TextEcho'), '')
                    self.assert_flags(engine, 'TextWriteControl', DN=False, ER=True, ERR=0xFC if case == 'different' else 0x0F)

    def test_queue_exhaustion_waits_and_retries_on_a_false_rung(self):
        engine = self.engine()
        memory = engine.memory
        memory.write('SendRead', True)
        memory.write('SendWrite', True)
        with patch('logixlab.ladder_message.MAX_PENDING', 1):
            engine.step()
            self.assert_flags(engine, 'ReadControl', EW=True, ER=False)
            self.assert_flags(engine, 'WriteControl', FLAGS=0x80, ERR=0)
            memory.write('SendWrite', False)
            engine.step()
            self.assert_flags(engine, 'WriteControl', FLAGS=0x80, ERR=0)
            engine.step()
            self.assert_flags(engine, 'ReadControl', DN=True)
            self.assert_flags(engine, 'WriteControl', FLAGS=0x84, ERR=0)
            self.assertEqual(memory.read('VirtualValue'), 17)
            engine.step()
            self.assert_flags(engine, 'WriteControl', FLAGS=0xC0, ERR=0)
            engine.step()
            self.assert_flags(engine, 'WriteControl', FLAGS=0x20, ERR=0)
            self.assertEqual(memory.read('VirtualValue'), 42)

    def test_seventeenth_message_waits_and_captures_settings_at_admission(self):
        engine = self.engine(add_message_burst)
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        control = 'BurstControl17'
        memory.write('SendBurst', True)
        memory.write(f'{control}.UnconnectedTimeout', 1)
        engine.step()
        self.assertEqual(len(engine._messages), 16)
        for number in range(1, 17):
            self.assert_flags(engine, f'BurstControl{number}', FLAGS=0x84)
        self.assert_flags(engine, control, FLAGS=0x80, ERR=0)
        memory.write('SendBurst', False)
        memory.write(f'{control}.RemoteElement', 'AlternateValue')
        memory.write(f'{control}.UnconnectedTimeout', 30_000_000)
        engine.step()
        self.assert_flags(engine, control, FLAGS=0x84, ERR=0)
        memory.write(f'{control}.RemoteElement', 'VirtualValue')
        memory.write(f'{control}.UnconnectedTimeout', 1)
        engine.step()
        self.assert_flags(engine, control, FLAGS=0xC0)
        self.assertEqual(memory.read('BurstValues'), [17] * 16 + [0])
        engine.step()
        self.assert_flags(engine, control, FLAGS=0x20)
        self.assertEqual(memory.read('BurstValues'), [17] * 16 + [64])
        engine.step()
        self.assertEqual(engine._messages, {})

    def test_throttled_message_can_be_cancelled_or_cleared_by_prescan(self):
        for prescan in (False, True):
            with self.subTest(prescan=prescan):
                engine = self.engine(add_message_burst)
                memory = engine.memory
                control = 'BurstControl17'
                memory.write('SendBurst', True)
                engine.step()
                self.assert_flags(engine, control, FLAGS=0x80)
                memory.write('SendBurst', False)
                if prescan:
                    engine.enter_run()
                else:
                    memory.write(f'{control}.FLAGS.8', True)
                for _ in range(3):
                    engine.step()
                self.assert_flags(engine, control, FLAGS=0 if prescan else 0x10,
                                  ERR=0 if prescan else 0xFE, DN_LEN=0)
                self.assertEqual(memory.read('BurstValues[16]'), 0)
                self.assertEqual(engine._messages, {})

    def test_unqualified_message_forms(self):
        self.assertTrue(self.engine(mode='routine', routine='MainProgram/Main').blockers)
        for name, value in [('ConnectionPath', '2,192.0.2.20'), ('ConnectedFlag', '1'),
                            ('RequestedLength', '65'), ('LocalElement', 'ReadValue[1]')]:
            with self.subTest(name=name, value=value):
                def configure(root):
                    root.find('.//Tag[@Name="ReadControl"]//MessageParameters').set(name, value)

                self.assertTrue(any('MSG' in item for item in self.engine(configure).blockers))
