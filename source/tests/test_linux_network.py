"""Synthetic Linux address dumps and read-only secondary-address selection."""
from dataclasses import FrozenInstanceError
from contextlib import nullcontext
import socket
import struct
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from logixlab import linux_network as ln
from logixlab.network_objects import linux_snapshot

SEQUENCE=12345
PORT=876


def attr(kind,value):
    raw=struct.pack('=HH',len(value)+4,kind)+value
    return raw+bytes(-len(raw)%4)


def message(kind,payload=b'',flags=2,sequence=SEQUENCE,port=PORT):
    raw=struct.pack('=IHHII',len(payload)+16,kind,flags,sequence,port)+payload
    return raw+bytes(-len(raw)%4)


def address(local='192.0.2.130',prefix=24,index=7,attributes=None,family=socket.AF_INET,flags=0):
    attributes=attr(1,socket.inet_aton(local))+attr(2,socket.inet_aton(local)) if attributes is None else attributes
    return message(ln.RTM_NEWADDR,struct.pack('=BBBBI',family,prefix,flags,0,index)+attributes)


DONE=message(ln.NLMSG_DONE,struct.pack('=i',0))


class NetlinkParserTests(unittest.TestCase):
    def test_multiple_secondary_addresses_and_unknown_bounded_attributes_preserve_prefix_and_index(self):
        raw=address('192.0.2.128',24)+address('192.0.2.130',27)+DONE
        rows,done=ln.parse_datagram(raw,SEQUENCE,PORT)
        self.assertTrue(done);self.assertEqual(rows,(ln.IPv4Address(7,'192.0.2.128',24),ln.IPv4Address(7,'192.0.2.130',27)))
        raw=address(attributes=attr(99,b'unknown')+attr(2,socket.inet_aton('192.0.2.130')))
        self.assertEqual(ln.parse_datagram(raw,SEQUENCE,PORT)[0][0].address,'192.0.2.130')
        with self.assertRaises(FrozenInstanceError):rows[0].prefix=30

    def test_local_is_preferred_to_point_to_point_peer_and_address_only_is_supported(self):
        raw=address(attributes=attr(1,socket.inet_aton('192.0.2.1'))+attr(2,socket.inet_aton('192.0.2.130')))
        self.assertEqual(ln.parse_datagram(raw,SEQUENCE,PORT)[0][0].address,'192.0.2.130')
        raw=address(attributes=attr(1,socket.inet_aton('192.0.2.130')))
        self.assertEqual(ln.parse_datagram(raw,SEQUENCE,PORT)[0][0].address,'192.0.2.130')

    def test_sequence_sender_interruption_and_unexpected_message_are_rejected(self):
        raw=address()
        for value in (raw[:8]+struct.pack('=I',SEQUENCE+1)+raw[12:],raw[:12]+struct.pack('=I',PORT+1)+raw[16:],
                      message(ln.RTM_NEWADDR,raw[16:],flags=ln.NLM_F_DUMP_INTR),message(99)):
            with self.assertRaises(ValueError):ln.parse_datagram(value,SEQUENCE,PORT)
        kernel=raw[:12]+bytes(4)+raw[16:]
        self.assertEqual(len(ln.parse_datagram(kernel,SEQUENCE,PORT)[0]),1)

    def test_message_lengths_padding_and_data_after_done_are_checked(self):
        raw=address()
        for value in (b'',raw[:15],struct.pack('=I',15)+raw[4:],struct.pack('=I',len(raw)+1)+raw[4:],
                      raw[:-1],DONE+raw,DONE+b'\0',b'A'*(ln.MAX_DATAGRAM_BYTES+1)):
            with self.subTest(size=len(value)),self.assertRaises(ValueError):ln.parse_datagram(value,SEQUENCE,PORT)
        for sequence,port in ((True,PORT),(0,PORT),(SEQUENCE,True),(SEQUENCE,-1)):
            with self.assertRaises(ValueError):ln.parse_datagram(raw,sequence,port)

    def test_address_header_family_index_prefix_and_actual_local_address_are_validated(self):
        for value in (address(prefix=33),address(index=0),address(index=0xFFFFFFFF),address('0.0.0.0'),
                      address('224.0.0.1'),address(attributes=b''),message(ln.RTM_NEWADDR,bytes(7))):
            with self.assertRaises(ValueError):ln.parse_datagram(value,SEQUENCE,PORT)
        self.assertEqual(ln.parse_datagram(address(family=10,prefix=128),SEQUENCE,PORT),((),False))
        for flag in (0x08,0x40):
            self.assertEqual(ln.parse_datagram(address(flags=flag),SEQUENCE,PORT),((),False))

    def test_attribute_lengths_duplicates_flags_and_extended_address_flags_are_checked(self):
        local=attr(2,socket.inet_aton('192.0.2.130'))
        for attrs in (b'\1',struct.pack('=HH',3,2),struct.pack('=HH',12,2)+bytes(4),attr(2,bytes(3)),
                      local+local,attr(0x8002,bytes(4)),local+attr(8,bytes(3)),
                      local+struct.pack('=HH',5,99)+b'a\0'):
            with self.subTest(attrs=attrs.hex()),self.assertRaises(ValueError):
                ln.parse_datagram(address(attributes=attrs),SEQUENCE,PORT)
        raw=address(flags=0x40,attributes=local+attr(8,bytes(4)))
        self.assertEqual(len(ln.parse_datagram(raw,SEQUENCE,PORT)[0]),1)

    def test_done_and_error_require_successful_matching_request(self):
        self.assertTrue(ln.parse_datagram(message(ln.NLMSG_DONE),SEQUENCE,PORT)[1])
        original=struct.pack('=IHHII',24,ln.RTM_GETADDR,ln.NLM_F_REQUEST|ln.NLM_F_DUMP,SEQUENCE,0)
        ack=message(ln.NLMSG_ERROR,struct.pack('=i',0)+original)
        self.assertEqual(ln.parse_datagram(ack,SEQUENCE,PORT),((),False))
        with self.assertRaises(OSError):ln.parse_datagram(message(ln.NLMSG_ERROR,struct.pack('=i',-1)+original),SEQUENCE,PORT)
        for raw in (message(ln.NLMSG_DONE,b'\1'),message(ln.NLMSG_DONE,struct.pack('=i',-1)),
                    message(ln.NLMSG_ERROR,bytes(19)),message(ln.NLMSG_ERROR,bytes(20))):
            with self.assertRaises(ValueError):ln.parse_datagram(raw,SEQUENCE,PORT)


