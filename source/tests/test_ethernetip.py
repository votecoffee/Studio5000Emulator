"""Wire-level behavior and negative controls for the research target."""
import copy
import socket
import struct
import tempfile
import unittest
from logixlab.server import Application
from logixlab.model import ModelError,Tag
from logixlab.ethernetip import Endpoint,decode_path,symbol_path,CIPError


H=struct.Struct('<HHII8sI')


class Client:
    def __init__(self,port,host='127.0.0.1'):
        self.socket=socket.create_connection((host,port),timeout=2);self.socket.settimeout(2);self.session=0

    def read(self,size):
        result=b''
        while len(result)<size:
            data=self.socket.recv(size-len(result))
            if not data:raise EOFError('Socket closed')
            result+=data
        return result

    def packet(self,command,body=b'',handle=None):
        self.socket.sendall(H.pack(command,len(body),self.session if handle is None else handle,0,b'TESTWIRE',0)+body)
        head=self.read(24);fields=H.unpack(head);return fields,self.read(fields[1])

    def register(self):
        head,data=self.packet(0x65,b'\x01\x00\x00\x00',0)
        assert head[3]==0 and data==b'\x01\x00\x00\x00';self.session=head[2]

    def cip(self,request,connection=None,sequence=0):
        if connection is None:address=(0,b'');payload=(0xB2,request);command=0x6F
        else:address=(0xA1,struct.pack('<I',connection));payload=(0xB1,struct.pack('<H',sequence)+request);command=0x70
        body=struct.pack('<IHH',0,0,2)+b''.join(struct.pack('<HH',k,len(d))+d for k,d in (address,payload))
        head,data=self.packet(command,body)
        if head[3]:return head[3],b''
        pos=8;items=[]
        for _ in range(2):
            kind,size=struct.unpack_from('<HH',data,pos);pos+=4;items.append((kind,data[pos:pos+size]));pos+=size
        assert pos==len(data)
        result=items[1][1]
        if connection is not None:assert struct.unpack_from('<H',result)[0]==sequence;result=result[2:]
        return 0,result

    def close(self):self.socket.close()


