import copy
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E
from logixlab.server import Application
from logixlab.model import Tag
from logixlab.ethernetip import Endpoint,symbol_path
from test_ethernetip import Client,request


class SymbolMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'TextLab'});self.endpoint=Endpoint(self.app,0,True).start()
        self.client=Client(self.endpoint.port);self.client.register()

    def tearDown(self):
        self.client.close();self.endpoint.stop();self.app.close();self.tmp.cleanup()

    def add(self,name,value=1,**kwargs):
        tag=Tag(name,'DINT',value,**kwargs);key=tag.key.lower()
        self.app.engine.project.tags[key]=tag;self.app.engine.memory.values[key]=copy.deepcopy(value)

    def cip(self,service,path,data=b''):
        status,result=self.client.cip(bytes((service,len(path)//2))+path+data)
        self.assertEqual(status,0);return result

    def path(self,name,scope=''):
        symbol=next(s for s in self.endpoint.router.symbols(scope) if s['name']==name)
        return (symbol_path('Program:'+scope) if scope else b'')+b'\x20\x6B\x25\0'+struct.pack('<H',symbol['id'])

    def test_single_and_list_attribute_formats(self):
        path=self.path('Values')
        self.assertEqual(self.cip(0x0E,path+b'\x30\1'),b'\x8E\0\0\0\6\0Values')
        self.assertEqual(self.cip(0x0E,path+b'\x30\2')[4:],struct.pack('<H',0x20C4))
        result=self.cip(3,path,struct.pack('<HHHH',3,8,10,99))
        self.assertEqual(result[:4],b'\x83\0\x0A\0')
        self.assertEqual(result[4:],struct.pack('<HHHIIIHHBHH',3,8,0,5,0,0,10,0,0,99,0x14))

    def test_external_access_includes_constants_aliases_and_readonly_members(self):
        self.add('ReadOnly',external_access='Read Only');self.add('Constant',constant=True)
        self.add('ReadOnlyAlias',value=None,alias='ReadOnly')
        self.add('Pair',value={'A':1});self.app.engine.project.tags['pair'].dtype='PAIR'
        self.app.engine.project.udts['pair']=E.fromstring('<DataType><Members><Member Name="A" DataType="DINT" ExternalAccess="Read Only"/></Members></DataType>')
        self.add('MemberAlias',value=None,alias='Pair.A')
        for name in ('ReadOnly','ReadOnlyAlias','MemberAlias'):
            with self.subTest(name=name):self.assertEqual(self.cip(0x0E,self.path(name)+b'\x30\x0A')[4:],b'\2')
        self.assertEqual(self.cip(0x0E,self.path('Step')+b'\x30\x0A')[4:],b'\0')
        self.endpoint.allow_writes=False
        self.assertEqual(self.cip(0x0E,self.path('Step')+b'\x30\x0A')[4:],b'\0')

    def test_constant_declaration_and_flag_do_not_enable_writes(self):
        for name,value,dtype,scope in (('Fixed',7,'DINT',''),('Analog',3.5,'REAL',''),
                ('Array',[1,2],'DINT',''),('LocalFixed',9,'DINT','MainProgram')):
            self.add(name,value,constant=True,scope=scope)
            key=(f'Program:{scope}.{name}' if scope else name).lower()
            self.app.engine.project.tags[key].dtype=dtype
            path=self.path(name,scope);ref=f'Program:{scope}.{name}' if scope else name
            with self.subTest(name=name):
                self.assertEqual(self.cip(0x0E,path+b'\x30\x0A')[4:],b'\0')
                self.assertEqual(self.cip(0x0E,path+b'\x30\x0B')[4:],b'\1')
                row=next(s for s in self.endpoint.router.symbols(scope) if s['name']==name)
                listing=self.cip(0x55,path,struct.pack('<HHH',2,10,11))
                self.assertEqual(listing[4:10],struct.pack('<IBB',row['id'],0,1))
                code,fmt=(0xCA,'f') if dtype=='REAL' else (0xC4,'i')
                result=self.client.cip(request(0x4D,ref,struct.pack('<HH'+fmt,code,1,0)))[1]
                self.assertEqual(result[2],0x0F)
                self.assertEqual(self.app.engine.memory.values[key],value)
                self.endpoint.allow_writes=False
                self.assertEqual(self.cip(0x0E,path+b'\x30\x0A')[4:],b'\0')
                self.endpoint.allow_writes=True
        self.add('DeclaredRO',constant=True,external_access='Read Only')
        self.add('FixedAlias',value=None,alias='Fixed')
        for name in ('DeclaredRO','FixedAlias'):
            with self.subTest(name=name):self.assertEqual(self.cip(0x0E,self.path(name)+b'\x30\x0A')[4:],b'\2')

    def test_enumeration_supports_access_attribute_and_reordered_attributes(self):
        path=self.path('Step');instance=struct.unpack_from('<H',path,4)[0]
        result=self.cip(0x55,path,struct.pack('<HHHHH',4,10,8,2,1))
        self.assertIn(result[2],(0,6))
        self.assertEqual(result[4:29],struct.pack('<IBIIIHH',instance,0,0,0,0,0xC4,4)+b'Step')

    def test_program_scope_is_case_insensitive_and_has_its_own_catalog(self):
        self.add('Local',scope='MainProgram',external_access='Read Only')
        path=self.path('Local','mainprogram')
        self.assertEqual(self.cip(0x0E,path+b'\x30\1')[4:],b'\5\0Local')
        self.assertEqual(self.cip(0x0E,path+b'\x30\x0A')[4:],b'\2')
        bad=symbol_path('Program:Missing')+b'\x20\x6B\x24\0'
        self.assertEqual(self.cip(0x55,bad,b'\1\0\1\0')[2],5)

    def test_private_and_safety_program_tags_are_not_disclosed(self):
        self.add('Private',external_access='None');self.add('PrivateAlias',value=None,alias='Private')
        self.add('Safety',tag_class='Safety')
        self.app.engine.project.programs['SafetyProgram']={'class':'Safety'}
        self.add('SafetyLocal',scope='SafetyProgram');self.add('SafetyAlias',value=None,alias='Program:SafetyProgram.SafetyLocal')
        names={s['name'] for s in self.endpoint.router.symbols()}
        self.assertTrue({'Private','PrivateAlias','Safety','SafetyAlias'}.isdisjoint(names))
        path=symbol_path('Program:SafetyProgram')+b'\x20\x6B\x24\0'
        self.assertEqual(self.cip(0x55,path,b'\1\0\1\0')[2],0x0F)
        for name in ('SafetyAlias','Program:SafetyProgram.SafetyLocal'):
            self.assertEqual(self.client.cip(request(0x4C,name,b'\1\0'))[1][2],0x0F)

    def test_unknown_internal_attributes_and_bad_paths_do_not_mutate_memory(self):
        before=copy.deepcopy(self.app.engine.memory.values);path=self.path('Step')
        for attr in (4,13,255):self.assertEqual(self.cip(0x0E,path+bytes((0x30,attr)))[2],0x14)
        self.assertEqual(self.cip(0x55,path+b'\x30\1',b'\1\0\1\0')[2],4)
        self.assertNotEqual(self.cip(3,path,b'\2\0\1\0')[2],0)
        self.assertEqual(self.cip(0x0E,b'\x20\x6B\x25\0\xFF\xFF\x30\1')[2],5)
        self.assertEqual(self.app.engine.memory.values,before)


if __name__=='__main__':unittest.main()
