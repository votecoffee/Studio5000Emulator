"""Instance identities, guarded RLL state and complete scoped bulk framing."""
import base64
import copy
from dataclasses import replace
import hashlib
import json
import struct
import tempfile
from types import SimpleNamespace
import unittest
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint,Session
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_routines import NativeRoutines
from logixlab.native_symbols import NativeSymbols
from logixlab.server import Application
from logixlab.model import ModelError
from logixlab import routine_state
from tools.anonymous_client import AnonymousClient
from tools.collection_inventory import decode_attribute_list,CollectionError
from tools.upload_inventory import logical_path
from tools.analyze_native_transfer import analyze
from tools.inspect_cip_capture import summarize
from test_capture_inspection import packet
from test_native_transfer_trace import event
import test_routine_metadata_wire as fixtures
import test_native_routine_types as types

BULK=(1,2,8,*range(9,25),26,27,28)
STATE=(2,*range(10,22),23,26,27)


def answer(values,order=BULK):
    return b'\x83\0\0\0'+struct.pack('<H',len(order))+b''.join(struct.pack('<HH',n,0)+values[n] for n in order)


class RoutineStateWireTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.root=E.fromstring(fixtures.fixture())
        for program in self.root.findall('./Controller/Programs/Program'):program.set('TestEdits','false')
        # This parent-isolation fixture removes Reporting. Keep the source
        # executable rather than leaving the original call to that routine.
        for text in self.root.findall('.//Rung/Text'):
            if 'JSR(' in (text.text or ''):text.text='NOP();'
        self.load(self.root)
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint;self.endpoint.start()

    def load(self,root):
        raw=E.tostring(root);sha=hashlib.sha256(raw).hexdigest()
        self.identity=NativeProjectIdentity('a'*64,sha,1,1,1,1,1,1)
        self.symbols=NativeSymbols('a'*64,sha,[],[dict(name=n,instance=p) for n,p in (('MainProgram',10),('OtherProgram',20))])
        self.binding=NativeRoutines('a'*64,sha,[dict(program=n,name='MainRoutine',program_instance=p,instance=7,type_word=0x7ff) for n,p in (('MainProgram',10),('OtherProgram',20))])
        self.data=dict(name='routines.L5X',content=base64.b64encode(raw).decode(),native_project_identity=self.identity.manifest(),native_symbols=self.symbols.manifest(),native_routines=self.binding.manifest())
        self.app.command('load',self.data)

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def call(self,attr,parent=10,instance=7):
        path=logical_path(0x6d,instance,program=parent)+bytes((0x30,attr))
        return self.endpoint.router.handle(bytes((14,len(path)//2))+path,Session())

    def test_signed_bulk_reports_original_instance_and_guarded_state_without_writes_or_execution(self):
        before=copy.deepcopy(self.app.state());path=logical_path(0x6d,7,program=10)
        with AnonymousClient(self.endpoint) as client:
            client.bind();raw=client.request(bytes((3,len(path)//2))+path+struct.pack('<'+'H'*(len(BULK)+1),len(BULK),*BULK))
            decoded=decode_attribute_list(raw,BULK,0x6d,include_payloads=True)
            available={r['attribute']:bytes.fromhex(r['data_hex']) for r in decoded['attributes'] if r['status']==0}
            self.assertEqual(set(available),{1,9,*STATE});self.assertEqual(available[9],struct.pack('<I',7))
            self.assertTrue(all(not any(available[n]) for n in STATE))
            self.assertEqual([r['attribute'] for r in decoded['attributes'] if r['status']],[8,22,24,28])
            for attr in (2,9,10,23,26):
                target=path+bytes((0x30,attr));self.assertNotEqual(client.request(bytes((0x10,len(target)//2))+target+bytes(4))[2],0)
        for key in ('tags','scan','ms','controller','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])
        self.assertFalse(self.app.state()['connectivity']['routine_state']['test_untest_assemble'])

    def test_live_edit_reservation_phase_and_pending_transfer_revoke_state_but_not_identity(self):
        lease=self.endpoint.programming_lease;owner=SimpleNamespace(stage='bound',key=b'test',deadline=lease.clock()+300)
        generation=self.app.generation;sha=self.app.engine.project.sha256
        lease.acquire(owner,generation,sha,selector=1);lease.reserve_program(owner,generation,sha,10)
        self.assertEqual(self.call(10)[2],0x14);self.assertEqual(self.call(9)[2],0)
        self.assertEqual(self.call(10,parent=20)[2],0)
        lease.release_program(owner,generation,sha,10);lease.open_edit_preparation(owner,generation,sha)
        self.assertEqual(self.call(10,parent=20)[2],0x14)
        lease.close_edit_preparation(owner,generation,sha);lease.edit_transfer.target=(10,7)
        self.assertEqual(self.call(10)[2],0x14);lease.clear()
        self.assertEqual(self.call(10)[2],0)

    def test_fault_history_changed_logic_blocked_or_active_execution_withhold_state(self):
        changes=(lambda e:setattr(e,'fault','failed scan'),lambda e:setattr(e,'_native_fault_history_uncertain',True),
            lambda e:e.blockers.append('unsupported'),lambda e:setattr(e,'mode','routine'),
            lambda e:setattr(e.project,'runtime_revision',1),lambda e:setattr(e.project,'runtime_edited_routines',('mainprogram/mainroutine',)),
            lambda e:e.calls.stack.append('frame'),lambda e:e.memory.frames.update({'frame':{}}),
            lambda e:setattr(e.project.routines['mainprogram/mainroutine'],'kind','ST'))
        for change in changes:
            self.app.command('load',self.data);change(self.app.engine)
            for attr in STATE:self.assertEqual(self.call(attr)[2],0x14)
            self.assertEqual(self.call(9)[2],0)
        self.app.command('load',self.data);self.app.engine.fault='failed';self.app.engine.fault=''
        self.assertEqual(self.call(10)[2],0x14);self.app.command('reset',{})
        self.assertEqual(self.call(10)[2],0)

    def test_unknown_test_edit_source_and_unvalidated_storage_withhold_state(self):
        for change in ('missing','enabled','insert','ST'):
            root=copy.deepcopy(self.root);program=root.find('./Controller/Programs/Program');routine=program.find('./Routines/Routine')
            if change=='missing':program.attrib.pop('TestEdits')
            elif change=='enabled':program.set('TestEdits','true')
            elif change=='insert':routine.find('./RLLContent/Rung').set('Type','I')
            else:
                routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
                E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='SpeedCommand := SpeedCommand;'
            self.load(root)
            self.assertEqual(self.call(10)[2],0x14);self.assertEqual(self.call(9)[2],0)
        self.load(self.root)
        self.app.native_routines=NativeRoutines('a'*64,self.binding.source_l5x_sha256,[{k:v for k,v in row.manifest().items() if k!='type_word'} for row in self.binding.rows])
        self.assertEqual(self.call(10)[2],0x14);self.assertEqual(self.call(9)[2],0)

    def test_foreign_stale_or_missing_identity_and_unknown_children_cannot_leak_state(self):
        for identity in (None,replace(self.identity,source_acd_sha256='b'*64),replace(self.identity,source_l5x_sha256='b'*64)):
            self.app.native_project_identity=identity
            for attr in (1,2,9,10,23):self.assertEqual(self.call(attr)[2],0x14)
        self.app.native_project_identity=self.identity
        for parent,child in ((10,8),(30,7)):self.assertEqual(self.call(9,parent,child)[2],5)
        self.assertEqual(routine_state.attributes(self.app.engine,'MainProgram','MainRoutine',source_sha256='b'*64,idle=True,type_bound=True),{})
        for idle in (False,None,0,1):
            self.assertEqual(routine_state.attributes(self.app.engine,'MainProgram','MainRoutine',source_sha256=self.identity.source_l5x_sha256,idle=idle,type_bound=True),{})


class RoutineInstanceAOITests(unittest.TestCase):
    setUp=types.RoutineTypeAOITests.setUp
    tearDown=types.RoutineTypeAOITests.tearDown
    request=types.RoutineTypeAOITests.request

    def test_aoi_reports_original_child_instance_and_withholds_program_state_fields(self):
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            for parent in (700,701):
                self.assertEqual(client.request(self.request(14,parent,7,9)),b'\x8e\0\0\0'+struct.pack('<I',7))
                for attr in (2,10,23,26,27):self.assertEqual(client.request(self.request(14,parent,7,attr))[2],0x14)


class ExecutableBulkDecoderTests(unittest.TestCase):
    def test_all_bulk_widths_and_variable_source_keys_frame_with_parent_scope_and_privacy(self):
        values={n:struct.pack('<I',n*12345) for n in (2,*range(8,22),24,28)}
        values.update({1:struct.pack('<H',0x7ff),23:b'\0',26:b'\1',27:b'\0'})
        for key in (b'',b'key',b'k'*66):
            values[22]=struct.pack('<H',len(key))+key;raw=answer(values)
            decoded=decode_attribute_list(raw,BULK,0x6d)
            self.assertEqual([r['value_bytes'] for r in decoded['attributes']],[len(values[n]) for n in BULK])
            self.assertNotIn('data_hex',json.dumps(decoded))
            for scope in ('program','aoi'):
                path=logical_path(0x6d,7,**{scope:11});query=bytes((3,len(path)//2))+path+struct.pack('<'+'H'*(len(BULK)+1),len(BULK),*BULK)
                result=analyze({'events':[]},{'events':[event(query,raw)]},'upload')
                self.assertTrue(result['analysis_complete']);self.assertEqual(result['collection_attribute_lists'][0][scope+'_instance'],11)
                captured=summarize([packet(1,query),packet(2,raw,1)])['exchanges'][0]['response']
                self.assertEqual(len(captured['collection_attribute_list']['attributes']),22)

    def test_bulk_truncation_oversize_unknown_success_partial_errors_and_duplicates_keep_boundaries(self):
        values={n:bytes(4) for n in (2,*range(8,22),24,28)};values.update({1:bytes(2),22:b'\3\0key',23:b'\0',26:b'\0',27:b'\0'})
        raw=answer(values)
        for end in range(len(raw)):
            with self.assertRaises(CollectionError):decode_attribute_list(raw[:end],BULK,0x6d)
        for value in (b'\x43\0'+bytes(67),b'\3\0ke',b'\0\0x'):
            with self.assertRaises(CollectionError):decode_attribute_list(answer({22:value},(22,)),(22,),0x6d)
        with self.assertRaises(CollectionError):decode_attribute_list(answer({5:bytes(4)},(5,)),(5,),0x6d)
        duplicate=decode_attribute_list(answer(values,(9,22,9)),(9,22,9),0x6d)
        self.assertEqual(duplicate['attributes'][0],duplicate['attributes'][2])
        partial=b'\x83\0\6\0'+struct.pack('<HHHIHH',2,9,0,7,8,0x14)
        self.assertEqual(decode_attribute_list(partial,(9,8,22),0x6d)['remaining_attributes'],[22])


if __name__=='__main__':unittest.main()
