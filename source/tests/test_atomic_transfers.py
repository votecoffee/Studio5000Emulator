import copy
import struct
import tempfile
import unittest
from logixlab.server import Application
from logixlab.model import Tag
from logixlab.ethernetip import Endpoint
from test_ethernetip import Client,request,fo


class AtomicTransferTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'TextLab'});self.endpoint=Endpoint(self.app,0,True).start()
        self.client=Client(self.endpoint.port);self.client.register()

    def tearDown(self):
        self.client.close();self.endpoint.stop();self.app.close();self.tmp.cleanup()

    def add(self,name,dtype,value,**kwargs):
        tag=Tag(name,dtype,value,**kwargs);key=tag.key.lower()
        self.app.engine.project.tags[key]=tag;self.app.engine.memory.values[key]=copy.deepcopy(value)

    def cip(self,service,name,data):
        status,result=self.client.cip(request(service,name,data));self.assertEqual(status,0);return result

    def fragment(self,name,count,offset,payload,code=0xC4):
        return self.cip(0x53,name,struct.pack('<HHI',code,count,offset)+payload)

    def rmw(self,name,size,or_mask,and_mask):
        return self.cip(0x4E,name,struct.pack('<H',size)+or_mask.to_bytes(size,'little')+and_mask.to_bytes(size,'little'))

    def test_fragment_writes_can_split_integer_atoms_and_preserve_surrounding_bytes(self):
        self.add('Block','DINT',[0x11223344,0x55667788,0x01020304])
        self.assertEqual(self.fragment('Block',3,3,b'\xAA\xBB\xCC\xDD\xEE\xFF'),b'\xD3\0\0\0')
        expected=struct.unpack('<iii',bytes.fromhex('443322aabbccddeeff030201'))
        self.assertEqual(self.app.engine.memory.read('Block'),list(expected))

    def test_complete_atom_fragment_can_establish_unknown_value(self):
        self.add('Unknown','DINT',None)
        self.assertEqual(self.fragment('Unknown',1,0,struct.pack('<i',123))[2],0)
        self.assertEqual(self.app.engine.memory.read('Unknown'),123)

    def test_incomplete_unknown_atom_rejects_entire_packet(self):
        self.add('Block','DINT',[1,None]);before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.fragment('Block',2,0,b'\xFF'*5)[2],0x0C)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_complete_bool_fragment_can_establish_unknown_value_but_bit_alias_cannot(self):
        self.add('UnknownBool','BOOL',None);self.add('UnknownWord','DINT',None)
        self.assertEqual(self.fragment('UnknownBool',1,0,b'\1',0xC1)[2],0)
        self.assertEqual(self.app.engine.memory.read('UnknownBool'),True)
        self.add('BitAlias','',None,alias='UnknownWord.0')
        self.assertNotEqual(self.fragment('BitAlias',1,0,b'\1',0xC1)[2],0)
        self.assertIsNone(self.app.engine.memory.values['unknownword'])

    def test_fragment_bounds_type_length_and_count_fail_without_mutation(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        cases=[(5,20,b'x',0xC4),(5,19,b'xx',0xC4),(5,0,b'',0xC4),
               (5,0,b'\0'*4,0xCA),(0,0,b'\0'*4,0xC4),(4097,0,b'x',0xC4)]
        for count,offset,payload,code in cases:
            self.assertNotEqual(self.fragment('Values',count,offset,payload,code)[2],0)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_fragment_may_start_at_array_element_but_cannot_cross_array_boundary(self):
        self.assertEqual(self.fragment('Values[3]',2,4,struct.pack('<i',42))[2],0)
        self.assertEqual(self.app.engine.memory.read('Values'),[0,0,0,0,42])
        self.assertNotEqual(self.fragment('Values[3]',3,0,struct.pack('<i',99))[2],0)
        self.assertEqual(self.app.engine.memory.read('Values[4]'),42)

    def test_prior_fragments_remain_committed_after_later_packet_failure(self):
        self.assertEqual(self.fragment('Values',5,0,struct.pack('<ii',7,8))[2],0)
        self.assertNotEqual(self.fragment('Values',5,19,b'\xFF\xFF')[2],0)
        self.assertEqual(self.app.engine.memory.read('Values'),[7,8,0,0,0])

    def test_multi_atom_nonfinite_fragment_rolls_back_all_changes_in_packet(self):
        self.add('Floats','REAL',[1.0,2.0]);before=copy.deepcopy(self.app.engine.memory.values)
        result=self.fragment('Floats',2,0,struct.pack('<ff',3.0,float('nan')),0xCA)
        self.assertNotEqual(result[2],0);self.assertEqual(self.app.engine.memory.values,before)

    def test_fragment_signed_unsigned_real_and_bool_atoms(self):
        cases=[('SINT',0xC2,'b',-128),('INT',0xC3,'h',-32768),('LINT',0xC5,'q',-2**63),
               ('USINT',0xC6,'B',255),('UINT',0xC7,'H',65535),('UDINT',0xC8,'I',2**32-1),
               ('ULINT',0xC9,'Q',2**64-1),('REAL',0xCA,'f',1.25),('BOOL',0xC1,'B',1)]
        for dtype,code,fmt,value in cases:
            with self.subTest(dtype=dtype):
                self.add('Target',dtype,0);self.app.engine.memory._resolved.clear()
                self.assertEqual(self.fragment('Target',1,0,struct.pack('<'+fmt,value),code)[2],0)
                self.assertEqual(self.app.engine.memory.read('Target'),value)
        self.assertNotEqual(self.fragment('Target',1,0,b'\xFF',0xC1)[2],0)
        self.assertEqual(self.app.engine.memory.read('Target'),True)

    def test_read_modify_write_example_conflicting_masks_and_narrow_masks(self):
        self.add('ControlWord','DINT',0x20)
        self.assertEqual(self.rmw('ControlWord',4,4,0xFFFFFFDF),b'\xCE\0\0\0')
        self.assertEqual(self.app.engine.memory.read('ControlWord'),4)
        self.assertEqual(self.rmw('ControlWord',4,4,0xFFFFFFFB)[2],0)
        self.assertEqual(self.app.engine.memory.read('ControlWord'),0)
        self.app.engine.memory.write('ControlWord',0x123456FF)
        self.assertEqual(self.rmw('ControlWord',1,0,0xF0)[2],0)
        self.assertEqual(self.app.engine.memory.read('ControlWord'),0x123456F0)

    def test_read_modify_write_handles_signed_boundaries_at_each_integer_width(self):
        for dtype,size,signed in [('SINT',1,True),('INT',2,True),('DINT',4,True),('LINT',8,True),
                                 ('USINT',1,False),('UINT',2,False),('UDINT',4,False),('ULINT',8,False)]:
            with self.subTest(dtype=dtype):
                self.add('Word',dtype,0);self.app.engine.memory._resolved.clear();high=1<<(size*8-1)
                self.assertEqual(self.rmw('Word',size,high,(1<<(size*8))-1)[2],0)
                self.assertEqual(self.app.engine.memory.read('Word'),-high if signed else high)

    def test_read_modify_write_rejects_unknown_unsupported_and_oversized_masks(self):
        self.add('Unknown','DINT',None);self.add('Float','REAL',1.0)
        before=copy.deepcopy(self.app.engine.memory.values)
        for name in ('Unknown','Float','Enable'):self.assertNotEqual(self.rmw(name,4,1,0xFFFFFFFF)[2],0)
        for size in (0,3,8,12):self.assertNotEqual(self.rmw('Step',size,0,0)[2],0)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_both_new_writes_enforce_endpoint_and_tag_access(self):
        self.add('ReadOnly','DINT',3,external_access='Read Only');self.add('Fixed','DINT',4,constant=True)
        self.add('Private','DINT',5,external_access='None');self.add('Alias','',None,alias='ReadOnly')
        before=copy.deepcopy(self.app.engine.memory.values)
        for name in ('ReadOnly','Fixed','Private','Alias','Accumulator.Count'):
            self.assertEqual(self.fragment(name,1,0,struct.pack('<i',9))[2],0x0F)
            self.assertEqual(self.rmw(name,4,1,0xFFFFFFFF)[2],0x0F)
        self.endpoint.allow_writes=False
        self.assertEqual(self.fragment('Step',1,0,struct.pack('<i',9))[2],0x0F)
        self.assertEqual(self.rmw('Step',4,1,0xFFFFFFFF)[2],0x0F)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_rmw_and_fragment_follow_alias_and_program_scope(self):
        self.add('Local','DINT',0x123400,scope='MainProgram')
        self.add('LocalAlias','',None,alias='Program:MainProgram.Local')
        self.assertEqual(self.rmw('LocalAlias',1,0x80,0xFF)[2],0)
        self.assertEqual(self.fragment('Program:MainProgram.Local',1,0,b'\x01')[2],0)
        self.assertEqual(self.app.engine.memory.read('LocalAlias'),0x123401)

    def test_malformed_payloads_do_not_mutate_memory(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        for service,payloads in ((0x53,[b'',b'\xC4\0\1\0',b'\xC4\0\1\0\0\0\0']),
                                 (0x4E,[b'',b'\4\0'+b'\0'*7,b'\4\0'+b'\0'*9])):
            for payload in payloads:self.assertNotEqual(self.cip(service,'Step',payload)[2],0)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_connected_fragment_retry_uses_cached_reply_without_reapplying(self):
        status,opened=self.client.cip(fo());self.assertEqual(status,0);cid=struct.unpack_from('<I',opened,4)[0]
        packet=request(0x53,'Step',struct.pack('<HHIi',0xC4,1,0,7))
        first=self.client.cip(packet,cid,1);self.assertEqual(first[1][2],0)
        self.app.engine.memory.write('Step',99)
        self.assertEqual(self.client.cip(packet,cid,1),first)
        self.assertEqual(self.app.engine.memory.read('Step'),99)


if __name__=='__main__':unittest.main()
