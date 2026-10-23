"""Source identities, scoped headers and software references in later batches."""
import base64
import copy
from dataclasses import replace
import json
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E
import zlib

from logixlab.server import Application
from logixlab.download_headers import HeaderBindings,attributes
from logixlab.download_namespace import DownloadNamespace,VALUE_BASE,PROGRAM_BASE,ROUTINE_BASE
from logixlab.download_image import ImageError
from logixlab.incremental_download import IncrementalDownload
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.native_routines import NativeRoutines
from logixlab.native_auxiliary_symbols import NativeAuxiliarySymbols
from logixlab.native_tasks import NativeTasks
from logixlab.resilient_transport import ResilientTransport
from logixlab.ethernetip import logical
from test_native_types import catalog,source_types
import test_download_image as images
import test_diagnostic_staging as diagnostics
import test_object_staging as objects
import test_device_payload as payloads
from test_download_metadata import request
import test_io_map as io_tests


KEY=b'\0\x08'+b'A'*64


def update(cls,instance,values,program=0):
    path=(logical(0x20,0x68)+logical(0x24,program) if program else b'')+logical(0x20,cls)+logical(0x24,instance)
    body=struct.pack('<H',len(values))+b''.join(struct.pack('<H',n)+value for n,value in values.items())
    return request(cls,instance,body,4,path)


