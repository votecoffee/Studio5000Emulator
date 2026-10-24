"""Synthetic Program-scoped routine records, independent hashes and no guessed IDs."""
import copy
from dataclasses import FrozenInstanceError
import gzip
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from logixlab import native_routines
from logixlab.model import ModelError
from logixlab.native_routines import NativeRoutines
from logixlab.native_symbols import NativeSymbols


EXPECTED=[{'program':'ProgramA','name':'Run'}]
PROGRAMS={'ProgramA':11,'ProgramB':22}


def record(name='Run',parent=11,instance=7,version=54,logical=None,kind=0xFAFA,header_version=0,component_type=256):
    path=logical if logical is not None else (0x68,parent,0x6D,instance,0,0)
    body=bytes(8)+struct.pack('<H6H',version,*path)
    header=bytearray(148)
    struct.pack_into('<I',header,0,len(header)+len(body));struct.pack_into('<H',header,10,component_type)
    struct.pack_into('<I',header,12,header_version)
    encoded=name.encode('utf-16le')+bytes(2);header[24:24+len(encoded)]=encoded
    payload=header+body
    return struct.pack('<HI',kind,len(payload)+6)+payload


def database(*records,tail=b''):
    data=bytearray(512)+b''.join(records);end=len(data);data+=tail
    struct.pack_into('<III',data,0,len(data)-1,0,end-1);struct.pack_into('<I',data,12,512)
    return bytes(data)


def container(data,compressed=True):
    raw=gzip.compress(data,mtime=0) if compressed else data
    directory='Comps.Dat'.encode('utf-16le').ljust(520,b'\0')+struct.pack('<II',len(raw),2)
    return b'\r\n'+raw+directory+struct.pack('<II',1,0)


def row(program='ProgramA',name='Run',parent=11,instance=7):
    return dict(program=program,name=name,program_instance=parent,instance=instance)


def saved_record(*,logical=(0x68,11,0x6D,7,0,0),component_type=259,offset=None,value=None):
    """Canonical native storage example, retaining exact opaque source bytes."""
    original=record(logical=logical,component_type=component_type)
    data=bytearray(original[6:]+bytes(371-22))
    struct.pack_into('<I',data,0,len(data))
    struct.pack_into('<4I',data,148+74,297,9,1,189)
    struct.pack_into('<H',data,148+90,0x7FF)
    key=b'\0\x08'+bytes(range(64));data[148+156:148+224]=struct.pack('<H',66)+key
    if offset is not None:data[148+offset:148+offset+len(value)]=value
    return struct.pack('<HI',0xFAFA,len(data)+6)+data


