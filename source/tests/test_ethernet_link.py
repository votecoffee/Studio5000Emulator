"""Ethernet Link encodings use selected-interface observations, not defaults."""
import ctypes
from dataclasses import replace
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from logixlab.ethernet_link import LinkSnapshot, linux_link
from logixlab.ethernetip import Endpoint, Session
from logixlab.network_objects import InterfaceSnapshot
from logixlab.server import Application


class EthernetLinkTests(unittest.TestCase):
    def test_exact_wire_widths_and_negotiated_or_forced_state(self):
        link=LinkSnapshot(1000,True,True,True,True,2)
        self.assertEqual(link.attributes(),{1:struct.pack('<I',1000),2:struct.pack('<I',15),
            6:struct.pack('<HH',1,0),7:b'\2',8:b'\1',9:b'\1'})
        self.assertEqual(replace(link,autonegotiation=False).attributes()[6],struct.pack('<HH',2,1000))
        self.assertEqual(replace(link,autonegotiation=False).attributes()[2],struct.pack('<I',19))
        self.assertEqual(replace(link,enabled=False,carrier=False).attributes()[8],b'\2')
        self.assertEqual(replace(link,carrier=False).attributes()[8],b'\0')
        self.assertEqual(replace(link,full_duplex=False,autonegotiation=False).attributes()[6],struct.pack('<HH',0,1000))

    def test_invalid_driver_fields_cannot_form_a_snapshot(self):
        link=LinkSnapshot(1000,True,True,True,True,2)
        for fields in ({'speed':0},{'speed':-1},{'speed':65536},{'speed':True},
                       {'carrier':1},{'full_duplex':None},{'autonegotiation':'1'},
                       {'enabled':0},{'interface_type':4},{'interface_type':False}):
            with self.subTest(fields=fields),self.assertRaises(ValueError):replace(link,**fields)

    def test_linux_ioctl_is_get_only_and_uses_the_requested_interface(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'eth0';base.mkdir()
            for name,value in (('type','1'),('carrier','1'),('flags','0x1003')):
                (base/name).write_text(value)
            def ioctl(probe,operation,request):
                self.assertEqual(operation,0x8946);self.assertEqual(len(request),40)
                name,pointer=struct.unpack_from('16sP',request)
                self.assertEqual(name.rstrip(b'\0'),b'eth0')
                self.assertEqual(ctypes.string_at(pointer,4),struct.pack('=I',1))
                raw=bytearray(44);struct.pack_into('=H',raw,12,1000)
                raw[14]=1;raw[15]=0;raw[18]=1
                ctypes.memmove(pointer,bytes(raw),44)
            with patch('logixlab.ethernet_link.Path',return_value=root),patch.dict(sys.modules,{'fcntl':SimpleNamespace(ioctl=ioctl)}):
                self.assertEqual(linux_link('eth0'),LinkSnapshot(1000,True,True,True,True,2))

    def test_missing_non_ethernet_or_invalid_driver_observations_stay_unavailable(self):
        for name in ('.','..','../eth0','eth0/name','x'*16,None):self.assertIsNone(linux_link(name))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);base=root/'eth0';base.mkdir()
            with patch('logixlab.ethernet_link.Path',return_value=root):
                self.assertIsNone(linux_link('eth0'))
                (base/'type').write_text('772');self.assertIsNone(linux_link('eth0'))
                (base/'type').write_text('1');(base/'carrier').write_text('unknown');self.assertIsNone(linux_link('eth0'))
                (base/'carrier').write_text('1');(base/'flags').write_text('0x1')
                with patch.dict(sys.modules,{'fcntl':SimpleNamespace(ioctl=lambda *args:None)}):
                    self.assertIsNone(linux_link('eth0'))
                with patch.dict(sys.modules,{'fcntl':SimpleNamespace(ioctl=lambda *args:(_ for _ in ()).throw(OSError('unsupported')))}):
                    self.assertIsNone(linux_link('eth0'))

    def test_router_caches_selected_link_and_preserves_unsupported_counter_status(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            endpoint=Endpoint(app,0,True)
            link=LinkSnapshot(1000,True,True,True,True,2)
            snapshot=InterfaceSnapshot('127.0.0.1','255.0.0.0',name='test',link=link)
            raw=bytes.fromhex('030220f62401080001000200040005000600070008000900')
            try:
                with patch('logixlab.ethernetip.interface_snapshot',return_value=(snapshot,None)) as reader:
                    result=endpoint.router.handle(raw,Session())
                    expected=struct.pack('<H',8)
                    for attr in (1,2,4,5,6,7,8,9):
                        expected+=struct.pack('<HH',attr,0 if attr in link.attributes() else 0x14)+link.attributes().get(attr,b'')
                    self.assertEqual(result,b'\x83\0\x0A\0'+expected)
                    self.assertEqual(endpoint.router.handle(bytes.fromhex('0e0320f624013001'),Session())[4:],struct.pack('<I',1000))
                    reader.assert_called_once_with('127.0.0.1')
                for attr in (4,5):self.assertEqual(endpoint.router.handle(bytes.fromhex('0e0320f6240130')+bytes((attr,)),Session())[2],0x14)
                self.assertIn('ethernet_counters',link.description()['counter_status'])
            finally:app.close()

    def test_unavailable_link_does_not_invent_values_or_enable_network_setters(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'});endpoint=Endpoint(app,0,True)
            try:
                with patch('logixlab.ethernetip.interface_snapshot',return_value=(None,'unavailable')) as reader:
                    for attr in (1,2,3,6,7,8,9):
                        self.assertEqual(endpoint.router.handle(bytes.fromhex('0e0320f6240130')+bytes((attr,)),Session())[2],0x0C)
                    reader.assert_called_once()
                endpoint.interface_queried=False
                with patch('logixlab.ethernetip.interface_snapshot') as reader:
                    for service in (0x10,4,0x4C,5):
                        raw=bytes((service,3))+bytes.fromhex('20f624013006')+bytes(4)
                        self.assertEqual(endpoint.router.handle(raw,Session())[2],8)
                    reader.assert_not_called()
                self.assertEqual(endpoint.router.handle(bytes.fromhex('0e0320f624013001')+b'\0',Session())[2],0x15)
                self.assertEqual(endpoint.router.handle(bytes.fromhex('030220f624010100'),Session())[2],0x13)
            finally:app.close()


if __name__=='__main__':unittest.main()
