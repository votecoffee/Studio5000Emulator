"""Nested I/O Connection class reads do not create module connections."""
import copy
import hmac
import tempfile
import unittest

from logixlab import signed_messages
from logixlab.ethernetip import CIPError, Endpoint, Session, decode_path, logical, symbol_path
from logixlab.io_map import IOMap
from logixlab.server import Application
import test_native_session as native_tests
from test_signed_batches import batch
from test_signed_messages import KEY


def child(parent=1, instance=0, attribute=None):
    raw=logical(0x20,0x69)+logical(0x24,parent)+logical(0x20,0x7E)+logical(0x24,instance)
    return raw if attribute is None else raw+logical(0x30,attribute)


def message(service, path, payload=b''):
    return bytes((service,len(path)//2))+path+payload


class IOConnectionPathTests(unittest.TestCase):
    def test_nested_scope_and_logical_widths_are_preserved(self):
        for parent in (1,256,65536,0xFFFFFFFF):
            for instance in (0,1,256,65536):
                path=decode_path(child(parent,instance,1))
                self.assertEqual((path.class_id,path.instance,path.attribute,path.io_map_instance),(0x7E,instance,1,parent))
                self.assertIsNone(path.program_instance)
        path=decode_path(bytes.fromhex('20682401206b2400'))
        self.assertEqual((path.program_instance,path.class_id,path.instance,path.io_map_instance),(1,0x6B,0,None))

    def test_missing_duplicate_mixed_and_third_object_paths_are_rejected(self):
        for raw in (child()[:-2], bytes.fromhex('20692400207e2400'),
                    child()+bytes.fromhex('206b2401'), child()+bytes.fromhex('2400'),
                    child()+bytes.fromhex('30013001'),
                    bytes.fromhex('206924013001207e2400'),
                    bytes.fromhex('20692401')+symbol_path('Private')+bytes.fromhex('207e2400'),
                    bytes.fromhex('20692401206b2400'), bytes.fromhex('20682401207e2400'),
                    bytes.fromhex('2069240121017e002400')):
            with self.subTest(path=raw.hex()),self.assertRaises(CIPError):decode_path(raw)


class IOConnectionWireTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=Endpoint(self.app,0,True).start();self.app.endpoint=self.endpoint

    def tearDown(self):
        self.app.close();self.tmp.cleanup()

    def call(self, service, path, payload=b''):
        return self.endpoint.router.handle(message(service,path,payload),Session())

    def test_revision_single_and_list_reads_without_module_instances(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.call(0x0E,child(attribute=1)),bytes.fromhex('8e0000000100'))
        self.assertEqual(self.call(3,child(),bytes.fromhex('01000100')),bytes.fromhex('830000000100010000000100'))
        self.assertEqual(self.call(3,child(),bytes.fromhex('020001000200')),
                         bytes.fromhex('83000a00020001000000010002001400'))
        self.assertEqual(self.call(0x0E,child(attribute=2))[2],0x14)
        for raw in ('0e03206924013004','0e0320692401300a','0e0320692401300c'):
            self.assertEqual(self.endpoint.router.handle(bytes.fromhex(raw),Session())[2],5)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)
        self.assertEqual(self.endpoint.state()['io_map']['connection_class_revision'],1)
        self.assertFalse(self.endpoint.state()['io_map']['module_connections'])

    def test_scope_instance_service_and_payload_errors(self):
        cases=((0x0E,child(2,attribute=1),b'',5),
               (0x0E,child(instance=1,attribute=1),b'',5),
               (0x0E,bytes.fromhex('207e24003001'),b'',5),
               (0x0E,child(attribute=1)+symbol_path('Private'),b'',4),
               (0x0E,child(attribute=1),b'x',0x15),
               (3,child(),b'\1',0x13),(3,child(),b'\0\0',3),
               (3,child(),bytes.fromhex('0100010000'),0x15),
               (0x10,child(attribute=1),b'\2\0',8),
               (4,child(),bytes.fromhex('010001000200'),8),
               (0x4B,child(),b'',8),(1,child(),b'',8))
        for service,path,payload,status in cases:
            with self.subTest(service=service,path=path.hex(),payload=payload.hex()):
                self.assertEqual(self.call(service,path,payload)[2],status)

    def test_unavailable_source_withholds_revision_and_reloading_recomputes_it(self):
        self.app.engine.project.io_map=IOMap(False)
        self.assertEqual(self.call(0x0E,child(attribute=1))[2],0x0C)
        self.assertEqual(self.call(3,child(),bytes.fromhex('01000100'))[2],0x0C)
        self.assertIsNone(self.endpoint.state()['io_map']['connection_class_revision'])
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.call(0x0E,child(attribute=1))[2],0)

    def test_gap_diagnostics_preserve_parent_and_child_class(self):
        self.assertEqual(self.call(0x0E,child(attribute=2))[2],0x14)
        row=self.endpoint.state()['attribute_gaps'][0]
        self.assertEqual((row['class_name'],row['class_id'],row['instance'],row['io_map_instance']),('I/O Connection',0x7E,0,1))
        self.assertEqual(row['attributes'],[{'id':2,'status':0x14,'name':'Attribute 2'}])
        self.assertIsNone(row['program_instance'])


class IOConnectionSignedTests(unittest.TestCase):
    setUp=native_tests.NativeSessionTests.setUp
    tearDown=native_tests.NativeSessionTests.tearDown
    cip=native_tests.NativeSessionTests.cip
    begin=native_tests.NativeSessionTests.begin
    signed=native_tests.NativeSessionTests.signed
    bind=native_tests.NativeSessionTests.bind

    def test_signed_reference_shape_accepts_revision_and_retains_write_denial(self):
        self.bind();before=copy.deepcopy(self.app.engine.memory.values)
        read=bytes.fromhex('030420692401207e240001000100')
        self.assertEqual(self.signed(4,read),bytes.fromhex('830000000100010000000100'))
        self.assertEqual(self.endpoint.state()['native_rejections'],[])
        self.assertEqual(self.signed(5,message(0x10,child(attribute=1),b'\2\0'))[2],15)
        row=self.endpoint.state()['native_rejections'][0]
        self.assertEqual((row['io_map_instance'],row['class_id'],row['instance'],row['reason']),(1,0x7E,0,'read_only_policy'))
        self.assertEqual(self.signed(6,read)[2],0)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_signed_batch_keeps_sequence_after_nested_errors(self):
        self.bind()
        read=message(0x0E,child(attribute=1))
        children=(read,message(0x0E,child(2,attribute=1)),
                  bytes.fromhex('030420692401207f240001000100'),read)
        raw=batch(children,sequence=4);raw=raw[:-20]+hmac.digest(KEY,raw[:-20],'sha1')
        result=signed_messages.verify_response(self.cip(raw),KEY,request=signed_messages.parse_request(raw))
        self.assertEqual([value[2] for value in result.children],[0,5,4,0])
        self.assertEqual(self.signed(5,read)[2],0)
        self.app.engine.project.io_map=IOMap(False)
        self.assertEqual(self.signed(6,read)[2],0x0C)


if __name__=='__main__':unittest.main()
