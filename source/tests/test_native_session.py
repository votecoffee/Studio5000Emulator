"""Anonymous compatibility with synthetic keys; no vendor identity fixtures."""
import copy
from dataclasses import replace
import hmac
import struct
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

from logixlab import native_session, signed_messages
from logixlab.catalog_revision import CatalogRevision
from logixlab.controller_configuration import ControllerConfiguration
from logixlab.ethernetip import Endpoint
from logixlab.model import ModelError
from logixlab.native_symbols import NativeSymbols, Symbol
from logixlab.native_project import NativeProjectIdentity
from logixlab.server import Application
from test_ethernetip import Client
from test_key_exchange import offer
from test_signed_messages import KEY, request
from test_signed_batches import batch


class NativeSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample': 'ConveyorDemo'})
        self.endpoint = Endpoint(self.app, 0, False, 'logix-v35-l85e', native_read_only=True).start()
        self.app.endpoint = self.endpoint
        self.client = Client(self.endpoint.port)
        self.client.register()

    def tearDown(self):
        self.client.close()
        self.app.close()
        self.tmp.cleanup()

    def cip(self, data):
        status, result = self.client.cip(data)
        self.assertEqual(status, 0)
        return result

    def begin(self):
        original = native_session.NativeSession.begin
        with patch.object(native_session.NativeSession, 'begin', lambda obj, raw: original(obj, raw, nonce=KEY)):
            self.assertEqual(self.cip(b'\x4B\2\x20\x64\x24\1'+offer())[:6], b'\xCB\0\0\0\x80\0')
        result = self.cip(b'\x4C\2\x20\x64\x24\1\x14\0'+bytes(20))
        self.assertEqual(result[:6], b'\xCC\0\0\0\5\0')

    def signed(self, sequence, inner, service=0x36):
        raw = request(service, inner, sequence)
        result = self.cip(raw)
        parsed = signed_messages.verify_response(result, KEY, request=signed_messages.parse_request(raw))
        return parsed.inner

    def bind(self):
        self.begin()
        self.assertEqual(self.signed(1, b'\x5C\2\x20\x8E\x24\1operator', 0x37), b'\xDC\0\0\0')
        context = self.signed(2, bytes.fromhex('4b03210078032401')+b'anonymous-context')
        self.assertEqual(context[:4], b'\xCB\0\0\0')
        self.assertEqual(len(context), 8)
        self.assertEqual(self.signed(3, b'\x63\2\x20\x8E\x24\1'+context[4:]), b'\xE3\0\0\0')

    def test_source_timeline_proposals_are_acknowledged_without_replacing_any_header_field(self):
        identity=NativeProjectIdentity('1'*64,self.app.engine.project.sha256,2,3,4,5,6,0xFFFFFFFF)
        self.app.native_project_identity=identity
        before=copy.deepcopy(self.app.engine.memory.values);header=identity.attributes()
        self.bind();sequence=4
        for value in (1,123,0xFFFFFFFF):
            raw=bytes.fromhex('040220ac240101000a00')+struct.pack('<I',value)
            self.assertEqual(self.signed(sequence,raw),bytes.fromhex('8400000001000a000000'));sequence+=1
            self.assertEqual(self.signed(sequence,bytes.fromhex('030220ac240101000a00')),
                             bytes.fromhex('8300000001000a000000ffffffff'));sequence+=1
            self.assertEqual(self.signed(sequence,bytes.fromhex('010220ac2401')),
                             bytes.fromhex('81000000')+b''.join(header[n] for n in range(1,11)));sequence+=1
        self.assertIs(self.app.native_project_identity,identity)
        self.assertEqual(self.endpoint.counts['native_timeline_retained'],3)
        self.assertFalse(self.endpoint.state()['native_session']['timeline_replacement'])
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_timeline_ack_requires_bound_nonzero_source_and_exact_proposal(self):
        raw=bytes.fromhex('040220ac240101000a0001000000')
        self.bind();sequence=4
        for identity in (None,NativeProjectIdentity('1'*64,self.app.engine.project.sha256,1,1,1,1,1,0),
                         NativeProjectIdentity('1'*64,'2'*64,1,1,1,1,1,99)):
            self.app.native_project_identity=identity
            self.assertEqual(self.signed(sequence,raw)[2],0x0C);sequence+=1
        self.app.native_project_identity=NativeProjectIdentity('1'*64,self.app.engine.project.sha256,1,1,1,1,1,99)
        for invalid,status in ((raw[:-1],0x13),(raw+b'x',0x15),(raw[:-4]+bytes(4),3),
                (bytes.fromhex('040220ac240102000a0001000000'),15),
                (bytes.fromhex('040220ac24010100030001000000'),15),
                (bytes.fromhex('100320ac2401300a01000000'),15)):
            self.assertEqual(self.signed(sequence,invalid)[2],status);sequence+=1
        self.assertEqual(self.cip(raw)[2],8)  # The unsigned setter is still unsupported.
        self.assertEqual(self.app.native_project_identity.timeline_uid,99)
        self.begin()
        self.assertEqual(self.signed(1,raw)[2],15)
        self.assertEqual(self.endpoint.counts['native_timeline_retained'],0)

    def test_timeline_ack_in_signed_batch_preserves_source_and_other_write_denials(self):
        identity=NativeProjectIdentity('1'*64,self.app.engine.project.sha256,1,1,1,1,1,99)
        self.app.native_project_identity=identity;self.bind()
        proposal=bytes.fromhex('040220ac240101000a0001000000')
        setter=bytes.fromhex('100320ac2401300a01000000')
        read=bytes.fromhex('0e0320ac2401300a')
        raw=batch((proposal,setter,read),sequence=4);raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual(result.children,(bytes.fromhex('8400000001000a000000'),bytes.fromhex('90000f00'),
                                          bytes.fromhex('8e00000063000000')))
        self.assertEqual(identity.timeline_uid,99)

    def test_signed_data_logging_discovery_and_capacity_require_empty_source(self):
        from logixlab.data_log_catalog import DataLogCatalog
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.signed(4,bytes.fromhex('4b0220712465')),bytes.fromhex('cb000000'))
        self.assertEqual(self.signed(5,bytes.fromhex('030220712400020003000a00')),
                         bytes.fromhex('83000000020003000000000000000a00000000000000'))
        self.app.engine.project.data_log_catalog=DataLogCatalog(False)
        self.assertEqual(self.signed(6,bytes.fromhex('4b0220712465'))[2],0x0C)
        self.assertEqual(self.signed(7,bytes.fromhex('100320712400300a01000000'))[2],15)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_real_tcp_context_setup_and_signed_metadata_read(self):
        self.bind()
        self.assertEqual(self.signed(4, bytes.fromhex('0e03200124013001')), b'\x8E\0\0\0\1\0')
        metadata = self.endpoint.state()
        self.assertTrue(metadata['native_session']['enabled'])
        self.assertFalse(metadata['native_session']['confirmation_proof_verified'])
        self.assertFalse(metadata['native_session']['operator_authorization'])
        self.assertTrue(metadata['key_exchange']['signed_messages'])
        self.assertTrue(metadata['key_exchange']['session_secret_retained'])
        self.assertFalse(metadata['key_exchange']['confirmation'])
        self.assertFalse(metadata['key_exchange']['peer_identity_verified'])

    def test_time_sync_partial_lists_fit_signed_and_batch_reply_budgets(self):
        from logixlab.time_sync import TimeSync
        from tools.time_sync_inventory import decode_attribute_list
        self.app.engine.project.time_sync=TimeSync(False,128,128)
        before=copy.deepcopy(self.app.engine.memory.values)
        self.bind();sequence=4;order=(*range(1,29),102,103,104,105)
        def query(numbers):
            return bytes.fromhex('030220432401')+struct.pack('<'+'H'*(len(numbers)+1),len(numbers),*numbers)
        for wrapper in (0x36,0x37):
            pending=order;returned=[]
            while pending:
                raw=request(wrapper,query(pending),sequence);sequence+=1
                response=self.cip(raw);self.assertLessEqual(len(response),480)
                inner=signed_messages.verify_response(response,KEY,request=signed_messages.parse_request(raw)).inner
                decoded=decode_attribute_list(inner,pending)
                self.assertTrue(all(row['status']==0 for row in decoded['attributes']))
                returned.extend(row['attribute'] for row in decoded['attributes'])
                pending=tuple(decoded['remaining_attributes'])
            self.assertEqual(returned,list(order))
        raw=batch((query(order),bytes.fromhex('0e03200124013001')),sequence=sequence)
        raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        response=self.cip(raw);self.assertLessEqual(len(response),480)
        children=signed_messages.verify_response(response,KEY,request=signed_messages.parse_request(raw)).children
        self.assertEqual(children[1],bytes.fromhex('8e0000000100'))
        prefix=decode_attribute_list(children[0],order)
        self.assertTrue(prefix['partial']);self.assertTrue(prefix['attributes'])
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_signed_wall_clock_policy_and_counter_relation_preserve_write_denials(self):
        from logixlab.wall_clock import CoordinatedClock,WallClock,UTC_ZONE
        from tools.collection_inventory import decode_attribute_list
        self.app.engine.project.wall_clock=WallClock(True)
        self.app.coordinated_clock=CoordinatedClock(1_000_000)
        self.bind();order=tuple(range(1,12));utc=1_700_000_000_123_456
        with patch('logixlab.wall_clock.time.time_ns',return_value=utc*1000),\
             patch('logixlab.wall_clock.time.monotonic_ns',return_value=2_234_567):
            response=self.signed(4,bytes.fromhex('0302208b2401')+struct.pack('<12H',11,*order))
        rows=decode_attribute_list(response,order,0x8b,include_payloads=True)['attributes']
        self.assertTrue(all(row['status']==0 for row in rows))
        values={row['attribute']:bytes.fromhex(row['data_hex']) for row in rows}
        self.assertEqual(struct.unpack('<q',values[3])[0]+1234,utc)
        self.assertEqual(values[8],struct.pack('<I',len(UTC_ZONE))+UTC_ZONE)
        for sequence,attr in enumerate((3,8,9,10),5):
            self.assertEqual(self.signed(sequence,bytes((0x10,3,0x20,0x8b,0x24,1,0x30,attr))+b'\0')[2],15)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_signed_program_discovery_keeps_names_read_only_and_source_bound(self):
        self.app.native_symbols=NativeSymbols('1'*64,self.app.engine.project.sha256,[],
                                             [{'name':'MainProgram','instance':1234}])
        self.bind()
        self.assertEqual(self.signed(4,bytes.fromhex('4b0220682400')),b'\xCB\0\0\0'+struct.pack('<I',1234))
        path=bytes.fromhex('20682500')+struct.pack('<H',1234)+b'\x30\x1C'
        self.assertEqual(self.signed(5,bytes((0x0E,len(path)//2))+path,0x37),
                         b'\x8E\0\0\0'+struct.pack('<I',11)+b'MainProgram')
        self.assertEqual(self.signed(6,bytes((0x10,len(path)//2))+path+b'\0\0\0\0')[2],0x0F)
        self.assertEqual(self.app.engine.project.programs['MainProgram']['main'],'MainRoutine')

    def test_signed_driver_counters_keep_clear_services_denied_and_values_unchanged(self):
        from logixlab.ethernet_counters import CounterSnapshot
        from logixlab.network_objects import InterfaceSnapshot
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        snapshot=CounterSnapshot(tuple(range(11)),tuple(range(12)))
        interface=InterfaceSnapshot('127.0.0.1','255.0.0.0',name='test0')
        with patch('logixlab.ethernetip.interface_snapshot',return_value=(interface,None)),\
             patch('logixlab.ethernet_counters.linux_counters',return_value=snapshot) as provider:
            result=self.signed(4,bytes.fromhex('030220f62401020004000500'))
            self.assertEqual(result,bytes.fromhex('83000000020004000000')+snapshot.attributes()[4]+
                             bytes.fromhex('05000000')+snapshot.attributes()[5])
            self.assertEqual(self.signed(5,bytes.fromhex('4c0320f624013004'))[2],0x0F)
            self.assertEqual(self.signed(6,bytes.fromhex('100320f624013005'))[2],0x0F)
            provider.assert_called_once_with('test0')
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_signed_sfc_force_status_is_empty_for_non_sfc_source(self):
        self.bind()
        self.assertEqual(self.signed(4,bytes.fromhex('03022068240003000f0018001900')),
                         bytes.fromhex('8300000003000f000000000018000000000000001900000000000000'))
        self.assertEqual(self.signed(5,bytes.fromhex('100320682400300f0100'))[2],0x0F)
        self.assertFalse(self.endpoint.state()['program_forces']['force_writes'])
        self.assertEqual(self.signed(6,bytes.fromhex('030220692400020009000b00')),
                         bytes.fromhex('8300000002000900000000000b0000000000'))
        self.assertEqual(self.signed(7,bytes.fromhex('10032069240030090100'))[2],0x0F)

    def test_signed_source_instance_read_reaches_model_and_write_remains_denied(self):
        self.app.native_symbols=NativeSymbols('1'*64,self.app.engine.project.sha256,
                                              [Symbol('',0,'SpeedSetpoint',70000)])
        self.bind()
        path=bytes.fromhex('206b260070110100')  # Symbol instance 70000, 32-bit path
        read=b'\x4C\4'+path+b'\1\0'
        expected=b'\xCC\0\0\0'+struct.pack('<Hi',0xC4,50)
        self.assertEqual(self.signed(4,read),expected)
        write=b'\x4D\4'+path+struct.pack('<HHi',0xC4,1,99)
        raw=batch((read,write),sequence=5);raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual(result.children,(expected,b'\xCD\0\x0F\0'))
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'),50)

    def test_signed_empty_metadata_list_does_not_enable_other_vendor_services(self):
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.signed(4,bytes.fromhex('4b03210049032400')),b'\xCB\0\0\0')
        self.assertEqual(self.signed(5,bytes.fromhex('4b03210049032400')+b'\0')[2],0x15)
        self.assertEqual(self.signed(6,bytes.fromhex('4b02206b2400'))[2],0)
        self.assertEqual(self.signed(7,bytes.fromhex('4c03210049032400'))[2],0x0F)
        self.assertEqual(self.signed(8,bytes.fromhex('4b02206a2400'))[2],0)
        self.assertEqual(self.signed(9,bytes.fromhex('4b0220692400')),bytes.fromhex('cb000000'))
        self.assertEqual(self.app.engine.memory.values,before)

    def test_signed_scalar_symbol_descriptor_list_and_setter_boundary(self):
        self.app.native_symbols=NativeSymbols('1'*64,self.app.engine.project.sha256,
                                              [Symbol('',0,'SpeedSetpoint',70000)])
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        path=bytes.fromhex('206b260070110100')
        attrs=(1,2,3,5,6,7,8,10,11,12,14,9)
        result=self.signed(4,bytes((3,len(path)//2))+path+struct.pack('<13H',len(attrs),*attrs))
        self.assertEqual(result[:4],b'\x83\0\0\0')
        self.assertEqual(result[4:6],struct.pack('<H',12))
        self.assertIn(struct.pack('<HHI',12,0,70000),result)
        self.assertEqual(self.signed(5,bytes((0x10,len(path)//2))+path+b'\0')[2],0x0F)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_signed_controller_collection_exposes_null_handlers_and_settings_without_mutation(self):
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        query=bytes.fromhex('0302208e24010600030006000100070008001000')
        expected=(b'\x83\0\0\0'+struct.pack('<HHHH',6,3,0,20)+struct.pack('<HHI',6,0,0)+
                  struct.pack('<HHI',1,0,0)+struct.pack('<9H',7,0,0,8,0,0,16,0,1))
        self.assertEqual(self.signed(4,query),expected)
        self.assertEqual(self.signed(5,bytes.fromhex('1003208e24013003')+b'\x0A\0')[2],0x0F)
        self.assertEqual(self.signed(6,bytes.fromhex('0e03208e24013003'))[4:],b'\x14\0')
        self.assertEqual(self.app.engine.memory.values,before)

    def test_signed_null_handlers_keep_duplicate_list_widths_and_configured_handlers_stay_unavailable(self):
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        query=bytes.fromhex('0302208e24010300060001000600')
        expected=b'\x83\0\0\0'+struct.pack('<H',3)+b''.join(struct.pack('<HHI',n,0,0) for n in (6,1,6))
        self.assertEqual(self.signed(4,query),expected)
        self.assertEqual(self.signed(5,bytes.fromhex('0e03208e24013001')),bytes.fromhex('8e00000000000000'))
        self.app.engine.project.controller_configuration=replace(self.app.engine.project.controller_configuration,
            empty_power_loss_handler=False,empty_fault_handler=False)
        self.assertEqual(self.signed(6,bytes.fromhex('0e03208e24013001'))[2],0x14)
        self.assertEqual(self.signed(7,bytes.fromhex('0e03208e24013006'))[2],0x14)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_signed_controller_aggregate_requires_instance_scope_and_empty_payload_and_denies_configured_handlers(self):
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.signed(4,bytes.fromhex('0102208e2401')),b'\x81\0\0\0'+struct.pack('<HIIHHH',20,0,0,0,0,0))
        self.assertNotEqual(self.signed(5,bytes.fromhex('0102208e240100'))[2],0)
        self.assertNotEqual(self.signed(6,bytes.fromhex('0103208e24013001'))[2],0)
        self.app.engine.project.controller_configuration=replace(self.app.engine.project.controller_configuration,empty_fault_handler=False)
        self.assertEqual(self.signed(7,bytes.fromhex('0102208e2401'))[2],0x14)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_signed_axis_group_discovery_is_empty_only_for_motion_free_source(self):
        from logixlab.motion_catalog import MotionCatalog
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.signed(4,bytes.fromhex('4b0220b02400')),b'\xCB\0\0\0')
        self.assertEqual(self.signed(5,bytes.fromhex('4b0220b02400')+b'\0')[2],0x15)
        self.assertEqual(self.signed(6,bytes.fromhex('100320b024013001')+b'\1')[2],0x0F)
        self.app.engine.project.motion_catalog=MotionCatalog(False)
        self.assertEqual(self.signed(7,bytes.fromhex('4b0220b02400'))[2],0x0C)
        self.assertEqual(self.signed(8,bytes.fromhex('4b0220b12400'))[2],0x0C)
        self.app.engine.project.motion_catalog=MotionCatalog(True)
        self.assertEqual(self.signed(9,bytes.fromhex('4b0220b12400')),b'\xCB\0\0\0')
        self.assertEqual(self.signed(10,bytes.fromhex('4b0321002b032400')),b'\xCB\0\0\0')
        self.assertEqual(self.app.engine.memory.values,before)

    def test_signed_software_time_read_and_setter_denial_preserve_scan_clock(self):
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        timestamp=1_700_000_000_123_456_789
        with patch('logixlab.software_clock.time.time_ns',return_value=timestamp):
            self.assertEqual(self.signed(4,bytes.fromhex('030220432401020003000400')),
                bytes.fromhex('83000000020003000000')+struct.pack('<q',timestamp//1000)+
                bytes.fromhex('04000000')+struct.pack('<q',timestamp))
        self.assertEqual(self.signed(5,bytes.fromhex('1003204324013003')+bytes(8))[2],0x0F)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual((self.app.engine.time_ms,self.app.engine.scan_count),(0,0))

    def test_signed_upload_inventory_reads_are_source_checked_and_keep_writes_denied(self):
        from logixlab.alarm_catalog import AlarmCatalog
        from logixlab.aoi_catalog import AOICatalog
        from logixlab.io_map import IOMap
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        requests=('4b0220692400','4b032100a6032400','4b032100a7032400',
                  '4b032100a8032400','4b03210038032400')
        sequence=4
        for raw in requests:
            self.assertEqual(self.signed(sequence,bytes.fromhex(raw)),bytes.fromhex('cb000000'));sequence+=1
        self.assertEqual(self.signed(sequence,bytes.fromhex('030220f52400020065006600')),
                         bytes.fromhex('83000000020065000000006600000000'));sequence+=1
        self.app.engine.project.alarm_catalog=AlarmCatalog(False)
        self.app.engine.project.aoi_catalog=AOICatalog(False)
        self.app.engine.project.io_map=IOMap(False)
        for raw in requests:
            self.assertEqual(self.signed(sequence,bytes.fromhex(raw))[2],0x0C);sequence+=1
        for raw in ('100320f52400306501','100320692400300300000000','4c03210038032400'):
            self.assertEqual(self.signed(sequence,bytes.fromhex(raw))[2],0x0F);sequence+=1
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_signed_extended_device_defaults_do_not_authorize_an_operator_or_writes(self):
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        query=bytes.fromhex('03022064240104000300060007000800')
        expected=(bytes.fromhex('830000000400030000000000060000000500')+b'en-US'+
                  bytes.fromhex('0700000000000800000000000000'))
        self.assertEqual(self.signed(4,query),expected)
        self.assertEqual(self.signed(5,bytes.fromhex('1003206424013008')+b'\xff'*4)[2],0x0F)
        self.assertEqual(self.signed(6,bytes.fromhex('0e03206424013008')),bytes.fromhex('8e00000000000000'))
        self.assertFalse(self.endpoint.state()['native_session']['operator_authorization'])
        self.assertFalse(self.endpoint.state()['device_metadata']['trusted_slot_enforcement'])
        self.assertEqual(self.app.engine.memory.values,before)

    def test_signed_alarm_lists_require_alarm_free_source_and_keep_writes_denied(self):
        from logixlab.alarm_catalog import AlarmCatalog
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        for sequence,target in enumerate(('4b03210031032400','4b03210032032400'),4):
            self.assertEqual(self.signed(sequence,bytes.fromhex(target)),b'\xCB\0\0\0')
        self.assertEqual(self.signed(6,bytes.fromhex('4b03210031032400')+b'\0')[2],0x15)
        self.assertEqual(self.signed(7,bytes.fromhex('10042100310324013001')+bytes(4))[2],0x0F)
        self.app.engine.project.alarm_catalog=AlarmCatalog(False)
        self.assertEqual(self.signed(8,bytes.fromhex('4b03210032032400'))[2],0x0C)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_signed_hmi_button_list_requires_empty_source_and_keeps_writes_denied(self):
        from logixlab.hmi_button_catalog import HmiButtonCatalog
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.signed(4,bytes.fromhex('4b0321006e032400')),b'\xCB\0\0\0')
        self.assertEqual(self.signed(5,bytes.fromhex('4b0321006e032400')+b'\0')[2],0x15)
        self.assertEqual(self.signed(6,bytes.fromhex('100421006e0324013001')+b'\1')[2],0x0F)
        self.app.engine.project.hmi_button_catalog=HmiButtonCatalog(False)
        self.assertEqual(self.signed(7,bytes.fromhex('4b0321006e032400'))[2],0x0C)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_exact_empty_energy_probe_succeeds_without_dispatch_or_write_permission(self):
        probe=bytes.fromhex('3b02204e2400')
        self.begin()
        self.assertEqual(self.signed(1,probe)[2],0x0F)
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        count=self.endpoint.counts['cip']
        self.assertEqual(self.signed(4,probe),b'\xBB\0\0\0')
        self.assertEqual(self.endpoint.counts['cip'],count+1)  # no inner dispatch
        for sequence,raw in enumerate((probe+b'\0',bytes.fromhex('3b02204e2401'),
                bytes.fromhex('3b03204e24003001'),bytes.fromhex('1003204e24013001')+bytes(4)),5):
            self.assertEqual(self.signed(sequence,raw)[2],0x0F)
        raw=batch((probe,bytes.fromhex('1003204e24013001')+bytes(4)),sequence=9)
        raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual(result.children,(b'\xBB\0\0\0',b'\x90\0\x0F\0'))
        self.assertEqual(self.app.engine.memory.values,before)

    def test_user_memory_class_discovery_does_not_enable_instance_or_write_access(self):
        query=bytes.fromhex('03022072240001000100')
        self.begin();self.assertEqual(self.signed(1,query)[2],0x0F)
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.signed(4,query),bytes.fromhex('830000000100010000000500'))
        self.assertEqual(self.signed(5,bytes.fromhex('0e03207224013001'))[2],5)
        self.assertEqual(self.signed(6,bytes.fromhex('10032072240030010500'))[2],0x0F)
        self.assertEqual(self.signed(7,bytes.fromhex('03022066240001000100')),bytes.fromhex('830000000100010000000300'))
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_signed_wall_clock_reads_preserve_cst_and_setter_boundaries(self):
        from unittest.mock import patch
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        with patch('logixlab.wall_clock.time.time_ns',return_value=1_000_000) as clock:
            self.assertEqual(self.signed(4,bytes.fromhex('0e03208b24013006')),
                             bytes.fromhex('8e000000e803000000000000'))
            clock.assert_called_once_with()
        self.assertEqual(self.signed(5,bytes.fromhex('0e03208b24013003'))[2],0x14)
        self.assertEqual(self.signed(6,bytes.fromhex('1003208b24013006')+bytes(8))[2],0x0F)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)

    def test_only_observed_empty_energy_profiles_succeed_without_inner_dispatch(self):
        self.bind();count=self.endpoint.counts['cip']
        for sequence,cls in enumerate((0x4E,0x4F,0x50),4):
            expected=b'\xBB\0\0\0' if cls in (0x4E,0x4F) else b'\xBB\0\x08\0'
            self.assertEqual(self.signed(sequence,bytes((0x3B,2,0x20,cls,0x24,0))),expected)
        self.assertEqual(self.endpoint.counts['cip'],count+3)
        self.assertEqual(self.signed(7,bytes.fromhex('3b0220512400'))[2],0x0F)

    def test_energy_probe_program_scope_requires_original_known_program_binding(self):
        source=self.app.engine.project.sha256
        self.app.native_project_identity=NativeProjectIdentity('a'*64,source,1,1,1,1,1,1)
        self.app.native_symbols=NativeSymbols('a'*64,source,[],[{'name':'MainProgram','instance':1234}])
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        path=bytes.fromhex('20682500d204204e2400')
        self.assertEqual(self.signed(4,bytes((0x3B,len(path)//2))+path),b'\xBB\0\0\0')
        unknown=path.replace(bytes.fromhex('d204'),bytes.fromhex('d304'))
        self.assertEqual(self.signed(5,bytes((0x3B,len(unknown)//2))+unknown)[2],5)
        self.app.native_symbols=None
        self.assertEqual(self.signed(6,bytes((0x3B,len(path)//2))+path)[2],0x0C)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_energy_legacy_lists_require_supported_source_and_keep_other_operations_denied(self):
        from logixlab.energy_catalog import EnergyCatalog
        self.begin()
        self.assertEqual(self.signed(1,bytes.fromhex('4b02204e2400'))[2],0x0F)
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        for sequence,cls in enumerate((0x4E,0x4F,0x50),4):
            self.assertEqual(self.signed(sequence,bytes((0x4B,2,0x20,cls,0x24,0))),b'\xCB\0\0\0')
        self.assertEqual(self.signed(7,bytes.fromhex('4b02204e2400')+b'\0')[2],0x15)
        self.assertEqual(self.signed(8,bytes.fromhex('1003204e24013001')+bytes(4))[2],0x0F)
        self.app.engine.project.energy_catalog=EnergyCatalog(False)
        self.assertEqual(self.signed(9,bytes.fromhex('4b02204e2400'))[2],0x0C)
        raw=batch((bytes.fromhex('3b02204e2400'),bytes.fromhex('4b02204e2400'),bytes.fromhex('1003204e24013001')+bytes(4)),sequence=10)
        raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual(result.children,(b'\xBB\0\x08\0',b'\xCB\0\x0C\0',b'\x90\0\x0F\0'))
        self.assertEqual(self.app.engine.memory.values,before)

    def test_signed_message_list_requires_empty_source_and_keeps_msg_writes_denied(self):
        from logixlab.message_catalog import MessageCatalog
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.signed(4,bytes.fromhex('4b02208d2400')),b'\xCB\0\0\0')
        self.assertEqual(self.signed(5,bytes.fromhex('4b02208d2400')+b'\0')[2],0x15)
        self.assertEqual(self.signed(6,bytes.fromhex('1003208d24013001')+bytes(2))[2],0x0F)
        self.app.engine.project.message_catalog=MessageCatalog(False)
        self.assertEqual(self.signed(7,bytes.fromhex('4b02208d2400'))[2],0x0C)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_batch_reads_share_counter_and_reject_writes_nested_transport_and_locator(self):
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        children=(bytes.fromhex('0e03200124013005'),bytes.fromhex('1003208e2401300d')+bytes(4),
                  b'\x4B\2\x20\1\x24\1\x09',bytes.fromhex('380220022401')+bytes(30))
        raw=batch(children,sequence=4);raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual(result.status,0x1E)
        self.assertEqual(result.children[0],b'\x8E\0\0\0\x70\x30')
        self.assertEqual([r[2] for r in result.children[1:]],[0x0F]*3)
        self.assertEqual(self.signed(5,bytes.fromhex('0e03200124013005')),result.children[0])
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertFalse(self.endpoint.locator_state()['active'])
        self.assertEqual(self.cip(raw)[2],0x0F)  # replay closes the context

    def test_signed_data_table_reads_model_addresses_and_scalar_bytes_without_writes(self):
        self.app.native_symbols=NativeSymbols('1'*64,self.app.engine.project.sha256,
                                              [Symbol('',0,'SpeedSetpoint',70000)])
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.signed(4,bytes.fromhex('4b02206a2400')),b'\xCB\0\0\0'+struct.pack('<I',70000))
        path=bytes.fromhex('206a260070110100')
        self.assertEqual(self.signed(5,b'\x0E\5'+path+b'\x30\x08'),b'\x8E\0\0\0'+struct.pack('<I',70000))
        address=self.signed(6,b'\x0E\5'+path+b'\x30\x03')
        self.assertEqual(address[:4],b'\x8E\0\0\0')
        self.assertNotEqual(address[4:],bytes(4))
        self.assertEqual(self.signed(7,b'\x4C\4'+path+b'\1\0')[2],0x0F)
        self.assertEqual(self.signed(8,b'\x10\5'+path+b'\x30\2\xC4\0')[2],0x0F)
        self.assertEqual(self.signed(9,b'\x4F\4'+path+struct.pack('<IH',0,4)),b'\xCF\0\0\0'+struct.pack('<i',50))
        self.assertEqual(self.signed(10,b'\x4F\4'+path+struct.pack('<IH',1,4))[2],3)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_bad_batch_mac_never_dispatches_a_child_and_unbound_batch_cannot_register(self):
        self.bind();count=self.endpoint.counts['cip']
        raw=batch((bytes.fromhex('0e03200124013005'),),sequence=4)
        self.assertEqual(self.cip(raw)[2],0x0F)
        self.assertEqual(self.endpoint.counts['cip'],count+1)
        self.begin()
        raw=batch((b'\x5C\2\x20\x8E\x24\1operator',),sequence=1)
        raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual(result.children[0][2],0x0F)
        native,=self.endpoint.native_sessions.values();self.assertEqual(native.stage,'acknowledged')

    def test_native_identity_status_agrees_across_single_all_and_discovery(self):
        status=self.cip(bytes.fromhex('0e03200124013005'))[4:]
        self.assertEqual(status,b'\x70\x30')
        all_attributes=self.cip(bytes.fromhex('010220012401'))[4:]
        self.assertEqual(all_attributes[8:10],status)
        identity=self.endpoint.discovery(0x63)
        self.assertEqual(identity[32:34],status)

    def test_all_setters_nested_transports_and_locator_are_denied(self):
        self.bind()
        before = copy.deepcopy(self.app.engine.memory.values)
        for sequence, inner in enumerate((bytes.fromhex('1003208e2401300d')+bytes(4),
                bytes.fromhex('040220ac24010000'), bytes.fromhex('0a022002240101000400')+b'\x4D\0',
                b'\x52\2\x20\6\x24\1'+bytes(16), b'\x4B\2\x20\1\x24\1\x09'), 4):
            self.assertEqual(self.signed(sequence, inner)[2], 0x0F)
        self.assertEqual(self.app.engine.memory.values, before)
        self.assertFalse(self.endpoint.locator_state()['active'])

    def test_bad_mac_replay_and_cross_connection_requests_do_not_dispatch(self):
        for damage in ('mac', 'counter'):
            self.bind()
            raw = request(0x36, bytes.fromhex('0e03200124013001'), 4 if damage=='mac' else 3)
            if damage == 'mac':raw=raw[:-1]+bytes((raw[-1]^1,))
            self.assertEqual(self.cip(raw)[2], 0x0F)
            self.assertEqual(self.cip(request(0x36, bytes.fromhex('0e03200124013001'), 4))[2], 0x0F)
        other = Client(self.endpoint.port)
        try:
            other.register()
            self.assertEqual(other.cip(request(0x36, bytes.fromhex('0e03200124013001'), 1))[1][2], 0x0F)
        finally:other.close()

    def test_unbound_context_cannot_read_and_wrong_token_does_not_bind(self):
        self.begin()
        self.assertEqual(self.signed(1, bytes.fromhex('0e03200124013001'))[2], 0x0F)
        self.assertEqual(self.signed(2, b'\x5C\2\x20\x8E\x24\1operator', 0x37)[2], 0)
        context = self.signed(3, bytes.fromhex('4b03210078032401')+b'anonymous-context')
        wrong = bytes((context[4]^1,))+context[5:]
        self.assertEqual(self.signed(4, b'\x63\2\x20\x8E\x24\1'+wrong)[2], 0x0F)
        self.assertEqual(self.signed(5, bytes.fromhex('0e03200124013001'))[2], 0x0F)

    def test_empty_metadata_query_is_bounded_and_unsigned_service_stays_unsupported(self):
        self.bind()
        prefix=bytes.fromhex('5303210049032400')
        query=struct.pack('<II8H',0x101,0,1,0xFFFF,0x8E,1,0,0,0,0)
        selected=struct.pack('<II9H',0x101,0,9,0xFFFF,0x8E,1,0,0,0,0,26)
        for sequence,payload in enumerate((query,selected),4):
            self.assertEqual(self.signed(sequence,prefix+payload), b'\xD3\0\0\0'+struct.pack('<II',0x301,0))
            self.assertEqual(self.cip(prefix+payload)[2],8)
        sequence=6
        for payload in (query+b'x',query[:-1],struct.pack('<II',0x101,0)+bytes(18),
                        *(query[:n]+bytes((query[n]^1,))+query[n+1:] for n in range(len(query)))):
            self.assertEqual(self.signed(sequence,prefix+payload)[2],0x0F)
            sequence+=1

    def test_source_change_and_stop_release_keys_and_contexts(self):
        self.bind()
        native,=self.endpoint.native_sessions.values()
        self.assertEqual(native.stage,'bound')
        self.app.command('reset',{})
        self.assertIsNone(native.key)
        self.assertIsNone(native.operator_digest)
        self.assertIsNone(native.context)
        self.assertFalse(self.endpoint.native_sessions)
        self.client.close();self.client=Client(self.endpoint.port);self.client.register()
        self.bind()
        native,=self.endpoint.native_sessions.values()
        self.endpoint.stop()
        self.assertIsNone(native.key)

    def test_fresh_keys_expiry_and_invalid_acknowledgement(self):
        a=native_session.NativeSession();b=native_session.NativeSession()
        self.assertNotEqual(a.begin(offer()),b.begin(offer()))
        with self.assertRaises(native_session.NativeError):a.acknowledge(bytes(22))
        self.assertIsNone(a.key)
        b.deadline=0
        with self.assertRaises(native_session.NativeError):b.check_live()
        self.assertIsNone(b.key)

    def test_native_mode_requires_read_only_matching_profile_and_boolean_flag(self):
        for writes,profile,flag in ((True,'logix-v35-l85e',True),(False,'research',True),(False,'research',1)):
            with self.assertRaises(ModelError):Endpoint(self.app,0,writes,profile,native_read_only=flag)

    def test_standard_controller_reports_safety_object_absence(self):
        self.bind()
        self.assertEqual(self.signed(4,bytes.fromhex('0e042100340324013003')),b'\x8E\0\5\0')

    def test_signed_pass_through_setting_is_read_only_source_metadata(self):
        self.app.engine.project.controller_configuration=ControllerConfiguration.from_controller(
            E.fromstring('<Controller PassThroughConfiguration="EnabledWithAppend"/>'))
        self.bind()
        self.assertEqual(self.signed(4,bytes.fromhex('0302208e240101001900')),
                         bytes.fromhex('8300000001001900000003000000'))
        self.assertEqual(self.signed(5,bytes.fromhex('0e03208e24013019'),0x37),
                         bytes.fromhex('8e00000003000000'))
        self.assertEqual(self.signed(6,bytes.fromhex('1003208e24013019')+bytes(4))[2],0x0F)
        self.assertEqual(self.app.engine.project.controller_configuration.pass_through_configuration,'EnabledWithAppend')

    def test_virtual_change_log_all_agrees_with_single_and_list_reads(self):
        self.bind()
        fields=CatalogRevision.from_source(self.app.engine.project.sha256).compatibility_attributes()
        result=self.signed(4,bytes.fromhex('010220ac2401'))
        self.assertEqual(result,b'\x81\0\0\0'+b''.join(fields[n] for n in range(1,11)))
        self.assertEqual(len(result[4:]),32)
        self.assertEqual(fields[7],struct.pack('<I',2))
        self.assertEqual(fields[9],struct.pack('<HH',1,1))
        self.assertEqual(self.signed(5,bytes.fromhex('0e0320ac24013008')),b'\x8E\0\0\0'+fields[8])
        self.assertEqual(self.signed(6,bytes.fromhex('030220ac2401020007000900')),
                         b'\x83\0\0\0'+struct.pack('<HHH',2,7,0)+fields[7]+struct.pack('<HH',9,0)+fields[9])

    def test_virtual_status_fields_preserve_source_redundancy_availability(self):
        for value,expected in (('true',b'\1'),('false',b'\0'),('unknown',None)):
            node=E.fromstring(f'<Controller Name="Example"><Security Code="0"/><RedundancyInfo Enabled="{value}"/></Controller>')
            config=ControllerConfiguration.from_controller(node)
            fields=config.compatibility_attributes()
            self.assertEqual(fields.get(9),expected)
            self.assertEqual(fields[7],bytes(2))
            self.assertEqual(fields[26],bytes(4))
            self.assertEqual(fields[13],bytes(4))
        self.assertNotIn(9,ControllerConfiguration.from_controller(E.fromstring('<Controller/>')).compatibility_attributes())


if __name__ == '__main__':
    unittest.main()
