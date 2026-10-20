"""Synthetic task paths; source hashes and corrupt records cannot invent IDs."""
import copy
from dataclasses import FrozenInstanceError
import gzip
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from logixlab import native_tasks
from logixlab.model import ModelError
from logixlab.native_tasks import NativeTasks


def record(name='MainTask', instance=1, version=18, class_id=0x70, child=(0,0,0,0),
           kind=0xFAFA, component_type=256, header_version=0):
    body=bytes(8)+struct.pack('<7H',version,class_id,instance,*child)
    header=bytearray(148)
    struct.pack_into('<I',header,0,len(header)+len(body))
    struct.pack_into('<H',header,10,component_type)
    struct.pack_into('<I',header,12,header_version)
    encoded=name.encode('utf-16le')+bytes(2)
    header[24:24+len(encoded)]=encoded
    payload=header+body
    return struct.pack('<HI',kind,len(payload)+6)+payload


def database(*records, tail=b''):
    value=bytearray(512)+b''.join(records)
    end=len(value)
    value+=tail
    struct.pack_into('<III',value,0,len(value)-1,0,end-1)
    struct.pack_into('<I',value,12,512)
    return bytes(value)


def container(comps, compressed=True):
    payload=gzip.compress(comps,mtime=0) if compressed else comps
    directory='Comps.Dat'.encode('utf-16le').ljust(520,b'\0')+struct.pack('<II',len(payload),2)
    return b'\r\n'+payload+directory+struct.pack('<II',1,0)


