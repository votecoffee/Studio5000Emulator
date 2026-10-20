"""Executable inventory preserves Program parents and source identity."""
import base64
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint,Session,decode_path,CIPError
from logixlab.model import ModelError
from logixlab.native_routines import NativeRoutines
from logixlab.native_symbols import NativeSymbols
from logixlab.server import Application
import test_programming_lease as leases

ROOT=Path(__file__).resolve().parents[1]
HASH='a'*64


def fixture():
    root=E.fromstring((ROOT/'samples/ConveyorDemo.L5X').read_bytes())
    programs=root.find('./Controller/Programs')
    routine=programs[0].find('./Routines/Routine')
    for other in list(programs[0].find('Routines')):
        if other is not routine:programs[0].find('Routines').remove(other)
    description=E.Element('Description');description.text='First program';routine.insert(0,description)
    other=copy.deepcopy(programs[0]);other.set('Name','OtherProgram')
    other.find('./Routines/Routine/Description').text='Second program';programs.append(other)
    return E.tostring(root)


def bindings(digest):
    symbols=NativeSymbols(HASH,digest,[],[{'name':'MainProgram','instance':10},{'name':'OtherProgram','instance':20}])
    routines=NativeRoutines(HASH,digest,[{'program':program,'name':'MainRoutine','program_instance':parent,'instance':7}
                                       for program,parent in (('MainProgram',10),('OtherProgram',20))])
    return symbols,routines


class RoutineMetadataWireTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.app=Application(self.temp.name)
        self.data={'name':'routines.L5X','content':base64.b64encode(fixture()).decode()}
        self.app.command('load',self.data);self.digest=self.app.engine.project.sha256
        self.symbols,self.routines=bindings(self.digest)
        self.app.native_symbols=self.symbols;self.app.native_routines=self.routines
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e')

    def tearDown(self):self.app.close();self.temp.cleanup()

    def call(self,request,limit=480):return self.endpoint.router.handle(bytes.fromhex(request),Session(),limit=limit)

    def test_numeric_paths_keep_the_parent_and_reject_missing_or_deeper_scopes(self):
        for encoded,parent in (('2068240a206d2407',10),('206825002c01206d2407',300),
                                ('2068260070110100206d2407',70000)):
            path=decode_path(bytes.fromhex(encoded))
            self.assertEqual((path.program_instance,path.class_id,path.instance),(parent,0x6D,7))
        for encoded in ('2068240a206d','20682400206d2407','2068240a206d2407206b2401'):
            with self.assertRaises(CIPError):decode_path(bytes.fromhex(encoded))

    def test_same_child_id_in_two_programs_never_shares_description_or_inventory(self):
        before=copy.deepcopy(self.app.state())
        for parent,text in ((10,b'First program'),(20,b'Second program')):
            path='206824'+f'{parent:02x}'+'206d2407'
            self.assertEqual(self.call('0e05'+path+'3007'),b'\x8e\0\0\0'+struct.pack('<H',len(text))+text)
            self.assertEqual(self.call('4b04206824'+f'{parent:02x}'+'206d2400'),bytes.fromhex('cb00000007000000'))
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_class_counts_sparse_cursor_and_reply_bounds_use_actual_child_ids(self):
        self.assertEqual(self.call('03042068240a206d24000300010002000300'),
                         bytes.fromhex('83000000030001000000010002000000070000000300000001000000'))
        self.assertEqual(self.call('4b042068240a206d2408'),bytes.fromhex('cb000000'))
        self.assertEqual(self.call('4b042068240a206d2400',limit=7)[2],27)
        self.assertEqual(self.call('0e052068240a206d24073007',limit=8)[2],27)

    def test_unknown_fields_and_aggregate_reads_remain_unavailable(self):
        self.assertEqual(self.call('03042068240a206d240704000100020004000700'),
                         bytes.fromhex('83000a000400010014000200140004001400070000000d00')+b'First program')
        self.assertEqual(self.call('01042068240a206d2407')[2],8)
        self.assertEqual(self.call('0e03206d24003001'),bytes.fromhex('8e0000000100'))
        self.assertEqual(self.call('0e03206d24003003')[2],20)

    def test_global_and_unknown_parent_or_child_paths_cannot_flatten_programs(self):
        for request in ('4b02206d2400','0e03206d24073007'):
            self.assertEqual(self.call(request)[2],4)
        self.assertEqual(self.call('0e052068241e206d24073007')[2],5)
        self.assertEqual(self.call('0e052068240a206d24083007')[2],5)
        self.assertEqual(self.call('4b052068240a206d24003007')[2],4)

    def test_missing_stale_and_foreign_identity_cannot_become_an_empty_inventory(self):
        read='4b042068240a206d2400'
        for native in (None,NativeRoutines(HASH,'b'*64,[]),NativeRoutines('b'*64,self.digest,[]),
                       NativeRoutines(HASH,self.digest,[])):
            self.app.native_routines=native
            self.assertEqual(self.call(read)[2],12)

    def test_manifest_binding_is_atomic_and_plain_l5x_replacement_clears_it(self):
        self.app.command('load',{**self.data,'native_symbols':self.symbols.manifest(),'native_routines':self.routines.manifest()})
        before=self.app.engine;generation=self.app.generation
        for manifest in (NativeRoutines(HASH,self.digest,[]).manifest(),
                         NativeRoutines('b'*64,self.digest,[]).manifest(),
                         NativeRoutines(HASH,'b'*64,[]).manifest()):
            with self.assertRaises(ModelError):
                self.app.command('load',{**self.data,'native_symbols':self.symbols.manifest(),'native_routines':manifest})
            self.assertIs(self.app.engine,before);self.assertEqual(self.app.generation,generation)
        for action in ('reset','configure'):
            self.app.command(action,{})
            self.assertEqual(self.app.native_routines.manifest(),self.routines.manifest())
        self.app.command('load',self.data);self.assertIsNone(self.app.native_routines)


class RoutineSignedWireTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare

    def test_signed_catalog_read_succeeds_while_modification_stays_denied(self):
        self.prepare();digest=self.app.engine.project.sha256
        self.app.native_symbols=NativeSymbols(HASH,digest,[],[{'name':'MainProgram','instance':10}])
        names=self.app.engine.project.executable_configuration.routine_names('MainProgram',source_sha256=digest)
        self.app.native_routines=NativeRoutines(HASH,digest,[{'program':'MainProgram','name':name,'program_instance':10,'instance':7+i}
                                                          for i,name in enumerate(names)])
        self.assertEqual(self.signed(4,bytes.fromhex('4b042068240a206d2400')),b'\xcb\0\0\0'+b''.join(struct.pack('<I',7+i) for i in range(len(names))))
        self.assertEqual(self.signed(5,bytes.fromhex('0e052068240a206d24073007'))[2],20)
        self.assertEqual(self.signed(6,bytes.fromhex('10052068240a206d240730070000'))[2],15)


if __name__=='__main__':unittest.main()
