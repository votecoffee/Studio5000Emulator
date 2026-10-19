"""Anonymous compatibility with synthetic keys; no vendor identity fixtures."""
import copy
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
from logixlab.server import Application
from test_ethernetip import Client
from test_key_exchange import offer
from test_signed_messages import KEY, request


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
        payload=struct.pack('<II',0x101,0)+bytes(18)
        self.assertEqual(self.signed(4,prefix+payload), b'\xD3\0\0\0'+struct.pack('<II',0x301,0))
        self.assertEqual(self.signed(5,prefix+payload+b'x')[2],0x0F)
        self.assertEqual(self.cip(prefix+payload)[2],8)

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