def request(service,name,data=b''):
    path=symbol_path(name);return bytes((service,len(path)//2))+path+data


def fo(large=False,slot=0,serial=0x3123):
    params=struct.pack('<I',0x42000000|4000) if large else struct.pack('<H',0x4200|500)
    path=bytes((1,slot))+b'\x20\x02\x24\x01'
    data=b'\x0A\x0E'+struct.pack('<IIHHI',0,0x87654321,serial,0x1234,0x12345678)+b'\x03\0\0\0'+struct.pack('<I',2000000)+params+struct.pack('<I',2000000)+params+bytes((0xA3,len(path)//2))+path
    return bytes((0x5B if large else 0x54,2))+b'\x20\x06\x24\x01'+data


class EtherNetIPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name);self.app.command('demo',{'sample':'TextLab'})
        self.endpoint=Endpoint(self.app,0,True).start();self.clients=[]

    def tearDown(self):
        for client in self.clients:client.close()
        self.endpoint.stop();self.tmp.cleanup()

    def client(self,register=True):
        c=Client(self.endpoint.port);self.clients.append(c)
        if register:c.register()
        return c

    def cip(self,raw,client=None):
        status,data=(client or self.client()).cip(raw);self.assertEqual(status,0);return data

    def value(self,name,client=None):
        result=self.cip(request(0x4C,name,b'\x01\x00'),client);self.assertEqual(result[:4],b'\xCC\0\0\0');return result[4:]

    def add(self,name,dtype,value,**kw):
        tag=Tag(name,dtype,value,**kw);self.app.engine.project.tags[tag.key.lower()]=tag
        self.app.engine.memory.values[tag.key.lower()]=copy.deepcopy(value)
        self.app.engine.project.initial[tag.key.lower()]=copy.deepcopy(value)

    def test_tcp_and_udp_discovery_identify_research_target(self):
        head,identity=self.client(False).packet(0x63,handle=0)
        self.assertEqual(head[3],0);self.assertIn(b'LogixLab v35 research target',identity)
        self.assertEqual(struct.unpack_from('<H',identity,24)[0],0xFFFF)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
            s.settimeout(2);s.sendto(H.pack(0x63,0,0,0,b'TESTWIRE',0),('127.0.0.1',self.endpoint.port));raw,_=s.recvfrom(4096)
        self.assertEqual(raw[24:],identity);self.assertEqual(raw[12:20],b'TESTWIRE')

    def test_discovery_services_interfaces_and_sender_context(self):
        for command in (4,0x64):
            head,data=self.client(False).packet(command,handle=0);self.assertEqual(head[3],0);self.assertEqual(head[4],b'TESTWIRE')
            self.assertIn(b'Communications',data) if command==4 else self.assertEqual(data,b'\0\0')

    def test_session_required_and_bound_to_connection(self):
        c=self.client(False);self.assertEqual(c.cip(request(0x4C,'Step',b'\1\0'))[0],0x64)
        a=self.client();b=self.client(False);b.session=a.session
        self.assertEqual(b.cip(request(0x4C,'Step',b'\1\0'))[0],0x64)

    def test_project_reset_invalidates_registered_session(self):
        c=self.client();self.app.command('reset',{})
        self.assertEqual(c.cip(request(0x4C,'Step',b'\1\0'))[0],0x64)

    def test_golden_read_tag_packet_and_scan_updates(self):
        # Read one DINT, symbolic Step: independently specified wire bytes.
        raw=b'\x4C\x03\x91\x04Step\x01\x00'
        self.assertEqual(self.cip(raw),b'\xCC\0\0\0\xC4\0\x02\0\0\0')
        self.app.command('step',{'count':3})
        self.assertEqual(self.value('ScanTotal'),b'\xC4\0\x03\0\0\0')

    def test_all_supported_atomic_wire_types(self):
        client=self.client()
        cases={'SINT':(0xC2,'b',-12),'INT':(0xC3,'h',-1234),'DINT':(0xC4,'i',-123456),'LINT':(0xC5,'q',-(2**62)),
               'USINT':(0xC6,'B',255),'UINT':(0xC7,'H',65535),'UDINT':(0xC8,'I',2**32-1),
               'ULINT':(0xC9,'Q',2**64-1),'REAL':(0xCA,'f',1.25),'BOOL':(0xC1,'B',True)}
        for dtype,(code,fmt,value) in cases.items():
            with self.subTest(dtype=dtype):
                name='Probe'+dtype;self.add(name,dtype,value)
                self.assertEqual(self.value(name,client),struct.pack('<H'+fmt,code,value))
                data=struct.pack('<HH'+fmt,code,1,0)
                self.assertEqual(self.cip(request(0x4D,name,data),client)[2],0)
                self.assertEqual(self.app.engine.memory.read(name),0)

    def test_tag_write_changes_same_memory_used_by_scans(self):
        self.assertEqual(self.cip(request(0x4D,'Step',struct.pack('<HHi',0xC4,1,7)))[2],0)
        self.app.command('step',{})
        self.assertEqual(self.app.engine.memory.read('AOITotal'),7)

    def test_network_read_only_default_and_opt_in_writes(self):
        self.endpoint.allow_writes=False
        result=self.cip(request(0x4D,'Step',struct.pack('<HHi',0xC4,1,9)))
        self.assertEqual(result[2],0x0F);self.assertEqual(self.app.engine.memory.read('Step'),2)

    def test_declared_external_access_constant_and_alias_are_enforced(self):
        self.add('Private','DINT',8,external_access='None');self.add('RO','DINT',9,external_access='Read Only')
        self.add('Fixed','DINT',10,constant=True);self.add('Leak','',None,alias='Private')
        for name in ('Private','Leak'):
            self.assertEqual(self.cip(request(0x4C,name,b'\1\0'))[2],0x0F)
        for name in ('RO','Fixed'):
            self.assertEqual(self.cip(request(0x4D,name,struct.pack('<HHi',0xC4,1,7)))[2],0x0F)
        self.assertEqual(struct.unpack('<Hi',self.value('RO')),(0xC4,9))

    def test_aoi_locals_are_not_network_tags(self):
        self.assertEqual(self.cip(request(0x4C,'Accumulator.Count',b'\1\0'))[2],0x0F)
        self.assertEqual(struct.unpack('<Hi',self.value('Accumulator.Total')),(0xC4,0))

    def test_unknown_values_return_error_without_fabricated_zero(self):
        self.add('Unknown','DINT',None)
        self.assertEqual(self.cip(request(0x4C,'Unknown',b'\1\0'))[2],0x0C)

    def test_arrays_and_atomic_structure_members(self):
        self.app.command('step',{})
        self.assertEqual(self.cip(request(0x4C,'Values[1]',b'\x03\0'))[4:],struct.pack('<Hiii',0xC4,3,6,9))
        self.assertEqual(self.cip(request(0x4D,'Values[3]',struct.pack('<HHii',0xC4,2,42,43)))[2],0)
        self.assertEqual(self.app.engine.memory.read('Values'),[0,3,6,42,43])

    def test_fragment_read_offset_and_partial_status(self):
        self.add('Many','DINT',list(range(300)))
        first=self.cip(request(0x4C,'Many',struct.pack('<H',300)));self.assertEqual(first[2],6)
        second=self.cip(request(0x52,'Many',struct.pack('<HI',300,len(first)-6)))
        self.assertEqual(second[4:6],b'\xC4\0');self.assertEqual(second[2],6)
        self.assertEqual(self.cip(request(0x52,'Many',struct.pack('<HI',300,1200)))[2],0x20)

    def test_failed_multi_element_write_leaves_memory_unchanged(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        for data in (struct.pack('<HHii',0xC4,2,1,2),struct.pack('<HHf',0xCA,1,2.0)):
            self.assertNotEqual(self.cip(request(0x4D,'Values[4]',data))[2],0)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_nan_write_and_noncanonical_bool_are_rejected(self):
        self.add('RealProbe','REAL',1.25)
        self.assertNotEqual(self.cip(request(0x4D,'RealProbe',struct.pack('<HHf',0xCA,1,float('nan'))))[2],0)
        self.assertEqual(self.app.engine.memory.read('RealProbe'),1.25)
        self.assertNotEqual(self.cip(request(0x4D,'Enable',b'\xC1\0\1\0\xff'))[2],0)

    def test_symbol_instances_and_atomic_inventory(self):
        raw=b'\x55\x03\x20\x6B\x25\0\0\0\x02\0\x01\0\x02\0'
        result=self.cip(raw);self.assertIn(result[2],(0,6));self.assertIn(b'AOITotal',result)
        symbols=self.endpoint.router.symbols();item=next(s for s in symbols if s['name']=='Step')
        path=b'\x20\x6B\x25\0'+struct.pack('<H',item['id'])
        self.assertEqual(self.cip(b'\x4C'+bytes((len(path)//2,))+path+b'\1\0')[4:],struct.pack('<Hi',0xC4,2))

    def test_unknown_values_do_not_renumber_later_symbol_instances(self):
        self.add('AAAUnknown','DINT',None);before=self.endpoint.router.symbols()
        self.app.engine.memory.write('AAAUnknown',42);self.assertEqual(self.endpoint.router.symbols(),before)

    def test_program_scoped_symbolic_and_instance_access(self):
        self.add('LocalProbe','DINT',77,scope='MainProgram')
        self.assertEqual(struct.unpack('<Hi',self.value('Program:MainProgram.LocalProbe')),(0xC4,77))
        sym=next(s for s in self.endpoint.router.symbols('MainProgram') if s['name']=='LocalProbe')
        path=symbol_path('Program:MainProgram')+b'\x20\x6B\x25\0'+struct.pack('<H',sym['id'])
        self.assertEqual(self.cip(b'\x4C'+bytes((len(path)//2,))+path+b'\1\0')[4:],struct.pack('<Hi',0xC4,77))

    def test_local_slot_zero_unconnected_send(self):
        child=request(0x4C,'Step',b'\1\0');data=b'\x0A\x0E'+struct.pack('<H',len(child))+child+b'\0'*(len(child)%2)+b'\1\0\1\0'
        self.assertEqual(self.cip(b'\x52\x02\x20\x06\x24\x01'+data)[:4],b'\xCC\0\0\0')
        self.assertEqual(self.cip(b'\x52\x02\x20\x06\x24\x01'+data[:-1]+b'\1')[2],5)

    def test_standard_and_large_forward_open_connected_read_and_close(self):
        for large in (False,True):
            c=self.client();opened=self.cip(fo(large),c);self.assertEqual(opened[2],0)
            connection=struct.unpack_from('<I',opened,4)[0]
            status,result=c.cip(request(0x4C,'Step',b'\1\0'),connection,1)
            self.assertEqual(status,0);self.assertEqual(result[4:],struct.pack('<Hi',0xC4,2))
            data=b'\x0A\x0E'+struct.pack('<HHI',0x3123,0x1234,0x12345678)+b'\3\0\1\0\x20\2\x24\1'
            self.assertEqual(self.cip(b'\x4E\x02\x20\6\x24\1'+data,c)[2],0)
            self.assertNotEqual(c.cip(request(0x4C,'Step',b'\1\0'),connection,2)[0],0)

    def test_connected_replay_is_not_reexecuted_and_stale_sequence_rejected(self):
        c=self.client();opened=self.cip(fo(),c);cid=struct.unpack_from('<I',opened,4)[0]
        raw=request(0x4C,'Step',b'\1\0');first=c.cip(raw,cid,2)
        self.app.engine.memory.write('Step',9);self.assertEqual(c.cip(raw,cid,2),first)
        self.assertNotEqual(c.cip(raw,cid,1)[0],0)
        self.assertNotEqual(c.cip(request(0x4C,'Sum',b'\1\0'),cid,2)[0],0)

    def test_forward_open_rejects_other_slot_and_duplicate_connection(self):
        self.assertEqual(self.cip(fo(slot=1))[2],5)
        c=self.client();self.assertEqual(self.cip(fo(),c)[2],0);self.assertEqual(self.cip(fo(),c)[2],1)

    def test_multiple_services_and_per_service_errors(self):
        items=[request(0x4C,'Step',b'\1\0'),request(0x4C,'NoSuchTag',b'\1\0')]
        body=struct.pack('<HHH',2,6,6+len(items[0]))+b''.join(items)
        result=self.cip(b'\x0A\x02\x20\2\x24\1'+body)
        self.assertEqual(result[2],0x1E);self.assertEqual(result[10:14],b'\xCC\0\0\0')

    def test_unknown_studio_service_is_rejected_and_traced(self):
        result=self.cip(b'\x4B\x02\x20\xAC\x24\x01')
        self.assertEqual(result[2],8);trace=self.endpoint.state(True)
        self.assertTrue(trace['unsupported']);self.assertTrue(any(e['request_hex']=='4b0220ac2401' for e in trace['events']))
        self.assertEqual(trace['studio_go_online'],'NOT IMPLEMENTED OR VERIFIED')

    def test_malformed_paths_and_payloads_never_modify_tags(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        bad=[b'',b'\x4D',b'\x4D\xff',b'\x4D\1\xFF\0',b'\x4D\2\x91\xffxx',
             request(0x4D,'Step',b'\xC4\0\1\0'),request(0x4D,'Step',b'\xC4\0\1\0'+b'\1'*5)]
        c=self.client()
        for data in bad:self.assertNotEqual(self.cip(data,c)[2],0)
        self.assertEqual(before,self.app.engine.memory.values)
        self.assertEqual(self.value('Step',c),struct.pack('<Hi',0xC4,2))

    def test_tcp_fragmentation_and_coalesced_frames(self):
        c=self.client(False);packet=H.pack(0x63,0,0,0,b'TESTWIRE',0)
        c.socket.sendall(packet[:7]);c.socket.sendall(packet[7:]+packet)
        for _ in range(2):
            head=H.unpack(c.read(24));self.assertEqual(head[0],0x63);self.assertIn(b'LogixLab',c.read(head[1]))

    def test_configuration_rejects_invalid_ports_and_write_flags(self):
        for port in (-1,65536,True,'44818'):
            with self.assertRaises(ModelError):Endpoint(self.app,port)
        with self.assertRaises(ModelError):Endpoint(self.app,0,'true')

    def test_application_start_stop_export_and_failed_bind(self):
        result=self.app.command('connectivity-start',{'port':0});self.assertTrue(result['connectivity']['enabled'])
        try:
            with self.assertRaises(ModelError):Endpoint(self.app,self.app.endpoint.port).start()
            trace=self.app.command('connectivity-trace',{});self.assertIn('events',trace)
            with self.assertRaises(ModelError):self.app.command('connectivity-start',{'port':0})
        finally:self.app.close()
        self.assertFalse(self.app.command('connectivity-stop',{})['connectivity']['enabled'])

    def test_small_negotiated_connection_bounds_fragment_response(self):
        self.add('Many','DINT',list(range(30)));c=self.client()
        opening=bytearray(fo());struct.pack_into('<H',opening,6+26,0x4200|32);struct.pack_into('<H',opening,6+32,0x4200|32)
        opened=self.cip(bytes(opening),c);self.assertEqual(opened[2],0);cid=struct.unpack_from('<I',opened,4)[0]
        status,result=c.cip(request(0x4C,'Many',struct.pack('<H',30)),cid,1)
        self.assertEqual(status,0);self.assertEqual(result[2],6);self.assertLessEqual(len(result)+2,32)

    def test_readonly_udt_member_rejects_write_and_alias_bypass(self):
        from xml.etree import ElementTree as E
        self.add('Pair','PAIR',{'A':5})
        schema=E.fromstring('<DataType><Members><Member Name="A" DataType="DINT" ExternalAccess="Read Only"/></Members></DataType>')
        self.app.engine.project.udts['pair']=schema;self.add('PairAlias','',None,alias='Pair.A')
        self.assertEqual(self.value('PairAlias'),struct.pack('<Hi',0xC4,5))
        self.assertEqual(self.cip(request(0x4D,'PairAlias',struct.pack('<HHi',0xC4,1,9)))[2],0x0F)

    def test_unregister_can_register_again_on_same_transport(self):
        c=self.client();old=c.session
        c.socket.sendall(H.pack(0x66,0,old,0,b'TESTWIRE',0));c.register()
        self.assertNotEqual(old,c.session);self.assertEqual(self.value('Step',c),struct.pack('<Hi',0xC4,2))

    def test_udp_does_not_allow_tag_services(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(2);sock.sendto(H.pack(0x6F,0,1,0,b'TESTWIRE',0),('127.0.0.1',self.endpoint.port));raw,_=sock.recvfrom(100)
        self.assertEqual(H.unpack(raw)[3],1);self.assertEqual(self.app.engine.memory.values,before)

    def test_identity_attribute_reads_and_malformed_cpf_are_rejected(self):
        self.assertEqual(self.cip(b'\x0E\x03\x20\1\x24\1\x30\1')[4:],b'\xFF\xFF')
        self.assertEqual(self.cip(b'\x0E\x03\x20\1\x24\1\x30\xFF')[2],0x14)
        c=self.client();head,_=c.packet(0x6F,b'\0'*8);self.assertEqual(head[3],3)
        self.assertEqual(self.value('Step',c),struct.pack('<Hi',0xC4,2))

    def test_tcp_peer_error_is_not_reflected_and_session_remains_usable(self):
        client=self.client()
        before=copy.deepcopy(self.app.engine.memory.values)
        # Observed Linx error reply followed by a legitimate request. The first
        # response must belong to that request, with no reflected error ahead.
        client.socket.sendall(H.pack(0x6F,0,client.session,3,b'TESTWIRE',0))
        header,identity=client.packet(0x63)
        self.assertEqual(header[0],0x63);self.assertEqual(header[3],0)
        self.assertIn(b'LogixLab',identity)
        self.assertEqual(self.value('Step',client),struct.pack('<Hi',0xC4,2))
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.endpoint.state()['counts']['peer_error'],1)

    def test_udp_peer_error_is_not_reflected_and_discovery_remains_usable(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.1)
            sock.sendto(H.pack(0x63,0,0,3,b'TESTWIRE',0),('127.0.0.1',self.endpoint.port))
            with self.assertRaises(socket.timeout):sock.recvfrom(4096)
            sock.settimeout(2)
            sock.sendto(H.pack(0x63,0,0,0,b'TESTWIRE',0),('127.0.0.1',self.endpoint.port))
            response,_=sock.recvfrom(4096)
            self.assertEqual(H.unpack_from(response)[3],0)
            self.assertIn(b'LogixLab',response[24:])
        self.assertEqual(self.endpoint.state()['counts']['peer_error'],1)


if __name__=='__main__':unittest.main()
