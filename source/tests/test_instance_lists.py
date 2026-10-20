"""Read-only discovery with sparse IDs, pagination and access boundaries."""
import copy
import struct
import tempfile
import unittest

from logixlab.ethernetip import Endpoint,Session,symbol_path
from logixlab.model import Tag
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.server import Application


class InstanceListTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e')
        self.router=self.endpoint.router

    def tearDown(self):
        self.app.close();self.tmp.cleanup()

    def call(self,path,data=b'',limit=480):
        return self.router.handle(bytes((0x4B,len(path)//2))+path+data,Session(),limit=limit)

    def bind(self,symbols):
        self.app.native_symbols=NativeSymbols('1'*64,self.app.engine.project.sha256,symbols)

    def test_sparse_native_symbol_ids_are_packed_udints_and_cursor_is_inclusive(self):
        self.bind([Symbol('',0,'StartPB',3),Symbol('',0,'SpeedSetpoint',70000)])
        for cursor,ids in ((0,(3,70000)),(3,(3,70000)),(4,(70000,)),(70000,(70000,)),(70001,())):
            path=bytes.fromhex('206b2600')+struct.pack('<I',cursor)
            self.assertEqual(self.call(path),b'\xCB\0\0\0'+b''.join(struct.pack('<I',i) for i in ids))

    def test_pages_respect_reply_budget_and_resume_without_duplicate_ids(self):
        self.bind([Symbol('',0,'StartPB',3),Symbol('',0,'SpeedSetpoint',70000)])
        self.assertEqual(self.call(bytes.fromhex('206b2400'),limit=8),b'\xCB\0\6\0'+struct.pack('<I',3))
        self.assertEqual(self.call(bytes.fromhex('206b2404'),limit=8),b'\xCB\0\0\0'+struct.pack('<I',70000))
        self.assertEqual(self.call(bytes.fromhex('206b2400'),limit=7),b'\xCB\0\x1B\0')

    def test_program_scopes_keep_local_and_controller_symbols_separate(self):
        tag=Tag('Local','DINT',10,scope='MainProgram')
        self.app.engine.project.tags[tag.key.lower()]=tag;self.app.engine.memory.values[tag.key.lower()]=10
        self.bind([Symbol('',0,'StartPB',3),Symbol('MainProgram',42,'Local',3)])
        expected=b'\xCB\0\0\0'+struct.pack('<I',3)
        for prefix in (symbol_path('Program:MainProgram'),bytes.fromhex('2068242a')):
            self.assertEqual(self.call(prefix+bytes.fromhex('206b2400')),expected)
        self.app.engine.project.programs['MainProgram']['class']='Safety'
        self.assertEqual(self.call(symbol_path('Program:MainProgram')+bytes.fromhex('206b2400'))[2],0x0F)
        self.assertEqual(self.call(bytes.fromhex('206b2400')),expected)

    def test_private_tags_and_unmapped_ids_are_not_disclosed(self):
        self.bind([Symbol('',0,'StartPB',3),Symbol('',0,'SpeedSetpoint',70000)])
        self.app.engine.project.tags['speedsetpoint'].external_access='None'
        self.assertEqual(self.call(bytes.fromhex('206b2400')),b'\xCB\0\0\0'+struct.pack('<I',3))

    def test_templates_list_existing_model_ids_and_respects_cursor(self):
        self.app.command('demo',{'sample':'StructureLab'})
        ids=sorted(t.instance for t in self.router.templates().types.values())
        self.assertTrue(ids)
        self.assertEqual(self.call(bytes.fromhex('206c2400')),b'\xCB\0\0\0'+b''.join(struct.pack('<I',i) for i in ids))
        path=bytes.fromhex('206c2600')+struct.pack('<I',ids[-1]+1)
        self.assertEqual(self.call(path),b'\xCB\0\0\0')

    def test_bad_payload_paths_and_other_classes_cannot_mutate_state(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        for path,data,status in ((bytes.fromhex('206b24003001'),b'',4),(bytes.fromhex('206b'),b'',4),
                (bytes.fromhex('206c2400'),b'x',0x15),(bytes.fromhex('20702400'),b'',0x0C),
                (bytes.fromhex('206c2400')+symbol_path('Anything'),b'',4)):
            self.assertEqual(self.call(path,data)[2],status)
        self.assertEqual(self.app.engine.memory.values,before)


if __name__=='__main__':unittest.main()