class FakeSocket:
    def __init__(self,packets=None):self.packets=packets;self.request=None;self.closed=False;self.calls=0
    def __enter__(self):return self
    def __exit__(self,*args):self.closed=True
    def bind(self,target):self.bound=target
    def getsockname(self):return PORT,0
    def sendto(self,raw,target):self.request=raw;self.target=target;return len(raw)
    def settimeout(self,value):self.timeout=value
    def recvmsg(self,limit):
        self.calls+=1
        if self.packets is None:
            seq=struct.unpack_from('=I',self.request,8)[0]
            raw=(address()+DONE).replace(struct.pack('=I',SEQUENCE),struct.pack('=I',seq))
            return raw,[],0,(0,0)
        if not self.packets:raise TimeoutError('no completion')
        return self.packets.pop(0)


class NetlinkReaderTests(unittest.TestCase):
    def run_reader(self,probe,**limits):
        with patch.object(ln.socket,'AF_NETLINK',16,create=True),patch.object(ln.socket,'MSG_TRUNC',32,create=True),\
             patch.object(ln.socket,'socket',return_value=probe),patch.object(ln.time,'monotonic_ns',return_value=SEQUENCE):
            with (patch.multiple(ln,**limits) if limits else nullcontext()):return ln.linux_ipv4_addresses()

    def test_request_is_get_only_and_complete_dump_returns_verified_rows(self):
        probe=FakeSocket();rows=self.run_reader(probe)
        self.assertEqual(rows,(ln.IPv4Address(7,'192.0.2.130',24),));self.assertTrue(probe.closed)
        self.assertEqual(struct.unpack('=IHHIIBBBBI',probe.request),
                         (24,ln.RTM_GETADDR,ln.NLM_F_REQUEST|ln.NLM_F_DUMP,SEQUENCE,0,socket.AF_INET,0,0,0,0))
        self.assertEqual(probe.bound,(0,0));self.assertEqual(probe.target,(0,0));self.assertLessEqual(probe.timeout,ln.DUMP_TIMEOUT_SECONDS)

    def test_partial_missing_done_non_kernel_and_truncated_datagrams_never_return_rows(self):
        for packet in ((address(),[],32,(0,0)),(address()+DONE,[],0,(123,0))):
            with self.assertRaises(ValueError):self.run_reader(FakeSocket([packet]))
        with self.assertRaises(TimeoutError):self.run_reader(FakeSocket([(address(),[],0,(0,0))]))

    def test_dump_count_byte_and_address_limits_are_bounded(self):
        for limit,value,packets in (('MAX_DATAGRAMS',1,[(address(),[],0,(0,0))]),
                ('MAX_TOTAL_BYTES',1,[(address()+DONE,[],0,(0,0))]),
                ('MAX_ADDRESSES',1,[(address()+address('192.0.2.131')+DONE,[],0,(0,0))])):
            with self.subTest(limit=limit),self.assertRaises(ValueError):self.run_reader(FakeSocket(packets),**{limit:value})


