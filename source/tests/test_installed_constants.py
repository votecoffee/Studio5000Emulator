"""Native constant descriptors need a proved source value and keep writes denied."""
import copy
import struct
from types import MappingProxyType
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from logixlab.installed_memory import constant_keys,read_constant
from logixlab.download_image import ImageError
from logixlab.model import ModelError
from logixlab.model import Tag
from logixlab.data_table import AddressSpace
from logixlab.download_values import encode_initial
from logixlab.native_symbols import Symbol
import test_installed_memory as memory
import test_download_changelog as logs
import test_download_headers as headers


def constant_symbol(original):
    def symbol(instance,name,*args,**kwargs):
        row=original(instance,name,*args,**kwargs)
        if name!='SpeedSetpoint':return row
        values=headers.attributes(0x6B,row.request[2+2*row.request[1]:]);values[11]=b'\1'
        return headers.update(0x6B,instance,values)
    return symbol


class InstalledConstantTests(logs.NamespaceFixture,unittest.TestCase):
    complete_tasks=memory.InstalledMemoryTests.complete_tasks
    configure=memory.InstalledMemoryTests.configure
    ready_setup=memory.InstalledMemoryTests.ready_setup
    ready_routines=memory.InstalledMemoryTests.ready_routines
    next_routines=memory.InstalledMemoryTests.next_routines
    ready_map=memory.InstalledMemoryTests.ready_map
    ready_log=memory.InstalledMemoryTests.ready_log
    proposal=memory.InstalledMemoryTests.proposal
    ready_install=memory.InstalledMemoryTests.ready_install

    def setUp(self):
        original=logs.maps.map_route
        def route(test):
            result=original(test)
            result[1].find('./Tags/Tag[@Name="SpeedSetpoint"]').set('Constant','true')
            return result
        with patch.object(logs.maps,'map_route',route),patch.object(headers,'symbol',constant_symbol(headers.symbol)):
            memory.InstalledMemoryTests.setUp(self)
        self.assertTrue(self.app.engine.project.tags['speedsetpoint'].constant)

    def installed(self):
        with patch.object(headers,'symbol',constant_symbol(headers.symbol)):memory.InstalledMemoryTests.installed(self)

    def test_constant_table_has_complete_read_only_native_storage_after_install(self):
        router=self.endpoint.router;self.assertFalse(constant_keys(self.app,router))
        self.assertNotIn('speedsetpoint',router.scalar_storage().by_ref)
        self.installed();before=copy.deepcopy(self.app.state())
        self.assertEqual(constant_keys(self.app,router),{'speedsetpoint'})
        self.assertEqual(read_constant(self.app,router,'speedsetpoint'),bytes(4))
        self.assertEqual(self.send(bytes.fromhex('0302206a240107000100020003000600070008000900'))[2],0)
        self.assertEqual(self.send(bytes.fromhex('4f02206a2401000000000400')),bytes.fromhex('cf000000')+bytes(4))
        self.assertEqual(self.send(bytes.fromhex('0e03206b2401300b')),bytes.fromhex('8e00000001'))
        self.assertNotEqual(memory.InstalledMemoryTests.read_value(self)[2],0)
        for service in (4,0x10,0x4D,0x50):self.assertNotEqual(self.send(bytes((service,2))+bytes.fromhex('206a2401')+bytes(8))[2],0)
        with self.assertRaises(ModelError):self.app.command('write',dict(tag='SpeedSetpoint',value=1))
        for field in ('tags','scan','ms','routine_edits'):self.assertEqual(self.app.state()[field],before[field])

    def test_changed_value_or_effect_and_reset_revoke_constant_readback(self):
        self.installed();router=self.endpoint.router;engine=self.app.engine
        engine.memory.values['speedsetpoint']=1
        with self.assertRaises(ImageError):read_constant(self.app,router,'speedsetpoint')
        engine.memory.values['speedsetpoint']=0
        self.assertEqual(read_constant(self.app,router,'speedsetpoint'),bytes(4))
        stage=engine.installed_download.namespace._incremental;values=dict(stage._headers)
        row=dict(values[0x6B,0,1]);row[11]=b'\0';values[0x6B,0,1]=tuple(sorted(row.items()));stage._headers=MappingProxyType(values)
        self.assertNotEqual(self.send(bytes.fromhex('0e03206a24013003'))[2],0)
        self.app.command('reset',{});self.assertFalse(constant_keys(self.app,router))
        self.assertNotIn('speedsetpoint',router.scalar_storage().by_ref)


class ConstantShapeTests(unittest.TestCase):
    def fixture(self,dtype,value,fmt):
        tag=Tag('Const',dtype,value,scope='MainProgram',constant=True);key=tag.key.casefold()
        code,dimensions,_,raw=encode_initial(dtype,value,None)
        logical_dimensions=(len(value),0,0) if dtype=='BOOL' and isinstance(value,list) else dimensions
        logical_code=0x20C1 if code==0x20D3 else code
        space=AddressSpace([(dict(ref=tag.key,id=9,type=logical_code,dimensions=logical_dimensions),fmt)])
        ns=NS(_tables=[NS(key=(2,5),value_address=0x72000000)],_image=NS(_symbols={(2,9):(2,5)}))
        installed=NS(check=lambda identity,project:None,values=NS(values=((key,(2,5),code,raw),)),namespace=ns)
        app=NS(engine=NS(project=NS(tags={key:tag}),installed_download=installed,memory=NS(read=lambda ref:value)),
            native_project_identity=object(),native_symbols=NS(by_key={key:Symbol('MainProgram',2,'Const',9)}))
        router=NS(endpoint=NS(native_read_only=True),access=lambda ref:None,scalar_storage=lambda:space)
        return app,router,installed,ns,key,raw

    def test_complete_constant_scalar_and_array_bytes_use_storage_type_and_size(self):
        cases=(('BOOL',True,'<B',b'\1'),('INT',-1234,'<h',struct.pack('<h',-1234)),
            ('REAL',1.25,'<f',struct.pack('<f',1.25)),('LINT',2**40,'<q',struct.pack('<q',2**40)),
            ('DINT',[-300,0,12345],'<i',struct.pack('<3i',-300,0,12345)),
            ('BOOL',[i in (0,7,31) for i in range(32)],'<B',struct.pack('<I',0x80000081)))
        for dtype,value,fmt,expected in cases:
            with self.subTest(dtype=dtype,shape=type(value)):
                app,router,installed,ns,key,raw=self.fixture(dtype,value,fmt)
                self.assertEqual(raw,expected)
                with patch('logixlab.installed_memory._verified_installation',return_value=(installed,ns)):
                    self.assertEqual(read_constant(app,router,key),expected)
                    self.assertIs(app.engine.memory.read(key),value)

    def test_changed_array_element_storage_code_and_missing_scoped_handle_reject(self):
        value=[-300,0,12345];app,router,installed,ns,key,raw=self.fixture('DINT',value,'<i')
        with patch('logixlab.installed_memory._verified_installation',return_value=(installed,ns)):
            value[2]=12346
            with self.assertRaises(ImageError):read_constant(app,router,key)
            value[2]=12345
            installed.values.values=((key,(2,5),0x20C3,raw),)
            with self.assertRaises(ImageError):read_constant(app,router,key)
            installed.values.values=((key,(2,5),0x20C4,raw),);ns._tables[0].key=(3,5)
            with self.assertRaises(ImageError):read_constant(app,router,key)
