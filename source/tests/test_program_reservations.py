"""Source-bound Program reservations coordinate preparation without active edits."""
import copy
import unittest
from logixlab.ethernetip import CIPError,Session,decode_path,logical
from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_symbols import NativeSymbols
import test_native_session as native

CONTROLLER_ACQUIRE=bytes.fromhex('4b04208e24012074240101')
CONTROLLER_RELEASE=bytes.fromhex('4c04208e240120742401')

def message(service=0x4B,program=300,instance=1,payload=b'\0'):
    path=logical(0x20,0x68)+logical(0x24,program)+logical(0x20,0x74)+logical(0x24,instance)
    return bytes((service,len(path)//2))+path+payload

class ProgramReservationTests(unittest.TestCase):
    setUp=native.NativeSessionTests.setUp
    tearDown=native.NativeSessionTests.tearDown
    cip=native.NativeSessionTests.cip
    begin=native.NativeSessionTests.begin
    signed=native.NativeSessionTests.signed
    bind=native.NativeSessionTests.bind

    def prepare(self):
        digest=self.app.engine.project.sha256
        self.app.native_project_identity=NativeProjectIdentity('a'*64,digest,1,1,1,1,1,1)
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':300}])
        self.bind();self.sequence=4

    def send(self,raw):
        result=self.signed(self.sequence,raw);self.sequence+=1;return result

    def test_path_preserves_program_parent_and_rejects_mixed_scopes(self):
        for program in (7,300,70000):
            path=decode_path(message(program=program)[2:-1])
            self.assertEqual((path.program_instance,path.class_id,path.instance),(program,0x74,1))
            self.assertIsNone(path.controller_instance)
        for raw in ('2068240020742401','206824012074','2068240120742401208e2401','20682401300120742401'):
            with self.assertRaises(CIPError):decode_path(bytes.fromhex(raw))

    def test_signed_reservation_blocks_run_until_release_and_preserves_project(self):
        self.prepare();before=copy.deepcopy(self.app.state())
        self.assertEqual(self.send(CONTROLLER_ACQUIRE)[2],0)
        self.assertEqual(self.send(message()),bytes.fromhex('cb000000'))
        self.assertEqual(self.send(message()),bytes.fromhex('cb000000'))
        lease=self.endpoint.state()['native_programming_lease']
        self.assertEqual(lease['edit_preparation']['program_reservations'],1)
        self.assertTrue(lease['scan_inhibited']);self.assertEqual(lease['run_mode_inhibit'],0)
        self.assertFalse(lease['online_edits'] or lease['project_transfer'])
        with self.assertRaises(ModelError):self.app.command('controller-mode',{'mode':'Run'})
        for request in (bytes.fromhex('5502208e2401'),bytes.fromhex('5702208e2401')):
            self.assertEqual(self.send(request)[2],15)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])
        self.assertEqual(self.send(message(0x4C,payload=b'')),bytes.fromhex('cc000000'))
        self.assertEqual(self.send(message(0x4C,payload=b''))[2],0)
        self.assertFalse(self.endpoint.state()['native_programming_lease']['scan_inhibited'])
        self.app.command('controller-mode',{'mode':'Run'});self.app.command('controller-mode',{'mode':'Program'})
        self.assertEqual(self.send(CONTROLLER_RELEASE)[2],0)

    def test_owner_purpose_source_and_native_program_binding_are_required(self):
        self.prepare()
        self.assertEqual(self.send(message())[2],15)
        self.assertEqual(self.send(CONTROLLER_ACQUIRE[:-1]+b'\0')[2],0)
        self.assertEqual(self.send(message())[2],15)
        self.send(CONTROLLER_RELEASE);self.send(CONTROLLER_ACQUIRE)
        digest=self.app.engine.project.sha256
        for symbols in (None,NativeSymbols('b'*64,digest,[],[{'name':'MainProgram','instance':300}]),
                        NativeSymbols('a'*64,'b'*64,[],[{'name':'MainProgram','instance':300}])):
            self.app.native_symbols=symbols
            self.assertEqual(self.send(message())[2],12)
        self.assertEqual(self.endpoint.state()['native_programming_lease']['edit_preparation']['program_reservations'],0)

    def test_program_child_selector_and_exact_payload_guards(self):
        self.prepare();self.send(CONTROLLER_ACQUIRE)
        for raw,status in ((message(program=301),5),(message(instance=2),5),
                           (message(payload=b''),19),(message(payload=b'\0x'),21),
                           (message(payload=b'\1'),3),(message(0x4C,payload=b'x'),21)):
            self.assertEqual(self.send(raw)[2],status)
        self.assertEqual(self.endpoint.state()['native_programming_lease']['edit_preparation']['program_reservations'],0)

    def test_unsigned_reservations_are_denied_and_scoped_class_revision_reads_are_bounded(self):
        self.prepare()
        self.assertEqual(self.cip(message())[2],15)
        def revision(program):
            raw=message(0x0E,program=program,instance=0,payload=b'')
            return bytes((raw[0],raw[1]+1))+raw[2:]+b'\x30\1'
        self.assertEqual(self.cip(revision(300)),bytes.fromhex('8e0000000100'))
        self.assertEqual(self.cip(revision(301))[2],5)

    def test_controller_release_clears_program_reservations_and_run_inhibition(self):
        self.prepare();self.send(CONTROLLER_ACQUIRE);self.send(message())
        self.send(CONTROLLER_RELEASE)
        lease=self.endpoint.state()['native_programming_lease']
        self.assertFalse(lease['owned'] or lease['scan_inhibited'])
        self.assertEqual(lease['edit_preparation']['program_reservations'],0)
