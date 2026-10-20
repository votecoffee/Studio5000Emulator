"""Read-only Linux IPv4 address enumeration, including secondary addresses.

Uses the Linux RTM_GETADDR/ifaddrmsg interface without an external `ip` command.
Only a completed, bounded kernel dump is returned; partial dumps never describe
an interface. See Linux uAPI linux/netlink.h, rtnetlink.h and if_addr.h.
"""
from dataclasses import dataclass
import ipaddress
import socket
import struct
import time

NETLINK_ROUTE=0
RTM_NEWADDR=20
RTM_GETADDR=22
NLM_F_REQUEST=1
NLM_F_DUMP=0x300
NLM_F_DUMP_INTR=0x10
NLMSG_NOOP=1
NLMSG_ERROR=2
NLMSG_DONE=3
MAX_DATAGRAM_BYTES=65536
MAX_TOTAL_BYTES=1024*1024
MAX_DATAGRAMS=64
MAX_ADDRESSES=4096
DUMP_TIMEOUT_SECONDS=2.0


@dataclass(frozen=True)
class IPv4Address:
    index:int
    address:str
    prefix:int


def _aligned(size):return (size+3)&~3


def _address(payload):
    if len(payload)<8:raise ValueError('Truncated Linux address header')
    family,prefix,flags,scope,index=struct.unpack_from('=BBBBI',payload)
    if family!=socket.AF_INET:return None
    if not 0<=prefix<=32 or not 1<=index<=0x7FFFFFFF:
        raise ValueError('Invalid Linux IPv4 index or prefix')
    values={};position=8
    while position<len(payload):
        if position+4>len(payload):raise ValueError('Truncated Linux address attribute')
        size,kind=struct.unpack_from('=HH',payload,position)
        end=position+size
        if size<4 or end>len(payload):raise ValueError('Invalid Linux address attribute length')
        if kind in (1,2,8):
            if kind in values or size!=8:raise ValueError('Invalid or duplicate Linux IPv4 attribute')
            values[kind]=payload[position+4:end]
        elif kind&0x3FFF in (1,2,8):
            raise ValueError('Unsupported Linux IPv4 attribute flags')
        position=_aligned(end)
        if position>len(payload) and end!=len(payload):raise ValueError('Truncated Linux address attribute padding')
    if 8 in values:flags=struct.unpack('=I',values[8])[0]
    if flags&(0x08|0x40):return None  # DAD failed or tentative addresses cannot identify a live endpoint.
    local=values.get(2,values.get(1))  # IFA_LOCAL differs from the peer in point-to-point configurations.
    if local is None:raise ValueError('Linux IPv4 address is unavailable')
    address=ipaddress.IPv4Address(local)
    if address.is_unspecified or address.is_multicast:raise ValueError('Invalid local Linux IPv4 address')
    return IPv4Address(index,str(address),prefix)


def parse_datagram(raw,sequence,port_id=0):
    """Decode one kernel datagram; the caller must wait for a matching DONE."""
    if not isinstance(raw,bytes) or not 1<=len(raw)<=MAX_DATAGRAM_BYTES:
        raise ValueError('Linux IPv4 datagram size limit')
    if type(sequence) is not int or not 1<=sequence<=0xFFFFFFFF or type(port_id) is not int or not 0<=port_id<=0xFFFFFFFF:
        raise ValueError('Invalid Linux IPv4 query identity')
    position=0;rows=[];done=False
    while position<len(raw):
        if done:raise ValueError('Data follows Linux IPv4 dump completion')
        if position+16>len(raw):raise ValueError('Truncated Linux netlink header')
        size,kind,flags,reply_sequence,sender=struct.unpack_from('=IHHII',raw,position)
        end=position+size
        if size<16 or end>len(raw):raise ValueError('Invalid Linux netlink message length')
        if reply_sequence!=sequence or sender not in (0,port_id):
            raise ValueError('Linux IPv4 query identity mismatch')
        if flags&NLM_F_DUMP_INTR:raise ValueError('Linux IPv4 dump was interrupted')
        payload=raw[position+16:end]
        if kind==RTM_NEWADDR:
            row=_address(payload)
            if row is not None:rows.append(row)
            if len(rows)>MAX_ADDRESSES:raise ValueError('Linux IPv4 address count limit')
        elif kind==NLMSG_DONE:
            if payload and (len(payload)<4 or struct.unpack_from('=i',payload)[0]!=0):
                raise ValueError('Linux IPv4 dump completion failed')
            done=True
        elif kind==NLMSG_ERROR:
            if len(payload)<20:raise ValueError('Truncated Linux netlink error')
            error=struct.unpack_from('=i',payload)[0]
            original_size,original_kind,_,original_sequence,_=struct.unpack_from('=IHHII',payload,4)
            if original_size<24 or original_kind!=RTM_GETADDR or original_sequence!=sequence:
                raise ValueError('Linux IPv4 error identity mismatch')
            if error:raise OSError(abs(error),'Linux IPv4 address dump failed')
        elif kind!=NLMSG_NOOP:raise ValueError('Unexpected Linux IPv4 dump message')
        position=_aligned(end)
        if position>len(raw) and end!=len(raw):raise ValueError('Truncated Linux netlink padding')
    return tuple(rows),done


def linux_ipv4_addresses():
    """Return every complete IPv4 address/prefix, without changing adapters."""
    if not hasattr(socket,'AF_NETLINK'):raise OSError('Linux netlink is unavailable')
    sequence=(time.monotonic_ns()&0xFFFFFFFF) or 1
    request=struct.pack('=IHHII',24,RTM_GETADDR,NLM_F_REQUEST|NLM_F_DUMP,sequence,0)
    request+=struct.pack('=BBBBI',socket.AF_INET,0,0,0,0)
    deadline=time.monotonic()+DUMP_TIMEOUT_SECONDS;total=0;rows=[]
    with socket.socket(socket.AF_NETLINK,socket.SOCK_RAW,NETLINK_ROUTE) as probe:
        probe.bind((0,0));port_id=probe.getsockname()[0]
        if type(port_id) is not int or not 1<=port_id<=0xFFFFFFFF:
            raise ValueError('Invalid Linux netlink port')
        if probe.sendto(request,(0,0))!=len(request):raise OSError('Incomplete Linux IPv4 dump request')
        for _ in range(MAX_DATAGRAMS):
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Linux IPv4 address dump timed out')
            probe.settimeout(remaining)
            raw,ancillary,flags,sender=probe.recvmsg(MAX_DATAGRAM_BYTES)
            if flags&socket.MSG_TRUNC or sender!=(0,0):raise ValueError('Truncated or non-kernel Linux IPv4 reply')
            total+=len(raw)
            if total>MAX_TOTAL_BYTES:raise ValueError('Linux IPv4 dump byte limit')
            found,done=parse_datagram(raw,sequence,port_id);rows.extend(found)
            if len(rows)>MAX_ADDRESSES:raise ValueError('Linux IPv4 address count limit')
            if done:return tuple(rows)
    raise ValueError('Linux IPv4 dump datagram limit')
