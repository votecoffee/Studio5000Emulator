"""UTC policy and a real elapsed software counter replace no clock hardware."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from logixlab.server import Application
from logixlab.wall_clock import CoordinatedClock, UTC_ZONE, LEGACY_EPOCH_MICROSECONDS
from tools.collection_inventory import decode_attribute_list
import test_wall_clock as clocks


class WallClockPolicyTests(unittest.TestCase):
    setUp=clocks.WallClockTests.setUp
    tearDown=clocks.WallClockTests.tearDown
    send=clocks.WallClockTests.send
    load=clocks.WallClockTests.load

    def test_all_eleven_fields_use_utc_policy_and_one_paired_clock_sample(self):
        self.app.coordinated_clock=CoordinatedClock(1_000_000)
        utc=951827696123456;order=tuple(range(1,12))
        with patch('logixlab.wall_clock.time.time_ns',return_value=utc*1000+999) as wall,\
             patch('logixlab.wall_clock.time.monotonic_ns',return_value=1_123_456) as cst:
            reply=self.send(service=3,data=struct.pack('<12H',11,*order))
        wall.assert_called_once_with();cst.assert_called_once_with()
        self.assertEqual(reply[:4],bytes.fromhex('83000000'))
        rows=decode_attribute_list(reply,order,0x8b,include_payloads=True)['attributes']
        values={row['attribute']:bytes.fromhex(row['data_hex']) for row in rows}
        self.assertTrue(all(row['status']==0 for row in rows))
        self.assertEqual(struct.unpack('<q',values[3])[0]+123,utc)
        self.assertEqual(struct.unpack('<Q',values[1])[0]+LEGACY_EPOCH_MICROSECONDS,utc)
        self.assertEqual(values[6],values[11]);self.assertEqual(values[5],values[7])
        self.assertEqual(struct.unpack('<7I',values[7]),(2000,2,29,12,34,56,123456))
        self.assertEqual(values[8],struct.pack('<I',len(UTC_ZONE))+UTC_ZONE)
        self.assertEqual(values[9],bytes(2));self.assertEqual(values[10],bytes(1))

    def test_duplicate_offsets_share_one_sample_and_do_not_use_legacy_epoch(self):
        self.app.coordinated_clock=CoordinatedClock(0);order=(3,6,3,1,11)
        utc=LEGACY_EPOCH_MICROSECONDS+12345
        with patch('logixlab.wall_clock.time.time_ns',return_value=utc*1000) as wall,\
             patch('logixlab.wall_clock.time.monotonic_ns',return_value=1_000_000) as cst:
            reply=self.send(service=3,data=struct.pack('<6H',5,*order))
        wall.assert_called_once_with();cst.assert_called_once_with()
        rows=decode_attribute_list(reply,order,0x8b,include_payloads=True)['attributes']
        self.assertEqual(rows[0]['data_hex'],rows[2]['data_hex'])
        self.assertEqual(struct.unpack('<q',bytes.fromhex(rows[0]['data_hex']))[0],utc-1000)
        self.assertEqual(struct.unpack('<Q',bytes.fromhex(rows[3]['data_hex']))[0],12345)

    def test_static_settings_and_api_state_sample_neither_clock(self):
        self.endpoint.start()
        with patch('logixlab.wall_clock.time.time_ns',side_effect=AssertionError('No UTC sampling')),\
             patch('logixlab.wall_clock.time.monotonic_ns',side_effect=AssertionError('No CST sampling')):
            for attr in (8,9,10):self.assertEqual(self.send(attr)[2],0)
            info=self.app.state()['connectivity']['wall_clock_time']
        self.assertEqual(info['static_attributes'],[2,4,8,9,10])
        self.assertEqual(info['dynamic_attributes'],[1,3,5,6,7,11])
        self.assertTrue(info['cst_offset']);self.assertTrue(info['timezone_string']);self.assertTrue(info['dst_parameters'])
        self.assertEqual(info['timezone_value'],UTC_ZONE.decode())
        self.assertEqual(info['dst_adjustment_minutes'],0);self.assertFalse(info['apply_dst'])
        self.assertFalse(info['source_extended_timezone_dst_imported'])
        self.assertFalse(info['coordinated_clock']['network_synchronized'])
        self.assertFalse(info['coordinated_clock']['cip_object_exposed'])

    def test_clock_origin_is_per_app_and_survives_project_reload_and_reset(self):
        self.app.coordinated_clock=CoordinatedClock(1_000_000);counter=self.app.coordinated_clock
        self.app.engine.time_ms=900;self.app.engine.scan_count=20
        with patch('logixlab.wall_clock.time.monotonic_ns',return_value=2_000_000):
            self.assertEqual(counter.microseconds(),1000)
        self.load(self.root);self.app.command('reset',{})
        self.assertIs(self.app.coordinated_clock,counter)
        with patch('logixlab.wall_clock.time.monotonic_ns',return_value=4_000_000):
            self.assertEqual(counter.microseconds(),3000)
        with tempfile.TemporaryDirectory() as folder,\
             patch('logixlab.wall_clock.time.monotonic_ns',return_value=4_000_000):
            other=Application(Path(folder))
            try:self.assertEqual(other.coordinated_clock.microseconds(),0)
            finally:other.close()

    def test_wall_clock_steps_adjust_offset_without_rewinding_elapsed_time(self):
        counter=CoordinatedClock(0)
        with patch('logixlab.wall_clock.time.monotonic_ns',side_effect=(1000,2000)),\
             patch('logixlab.wall_clock.time.time_ns',side_effect=(100_000,90_000)):
            first=self.app.engine.project.wall_clock.attributes(read_time=True,coordinated_clock=counter)
            second=self.app.engine.project.wall_clock.attributes(read_time=True,coordinated_clock=counter)
        self.assertEqual(struct.unpack('<q',first[3])[0],99)
        self.assertEqual(struct.unpack('<q',second[3])[0],88)

    def test_bad_start_or_samples_never_fabricate_a_counter_or_offset(self):
        for bad in (None,True,-1,1.5,'1000'):
            with patch('logixlab.wall_clock.time.monotonic_ns',return_value=bad):
                self.assertFalse(CoordinatedClock.start().available)
                self.assertIsNone(CoordinatedClock(0).microseconds())
        for bad in (999,None,True,-1,1.5,'1000',1000+(1<<63)*1000):
            self.app.coordinated_clock=CoordinatedClock(1000)
            with patch('logixlab.wall_clock.time.monotonic_ns',return_value=bad),\
                 patch('logixlab.wall_clock.time.time_ns',return_value=100_000):
                self.assertEqual(self.send(3)[2],20)
                self.assertEqual(self.send(6)[4:],struct.pack('<q',100))
        for error in (OSError('unavailable'),OverflowError('range'),ValueError('invalid')):
            with patch('logixlab.wall_clock.time.monotonic_ns',side_effect=error):
                self.assertFalse(CoordinatedClock.start().available)
                self.assertIsNone(CoordinatedClock(0).microseconds())

    def test_offset_requires_nonnegative_representable_relation_and_valid_wall_clock(self):
        counter=CoordinatedClock(0);wall=self.app.engine.project.wall_clock
        with patch('logixlab.wall_clock.time.monotonic_ns',return_value=101_000),\
             patch('logixlab.wall_clock.time.time_ns',return_value=100_000):
            self.assertNotIn(3,wall.attributes(read_time=True,coordinated_clock=counter))
        with patch('logixlab.wall_clock.time.monotonic_ns',return_value=0),\
             patch('logixlab.wall_clock.time.time_ns',return_value=0x7fffffffffffffff*1000):
            self.assertEqual(wall.attributes(read_time=True,coordinated_clock=counter)[3],struct.pack('<q',0x7fffffffffffffff))
        with patch('logixlab.wall_clock.time.time_ns',side_effect=OSError('unavailable')):
            self.assertEqual(self.send(3)[2],20)
            for attr in (8,9,10):self.assertEqual(self.send(attr)[2],0)
        self.app.coordinated_clock=CoordinatedClock()
        self.assertFalse(wall.description(coordinated_clock=self.app.coordinated_clock)['cst_offset'])

    def test_reads_unknown_fields_and_denied_writes_preserve_source_model_and_audit(self):
        before=copy.deepcopy(self.app.state());source=self.app.engine.project.path.read_bytes()
        origin=self.app.coordinated_clock.origin_ns
        for attr in (3,8,9,10):
            self.assertEqual(self.send(attr)[2],0)
            self.assertEqual(self.send(attr,0x10,b'\0')[2],8)
            self.assertEqual(self.send(service=4,data=struct.pack('<HH',1,attr)+b'\0')[2],8)
            self.assertEqual(self.send(attr,data=b'\0')[2],0x15)
        self.assertEqual(self.send(99)[2],20)
        self.assertEqual(self.app.engine.project.path.read_bytes(),source)
        self.assertEqual(self.app.coordinated_clock.origin_ns,origin)
        after=self.app.state()
        for key in ('tags','controller','scan','ms','routines','tasks','routine_edits'):
            self.assertEqual(before[key],after[key])
        self.assertEqual(before['connectivity']['controller_change_detection'],after['connectivity']['controller_change_detection'])


if __name__=='__main__':unittest.main()
