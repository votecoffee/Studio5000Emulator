"""Local software-clock identity never becomes PTP master or hardware evidence."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from logixlab import software_clock
from logixlab.server import Application
from logixlab.time_sync import TimeSync
from tools.time_sync_inventory import decode_attribute_list
import test_software_clock as clocks


class SoftwareClockIdentityTests(unittest.TestCase):
    setUp=clocks.SoftwareClockTests.setUp
    tearDown=clocks.SoftwareClockTests.tearDown
    send=clocks.SoftwareClockTests.send

    def read(self,attribute):return self.send(path=bytes.fromhex('2043240130')+bytes((attribute,)))

    def test_local_info_and_user_description_share_a_local_identity_and_unknown_quality(self):
        with patch('logixlab.software_clock.time.time_ns',side_effect=AssertionError('Static identity')):
            local=self.read(10);user=self.read(105)
        self.assertEqual(local[:4],bytes.fromhex('8e000000'))
        self.assertEqual(len(local),24)
        self.assertEqual(user,bytes.fromhex('8e000000')+local[4:12]+bytes(2))
        self.assertEqual(local[4]&3,2)
        self.assertEqual(struct.unpack('<6H',local[12:]),(248,254,65535,0,0,160))
        info=self.app.engine.project.time_sync.description(instance_id=self.app.instance_id)['software_clock']
        self.assertEqual(info['clock_identity'],local[4:12].hex())
        self.assertEqual(info['identity_attributes'],[10,105])
        self.assertEqual(info['local_clock_accuracy'],'unknown')
        self.assertEqual(info['local_clock_variance'],'not computed')
        for field in ('utc_offset_valid','time_traceable','frequency_traceable','synchronized','ptp_engine','hardware_clock'):
            self.assertFalse(info[field])
        self.assertIsNone(info['clock_type']);self.assertIsNone(info['manufacturer_oui'])

    def test_identity_survives_source_reload_and_is_distinct_per_app(self):
        first=self.read(10)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.read(10),first)
        with tempfile.TemporaryDirectory() as folder:
            other=Application(Path(folder))
            try:
                identity=software_clock.clock_identity(other.instance_id)
                self.assertNotEqual(identity,first[4:12])
                self.assertEqual(software_clock.identity_attributes(self.app.instance_id)[10],first[4:])
            finally:other.close()

    def test_list_duplicates_share_identity_and_one_time_sample_without_master_substitutes(self):
        order=(105,10,3,5,105,10)
        with patch('logixlab.software_clock.time.time_ns',return_value=1_700_000_000_123_456_789) as clock:
            response=self.send(3,bytes.fromhex('20432401'),struct.pack('<7H',len(order),*order))
        clock.assert_called_once_with()
        rows=decode_attribute_list(response,order,include_payloads=True)['attributes']
        self.assertEqual([r['status'] for r in rows],[0,0,0,20,0,0])
        self.assertEqual(rows[0]['data_hex'],rows[4]['data_hex'])
        self.assertEqual(rows[1]['data_hex'],rows[5]['data_hex'])
        self.assertEqual(rows[0]['data_hex'][:16],rows[1]['data_hex'][:16])
        self.assertEqual(rows[0]['value_bytes'],10);self.assertEqual(rows[1]['value_bytes'],20)

    def test_bad_or_missing_instance_id_leaves_identity_unavailable_without_zero_fallback(self):
        for value in (None,False,42,b'0'*32,'','A'*32,'a'*31,'z'*32,'a'*32+'\0'):
            with self.subTest(value=value),patch.object(self.app,'instance_id',value):
                self.assertIsNone(software_clock.clock_identity(value))
                self.assertEqual(software_clock.identity_attributes(value),{})
                self.assertEqual(self.read(10),bytes.fromhex('8e001400'))
                self.assertEqual(self.read(105),bytes.fromhex('8e001400'))
        self.assertNotEqual(self.read(10)[4:12],bytes(8))

    def test_reads_and_denied_writes_preserve_source_model_audit_and_clock_configuration(self):
        before=copy.deepcopy(self.app.state());source=self.app.engine.project.path.read_bytes()
        with patch('logixlab.software_clock.time.time_ns',side_effect=AssertionError('No clock sampling')):
            for attr,width in ((10,20),(105,10)):
                path=bytes.fromhex('2043240130')+bytes((attr,))
                self.assertEqual(self.send(path=path,data=b'\0')[2],0x15)
                self.assertEqual(self.send(0x10,path,bytes(width))[2],8)
                self.assertEqual(self.send(4,bytes.fromhex('20432401'),struct.pack('<HH',1,attr)+bytes(width))[2],8)
                self.assertEqual(self.read(attr)[2],0)
        after=self.app.state()
        for field in ('tags','controller','routines','tasks','scan','ms','routine_edits'):
            self.assertEqual(before[field],after[field])
        self.assertEqual(self.app.engine.project.path.read_bytes(),source)
        self.assertEqual(before['connectivity']['controller_change_detection'],after['connectivity']['controller_change_detection'])

    def test_imported_ptp_enable_never_changes_identity_or_creates_master_or_ports(self):
        identity=self.read(10)[4:12]
        for enabled in (False,True,None):
            self.app.engine.project.time_sync=TimeSync(enabled,128,128)
            self.assertEqual(self.read(10)[4:12],identity)
            self.assertEqual(self.read(2),bytes.fromhex('8e00000000'))
            self.assertEqual(self.read(11),bytes.fromhex('8e0000000000'))
            for attr in (5,6,7,8,9,18,19,20,27,102,103,104):
                self.assertEqual(self.read(attr)[2],20)

    def test_running_endpoint_state_advertises_the_same_identity_without_sampling_time(self):
        self.endpoint.start()
        with patch('logixlab.software_clock.time.time_ns',side_effect=AssertionError('State polling is static')):
            state=self.app.state()['connectivity']['time_sync']
            local=self.read(10)
        self.assertEqual(state['software_clock']['clock_identity'],local[4:12].hex())
        for attr in (10,105):self.assertIn(attr,state['available_attributes'])
        self.assertFalse(state['software_clock']['ptp_engine'])


if __name__=='__main__':unittest.main()
