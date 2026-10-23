"""Repository registration is a source-checked, private download effect."""
import copy
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch
from logixlab.download_image import ImageError,Source
from logixlab.download_repository import DownloadRepository,HANDLE,expected
from logixlab.identity import Identity
from test_download_namespace import NamespaceFixture,ENUM
import test_download_controller as controllers
import test_programming_preparation as prep

REGISTER=bytes.fromhex('4b03210078032401')
LINK=bytes.fromhex('040220642401')


class RepositorySignedTests(NamespaceFixture,unittest.TestCase):
    def setUp(self):
        controllers.ControllerSignedTests.setUp(self)
        self.endpoint.identity=Identity.from_project('logix-v35-l85e',self.app.engine.project)
        self.source=self.namespace._source;self.project=self.app.engine.project;self.identity=self.endpoint.identity
        self.payload=expected(self.source,self.project,self.identity)[0]
        self.link=struct.pack('<HHI',1,8,HANDLE)
    complete_tasks=controllers.ControllerSignedTests.complete_tasks

    def configure(self):
        self.complete_tasks()
        self.assertEqual(self.send(bytes.fromhex('0402208e2401')+controllers.payload())[2],0)

    def test_registration_and_link_are_idempotent_private_and_discarded_at_end(self):
        self.assertEqual(self.send(REGISTER+self.payload)[2],12);self.configure()
        before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.send(LINK+self.link)[2],12)
        for _ in range(2):
            self.assertEqual(self.send(REGISTER+self.payload),b'\xcb\0\0\0'+struct.pack('<I',HANDLE))
            self.assertEqual(self.send(LINK+self.link),b'\x84\0\0\0'+struct.pack('<HHH',1,8,0))
        description=self.namespace.repository.description()
        self.assertTrue(description['registered'] and description['linked'] and description['source_bound'])
        self.assertFalse(description['operator_authorization'] or description['active_device_changed'] or description['commit'])
        self.assertEqual(self.send(bytes.fromhex('0e03206424013008'))[4:],bytes(4))
        self.assertIs(self.endpoint.identity,self.identity);self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.send(ENUM)[2],0);self.assertEqual(self.send(prep.END)[2],0)
        self.assertIsNone(self.endpoint.programming_lease.download_namespace)
        self.assertNotEqual(self.send(REGISTER+self.payload)[2],0)

    def test_foreign_unsigned_run_mode_and_wrong_scope_do_not_register(self):
        self.configure();raw=REGISTER+self.payload
        self.assertNotEqual(self.cip(raw)[2],0)
        first=self.client;second=self.second_client()
        try:
            self.client=second;self.assertEqual(self.signed(4,raw)[2],15)
        finally:self.client=first;second.close()
        with patch.object(self.app,'controller_state',return_value={'mode':'Run'}):self.assertEqual(self.send(raw)[2],12)
        for wrong in (bytes.fromhex('4b03210078032400'),bytes.fromhex('4b042100780324013001')):
            self.assertEqual(self.send(wrong+self.payload)[2],4)
        self.assertFalse(self.namespace.repository.description()['registered'])

    def test_changed_device_or_source_revokes_following_namespace_operations(self):
        self.configure();self.assertEqual(self.send(REGISTER+self.payload)[2],0)
        self.endpoint.identity=replace(self.identity,serial=self.identity.serial+1)
        self.assertEqual(self.send(ENUM)[2],12)
        self.endpoint.identity=self.identity
        self.assertEqual(self.send(ENUM)[2],0)
        self.project.name+='Other';self.assertEqual(self.send(ENUM)[2],12)

    def test_truncated_mismatched_records_and_wrong_handles_are_atomic(self):
        stage=DownloadRepository()
        for size in range(len(self.payload)):
            with self.assertRaises(ImageError):stage.register(self.payload[:size],self.source,self.project,self.identity)
        for bad in (self.payload+b'\0',bytes(4)+self.payload[4:],self.payload[:-2]+b'X\0'):
            with self.assertRaises(ImageError):stage.register(bad,self.source,self.project,self.identity)
        self.assertFalse(stage.description()['registered'])
        stage.register(self.payload,self.source,self.project,self.identity)
        for bad in (self.link[:-1],self.link+b'\0',struct.pack('<HHI',1,8,HANDLE+1),struct.pack('<HHI',1,7,HANDLE)):
            with self.assertRaises(ImageError):stage.link(bad,self.source,self.project,self.identity)
        self.assertFalse(stage.description()['linked'])
        stage.link(self.link,self.source,self.project,self.identity)
        for case in ('source','device','record','link','binding'):
            source=self.source;identity=self.identity;stage=DownloadRepository()
            stage.register(self.payload,source,self.project,identity)
            if case=='source':source=Source('c'*64,source.l5x_sha256)
            elif case=='device':identity=replace(identity,product_name='Other')
            elif case=='record':stage._record=b'other'
            elif case=='link':stage._linked=1
            else:stage._binding=None
            with self.subTest(case=case),self.assertRaises(ImageError):stage.validate(source,self.project,identity)


if __name__=='__main__':unittest.main()
