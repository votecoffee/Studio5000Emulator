"""Rejected native operations stay bounded and do not reveal request values."""
import copy
import json
import unittest
from logixlab.ethernetip import Path,symbol_path
from logixlab.native_rejections import MAX_REJECTIONS,NativeRejections
import test_native_session as native_tests
from test_signed_messages import request


class NativeRejectionCollectorTests(unittest.TestCase):
    def test_structural_grouping_counts_order_and_copies(self):
        collector=NativeRejections();path=Path(class_id=0xAC,instance=1)
        collector.record(0,4,path,15,'read_only_policy')
        collector.record(0,4,Path(class_id=0x8E,instance=1),15,'read_only_policy')
        collector.record(0,4,path,15,'read_only_policy')
        rows=collector.snapshot(0)
        self.assertEqual((rows[0]['class_id'],rows[0]['count']),(0xAC,2))
        rows[0]['count']=999
        self.assertEqual(collector.snapshot(0)[0]['count'],2)
        self.assertEqual(collector.snapshot(1),[])

    def test_capacity_generation_and_payload_free_symbolic_diagnostics(self):
        collector=NativeRejections();path=Path(symbols=['PrivateTag',123],program_instance=42)
        collector.record(0,0x4D,path,15,'read_only_policy')
        row=collector.snapshot(0)[0]
        self.assertTrue(row['symbolic']);self.assertEqual(row['program_instance'],42)
        self.assertNotIn('PrivateTag',json.dumps(row));self.assertNotIn('payload',row)
        for number in range(MAX_REJECTIONS+2):
            collector.record(1,0x4B,Path(class_id=number,instance=0),15,'read_only_policy')
        self.assertEqual(len(collector.snapshot(1)),MAX_REJECTIONS)
        self.assertEqual(collector.snapshot(0),[])
        collector.record(1,3,None,4,'invalid_request')
        self.assertIsNone(collector.snapshot(1)[0]['class_id'])


class NativeRejectionEndpointTests(unittest.TestCase):
    # Share signed TCP setup helpers, not the other class's test methods.
    setUp=native_tests.NativeSessionTests.setUp
    tearDown=native_tests.NativeSessionTests.tearDown
    cip=native_tests.NativeSessionTests.cip
    begin=native_tests.NativeSessionTests.begin
    signed=native_tests.NativeSessionTests.signed
    bind=native_tests.NativeSessionTests.bind

    def test_rejections_are_visible_without_payloads_and_do_not_change_tags(self):
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        denied=bytes.fromhex('4b03210077072400')
        self.assertEqual(self.signed(4,denied)[2],15)
        self.assertEqual(self.signed(5,denied)[2],15)
        invalid=bytes.fromhex('030420692401207e240001000100')
        self.assertEqual(self.signed(6,invalid)[2],4)
        rows=self.endpoint.state()['native_rejections']
        self.assertEqual(rows[0]['reason'],'invalid_request')
        self.assertEqual((rows[1]['class_id'],rows[1]['service'],rows[1]['count']),(0x777,0x4B,2))
        self.assertEqual(self.endpoint.state(True)['native_rejections'],rows)
        self.assertNotIn('request_hex',json.dumps(rows));self.assertNotIn('response_hex',json.dumps(rows))
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.endpoint.state()['native_rejections'],[])

    def test_bad_mac_never_creates_policy_or_payload_diagnostics(self):
        self.bind()
        raw=request(0x36,bytes.fromhex('4b0220712465'),4)
        self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
        self.assertEqual(self.endpoint.state()['native_rejections'],[])

    def test_symbolic_write_summary_hides_tag_name_and_value(self):
        self.bind();path=symbol_path('PrivateTag')
        payload=b'private-write-value'
        self.assertEqual(self.signed(4,bytes((0x4D,len(path)//2))+path+payload)[2],15)
        row=self.endpoint.state()['native_rejections'][0]
        self.assertTrue(row['symbolic']);self.assertIsNone(row['class_id'])
        text=json.dumps(row)
        self.assertNotIn('PrivateTag',text);self.assertNotIn(payload.decode(),text)


if __name__=='__main__':unittest.main()
