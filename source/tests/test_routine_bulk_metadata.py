"""Original opaque source metadata and live Routine headers, flags and signatures."""
import copy
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

from logixlab.model import ModelError
from logixlab.native_routines import NativeRoutines,routine_paths
from logixlab.native_aoi_routines import NativeAOIRoutines
from logixlab.native_symbols import NativeSymbols
from logixlab.native_aois import NativeAOIs
from tools.anonymous_client import AnonymousClient
from tools.collection_inventory import decode_attribute_list
from tools.upload_inventory import logical_path
from test_native_routines import database,container,EXPECTED,PROGRAMS
from test_native_routine_types import typed_record
import test_routine_state as states
import test_program_diagnostics as diagnostics

BLOB=b'\0\x08'+bytes(range(64))


def metadata_record(blob=BLOB,**kwargs):
    record=bytearray(typed_record(**kwargs));record[6+148+156:6+148+224]=struct.pack('<H',len(blob))+blob
    return bytes(record)


class RoutineBlobSourceTests(unittest.TestCase):
    def test_exact_source_bytes_roundtrip_across_program_aoi_and_compressed_containers(self):
        for parent in (0x68,0x338):
            data=database(metadata_record(logical=(parent,11,0x6d,7,0,0),component_type=256 if parent==0x68 else 259))
            result=routine_paths(data,EXPECTED,PROGRAMS,parent_class=parent)
            self.assertEqual(result[0]['source_key_hex'],BLOB.hex())
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'owned.ACD'
                for compressed in (False,True):
                    raw=container(data,compressed);path.write_bytes(raw);digest=hashlib.sha256(raw).hexdigest()
                    if parent==0x68:
                        binding=NativeRoutines.from_acd(path,'b'*64,EXPECTED,NativeSymbols(digest,'b'*64,[],[dict(name='ProgramA',instance=11)]))
                    else:
                        binding=NativeAOIRoutines.from_acd(path,'b'*64,[dict(aoi='ProgramA',name='Run')],NativeAOIs(digest,'b'*64,[dict(name='ProgramA',instance=11)]))
                    row=binding.rows[0];self.assertEqual(row.source_key,BLOB);self.assertEqual(row.manifest()['source_key_hex'],BLOB.hex())
                    self.assertEqual(type(binding).from_manifest(binding.manifest(),'b'*64).manifest(),binding.manifest())
                    self.assertNotIn(BLOB.hex(),repr(row));self.assertNotIn(BLOB.hex(),json.dumps(binding.description()))
                    self.assertEqual(path.read_bytes(),raw)

    def test_unknown_key_format_count_or_storage_never_becomes_a_default(self):
        good=metadata_record()
        for offset,value in ((156,b'\x41\0'),(158,b'\1\x08'),(74,bytes(4))):
            changed=bytearray(good);changed[6+148+offset:6+148+offset+len(value)]=value
            result=routine_paths(database(bytes(changed)),EXPECTED,PROGRAMS)[0]
            self.assertNotIn('source_key_hex',result)
        self.assertNotIn('source_key_hex',routine_paths(database(typed_record()),EXPECTED,PROGRAMS)[0])

    def test_legacy_absence_strict_blob_manifest_and_immutability(self):
        base=dict(program='ProgramA',name='Run',program_instance=11,instance=7,type_word=0x7ff)
        self.assertNotIn('source_key_hex',NativeRoutines('a'*64,'b'*64,[base]).manifest()['routines'][0])
        for blob in (None,True,BLOB,BLOB.hex().upper(),BLOB.hex()[:-2],BLOB.hex()+'00','ff'*66):
            with self.assertRaises(ModelError):NativeRoutines('a'*64,'b'*64,[{**base,'source_key_hex':blob}])
        with self.assertRaises(ModelError):NativeRoutines('a'*64,'b'*64,[{k:v for k,v in {**base,'source_key_hex':BLOB.hex()}.items() if k!='type_word'}])
        binding=NativeRoutines('a'*64,'b'*64,[{**base,'source_key_hex':BLOB.hex()}])
        with self.assertRaises(FrozenInstanceError):binding.rows[0].source_key=bytes(66)
        manifest=binding.manifest();manifest['routines'][0]['source_key_hex']='ff'*66
        self.assertEqual(binding.rows[0].source_key,BLOB)