class NativeTasksTests(unittest.TestCase):
    def test_only_expected_active_task_identities_bind_without_collection_or_program_ids(self):
        raw=database(record('RxTaskCollection',0,version=0,component_type=0),
            record(class_id=0x68,version=19,instance=400),record('PeriodicTask',17),record(),
            record('OldTask',9),record(instance=22,kind=0xFDFD),tail=record(instance=33))
        self.assertEqual(native_tasks.task_paths(raw,['MainTask','PeriodicTask']),
            [{'name':'MainTask','instance':1},{'name':'PeriodicTask','instance':17}])
        self.assertEqual(native_tasks.task_paths(raw,['maintask']),[{'name':'maintask','instance':1}])
        self.assertEqual(native_tasks.task_paths(raw,[]),[])
        self.assertEqual(native_tasks.task_paths(database(),[]),[])

    def test_missing_duplicate_and_conflicting_historical_paths_withhold_the_whole_inventory(self):
        for raw,names in ((database(),['MainTask']),
                (database(record(),record()),['MainTask']),
                (database(record(),record(instance=2)),['MainTask']),
                (database(record(),record('OtherTask',1)),['MainTask','OtherTask']),
                (database(record('OtherTask',2)),['MainTask']),
                (database(record(component_type=0)),['MainTask']),
                (database(record(kind=0xFDFD)),['MainTask'])):
            with self.subTest(names=names),self.assertRaises(ModelError):native_tasks.task_paths(raw,names)

    def test_unknown_versions_scopes_and_zero_ids_cannot_be_mistaken_for_active_tasks(self):
        for bad in (record(version=17),record(version=19),record(instance=0),record(child=(1,0,0,0)),
                    record(child=(0,0,0,1)),record(header_version=1)):
            for raw in (database(bad),database(record(),bad)):
                with self.subTest(prefix=bad[:20]),self.assertRaises(ModelError):
                    native_tasks.task_paths(raw,['MainTask'])
        # Class 0x68 IDs never become Task IDs merely because a name matches.
        with self.assertRaises(ModelError):native_tasks.task_paths(database(record(class_id=0x68)),['MainTask'])

    def test_expected_names_are_explicit_valid_case_insensitive_and_bounded(self):
        for names in (None,'MainTask',{},['MainTask','maintask'],[''],['Bad.Name'],['x'*41],[True],[None],
                      ['Task'+str(index) for index in range(33)]):
            with self.subTest(names=names),self.assertRaises(ModelError):native_tasks.task_paths(database(record()),names)
        self.assertEqual(native_tasks.task_paths(database(record(instance=65535)),('MAINTASK',)),
                         [{'name':'MAINTASK','instance':65535}])

    def test_database_record_bounds_header_versions_and_terminated_names_fail_closed(self):
        good=database(record());variants=[b'',good[:23],good[:-1]]
        for offset,value,fmt in ((0,len(good),'<I'),(8,len(good)+5,'<I'),(12,10,'<I'),(12,4097,'<I'),
                (512,0x1234,'<H'),(514,5,'<I'),(514,len(good),'<I'),(518,147,'<I'),
                (518,len(good),'<I'),(518+12,1,'<I')):
            changed=bytearray(good);struct.pack_into(fmt,changed,offset,value);variants.append(changed)
        changed=bytearray(good);changed[518+24:518+148]=b'A\0'*62;variants.append(changed)
        changed=bytearray(good);changed[518+24:518+28]=b'\0\xd8\0\0';variants.append(changed)
        changed=bytearray(good);struct.pack_into('<I',changed,518,169);variants.append(changed)
        for raw in variants:
            with self.subTest(prefix=raw[:16]),self.assertRaises(ModelError):native_tasks.task_paths(raw,['MainTask'])
        with patch.object(native_tasks,'MAX_RECORDS',0),self.assertRaises(ModelError):
            native_tasks.task_paths(good,['MainTask'])
        with patch.object(native_tasks,'MAX_BYTES',50),self.assertRaises(ModelError):
            native_tasks.task_paths(good,['MainTask'])

    def test_compressed_and_raw_acd_paths_bind_both_hashes_without_modifying_the_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.ACD'
            for compressed in (True,False):
                data=container(database(record()),compressed);path.write_bytes(data)
                tasks=NativeTasks.from_acd(path,'b'*64,['MainTask'])
                self.assertEqual(tasks.lookup('MAINTASK'),1)
                self.assertEqual(tasks.tasks,{'maintask':1});self.assertEqual(tasks.task_ids,{1:'maintask'})
                self.assertEqual(tasks.source_acd_sha256,hashlib.sha256(data).hexdigest())
                self.assertEqual(tasks.source_l5x_sha256,'b'*64)
                self.assertEqual(path.read_bytes(),data)
                self.assertFalse(tasks.description()['compiled_addresses'])
                self.assertFalse(tasks.description()['native_edit_authority'])

    def test_corrupt_compressed_acd_and_expansion_limits_remain_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'synthetic.ACD'
            path.write_bytes(container(b'\x1f\x8bbad-compressed-stream',compressed=False))
            with self.assertRaises(ModelError):NativeTasks.from_acd(path,'b'*64,['MainTask'])
            path.write_bytes(container(database(record())))
            with patch.object(native_tasks,'MAX_BYTES',50),self.assertRaises(ModelError):
                NativeTasks.from_acd(path,'b'*64,['MainTask'])
            with patch.object(native_tasks,'MAX_STREAM_BYTES',10),self.assertRaises(ModelError):
                NativeTasks.from_acd(path,'b'*64,['MainTask'])

    def test_manifest_round_trip_lookup_and_empty_inventory_are_immutable_and_explicit(self):
        rows=[{'name':'MainTask','instance':1}]
        catalog=NativeTasks('a'*64,'b'*64,rows);rows[0]['instance']=5
        manifest=catalog.manifest();manifest['tasks'][0]['instance']=7
        self.assertEqual(catalog.lookup('maintask'),1)
        self.assertEqual(catalog.lookup('Unknown'),None);self.assertEqual(catalog.lookup(None),None)
        self.assertEqual(NativeTasks.from_manifest(catalog.manifest(),'b'*64).manifest(),catalog.manifest())
        with self.assertRaises(FrozenInstanceError):catalog.source_l5x_sha256='c'*64
        with self.assertRaises(FrozenInstanceError):catalog.rows[0].instance=2
        with self.assertRaises(TypeError):catalog.tasks['maintask']=5
        with self.assertRaises(TypeError):catalog.task_ids[1]='other'
        empty=NativeTasks.from_manifest({'source_acd_sha256':'a'*64,'source_l5x_sha256':'b'*64,'tasks':[]},'b'*64)
        self.assertEqual(empty.manifest()['tasks'],[])
        self.assertTrue(empty.description()['complete']);self.assertEqual(empty.description()['tasks'],0)

    def test_manifest_hashes_fields_duplicate_ids_ranges_and_ambiguous_names_fail_closed(self):
        good={'source_acd_sha256':'a'*64,'source_l5x_sha256':'b'*64,'tasks':[{'name':'MainTask','instance':1}]}
        for rows in (None,(),{},[{'name':'MainTask','instance':True}],[{'name':'MainTask','instance':0}],
                [{'name':'MainTask','instance':65536}],[{'name':'Bad.Name','instance':1}],
                [{'name':'MainTask','instance':1},{'name':'MAINTASK','instance':2}],
                [{'name':'MainTask','instance':1},{'name':'Other','instance':1}],
                [{'name':'MainTask','instance':1,'extra':0}]):
            with self.subTest(rows=rows),self.assertRaises(ModelError):
                NativeTasks.from_manifest({**good,'tasks':rows},'b'*64)
        for field,value in (('source_acd_sha256',''),('source_acd_sha256','A'*64),
                            ('source_l5x_sha256','c'*64),('extra',1)):
            changed=copy.deepcopy(good);changed[field]=value
            with self.assertRaises(ModelError):NativeTasks.from_manifest(changed,'b'*64)
        for field in good:
            changed=copy.deepcopy(good);del changed[field]
            with self.assertRaises(ModelError):NativeTasks.from_manifest(changed,'b'*64)
        with self.assertRaises(ModelError):NativeTasks.from_manifest(good,None)


if __name__=='__main__':unittest.main()
