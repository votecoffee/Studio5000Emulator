"""Local Map identity reads require an explicit matching source and profile."""
import base64
import copy
from dataclasses import replace
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint,Session
from logixlab.server import Application
import test_io_map as maps


SINGLE=bytes.fromhex('0e03206924013002')
LIST=bytes.fromhex('03022069240101000200')


def route():
    result=maps.IOMapTests().local_route();result[2].attrib.update(ProductCode='168',Major='35',Minor='11')
    return result


class MapIdentityTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.app=Application(folder.name);self.addCleanup(self.app.close)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e');self.app.endpoint=self.endpoint
        self.load(route()[0])

    def load(self,root):
        self.app.command('load',{'name':'local.L5X','content':base64.b64encode(E.tostring(root)).decode()})

    def call(self,raw):return self.endpoint.router.handle(raw,Session())

    def test_list_single_and_duplicate_reads_share_explicit_identity_bytes_without_mutation(self):
        before=copy.deepcopy(self.app.engine.memory.values);identity=self.endpoint.identity
        expected=b''.join(identity.attributes()[n] for n in (1,2,3,4))
        self.assertEqual(expected,struct.pack('<HHHBB',1,14,168,35,11))
        self.assertEqual(self.call(SINGLE),b'\x8e\0\0\0'+expected)
        self.assertEqual(self.call(LIST),bytes.fromhex('83000000010002000000')+expected)
        duplicates=bytes.fromhex('030220692401020002000200')
        self.assertEqual(self.call(duplicates),bytes.fromhex('83000000020002000000')+expected+b'\2\0\0\0'+expected)
        self.endpoint.identity=replace(identity,serial=0x12345678,hardware_revision=(2,3))
        self.assertEqual(self.call(SINGLE),b'\x8e\0\0\0'+expected)
        self.assertIsNotNone(self.app.engine.project.io_map.local_identity)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)

    def test_mismatched_or_research_device_identity_cannot_supply_a_local_key(self):
        original=self.endpoint.identity
        for field,value in (('vendor',2),('vendor',True),('device_type',15),('product_code',212),('major',36),('minor',12),('profile','research')):
            self.endpoint.identity=replace(original,**{field:value})
            with self.subTest(field=field):self.assertNotEqual(self.call(SINGLE)[2],0)
            self.assertEqual(self.call(LIST),bytes.fromhex('83000a00010002001400'))
        self.endpoint.identity=original
        self.assertEqual(self.call(SINGLE)[2],0)

    def test_missing_conflicting_or_noncanonical_source_never_infers_identity(self):
        for field,value in (('ProductCode',None),('Major',None),('Minor',None),('ProductCode','212'),
                            ('Major','34'),('Minor','12'),('Minor','256'),('Major','+35'),('ProductCode','65536'),('ProductCode','9'*5000)):
            root,_,module,*_=route()
            if value is None:del module.attrib[field]
            else:module.set(field,value)
            self.load(root)
            with self.subTest(field=field,value=value):self.assertNotEqual(self.call(SINGLE)[2],0)
        root,controller,*_=route();E.SubElement(controller.find('Modules'),'Module',Name='Remote')
        self.load(root);self.assertNotEqual(self.call(SINGLE)[2],0)
        self.app.command('demo',{'sample':'ConveyorDemo'});self.assertNotEqual(self.call(SINGLE)[2],0)

    def test_registry_rechecks_project_hash_revision_and_foreign_project(self):
        project=self.app.engine.project;space=self.app.engine.runtime_references;identity=self.endpoint.identity
        self.assertIn(2,space.io_map_attributes(project,identity))
        project.minor_version='12';self.assertNotIn(2,space.io_map_attributes(project,identity));project.minor_version='11'
        digest=project.sha256;project.sha256='f'*64
        self.assertEqual(space.io_map_attributes(project,identity),{});project.sha256=digest
        self.assertEqual(space.io_map_attributes(copy.copy(project),identity),{})
        self.assertNotIn(2,space.io_map_attributes(project))

    def test_unknown_instances_partial_lists_and_writes_keep_their_existing_errors(self):
        self.assertEqual(self.call(bytes.fromhex('0e03206924023002'))[2],5)
        answer=self.call(bytes.fromhex('03022069240102000200ffff'))
        self.assertEqual(answer[:10],bytes.fromhex('83000a00020002000000'))
        self.assertEqual(answer[-4:],bytes.fromhex('ffff1400'))
        for service in (0x10,4):
            raw=(bytes.fromhex('1003206924013002') if service==0x10 else bytes.fromhex('04022069240101000200'))+bytes(8)
            self.assertNotEqual(self.call(raw)[2],0)


if __name__=='__main__':unittest.main()