class RoutineHeaderWireTests(states.RoutineStateWireTests):
    # Inherited guard tests exercise every new field using this original blob.
    def load(self,root):
        super().load(root)
        self.binding=NativeRoutines('a'*64,self.binding.source_l5x_sha256,
            [{**row.manifest(),'source_key_hex':BLOB.hex()} for row in self.binding.rows])
        self.data['native_routines']=self.binding.manifest();self.app.command('load',self.data)

    def test_signed_bulk_reports_original_instance_and_guarded_state_without_writes_or_execution(self):
        before=copy.deepcopy(self.app.state());path=logical_path(0x6d,7,program=10)
        with AnonymousClient(self.endpoint) as client:
            client.bind();raw=client.request(bytes((3,len(path)//2))+path+struct.pack('<23H',22,*states.BULK))
            values=decode_attribute_list(raw,states.BULK,0x6d,include_payloads=True)['attributes']
            self.assertEqual(raw[2],0);self.assertEqual(len(values),22);self.assertTrue(all(not row['status'] for row in values))
            fields={row['attribute']:bytes.fromhex(row['data_hex']) for row in values}
            self.assertEqual(fields[22],b'\x42\0'+BLOB);self.assertEqual(fields[24],bytes(4));self.assertEqual(fields[28],bytes(4))
            address=int.from_bytes(fields[8],'little');self.assertEqual(address%4,0);self.assertGreaterEqual(address,0x10000000)
            engine=self.app.engine;self.assertIs(engine.runtime_references.resolve(engine.project,address,'routine'),engine.project.routines['mainprogram/mainroutine'])
            self.assertEqual(engine.runtime_references.program_attributes(engine.project,'MainProgram')[5],fields[8])
            for n in (8,22,24,28):
                target=path+bytes((0x30,n))
                self.assertNotEqual(client.request(bytes((0x10,len(target)//2))+target+fields[n])[2],0)
        for key in ('tags','routines','tasks','controller','scan','ms'):self.assertEqual(before[key],self.app.state()[key])
        self.assertNotIn(BLOB.hex(),json.dumps(self.app.state()))

    def test_live_references_keep_parent_scope_and_revoke_on_reset_or_object_replacement(self):
        first=int.from_bytes(self.call(8)[4:],'little');other=int.from_bytes(self.call(8,parent=20)[4:],'little')
        self.assertNotEqual(first,other);old=self.app.engine;project=old.project
        target=copy.deepcopy(project.routines['mainprogram/mainroutine']);target.name='Subroutine'
        project.routines['mainprogram/subroutine']=target
        values=old.runtime_references.routine_attributes(project,'MainProgram','Subroutine')
        self.assertEqual(values[24],b'\2\0\0\0');self.assertNotEqual(values[8],struct.pack('<I',first))
        project.routines['mainprogram/mainroutine']=copy.deepcopy(project.routines['mainprogram/mainroutine'])
        self.assertIsNone(old.runtime_references.resolve(project,first,'routine'))
        with patch('logixlab.runtime_references._allocate',side_effect=OverflowError):self.assertEqual(old.runtime_references.routine_attributes(project,'MainProgram','MainRoutine'),{})
        self.app.command('reset',{});self.assertNotEqual(int.from_bytes(self.call(8)[4:],'little'),first)

    def test_new_fields_withhold_faulted_edited_or_reserved_state(self):
        for mode in ('fault','changed','reservation'):
            self.app.command('load',self.data)
            if mode=='fault':self.app.engine.fault='failed'
            elif mode=='changed':self.app.engine.project.runtime_revision=1
            else:
                from types import SimpleNamespace
                lease=self.endpoint.programming_lease;owner=SimpleNamespace(stage='bound',key=b'test',deadline=lease.clock()+300)
                lease.acquire(owner,self.app.generation,self.app.engine.project.sha256,selector=1)
                lease.reserve_program(owner,self.app.generation,self.app.engine.project.sha256,10)
            for n in (8,22,24,28):self.assertEqual(self.call(n)[2],0x14)
            self.assertEqual(self.call(9)[2],0)
            self.endpoint.programming_lease.clear()

    def test_unknown_signature_markers_and_routine_attributes_withhold_unsigned_state(self):
        for mode in ('attribute','child','controller','root','namespace','opaque'):
            root=copy.deepcopy(self.root);controller=root.find('Controller');routine=controller.find('./Programs/Program/Routines/Routine')
            if mode=='attribute':routine.set('SignatureID','0')
            elif mode=='child':E.SubElement(routine,'Signature')
            elif mode=='controller':controller.set('SafetySignature','0')
            elif mode=='root':root.set('RoutineSignatureUId','0')
            elif mode=='namespace':routine.set('{urn:test}signature','0')
            else:routine.set('VendorData','unknown')
            if mode=='child':
                with self.assertRaises(ModelError):self.load(root)
            else:
                with self.subTest(mode=mode):
                    self.load(root);self.assertEqual(self.call(28)[2],0x14)

    def test_unknown_test_edit_source_and_unvalidated_storage_withhold_state(self):
        # Old manifests can keep Type and ID while omitting new opaque bytes.
        super().test_unknown_test_edit_source_and_unvalidated_storage_withhold_state()


class UnsignedSourceTests(diagnostics.ProgramDiagnosticTests):
    def test_unsigned_source_is_immutable_current_canonical_and_marker_sensitive(self):
        root,controller=self.source();reader=diagnostics.build(root,controller)
        self.assertEqual(reader.signature_attributes('MainProgram',source_sha256=diagnostics.SHA),{28:bytes(4)})
        for program,digest in ((None,diagnostics.SHA),('Missing',diagnostics.SHA),('MainProgram','b'*64)):
            self.assertEqual(reader.signature_attributes(program,source_sha256=digest),{})
        controller.find('./Programs/Program/Routines/Routine').set('SignatureID','0')
        self.assertEqual(diagnostics.build(root,controller).signature_attributes('MainProgram',source_sha256=diagnostics.SHA),{})
        self.assertEqual(reader.signature_attributes('MainProgram',source_sha256=diagnostics.SHA),{28:bytes(4)})


if __name__=='__main__':unittest.main()