class LinuxSnapshotTests(unittest.TestCase):
    def snapshot(self,target,rows):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'proc/net').mkdir(parents=True);(root/'etc').mkdir()
            (root/'proc/net/route').write_text('Iface Destination Gateway Flags RefCnt Use Metric Mask\neth7 00000000 010200C0 0003 0 0 100 00000000\n')
            (root/'etc/resolv.conf').write_text('nameserver 192.0.2.53\n')
            with patch('logixlab.network_objects.linux_ipv4_addresses',return_value=rows),\
                 patch('logixlab.network_objects.socket.if_indextoname',return_value='eth7') as by_index,\
                 patch('logixlab.network_objects.Path',side_effect=lambda p:root/str(p).lstrip('/')),\
                 patch('logixlab.network_objects.linux_link',return_value=None),\
                 patch('logixlab.network_objects.linux_tcpip_configuration',return_value=None):
                result=linux_snapshot(target);by_index.assert_called_once_with(7);return result

    def test_secondary_address_uses_its_actual_prefix_and_interface_index(self):
        rows=(ln.IPv4Address(7,'192.0.2.128',24),ln.IPv4Address(7,'192.0.2.130',27))
        result=self.snapshot('192.0.2.130',rows)
        self.assertEqual((result.address,result.netmask,result.name,result.gateway),
                         ('192.0.2.130','255.255.255.224','eth7','192.0.2.1'))
        self.assertEqual(result.dns,('192.0.2.53',))

    def test_exact_loopback_prefix_wins_and_loopback_subnet_fallback_remains(self):
        rows=(ln.IPv4Address(7,'127.0.0.1',8),ln.IPv4Address(7,'127.0.0.2',32))
        self.assertEqual(self.snapshot('127.0.0.2',rows).netmask,'255.255.255.255')
        self.assertEqual(self.snapshot('127.0.0.3',rows).netmask,'255.0.0.0')

    def test_unassigned_non_loopback_address_cannot_borrow_primary_interface_metadata(self):
        with self.assertRaises(ValueError):self.snapshot('192.0.2.131',(ln.IPv4Address(7,'192.0.2.128',24),))


if __name__=='__main__':unittest.main()
