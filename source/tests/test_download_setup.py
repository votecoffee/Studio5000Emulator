"""Prepared setup writes preserve source values, active state and atomicity."""
import copy
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch
from logixlab.download_image import ImageError
from logixlab.download_setup import DownloadSetup,SetupBindings
from logixlab.ethernetip import Session
from logixlab.ethernet_link import LinkSnapshot
from logixlab.network_objects import InterfaceSnapshot
from logixlab.pccc_mapping import PcccMapping
from logixlab.time_sync import TimeSync
from logixlab.wall_clock import WallClock
from test_download_namespace import NamespaceFixture,ENUM
import test_download_repository as repository
import test_download_controller as controllers
import test_programming_preparation as prep


def request(class_id,payload):return bytes((4,2,0x20,class_id,0x24,1))+payload
def text(value):
    raw=value.encode('ascii');return struct.pack('<H',len(raw))+raw


class SetupSignedTests(NamespaceFixture,unittest.TestCase):
    def setUp(self):
        repository.RepositorySignedTests.setUp(self)
        self.project.controller_configuration=replace(self.project.controller_configuration,project_description='Source description')
        self.project.pccc_mapping=PcccMapping(True);self.project.time_sync=TimeSync(False,128,128)
        self.project.wall_clock=WallClock(True)
        self.endpoint.interface=InterfaceSnapshot('127.0.0.1','255.0.0.0',name='test',
            link=LinkSnapshot(1000,True,True,True,True,2))
        self.endpoint.interface_queried=True
        self.payloads={0xF6:bytes.fromhex('0100090001'),
            0x64:bytes.fromhex('06000100')+text(self.project.name)+b'\2\0'+text('Source description')+
                bytes.fromhex('0300000006000000070000000800')+struct.pack('<I',repository.HANDLE),
            0x67:bytes.fromhex('020001000000020000000000'),
            0x43:bytes.fromhex('0300100080110080010000'),0x8B:bytes.fromhex('02000400000002000000')}
    complete_tasks=controllers.ControllerSignedTests.complete_tasks
    configure=repository.RepositorySignedTests.configure

    def ready_setup(self):
        self.configure()
        self.assertEqual(self.send(repository.REGISTER+self.payload)[2],0)
        self.assertEqual(self.send(repository.LINK+self.link)[2],0)

    def bindings(self):return SetupBindings(self.project,self.namespace,self.identity,self.endpoint.interface)

    def test_all_five_setup_writes_have_exact_private_readback_without_active_changes(self):
        self.ready_setup();before=copy.deepcopy(self.app.engine.memory.values)
        source=(self.project.controller_configuration,self.project.pccc_mapping,self.project.time_sync,self.project.wall_clock)
        for _ in range(2):
            for class_id,payload in self.payloads.items():self.assertEqual(self.send(request(class_id,payload))[2],0)
        stage=self.namespace.setup;bindings=self.bindings()
        self.assertEqual(stage.description()['attributes'],14)
        self.assertEqual(stage.read(0x64,2,bindings),text('Source description'))
        self.assertEqual(stage.read(0x64,6,bindings),bytes(2))
        self.assertEqual(stage.read(0x64,8,bindings),struct.pack('<I',repository.HANDLE))
        self.assertEqual(stage.read(0xF6,9,bindings),b'\1')
        for cls,attr,value in ((0x43,16,b'\x80'),(0x43,17,b'\x80'),(0x43,1,b'\0'),
                               (0x67,1,bytes(2)),(0x67,2,bytes(4)),(0x8B,2,bytes(2)),(0x8B,4,bytes(2))):
            self.assertEqual(stage.read(cls,attr,bindings),value)
        self.assertEqual(self.send(bytes.fromhex('0e03206424013006'))[4:],text('en-US'))
        self.assertEqual(self.send(bytes.fromhex('0e03206424013008'))[4:],bytes(4))
        self.assertEqual(source,(self.project.controller_configuration,self.project.pccc_mapping,self.project.time_sync,self.project.wall_clock))
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        for key in ('active_configuration_changed','host_network_changed','clock_changed','operator_authorization','commit'):
            self.assertFalse(stage.description()[key])
        self.assertEqual(self.send(ENUM)[2],0);self.assertEqual(self.send(prep.END)[2],0)
        self.assertIsNone(self.endpoint.programming_lease.download_namespace)

    def test_setup_requires_linked_repository_and_rejects_foreign_unsigned_and_run_writes(self):
        self.configure()
        for cls,payload in self.payloads.items():self.assertEqual(self.send(request(cls,payload))[2],12)
        self.assertEqual(self.send(repository.REGISTER+self.payload)[2],0)
        self.assertEqual(self.send(request(0x67,self.payloads[0x67]))[2],12)
        self.assertEqual(self.send(repository.LINK+self.link)[2],0)
        first=self.client;second=self.second_client()
        try:
            self.client=second
            for cls,payload in self.payloads.items():self.assertEqual(self.signed(4+list(self.payloads).index(cls),request(cls,payload))[2],15)
        finally:self.client=first;second.close()
        for cls,payload in self.payloads.items():
            self.assertNotEqual(self.cip(request(cls,payload))[2],0)
            with patch.object(self.app,'controller_state',return_value={'mode':'Run'}):
                self.assertEqual(self.send(request(cls,payload))[2],12)
        self.assertEqual(self.namespace.setup.description()['attributes'],0)

    def test_truncation_unknown_values_order_and_wrong_reference_are_atomic(self):
        self.ready_setup();stage=DownloadSetup();bindings=self.bindings()
        stage.stage(0x67,self.payloads[0x67],bindings)
        for cls,payload in self.payloads.items():
            for end in range(len(payload)):
                with self.subTest(cls=cls,end=end),self.assertRaises(ImageError):stage.stage(cls,payload[:end],bindings)
            for wrong in (payload+b'\0',payload[:2]+b'\xff\xff'+payload[4:],payload[:-1]+bytes((payload[-1]^1,))):
                with self.assertRaises(ImageError):stage.stage(cls,wrong,bindings)
            self.assertEqual(stage.description()['classes'],[0x67])
        for cls in (True,0x8E,0x334):
            with self.assertRaises(ImageError):stage.stage(cls,b'\0\0',bindings)
        self.assertEqual(stage.read(0x67,2,bindings),bytes(4))
        for cls,attr in ((True,1),(0x67,True),(0x67,3),(0x43,1)):
            with self.assertRaises(ImageError):stage.read(cls,attr,bindings)

    def test_changed_source_interface_and_retained_effects_revoke_readback(self):
        self.ready_setup()
        for cls,payload in self.payloads.items():self.namespace.setup.stage(cls,payload,self.bindings())
        initial=(self.project.time_sync,self.endpoint.interface,self.namespace.repository._linked)
        for case in ('time','interface','repository','value','binding','digest'):
            stage=copy.copy(self.namespace.setup)
            if case=='time':self.project.time_sync=replace(initial[0],priority1=1)
            elif case=='interface':self.endpoint.interface=replace(initial[1],name='other')
            elif case=='repository':self.namespace.repository._linked=False
            elif case=='value':stage._values={**stage._values,0x67:{1:bytes(2),2:b'X'*4}}
            elif case=='binding':stage._bindings={}
            else:stage._digest='0'*64
            with self.subTest(case=case),self.assertRaises(ImageError):stage.read(0x67,2,self.bindings())
            self.project.time_sync,self.endpoint.interface,self.namespace.repository._linked=initial
        self.project.time_sync=replace(initial[0],priority2=1)
        self.assertEqual(self.send(ENUM)[2],12)

    def test_unavailable_source_and_disabled_link_do_not_become_enabled_defaults(self):
        self.ready_setup();stage=DownloadSetup()
        for cls,name,bad in ((0x67,'pccc_mapping',PcccMapping(False)),(0x43,'time_sync',TimeSync()),(0x8B,'wall_clock',WallClock())):
            old=getattr(self.project,name);setattr(self.project,name,bad)
            with self.assertRaises(ImageError):stage.stage(cls,self.payloads[cls],self.bindings())
            setattr(self.project,name,old)
        for interface in (None,replace(self.endpoint.interface,link=None),
                          replace(self.endpoint.interface,link=replace(self.endpoint.interface.link,enabled=False))):
            bindings=SetupBindings(self.project,self.namespace,self.identity,interface)
            with self.assertRaises(ImageError):stage.stage(0xF6,self.payloads[0xF6],bindings)
        self.assertEqual(stage.description()['attributes'],0)

    def test_reply_budget_and_wrong_scopes_reject_before_publication(self):
        self.ready_setup();router=self.endpoint.router;native=self.endpoint.programming_lease.owner
        for cls,payload in self.payloads.items():
            raw=request(cls,payload)
            self.assertEqual(router.native_read(raw,Session(),native,0,7,None,registration=False)[2],0x1B)
            self.assertEqual(self.send(bytes((4,2,0x20,cls,0x24,0))+payload)[2],4)
            self.assertEqual(self.send(bytes((4,3,0x20,cls,0x24,1,0x30,1))+payload)[2],4)
        self.assertEqual(self.namespace.setup.description()['attributes'],0)


if __name__=='__main__':unittest.main()
