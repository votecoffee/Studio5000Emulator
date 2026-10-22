"""Disabled-clock state is complete but never evidence of PTP measurements."""
import copy
import struct
import unittest
from unittest.mock import patch

from logixlab import __version__, software_clock
from logixlab.ethernetip import Session
from logixlab.time_sync import TimeSync
from tools.time_sync_inventory import decode_attribute_list
import test_software_clock as clocks


class InactiveClockTests(unittest.TestCase):
    setUp=clocks.SoftwareClockTests.setUp
    tearDown=clocks.SoftwareClockTests.tearDown
    send=clocks.SoftwareClockTests.send

    def disable(self):self.app.engine.project.time_sync=TimeSync(False,128,128)
    def read(self,attr):return self.send(path=bytes.fromhex('2043240130')+bytes((attr,)))
    def listing(self,order,limit=480):
        raw=bytes.fromhex('030220432401')+struct.pack('<'+'H'*(len(order)+1),len(order),*order)
        return self.endpoint.router.handle(raw,Session(),limit=limit)

    def test_full_upload_list_has_exact_framing_and_one_time_snapshot(self):
        self.disable();order=(*range(1,29),102,103,104,105)
        timestamp=1_700_000_000_123_456_789
        with patch('logixlab.software_clock.time.time_ns',return_value=timestamp) as clock:
            response=self.listing(order,2048)
        clock.assert_called_once_with()
        self.assertEqual(response[:4],bytes.fromhex('83000000'))
        rows=decode_attribute_list(response,order,include_payloads=True)['attributes']
        self.assertTrue(all(row['status']==0 for row in rows))
        values={r['attribute']:bytes.fromhex(r['data_hex']) for r in rows}
        for attr,width in ((5,8),(6,8),(7,8),(8,24),(9,16),(18,1),(19,2),(20,4),(27,2)):
            self.assertEqual(values[attr],bytes(width))
        self.assertEqual(values[2],b'\0');self.assertEqual(values[11],bytes(2))
        self.assertEqual(struct.unpack('<qq',values[28]),(0,timestamp//1000))

    def test_partial_reply_returns_only_whole_prefix_records_and_followup_completes(self):
        self.disable();order=(*range(1,29),102,103,104,105)
        for limit in (452,480,508):
            with self.subTest(limit=limit):
                pending=order;returned=[];requests=0
                while pending:
                    with patch('logixlab.software_clock.time.time_ns',return_value=1_700_000_000_123_456_789):
                        response=self.listing(pending,limit)
                    self.assertLessEqual(len(response),limit)
                    decoded=decode_attribute_list(response,pending,include_payloads=True)
                    self.assertTrue(all(row['status']==0 for row in decoded['attributes']))
                    returned.extend(row['attribute'] for row in decoded['attributes'])
                    pending=tuple(decoded['remaining_attributes']);requests+=1
                    self.assertLessEqual(requests,3)
                self.assertEqual(returned,list(order))
                self.assertEqual(requests,2 if limit==452 else 1)

    def test_partial_counts_errors_duplicates_and_exact_size_boundary(self):
        self.disable();order=(5,999,5)
        response=self.listing(order,22)
        first=decode_attribute_list(response,order,include_payloads=True)
        self.assertEqual(response[:4],bytes.fromhex('83000600'))
        self.assertEqual(len(response),22)
        self.assertEqual([row['attribute'] for row in first['attributes']],[5,999])
        self.assertEqual([row['status'] for row in first['attributes']],[0,20])
        self.assertEqual(first['remaining_attributes'],[5])
        self.assertEqual(self.listing((5,),17),bytes.fromhex('83001b00'))
        final=decode_attribute_list(self.listing((5,),18),(5,))
        self.assertEqual(final['status'],0)
        mixed=decode_attribute_list(self.listing((999,5),22),(999,5))
        self.assertEqual(mixed['status'],10)

    def test_vendor_aggregates_share_local_identity_and_unassigned_port(self):
        self.disable();identity=self.read(10)[4:12]
        self.assertNotEqual(identity,bytes(8))
        def text(raw):return bytes((len(raw),))+raw
        strings=(b'Studio5000Emulator',b'LogixLab',b'',b'',b'',__version__.encode())
        self.assertEqual(self.read(102)[4:],identity+bytes(2))
        self.assertEqual(self.read(103)[4:],identity+bytes(6)+b''.join(text(s) for s in strings)+bytes(6))
        self.assertEqual(self.read(104)[4:],identity+bytes(9))
        self.assertEqual(self.read(105)[4:12],identity)
        info=self.app.engine.project.time_sync.description(instance_id=self.app.instance_id)['software_clock']
        self.assertEqual(info['clock_type'],0)
        self.assertIsNone(info['manufacturer_oui'])
        self.assertEqual(info['inactive_dataset']['attributes'],list(software_clock.INACTIVE_ATTRIBUTES))
        for field in ('measurement_valid','master_assigned','parent_assigned',
                      'manufacturer_identity_assigned','profile_assigned'):
            self.assertFalse(info['inactive_dataset'][field])
        self.assertFalse(info['ptp_engine']);self.assertFalse(info['synchronized'])

    def test_only_explicit_false_enables_the_inactive_model(self):
        for enabled in (True,None,0,1,'false','',[]):
            self.assertEqual(software_clock.inactive_attributes(self.app.instance_id,enabled),{})
        for enabled in (True,None):
            self.app.engine.project.time_sync=TimeSync(enabled,128,128)
            for attr in software_clock.INACTIVE_ATTRIBUTES:self.assertEqual(self.read(attr)[2],20)
        self.disable()
        self.assertEqual(self.read(5)[2],0)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.read(5)[2],20)

    def test_bad_identity_does_not_produce_an_assigned_vendor_record(self):
        self.disable()
        for instance in (None,42,'A'*32,'z'*32,'a'*31):
            with patch.object(self.app,'instance_id',instance):
                for attr in (102,103,104):self.assertEqual(self.read(attr)[2],20)
                self.assertEqual(self.read(8)[4:],bytes(24))

    def test_vendor_revision_validation_is_shared_with_standard_description(self):
        self.disable()
        for version in ('x'*31,'bad\0version','bad\ud800version','a;b'):
            with patch('logixlab.software_clock.__version__',version):
                self.assertEqual(self.read(103)[2],20)
                self.assertEqual(self.read(102)[2],0);self.assertEqual(self.read(104)[2],0)
        with patch('logixlab.software_clock.__version__','é'*30):
            expected=('é'*30).encode('utf8')
            self.assertEqual(self.read(103)[4:][-67:],bytes((60,))+expected+bytes(6))

    def test_inactive_only_lists_are_static_and_duplicate_order_is_preserved(self):
        self.disable();order=(104,5,103,8,104,5,999)
        with patch('logixlab.software_clock.time.time_ns',side_effect=AssertionError('Static dataset')):
            response=self.send(3,bytes.fromhex('20432401'),struct.pack('<8H',7,*order))
        rows=decode_attribute_list(response,order,include_payloads=True)['attributes']
        self.assertEqual([r['status'] for r in rows],[0,0,0,0,0,0,20])
        self.assertEqual(rows[0]['data_hex'],rows[4]['data_hex'])
        self.assertEqual(rows[1]['data_hex'],rows[5]['data_hex'])

    def test_read_and_denied_writes_preserve_model_source_and_audit(self):
        self.disable();before=copy.deepcopy(self.app.state());source=self.app.engine.project.path.read_bytes()
        for attr in software_clock.INACTIVE_ATTRIBUTES:
            path=bytes.fromhex('2043240130')+bytes((attr,))
            self.assertEqual(self.send(0x10,path,b'\0')[2],8)
            self.assertEqual(self.send(4,bytes.fromhex('20432401'),struct.pack('<HH',1,attr)+b'\0')[2],8)
            self.assertEqual(self.send(path=path,data=b'\0')[2],0x15)
            self.assertEqual(self.read(attr)[2],0)
        after=self.app.state()
        for key in ('tags','controller','routines','tasks','scan','ms','routine_edits'):
            self.assertEqual(before[key],after[key])
        self.assertEqual(before['connectivity']['controller_change_detection'],after['connectivity']['controller_change_detection'])
        self.assertEqual(self.app.engine.project.path.read_bytes(),source)

    def test_api_lists_only_currently_available_clock_fields_without_sampling(self):
        self.disable();self.endpoint.start()
        with patch('logixlab.software_clock.time.time_ns',side_effect=AssertionError('State is static')):
            state=self.app.state()['connectivity']['time_sync']
        self.assertEqual(state['available_attributes'],[1,2,*range(5,28),102,103,104,105])
        self.assertEqual(state['dynamic_attributes'],[3,4,28])
        self.assertTrue(state['software_clock']['inactive_dataset']['available'])
        self.app.engine.project.time_sync=TimeSync(True,128,128)
        self.assertFalse(self.app.state()['connectivity']['time_sync']['software_clock']['inactive_dataset']['available'])


if __name__=='__main__':unittest.main()
