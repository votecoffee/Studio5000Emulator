"""TCP/IP flags require matching network configuration and a live DHCP client."""
import copy
from dataclasses import replace
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from logixlab.ethernetip import Endpoint, Session
from logixlab.network_objects import InterfaceSnapshot, cip_string
from logixlab.server import Application
from logixlab.tcpip_configuration import TcpIpConfiguration, linux_tcpip_configuration


CONFIG='auto eth0\niface eth0 inet dhcp\n'
CLIENT=b'/sbin/udhcpc\0-b\0-R\0-p\0/var/run/udhcpc.eth0.pid\0-i\0eth0\0'


class TcpIpReaderTests(unittest.TestCase):
    def read(self, config=CONFIG, pid='123\n', client=CLIENT, dns=('192.0.2.53',)):
        values={'/etc/network/interfaces':config, '/run/udhcpc.eth0.pid':pid,
                '/proc/123/cmdline':client}
        def read(path):
            value=values[path.as_posix()]
            if isinstance(value,Exception):raise value
            return value
        with patch.object(Path,'read_text',read),patch.object(Path,'read_bytes',read):
            return linux_tcpip_configuration('eth0',dns)

    def test_wire_flags_with_and_without_dns_do_not_advertise_cip_setters(self):
        for dns,capability,control in ((True,6,18),(False,6,2)):
            snapshot=TcpIpConfiguration(dns)
            self.assertEqual(snapshot.attributes(),{2:struct.pack('<I',capability),3:struct.pack('<I',control)})
            self.assertFalse(capability&16)
            self.assertFalse(snapshot.description()['configuration_settable'])
        with self.assertRaises(ValueError):TcpIpConfiguration(1)

    def test_recognizes_matching_interface_and_pid_file_with_optional_dns(self):
        self.assertEqual(self.read(),TcpIpConfiguration(True))
        self.assertEqual(self.read(dns=()),TcpIpConfiguration(False))
        self.assertEqual(self.read(config='# DHCP\n'+CONFIG+'iface eth0 inet6 auto\niface eth1 inet static\n'),TcpIpConfiguration(True))
        self.assertEqual(self.read(client=CLIENT.replace(b'/var/run/',b'/run/')),TcpIpConfiguration(True))

    def test_static_missing_duplicate_included_and_mapped_definitions_are_unknown(self):
        for text in ('',CONFIG.replace('dhcp','static'),CONFIG+CONFIG,
                     CONFIG+'source /etc/network/interfaces.d/*\n',
                     CONFIG+'source-directory interfaces.d\n',CONFIG+'mapping eth0\n',
                     CONFIG.replace('inet dhcp','inet dhcp extra'),CONFIG+'iface eth0\n','x'*65537):
            with self.subTest(text=text[:80]):self.assertIsNone(self.read(config=text))

    def test_pid_files_must_identify_one_positive_decimal_process(self):
        for pid in ('','0','-1','0x7B','123/../1','123 456','9'*11,'abc'):
            with self.subTest(pid=pid):self.assertIsNone(self.read(pid=pid))

    def test_clients_must_match_executable_interface_and_pid_file(self):
        for raw in (b'',CLIENT[:-1],CLIENT.replace(b'udhcpc\0',b'other\0'),
                    CLIENT.replace(b'-i\0eth0',b'-i\0eth1'),CLIENT+b'-i\0eth0\0',
                    CLIENT.replace(b'-i\0eth0\0',b'-i\0'),
                    CLIENT.replace(b'/var/run/udhcpc.eth0.pid',b'/tmp/client.pid'),
                    CLIENT.replace(b'-p\0/var/run/udhcpc.eth0.pid\0',b''),
                    CLIENT+b'-p\0/run/udhcpc.eth0.pid\0',b'\xff\0',b'x'*8193+b'\0'):
            with self.subTest(raw=raw[:80]):self.assertIsNone(self.read(client=raw))

    def test_invalid_interface_names_do_not_read_files(self):
        with patch.object(Path,'read_text') as reader:
            for name in (None,'','..','.', '../eth0','eth0/alias','x'*16,'eth0\0'):
                self.assertIsNone(linux_tcpip_configuration(name,()))
            reader.assert_not_called()

    def test_missing_permissions_and_undecodable_files_are_unavailable(self):
        for field in ('config','pid','client'):
            for error in (FileNotFoundError(),PermissionError(),UnicodeError()):
                with self.subTest(field=field,error=type(error).__name__):
                    self.assertIsNone(self.read(**{field:error}))


class TcpIpRouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=Endpoint(self.app,0,True);self.app.endpoint=self.endpoint
        self.snapshot=InterfaceSnapshot('127.0.0.1','255.0.0.0',name='eth0',
                                       tcpip=TcpIpConfiguration(True))

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def cip(self,raw):return self.endpoint.router.handle(bytes.fromhex(raw),Session())

    def test_native_requested_list_has_exact_field_widths_and_reuses_interface_snapshot(self):
        with patch('logixlab.ethernetip.interface_snapshot',return_value=(self.snapshot,None)) as reader, \
             patch('socket.gethostname',return_value='lab-vm'):
            result=self.cip('030220f52401050001000200030005000600')
            expected=struct.pack('<H',5)
            values={1:struct.pack('<I',1),**self.snapshot.tcpip.attributes(),
                    5:self.snapshot.configuration(),6:cip_string('lab-vm')}
            for attr in (1,2,3,5,6):expected+=struct.pack('<HH',attr,0)+values[attr]
            self.assertEqual(result,b'\x83\0\0\0'+expected)
            self.assertEqual(self.cip('0e0320f524013003'),b'\x8E\0\0\0'+struct.pack('<I',18))
            reader.assert_called_once_with('127.0.0.1')
        self.assertEqual(self.app.connectivity()['network_interface']['tcpip_configuration']['startup'],'DHCP')

    def test_unknown_manager_retains_configuration_status_and_individual_errors(self):
        snapshot=replace(self.snapshot,tcpip=None)
        with patch('logixlab.ethernetip.interface_snapshot',return_value=(snapshot,None)):
            self.assertEqual(self.cip('0e0320f524013001'),b'\x8E\0\0\0\1\0\0\0')
            for attr in ('02','03'):self.assertEqual(self.cip('0e0320f5240130'+attr)[2],0x0C)
            self.assertEqual(self.cip('030220f524010300010002000300'),
                             bytes.fromhex('83000a00030001000000010000000200140003001400'))
        self.assertEqual([a['id'] for a in self.endpoint.state()['attribute_gaps'][0]['attributes']],[2,3])

    def test_missing_ipv4_configuration_never_reports_configured_or_guesses_a_mode(self):
        with patch('logixlab.ethernetip.interface_snapshot',return_value=(None,'unavailable')):
            for attr in ('01','02','03'):self.assertEqual(self.cip('0e0320f5240130'+attr)[2],0x0C)
            self.assertEqual(self.cip('030220f524010300010002000300')[2],0x0C)

    def test_setters_unknown_fields_and_malformed_reads_do_not_query_os_or_change_tags(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        with patch('logixlab.ethernetip.interface_snapshot') as reader:
            for raw,status in (('100320f52401300300000000',8),
                               ('040220f524010100030000000000',8),
                               ('0e0320f524013063',0x14),('0e0320f52401300100',0x15),
                               ('030220f5240103000100',0x13),('030220f524010000',3)):
                with self.subTest(raw=raw):self.assertEqual(self.cip(raw)[2],status)
            reader.assert_not_called()
        self.assertEqual(self.app.engine.memory.values,before)


if __name__=='__main__':unittest.main()
