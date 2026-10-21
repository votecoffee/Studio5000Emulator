"""Supplemental schema discovery never grants instance or allocation access."""
import copy
import struct
import tempfile
import unittest
from logixlab import controller_schemas
from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.server import Application


class ControllerSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True)
        self.app.endpoint=self.endpoint

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def send(self,raw):return self.endpoint.router.handle(raw,Session())

    def test_reference_class_queries_report_uint_schema_revision_without_instance_data(self):
        self.assertEqual(self.send(bytes.fromhex('03022072240001000100')),bytes.fromhex('830000000100010000000500'))
        self.assertEqual(self.send(bytes.fromhex('0e03207224003001')),bytes.fromhex('8e0000000500'))
        self.assertEqual(controller_schemas.class_attributes(0x72),{1:b'\5\0'})
        self.assertEqual(self.send(bytes.fromhex('03022066240001000100')),bytes.fromhex('830000000100010000000300'))
        self.assertEqual(self.send(bytes.fromhex('0e03206624003001')),bytes.fromhex('8e0000000300'))
        before=copy.deepcopy(self.app.engine.memory.values)
        for cls in (0x66,0x72):
            for instance in (1,2,255):
                for service in (3,0x0E,0x4B,0x4D):
                    self.assertEqual(self.send(bytes((service,2,0x20,cls,0x24,instance)))[2],5)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_class_catalog_only_advertises_user_memory_in_native_compatibility(self):
        def classes():
            reply=self.send(bytes.fromhex('010220022401'));self.assertEqual(reply[2],0)
            count=struct.unpack_from('<H',reply,4)[0]
            return struct.unpack_from('<'+'H'*count,reply,6)
        self.assertIn(0x72,classes())
        self.assertIn(0x66,classes())
        self.endpoint.native_read_only=False
        self.assertNotIn(0x72,classes())
        self.assertNotIn(0x66,classes())
        self.assertEqual(self.send(bytes.fromhex('0e03207224003001'))[2],8)

    def test_unknown_pool_counts_and_mixed_list_fields_remain_errors(self):
        self.assertEqual(self.send(bytes.fromhex('0302207224000300020001000300')),
                         bytes.fromhex('83000a0003000200140001000000050003001400'))
        for attr in (2,3,4,100):
            self.assertEqual(self.send(bytes((0x0E,3,0x20,0x72,0x24,0,0x30,attr)))[2],0x14)

    def test_invalid_paths_payloads_and_mutating_services_do_not_change_model(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        for raw in ('0e0320722400300100','0302207224000000','0302207224000100',
                    '030320722400300101000100','010220722400','10032072240030010500',
                    '4b0220722400','4c0220722400','4d0220722400'):
            self.assertNotEqual(self.send(bytes.fromhex(raw))[2],0)
        for path in (bytes.fromhex('2072'),bytes.fromhex('20722400')+symbol_path('Extra'),
                     bytes.fromhex('2068240120722400')):
            self.assertEqual(self.send(bytes((0x0E,len(path)//2))+path+b'\x30\1')[2],4)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0)
        self.assertFalse(self.endpoint.allow_writes)

    def test_metadata_explicitly_limits_the_supported_subset(self):
        self.endpoint.start()
        info=self.endpoint.state()['controller_schemas']
        self.assertEqual([(row['class_id'],row['schema_revision']) for row in info['classes']],[(0x66,3),(0x72,5)])
        self.assertIsNone(info['classes'][0]['name'])
        for key in ('instance_attributes','capacity_reporting','pool_addresses','allocation_services','native_controller_equivalence'):
            self.assertFalse(info[key])
        self.endpoint.native_read_only=False;self.assertIsNone(self.endpoint.state()['controller_schemas'])


if __name__=='__main__':unittest.main()