def symbol(instance,name,code,address,ref=(),program=0):
    path=b''.join(logical(0x20,c)+logical(0x24,i) for c,i in ref);raw=name.encode()
    return update(0x6B,instance,{1:struct.pack('<H',len(raw))+raw,2:struct.pack('<H',code),3:struct.pack('<I',address),
        6:bytes.fromhex('78563412'),10:b'\0',11:b'\0',13:bytes((len(path)//2,))+path,14:bytes(4)},program)


def fixture(app):
    root,controller,*_=io_tests.IOMapTests().local_route();program=controller.find('./Programs/Program')
    program.set('SynchronizeRedundancyDataAfterExecution','true');program.set('UseAsFolder','false');program.set('TestEdits','false')
    app.command('load',dict(name='fixture.L5X',content=base64.b64encode(E.tostring(root)).decode()))
    source=app.engine.project.sha256;acd='a'*64
    symbols=NativeSymbols(acd,source,[Symbol('',0,'SpeedSetpoint',1)],programs=[dict(name='MainProgram',instance=2)])
    auxiliary=NativeAuxiliarySymbols(acd,source,[
        dict(program_instance=0,instance=2,name='__Map:Local',component_type=1288),
        dict(program_instance=0,instance=3,name='$11111111$',component_type=256,reference_name='Program:MainProgram'),
        dict(program_instance=0,instance=4,name='$22222222$',component_type=256,reference_name='Task:MainTask'),
        dict(program_instance=2,instance=1,name='$33333333$',component_type=256,reference_name='Routine:MainRoutine'),
        dict(program_instance=2,instance=2,name='$44444444$',component_type=256,reference_name='Routine:Reporting')])
    routines=NativeRoutines(acd,source,[dict(program='MainProgram',name=name,program_instance=2,instance=i,type_word=0x7FF,source_key_hex=KEY.hex())
        for i,name in ((1,'MainRoutine'),(2,'Reporting'))])
    tasks=NativeTasks(acd,source,[dict(name='MainTask',instance=1)])
    rows=images.batch()[:3]+(
        objects.symbol(),objects.table(),objects.symbol(2,0xFFFF),objects.symbol(3,0xFFFF),objects.symbol(4,0xFFFF),
        objects.request(0x68,2),objects.coordinate(),objects.symbol(1,0xFFFF,2),objects.symbol(2,0xFFFF,2),
        objects.request(0x6D,1,b'\0\0',program=2),objects.request(0x6D,2,b'\0\0',program=2),objects.coordinate(acquire=False),diagnostics.request())
    stage=ResilientTransport();expanded=b''.join(payloads.record(r.request) for r in rows)
    payloads.fill(stage,payloads.container(zlib.compress(expanded)),expanded)
    types=catalog(acd,source,types=source_types()[:1]);catalogs=dict(native_symbols=symbols,native_routines=routines,native_auxiliary_symbols=auxiliary)
    stage.inspect_payload(types,**catalogs);stage.start_prepared_image();namespace=DownloadNamespace(stage,types,**catalogs)
    bindings=HeaderBindings(app.engine,namespace,symbols,routines,auxiliary,tasks)
    app.native_symbols=symbols;app.native_routines=routines;app.native_auxiliary_symbols=auxiliary;app.native_types=types;app.native_tasks=tasks
    return namespace,bindings


class HeaderTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.app=Application(self.directory.name);self.namespace,self.bindings=fixture(self.app)
        self.image=self.namespace._image;self.source=self.image.source

    def batch(self):
        address=int.from_bytes(self.app.engine.runtime_references.io_map_attributes(self.app.engine.project)[13],'little')
        return (symbol(1,'SpeedSetpoint',0xC4,VALUE_BASE,((0x6A,1),)),
            symbol(2,'Map:Local',0x1069,address,((0x69,1),)),
            symbol(3,'Program:MainProgram',0x1068,PROGRAM_BASE,((0x68,2),)),symbol(4,'Task:MainTask',0x1070,0),
            update(0x68,2,{5:struct.pack('<I',ROUTINE_BASE),7:bytes(4),9:bytes(4),11:bytes(2),19:b'\0',27:bytes(4),29:b'\1',31:b'\1',32:bytes(2)}),
            objects.coordinate(),symbol(1,'Routine:MainRoutine',0x106D,ROUTINE_BASE,((0x68,2),(0x6D,1)),2),
            symbol(2,'Routine:Reporting',0x106D,ROUTINE_BASE+32,((0x68,2),(0x6D,2)),2),
            update(0x6D,1,{1:b'\xff\7',22:struct.pack('<H',66)+KEY,23:b'\0',26:b'\0',27:b'\0',28:bytes(4)},2),
            update(0x6D,2,{1:b'\xff\7',22:struct.pack('<H',66)+KEY,23:b'\0',26:b'\0',27:b'\0',28:bytes(4)},2),
            objects.coordinate(acquire=False),update(0x69,1,{3:bytes(2),12:b'\1\0\0\0',7:b'\5\0'}))

    def prepare(self,rows):return IncrementalDownload.prepare(rows,self.image,self.source,header_bindings=self.bindings)

    def test_all_header_kinds_have_typed_private_readback_without_modifying_source_or_base(self):
        before=copy.deepcopy(self.app.engine.memory.values);stage=self.prepare(self.batch());state=stage.description()
        self.assertEqual((state['records_modeled'],state['header_updates'],state['header_attributes']),(12,10,72))
        self.assertEqual(stage.read_attribute(0x6B,0,1,6,self.image,self.source,header_bindings=self.bindings),bytes.fromhex('78563412'))
        self.assertEqual(stage.read_attribute(0x6D,2,1,22,self.image,self.source,header_bindings=self.bindings),struct.pack('<H',66)+KEY)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.image.read_table(1,0,4,self.source),bytes(4))
        self.assertFalse(state['symbol_control_bits_interpreted'] or state['completion_supported'] or state['commit'])
        for private in ('SpeedSetpoint','MainRoutine',KEY.hex()):self.assertNotIn(private,json.dumps(state))

    def test_names_types_values_and_logical_references_must_resolve_to_exact_objects(self):
        for row in (symbol(1,'Other',0xC4,VALUE_BASE,((0x6A,1),)),symbol(1,'SpeedSetpoint',0xC3,VALUE_BASE,((0x6A,1),)),
                symbol(1,'SpeedSetpoint',0xC4,VALUE_BASE+1,((0x6A,1),)),symbol(1,'SpeedSetpoint',0xC4,VALUE_BASE,((0x6A,2),)),
                symbol(3,'Program:MainProgram',0x1068,ROUTINE_BASE,((0x68,2),)),symbol(4,'Task:OtherTask',0x1070,0)):
            with self.subTest(row=row.scopes[-1].instance),self.assertRaises(ImageError):self.prepare((row,))

    def test_routine_scope_reservation_source_key_type_and_unsigned_flags_are_enforced(self):
        valid=self.batch()[8]
        with self.assertRaises(ImageError):self.prepare((valid,))
        for number,data in ((1,b'\0\0'),(22,struct.pack('<H',66)+KEY[:-1]+b'B'),(23,b'\1'),(28,b'\1\0\0\0')):
            values=attributes(0x6D,valid.request[2+2*valid.request[1]:]);values[number]=data
            bad=update(0x6D,1,values,2)
            with self.subTest(number=number),self.assertRaises(ImageError):self.prepare((objects.coordinate(),bad,objects.coordinate(acquire=False)))

    def test_unknown_duplicated_partial_scoped_and_trailing_attribute_profiles_reject(self):
        row=self.batch()[0];body=row.request[2+2*row.request[1]:]
        for raw in (body[:-1],body+b'\0',b'\7\0'+body[2:],body[:2]+b'\2\0'+body[4:]):
            with self.assertRaises(ImageError):attributes(0x6B,raw)
        with self.assertRaises(ImageError):self.prepare((row,row))
        with self.assertRaises(ImageError):self.prepare((replace(row,scopes=(replace(row.scopes[0],attribute=1),)),))
        with self.assertRaises(ImageError):self.prepare((update(0x69,2,{3:bytes(2),7:b'\5\0',12:b'\1\0\0\0'}),))

    def test_reordered_attributes_and_alternative_logical_segment_widths_preserve_bytes(self):
        row=self.batch()[0];values=attributes(0x6B,row.request[2+2*row.request[1]:])
        values[13]=bytes.fromhex('0421006a0025000100')
        stage=self.prepare((update(0x6B,1,dict(reversed(list(values.items())))),))
        self.assertEqual(stage.read_attribute(0x6B,0,1,13,self.image,self.source,header_bindings=self.bindings),values[13])

    def test_readback_rechecks_source_catalog_live_map_and_current_project(self):
        stage=self.prepare(self.batch())
        with self.assertRaises(ImageError):stage.validate(self.image,self.source)
        old=self.app.engine.project.io_map
        self.app.engine.project.io_map=replace(old)
        with self.assertRaises(ImageError):stage.validate(self.image,self.source,header_bindings=self.bindings)
        self.app.engine.project.io_map=old
        self.bindings.symbols.program_ids[2]='Other'
        with self.assertRaises(ImageError):stage.validate(self.image,self.source,header_bindings=self.bindings)

    def test_missing_original_blob_context_or_changed_runtime_withholds_processing(self):
        stage=IncrementalDownload.prepare(self.batch(),self.image,self.source)
        self.assertEqual(stage.description()['unsupported_records'],10)
        self.app.engine.project.runtime_revision=1
        with self.assertRaises(ImageError):self.prepare(self.batch())

    def test_boolean_read_indices_cannot_alias_a_retained_object(self):
        stage=self.prepare(self.batch())
        for values in ((0x6B,0,True,1),(0x6B,False,1,1),(0x6B,0,1,True)):
            with self.assertRaises(ImageError):stage.read_attribute(*values,self.image,self.source,header_bindings=self.bindings)
