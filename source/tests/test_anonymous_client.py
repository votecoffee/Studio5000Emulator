"""Real TCP challenge/MAC exchange using an independent ephemeral client key."""
import importlib.util
import tempfile
import unittest

from logixlab.ethernetip import Endpoint,symbol_path
from logixlab.native_project import NativeProjectIdentity
from logixlab.server import Application
from tools.anonymous_client import AnonymousClient,ProbeError


@unittest.skipUnless(importlib.util.find_spec('cryptography'),'optional cryptography client key generator')
class AnonymousClientTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=Application(self.temp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.app.native_project_identity=NativeProjectIdentity('a'*64,self.app.engine.project.sha256,1,1,1,1,1,1)
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True).start()
        self.app.endpoint=self.endpoint

    def tearDown(self):self.app.close();self.temp.cleanup()

    def test_actual_challenge_decryption_signed_tag_read_and_edit_reservation(self):
        with AnonymousClient(self.endpoint) as client:
            client.bind();self.assertEqual(client.sequence,4)
            path=symbol_path('StartPB')
            self.assertEqual(client.request(bytes((0x4C,len(path)//2))+path+b'\1\0'),bytes.fromhex('cc000000c10000'))
            self.assertEqual(client.request(bytes.fromhex('4b04208e24012074240101')),bytes.fromhex('cb000000'))
            self.assertEqual(self.endpoint.state()['native_programming_lease']['edit_preparation']['status'],'reserved')
            self.assertEqual(client.request(bytes.fromhex('4c04208e240120742401')),bytes.fromhex('cc000000'))
        self.assertFalse(self.endpoint.state()['native_session']['peer_identity_verified'])
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])
        self.assertEqual(self.app.engine.scan_count,0)

    def test_source_generation_or_policy_change_stops_client_before_another_packet(self):
        for change in ('generation','writes'):
            with AnonymousClient(self.endpoint) as client:
                client.bind();before=self.endpoint.counts['native_verified']
                if change=='generation':self.app.generation+=1
                else:self.endpoint.allow_writes=True
                with self.assertRaises(ProbeError):client.request(bytes.fromhex('0e03200124013001'))
                self.assertEqual(self.endpoint.counts['native_verified'],before)
            self.endpoint.allow_writes=False

    def test_targets_require_owned_loopback_and_client_replies_verify_mac(self):
        with self.assertRaises(ProbeError):AnonymousClient(object())
        with AnonymousClient(self.endpoint) as client:
            client.bind();exchange=client.exchange
            def altered(request):
                raw=exchange(request);return raw[:-1]+bytes((raw[-1]^1,))
            client.exchange=altered
            with self.assertRaises(ProbeError):client.request(bytes.fromhex('0e03200124013001'))
            with self.assertRaises(ProbeError):client.request(bytes.fromhex('0e03200124013001'))


if __name__=='__main__':unittest.main()
