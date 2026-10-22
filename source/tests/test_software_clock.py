"""Local UTC reads stay coherent without asserting PTP synchronization."""
import copy
import struct
import tempfile
import unittest
from unittest.mock import patch

from logixlab import software_clock
from logixlab import __version__
from logixlab.ethernetip import Endpoint, Session
from logixlab.server import Application


class SoftwareClockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.endpoint = Endpoint(self.app, 0, True, 'logix-v35-l85e')
        self.app.endpoint = self.endpoint

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def send(self, service=0x0E, path=bytes.fromhex('204324013003'), data=b''):
        return self.endpoint.router.handle(bytes((service, len(path)//2))+path+data, Session())

    def test_epoch_large_integer_and_signed_64_bit_boundary_preserve_exact_units(self):
        for timestamp in (0, 999, 1000, 1_700_000_000_123_456_789, 0x7FFFFFFFFFFFFFFF):
            with self.subTest(timestamp=timestamp), patch('logixlab.software_clock.time.time_ns', return_value=timestamp):
                values = software_clock.attributes(read_time=True)
                self.assertEqual(struct.unpack('<q', values[3])[0], timestamp//1000)
                self.assertEqual(struct.unpack('<q', values[4])[0], timestamp)
                self.assertEqual(struct.unpack('<qq', values[28]), (0, timestamp//1000))
                self.assertEqual(len(values[3]), 8)
                self.assertEqual(len(values[4]), 8)

    def test_invalid_or_unrepresentable_host_time_is_unavailable_without_fallback_zero(self):
        for timestamp in (-1, 0x8000000000000000*1000, 1.5, True, None, '1000'):
            with self.subTest(timestamp=timestamp), patch('logixlab.software_clock.time.time_ns', return_value=timestamp):
                values = software_clock.attributes(read_time=True)
                self.assertNotIn(3, values); self.assertNotIn(4, values); self.assertNotIn(28, values)
                self.assertEqual(values[2], b'\0')
                self.assertEqual(values[11], bytes(2))
        for error in (OSError('clock unavailable'), OverflowError('range'), ValueError('clock unavailable')):
            with patch('logixlab.software_clock.time.time_ns', side_effect=error):
                self.assertEqual(self.send(), bytes.fromhex('8e001400'))

    def test_nanosecond_overflow_does_not_hide_representable_microseconds(self):
        for timestamp in (0x8000000000000000, 0x7FFFFFFFFFFFFFFF*1000+999):
            with self.subTest(timestamp=timestamp), patch('logixlab.software_clock.time.time_ns', return_value=timestamp):
                values = software_clock.attributes(read_time=True)
                self.assertEqual(struct.unpack('<q', values[3])[0], timestamp//1000)
                self.assertEqual(struct.unpack('<qq', values[28]), (0, timestamp//1000))
                self.assertNotIn(4, values)
                self.assertEqual(self.send(path=bytes.fromhex('204324013004')), bytes.fromhex('8e001400'))

    def test_single_reads_and_duplicate_list_fields_use_one_clock_snapshot(self):
        timestamp = 1_700_000_000_123_456_789
        with patch('logixlab.software_clock.time.time_ns', return_value=timestamp) as clock:
            self.assertEqual(self.send(), bytes.fromhex('8e000000')+struct.pack('<q', timestamp//1000))
            self.assertEqual(self.send(path=bytes.fromhex('204324013004')),
                             bytes.fromhex('8e000000')+struct.pack('<q', timestamp))
            self.assertEqual(clock.call_count, 2)
        order = (4, 3, 4)
        expected = (bytes.fromhex('83000000030004000000')+struct.pack('<q', timestamp)+
                    bytes.fromhex('03000000')+struct.pack('<q', timestamp//1000)+
                    bytes.fromhex('04000000')+struct.pack('<q', timestamp))
        with patch('logixlab.software_clock.time.time_ns', side_effect=(timestamp, timestamp+1000)) as clock:
            self.assertEqual(self.send(3, bytes.fromhex('20432401'), struct.pack('<4H', 3, *order)), expected)
            clock.assert_called_once_with()

    def test_empty_ptp_ports_have_exact_counted_structures_and_no_network_activity(self):
        with patch('logixlab.software_clock.time.time_ns', side_effect=AssertionError('Unneeded clock read')):
            self.assertEqual(self.send(path=bytes.fromhex('204324013002')), bytes.fromhex('8e00000000'))
            for attr in (11, 12, 13, 14, 15, 24, 25, 26):
                self.assertEqual(self.send(path=bytes.fromhex('2043240130')+bytes((attr,))), bytes.fromhex('8e0000000000'))
        info = self.app.engine.project.time_sync.description()['software_clock']
        self.assertEqual(info['ptp_port_count'], 0)
        for name in ('synchronized', 'ptp_engine', 'accuracy_claimed', 'set_time', 'master_offset_measurements', 'hardware_clock'):
            self.assertFalse(info[name])

    def test_system_time_and_offset_single_read_uses_the_host_clock_without_a_master(self):
        timestamp = 1_700_000_000_123_456_789
        before = copy.deepcopy(self.app.engine.memory.values)
        with patch('logixlab.software_clock.time.time_ns', return_value=timestamp) as clock:
            self.assertEqual(self.send(path=bytes.fromhex('20432401301c')),
                             bytes.fromhex('8e000000')+struct.pack('<qq', 0, timestamp//1000))
            clock.assert_called_once_with()
        info = self.app.engine.project.time_sync.description()['software_clock']
        self.assertEqual(info['system_time_offset_microseconds'], 0)
        self.assertFalse(info['master_offset_measurements'])
        self.assertEqual(self.app.engine.memory.values, before)
        self.assertEqual(self.app.engine.scan_count, 0)

    def test_system_time_and_offset_duplicates_share_microsecond_and_nanosecond_snapshot(self):
        timestamp = 1_700_000_000_123_456_789
        order = (28, 4, 3, 28)
        values = {28: struct.pack('<qq', 0, timestamp//1000),
                  4: struct.pack('<q', timestamp), 3: struct.pack('<q', timestamp//1000)}
        expected = bytes.fromhex('83000000')+struct.pack('<H', len(order))
        expected += b''.join(struct.pack('<HH', attr, 0)+values[attr] for attr in order)
        with patch('logixlab.software_clock.time.time_ns', side_effect=(timestamp, timestamp+9999)) as clock:
            self.assertEqual(self.send(3, bytes.fromhex('20432401'),
                                       struct.pack('<5H', len(order), *order)), expected)
            clock.assert_called_once_with()

    def test_system_time_and_offset_failure_and_setters_do_not_invent_or_change_clock(self):
        path = bytes.fromhex('20432401301c')
        with patch('logixlab.software_clock.time.time_ns', side_effect=OSError('unavailable')):
            self.assertEqual(self.send(path=path), bytes.fromhex('8e001400'))
            response = self.send(3, bytes.fromhex('20432401'), struct.pack('<4H', 3, 2, 28, 11))
            self.assertEqual(response, bytes.fromhex('83000a00030002000000001c0014000b0000000000'))
        with patch('logixlab.software_clock.time.time_ns', side_effect=AssertionError('Invalid reads cannot sample')):
            self.assertEqual(self.send(path=path, data=b'\0')[2], 0x15)
            self.assertEqual(self.send(0x10, path, bytes(16))[2], 8)
            self.assertEqual(self.send(4, bytes.fromhex('20432401'),
                                       struct.pack('<2H', 1, 28)+bytes(16))[2], 8)

    def test_static_unknown_class_and_malformed_or_mutating_queries_do_not_sample_clock(self):
        with patch('logixlab.software_clock.time.time_ns', side_effect=AssertionError('Unneeded clock read')):
            self.assertEqual(self.send(path=bytes.fromhex('204324003001')), bytes.fromhex('8e0000000100'))
            self.assertEqual(self.send(path=bytes.fromhex('204324013005')), bytes.fromhex('8e001400'))
            self.assertEqual(self.send(3, bytes.fromhex('20432401'), bytes.fromhex('01000b00')), bytes.fromhex('8300000001000b0000000000'))
            for service, path, data in ((0x0E, bytes.fromhex('204324013003'), b'\0'),
                    (3, bytes.fromhex('20432401'), b''), (3, bytes.fromhex('20432401'), bytes(2)),
                    (3, bytes.fromhex('20432401'), bytes.fromhex('02000300')),
                    (0x10, bytes.fromhex('204324013003'), bytes(8)),
                    (4, bytes.fromhex('20432401'), bytes.fromhex('01000300')+bytes(8)),
                    (1, bytes.fromhex('20432401'), b'')):
                self.assertNotEqual(self.send(service, path, data)[2], 0)

    def test_clock_failure_preserves_known_fields_in_a_mixed_list(self):
        with patch('logixlab.software_clock.time.time_ns', side_effect=OSError('unavailable')):
            self.assertEqual(self.send(3, bytes.fromhex('20432401'), struct.pack('<5H', 4, 2, 3, 11, 4)),
                             bytes.fromhex('83000a0004000200000000030014000b000000000004001400'))

    def test_descriptions_identify_software_with_exact_lengths_and_current_version(self):
        expected={21:b'Studio5000Emulator;LogixLab;',22:(';;'+__version__).encode('utf-8'),23:b''}
        before=copy.deepcopy(self.app.engine.memory.values)
        with patch('logixlab.software_clock.time.time_ns',side_effect=AssertionError('Static descriptions')):
            for attr,text in expected.items():
                response=self.send(path=bytes.fromhex('2043240130')+bytes((attr,)))
                self.assertEqual(response,bytes.fromhex('8e000000')+struct.pack('<I',len(text))+text)
            # No assigned manufacturer OUI or clock hardware identity is known.
            for attr in (19,20,102,103,104):
                self.assertEqual(self.send(path=bytes.fromhex('2043240130')+bytes((attr,))),bytes.fromhex('8e001400'))
        info=self.app.engine.project.time_sync.description()['software_clock']
        self.assertEqual(info['software_version'],__version__)
        self.assertEqual(info['description_attributes'],[21,22,23])
        for key in ('manufacturer_oui','hardware_revision','firmware_revision','serial_number'):
            self.assertIsNone(info[key])
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_description_lists_preserve_duplicates_and_report_only_actual_gaps(self):
        revision=(';;'+__version__).encode('utf-8')
        order=(23,22,5,21,22,20)
        expected=(struct.pack('<HHI',23,0,0)+struct.pack('<HHI',22,0,len(revision))+revision+
                  struct.pack('<HH',5,0x14)+struct.pack('<HHI',21,0,28)+b'Studio5000Emulator;LogixLab;'+
                  struct.pack('<HHI',22,0,len(revision))+revision+struct.pack('<HH',20,0x14))
        with patch('logixlab.software_clock.time.time_ns',side_effect=AssertionError('Static descriptions')):
            response=self.send(3,bytes.fromhex('20432401'),struct.pack('<7H',6,*order))
        self.assertEqual(response,bytes.fromhex('83000a000600')+expected)
        gap=self.endpoint.state()['attribute_gaps'][0]
        self.assertEqual([a['id'] for a in gap['attributes']],[5,20])
        for service,path,data in ((0x10,bytes.fromhex('204324013015'),bytes(4)),
                (4,bytes.fromhex('20432401'),bytes.fromhex('01001500')+bytes(4))):
            self.assertEqual(self.send(service,path,data)[2],8)

    def test_invalid_revision_is_unavailable_and_unicode_lengths_count_bytes(self):
        for revision in ('x'*31,'bad\0version','bad\ud800version'):
            with patch('logixlab.software_clock.__version__',revision):
                self.assertEqual(self.send(path=bytes.fromhex('204324013016')),bytes.fromhex('8e001400'))
                self.assertEqual(self.send(path=bytes.fromhex('204324013017')),bytes.fromhex('8e00000000000000'))
        with patch('logixlab.software_clock.__version__','é'*30):
            data=(';;'+'é'*30).encode('utf-8')
            self.assertEqual(self.send(path=bytes.fromhex('204324013016')),bytes.fromhex('8e000000')+struct.pack('<I',62)+data)

    def test_clock_is_independent_of_source_presence_scan_time_and_host_adjustments(self):
        before = copy.deepcopy(self.app.engine.memory.values)
        timestamp = 1_700_000_000_123_456_789
        self.app.engine.time_ms = 5000
        with patch('logixlab.software_clock.time.time_ns', side_effect=(timestamp, timestamp-1000)):
            first = struct.unpack('<q', self.send()[4:])[0]
            second = struct.unpack('<q', self.send()[4:])[0]
        self.assertEqual(first-second, 1)
        self.assertEqual(self.app.engine.memory.values, before)
        self.assertEqual(self.app.engine.time_ms, 5000)
        self.assertEqual(self.app.engine.scan_count, 0)
        # This authored demo has no TimeSynchronize source declaration.
        self.assertEqual(self.send(path=bytes.fromhex('204324013001')), bytes.fromhex('8e001400'))
        self.assertEqual(self.send(path=bytes.fromhex('204324013002')), bytes.fromhex('8e00000000'))
        info = self.app.engine.project.time_sync.description()['software_clock']
        self.assertTrue(info['scan_time_independent'])
        self.assertTrue(info['host_adjustments_visible'])


if __name__ == '__main__':
    unittest.main()
