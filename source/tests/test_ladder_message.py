"""Bounded THIS message lifecycle, simulated transfers and scan rollback."""
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine

SAMPLE = Path(__file__).resolve().parents[1] / 'samples/MessageLab.L5X'


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
            rung = ET.SubElement(root.find('.//RLLContent'), 'Rung', Number='11', Type='N')
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
            rung = ET.SubElement(root.find('.//RLLContent'), 'Rung', Number='11', Type='N')
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
                                  (field + '.LEN', 83, 0x05), (field, 'SendRead', 0xFC)]:
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
            rung = ET.SubElement(content, 'Rung', Number='11', Type='N')
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
                self.assert_flags(engine, 'WriteControl', EN=True, ST=True, DN=False, ER=False)
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

        self.assertTrue(any('directly named controller MESSAGE' in item
                            for item in self.engine(use_as_control).blockers))

    def test_queue_exhaustion_and_unqualified_forms(self):
        engine = self.engine()
        engine.memory.write('SendRead', True)
        engine.memory.write('SendWrite', True)
        with patch('logixlab.ladder_message.MAX_PENDING', 1):
            engine.step()
        self.assert_flags(engine, 'ReadControl', EW=True, ER=False)
        self.assert_flags(engine, 'WriteControl', EW=False, EN=True, ER=True, ERR=0x02)
        self.assertTrue(self.engine(mode='routine', routine='MainProgram/Main').blockers)
        for name, value in [('ConnectionPath', '2,192.0.2.20'), ('ConnectedFlag', '1'),
                            ('RequestedLength', '65'), ('LocalElement', 'ReadValue[1]')]:
            with self.subTest(name=name, value=value):
                def configure(root):
                    root.find('.//Tag[@Name="ReadControl"]//MessageParameters').set(name, value)

                self.assertTrue(any('MSG' in item for item in self.engine(configure).blockers))