class NativeRoutineTests(unittest.TestCase):
    def test_saved_download_program_headers_preserve_original_id_type_and_opaque_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'saved.ACD';original=container(database(saved_record()));path.write_bytes(original)
            digest=hashlib.sha256(original).hexdigest()
            symbols=NativeSymbols(digest,'b'*64,[],[{'name':'ProgramA','instance':11}])
            catalog=NativeRoutines.from_acd(path,'b'*64,EXPECTED,symbols)
            self.assertEqual(catalog.rows[0].manifest(),dict(row(),type_word=0x7FF,
                source_key_hex=(b'\0\x08'+bytes(range(64))).hex()))
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(NativeRoutines.from_manifest(catalog.manifest(),'b'*64).manifest(),catalog.manifest())

    def test_saved_program_and_aoi_headers_share_component_type_but_keep_exact_parent_scope(self):
        data=database(saved_record(),saved_record(logical=(0x338,11,0x6D,7,0,0)))
        program=native_routines.routine_paths(data,EXPECTED,PROGRAMS)
        aoi=native_routines.routine_paths(data,EXPECTED,PROGRAMS,parent_class=0x338)
        self.assertEqual(program,aoi)  # Each separate query resolves its own exact scoped record.
        for logical in ((0x338,11,0x6D,7,0,0),(0x68,22,0x6D,7,0,0),(0x6D,7,0,0,0,0)):
            with self.subTest(logical=logical),self.assertRaises(ModelError):
                native_routines.routine_paths(database(saved_record(logical=logical)),EXPECTED,PROGRAMS)

    def test_unknown_saved_program_storage_and_mixed_active_duplicates_are_rejected(self):
        invalid=[record(component_type=259),saved_record(offset=74,value=bytes(4)),
            saved_record(offset=90,value=b'\xfc\x07'),saved_record(offset=156,value=b'\x41\0'),
            saved_record(offset=158,value=b'\0\x09'),saved_record(logical=(0x68,11,0x6D,7,1,0))]
        for value in invalid:
            with self.subTest(profile=value[148:170]),self.assertRaises(ModelError):
                native_routines.routine_paths(database(value),EXPECTED,PROGRAMS)
        for values in ((record(),saved_record()),(saved_record(),record()),(saved_record(),saved_record())):
            with self.subTest(records=len(values)),self.assertRaises(ModelError):
                native_routines.routine_paths(database(*values),EXPECTED,PROGRAMS)

    def test_expected_names_bind_only_exact_program_scoped_paths_and_allow_reused_ids_across_programs(self):
        expected=[*EXPECTED,{'program':'ProgramB','name':'Run'},{'program':'ProgramA','name':'Other'}]
        data=database(record(),record(parent=22),record(name='Other',instance=50000),record(name='Historical',instance=8),
            record(logical=(0x68,11,0x6B,9,0,0),version=19),record(instance=9,kind=0xFDFD),tail=record(instance=10))
        paths=native_routines.routine_paths(data,expected,PROGRAMS)
        self.assertEqual(paths,[row(name='Other',instance=50000),row(),row(program='ProgramB',parent=22)])
        self.assertEqual(native_routines.routine_paths(data,[],PROGRAMS),[])
        self.assertEqual(native_routines.routine_paths(database(),[],{}),[])

    def test_missing_conflicting_and_duplicate_active_records_never_supply_a_partial_inventory(self):
        cases=((database(),EXPECTED),(database(record(),record()),EXPECTED),
            (database(record(),record(instance=8)),EXPECTED),
            (database(record(),record(name='Other')),EXPECTED+[{'program':'ProgramA','name':'Other'}]),
            (database(record(parent=22)),EXPECTED),(database(record(kind=0xFDFD)),EXPECTED),
            (database(record(component_type=0)),EXPECTED))
        for data,expected in cases:
            with self.subTest(expected=expected),self.assertRaises(ModelError):
                native_routines.routine_paths(data,expected,PROGRAMS)

    def test_unknown_body_formats_global_scope_nested_paths_and_invalid_headers_are_withheld(self):
        for bad in (record(version=18),record(version=19),record(version=53),record(version=55),
                record(instance=0),record(header_version=1),record(logical=(0x6D,7,0,0,0,0)),
                record(logical=(0x68,11,0x6D,7,1,0)),record(logical=(0x68,11,0x6D,7,0,1))):
            for data in (database(bad),database(record(),bad)):
                with self.subTest(prefix=bad[:20]),self.assertRaises(ModelError):
                    native_routines.routine_paths(data,EXPECTED,PROGRAMS)
        with self.assertRaises(ModelError):native_routines.routine_paths(database(record(parent=0)),EXPECTED,PROGRAMS)

    def test_expected_inventory_and_program_binding_types_ranges_names_and_limits_are_strict(self):
        for expected in (None,{},'Run',[{'program':'ProgramA','routine':'Run'}],[{'program':'ProgramA','name':'bad.name'}],
                [{'program':'Bad.Name','name':'Run'}],EXPECTED*2,EXPECTED+[{'program':'PROGRAMA','name':'RUN'}]):
            with self.subTest(expected=expected),self.assertRaises(ModelError):
                native_routines.routine_paths(database(record()),expected,PROGRAMS)
        for programs in (None,[],{'Other':11},{'ProgramA':True},{'ProgramA':0},{'ProgramA':65536},
                {'ProgramA':11,'PROGRAMA':12},{'ProgramA':11,'Other':11},{'Bad.Name':11}):
            with self.subTest(programs=programs),self.assertRaises(ModelError):
                native_routines.routine_paths(database(record()),EXPECTED,programs)
        with patch.object(native_routines,'MAX_ROUTINES',0),self.assertRaises(ModelError):
            native_routines.routine_paths(database(record()),EXPECTED,PROGRAMS)
        with patch.object(native_routines,'MAX_PROGRAMS',1),self.assertRaises(ModelError):
            native_routines.routine_paths(database(record()),EXPECTED,PROGRAMS)

    def test_bad_database_lengths_markers_names_record_headers_and_size_limits_fail_closed(self):
        good=database(record());variants=[b'',good[:23],good[:-1]]
        for offset,value,fmt in ((0,len(good),'<I'),(8,len(good)+10,'<I'),(12,10,'<I'),(12,4097,'<I'),
                (512,0x1234,'<H'),(514,5,'<I'),(514,len(good),'<I'),(518,147,'<I'),
                (518,len(good),'<I'),(530,1,'<I')):
            data=bytearray(good);struct.pack_into(fmt,data,offset,value);variants.append(data)
        data=bytearray(good);data[542:666]=b'A\0'*62;variants.append(data)
        data=bytearray(good);data[542:546]=b'\0\xd8\0\0';variants.append(data)
        data=bytearray(good);struct.pack_into('<I',data,518,169);variants.append(data)
        for data in variants:
            with self.subTest(prefix=data[:16]),self.assertRaises(ModelError):
                native_routines.routine_paths(data,EXPECTED,PROGRAMS)
        with patch.object(native_routines,'MAX_RECORDS',0),self.assertRaises(ModelError):
            native_routines.routine_paths(good,EXPECTED,PROGRAMS)
        with patch.object(native_routines,'MAX_BYTES',50),self.assertRaises(ModelError):
            native_routines.routine_paths(good,EXPECTED,PROGRAMS)

    def test_from_acd_compressed_or_raw_requires_same_acd_l5x_and_program_bindings_without_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.ACD'
            for compressed in (True,False):
                original=container(database(record()),compressed);path.write_bytes(original)
                digest=hashlib.sha256(original).hexdigest()
                symbols=NativeSymbols(digest,'b'*64,[],[{'name':'ProgramA','instance':11}])
                catalog=NativeRoutines.from_acd(path,'b'*64,EXPECTED,symbols)
                self.assertEqual(catalog.lookup('PROGRAMA','RUN').manifest(),row())
                self.assertEqual(catalog.source_acd_sha256,digest);self.assertEqual(catalog.source_l5x_sha256,'b'*64)
                self.assertEqual(path.read_bytes(),original)
                for bindings in (None,NativeSymbols('c'*64,'b'*64,[],[{'name':'ProgramA','instance':11}]),
                        NativeSymbols(digest,'c'*64,[],[{'name':'ProgramA','instance':11}]),
                        NativeSymbols(digest,'b'*64,[],[{'name':'ProgramA','instance':12}])):
                    with self.assertRaises(ModelError):NativeRoutines.from_acd(path,'b'*64,EXPECTED,bindings)

    def test_from_acd_compression_expansion_and_stream_bounds_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.ACD';data=container(b'\x1f\x8bbad',False);path.write_bytes(data)
            symbols=NativeSymbols(hashlib.sha256(data).hexdigest(),'b'*64,[],[{'name':'ProgramA','instance':11}])
            with self.assertRaises(ModelError):NativeRoutines.from_acd(path,'b'*64,EXPECTED,symbols)
            data=container(database(record()));path.write_bytes(data)
            symbols=NativeSymbols(hashlib.sha256(data).hexdigest(),'b'*64,[],[{'name':'ProgramA','instance':11}])
            with patch.object(native_routines,'MAX_BYTES',50),self.assertRaises(ModelError):
                NativeRoutines.from_acd(path,'b'*64,EXPECTED,symbols)
            with patch.object(native_routines,'MAX_STREAM_BYTES',10),self.assertRaises(ModelError):
                NativeRoutines.from_acd(path,'b'*64,EXPECTED,symbols)

    def test_immutable_maps_rows_and_manifest_roundtrip_preserve_parent_scopes(self):
        rows=[row(),row(program='ProgramB',parent=22)]
        catalog=NativeRoutines('a'*64,'b'*64,rows);rows[0]['instance']=9
        self.assertEqual(catalog.by_instance[(11,7)].program,'ProgramA')
        self.assertEqual(catalog.by_instance[(22,7)].program,'ProgramB')
        self.assertEqual(catalog.lookup('Missing','Run'),None);self.assertIsNone(catalog.lookup(None,None))
        manifest=catalog.manifest();manifest['routines'][0]['instance']=9
        self.assertEqual(catalog.lookup('ProgramA','Run').instance,7)
        self.assertEqual(NativeRoutines.from_manifest(catalog.manifest(),'b'*64).manifest(),catalog.manifest())
        with self.assertRaises(FrozenInstanceError):catalog.source_acd_sha256='c'*64
        with self.assertRaises(FrozenInstanceError):catalog.rows[0].instance=9
        with self.assertRaises(TypeError):catalog.by_key[('programa','run')]=None
        with self.assertRaises(TypeError):catalog.by_instance[(11,7)]=None
        self.assertFalse(catalog.description()['compiled_code']);self.assertFalse(catalog.description()['compiled_addresses'])

    def test_manifest_duplicate_child_names_parent_identity_conflicts_ranges_and_hashes_are_errors(self):
        good=NativeRoutines('a'*64,'b'*64,[row()]).manifest()
        for rows in (None,(),{},[row(),row()],[row(),row(name='RUN')],[row(),row(name='Other')],
                [row(),row(program='ProgramB')],[row(),row(name='Other',parent=22)],
                [row(instance=True)],[row(parent=0)],[row(instance=65536)],[row(name='bad.name')],[dict(row(),extra=1)]):
            with self.subTest(rows=rows),self.assertRaises(ModelError):
                NativeRoutines.from_manifest(dict(good,routines=rows),'b'*64)
        for field,value in (('source_acd_sha256',''),('source_acd_sha256','A'*64),('source_l5x_sha256','c'*64),('extra',1)):
            changed=copy.deepcopy(good);changed[field]=value
            with self.assertRaises(ModelError):NativeRoutines.from_manifest(changed,'b'*64)
        for field in good:
            changed=copy.deepcopy(good);del changed[field]
            with self.assertRaises(ModelError):NativeRoutines.from_manifest(changed,'b'*64)
        with self.assertRaises(ModelError):NativeRoutines.from_manifest(good,None)
        empty=NativeRoutines.from_manifest(dict(good,routines=[]),'b'*64)
        self.assertEqual(empty.manifest()['routines'],[])
        self.assertTrue(empty.description()['complete']);self.assertEqual(empty.description()['routines'],0)


if __name__=='__main__':unittest.main()
