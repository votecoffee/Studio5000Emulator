"""Stored Task settings never import runtime state or invent missing values."""
import base64
import copy
from dataclasses import FrozenInstanceError,replace
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

import test_native_tasks as containers
import test_runtime as runtime
import test_programming_lease as leases
from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_symbols import NativeSymbols
from logixlab.native_tasks import NativeTasks
from logixlab.native_task_configuration import BODY_BYTES,StoredTaskConfiguration,read
from logixlab.server import Application
from tools.collection_inventory import decode_attribute_list


def body(*,kind=4,rate=10000,priority=10,watchdog=500000,programs=(26038,),disable=False,inhibited=False):
    data=bytearray(BODY_BYTES)
    struct.pack_into('<7H',data,8,18,0x70,1,0,0,0,0)
    struct.pack_into('<H',data,90,len(programs))
    for n,instance in enumerate(programs):struct.pack_into('<I',data,92+4*n,instance)
    struct.pack_into('<I',data,4204,rate);struct.pack_into('<H',data,4212,5)
    struct.pack_into('<HH',data,4342,kind,priority);struct.pack_into('<I',data,4362,watchdog)
    struct.pack_into('<II',data,4398,disable,inhibited)
    return data


def full_record(data):
    header=bytearray(containers.record()[6:154]);struct.pack_into('<I',header,0,len(header)+len(data))
    return struct.pack('<HI',0xFAFA,6+len(header)+len(data))+header+data


class StoredTaskConfigurationTests(unittest.TestCase):
    setUp=runtime.RuntimeTests.setUp
    engine=runtime.RuntimeTests.engine

    def test_static_fields_and_exact_encodings_ignore_runtime_and_extended_properties(self):
        raw=body();raw[:8]=bytes.fromhex('123456789abcdef0')
        for offset in (4208,4346,4350,4354,4366,4374,4382,4390,4462):raw[offset:offset+4]=bytes.fromhex('deadbeef')
        row=read(raw)
        self.assertEqual(row.attributes(),{2:struct.pack('<I',10000),4:bytes.fromhex('05000000000000'),
            5:struct.pack('<H',4),17:bytes(4),21:bytes(2)})
        self.assertEqual(row.programs,(26038,))
        self.assertEqual(StoredTaskConfiguration.from_manifest(row.manifest()),row)
        self.assertNotIn('address',str(row.manifest()))
        with self.assertRaises(FrozenInstanceError):row.rate_us=25

    def test_unsupported_bodies_withhold_optional_configuration_without_losing_identity(self):
        variants=[body()[:-1],body()+bytes(1)]
        for offset,value,fmt in ((8,19,'<H'),(90,1029,'<H'),(92,0,'<I'),(4204,0,'<I'),
                (4204,0x80000000,'<I'),(4212,0,'<H'),(4214,1,'<B'),(4220,1,'<B'),
                (4342,1,'<H'),(4344,16,'<H'),(4362,0,'<I'),(4394,1,'<I'),
                (4398,2,'<I'),(4402,2,'<I'),(4406,6,'<H'),(4408,1,'<H'),(96,1,'<I')):
            raw=body();struct.pack_into(fmt,raw,offset,value);variants.append(raw)
        for raw in variants:
            with self.subTest(size=len(raw)):self.assertIsNone(read(raw))
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'synthetic.ACD';path.write_bytes(containers.container(containers.database(full_record(body()[:-1]))))
            catalog=NativeTasks.from_acd(path,'b'*64,['MainTask'])
            self.assertEqual(catalog.lookup('MainTask'),1);self.assertFalse(catalog.configurations)

    def test_full_record_catalog_and_legacy_manifests_are_immutable_and_compatible(self):
        with tempfile.TemporaryDirectory() as name:
            path=Path(name)/'synthetic.ACD';path.write_bytes(containers.container(containers.database(full_record(body()))))
            catalog=NativeTasks.from_acd(path,'b'*64,['MainTask']);manifest=catalog.manifest()
            self.assertEqual(NativeTasks.from_manifest(manifest,'b'*64).manifest(),manifest)
            self.assertEqual(catalog.configurations['maintask'].kind_code,4)
            manifest['configuration']['maintask']['programs'][0]=9
            self.assertEqual(catalog.configurations['maintask'].programs,(26038,))
            with self.assertRaises(TypeError):catalog.configurations['maintask']=read(body())
            legacy=NativeTasks(catalog.source_acd_sha256,'b'*64,[{'name':'MainTask','instance':1}])
            self.assertNotIn('configuration',legacy.manifest())
            self.assertEqual(NativeTasks.from_manifest(legacy.manifest(),'b'*64).manifest(),legacy.manifest())

    def test_manifest_validation_refuses_unknown_names_shapes_types_and_profiles(self):
        row=read(body());catalog=NativeTasks('a'*64,'b'*64,[{'name':'MainTask','instance':1}],configurations={'maintask':row})
        for field,value in (('rate_us',True),('kind_code',1),('trigger_hex','00'),('timeout_us',1),
                ('data_use',6),('tag_mapping_count',True),('programs',(26038,)),('priority',False),('extra',1)):
            manifest=catalog.manifest();manifest['configuration']['maintask'][field]=value
            with self.subTest(field=field),self.assertRaises(ModelError):NativeTasks.from_manifest(manifest,'b'*64)
        manifest=catalog.manifest();manifest['configuration']['other']=manifest['configuration'].pop('maintask')
        with self.assertRaises(ModelError):NativeTasks.from_manifest(manifest,'b'*64)
        with self.assertRaises(ModelError):NativeTasks('a'*64,'b'*64,[],configurations=[])

    def test_complete_source_binding_and_schedule_are_required_for_every_stored_field(self):
        project=self.engine(['NOP();']).project;digest=project.sha256
        identity=NativeProjectIdentity('a'*64,digest,0,1,0,1,2,3)
        programs=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        row=read(body());catalog=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}],configurations={'maintask':row})
        self.assertEqual(catalog.configuration_attributes(project,'MainTask',identity,programs),row.attributes())
        for ident,syms in ((None,programs),(identity,None),
                (NativeProjectIdentity('b'*64,digest,0,1,0,1,2,3),programs),
                (identity,NativeSymbols('b'*64,digest,[],[{'name':'MainProgram','instance':26038}])),
                (identity,NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':7}]))):
            self.assertEqual(catalog.configuration_attributes(project,'MainTask',ident,syms),{})
        for replacement in (replace(row,kind_code=2),replace(row,watchdog_us=700000),replace(row,priority=7),replace(row,inhibited=True)):
            bad=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}],configurations={'maintask':replacement})
            self.assertEqual(bad.configuration_attributes(project,'MainTask',identity,programs),{})

    def test_continuous_stored_rate_is_not_defaulted_and_explicit_source_rates_must_match(self):
        for kind,source_rate,stored_rate,expected in (('Continuous',None,25000,True),('Continuous','25',25000,True),
                ('Continuous','25',10000,False),('Continuous','bad',10000,False),
                ('Periodic','25',25000,True),('Periodic','25',10000,False),('Periodic',None,10000,False)):
            self.root=E.parse(runtime.SAMPLE).getroot()
            def mutate(root):
                task=root.find('./Controller/Tasks/Task');task.set('Type',kind)
                if source_rate is None:task.attrib.pop('Rate',None)
                else:task.set('Rate',source_rate)
            project=self.engine(['NOP();'],mutate=mutate).project
            result=project.task_timing.matches_stored('MainTask',source_sha256=project.sha256,
                kind_code=4 if kind=='Continuous' else 2,rate_us=stored_rate,watchdog_us=500000)
            with self.subTest(kind=kind,source=source_rate,stored=stored_rate):self.assertEqual(result,expected)
            if kind=='Continuous':self.assertNotIn(2,project.task_timing.attributes('MainTask',source_sha256=project.sha256))

    def test_source_context_event_safety_and_noncanonical_task_settings_cannot_unlock_stored_fields(self):
        for kind in ('context','event','safety','unknown-setting','duplicate-schedule'):
            self.root=E.parse(runtime.SAMPLE).getroot()
            def mutate(root):
                task=root.find('./Controller/Tasks/Task')
                if kind=='context':root.set('ContainsContext','true')
                elif kind=='event':task.set('Type','Event')
                elif kind=='safety':task.set('Class','Safety')
                elif kind=='unknown-setting':task.set('FutureSetting','true')
                else:task.find('ScheduledPrograms').append(copy.deepcopy(task.find('./ScheduledPrograms/ScheduledProgram')))
            project=self.engine(['NOP();'],mutate=mutate).project;digest=project.sha256
            native=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}],configurations={'maintask':read(body())})
            identity=NativeProjectIdentity('a'*64,digest,0,1,0,1,2,3)
            programs=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
            with self.subTest(kind=kind):self.assertEqual(native.configuration_attributes(project,'MainTask',identity,programs),{})

    def test_optional_configuration_survives_reset_and_clears_with_a_plain_source_import(self):
        with tempfile.TemporaryDirectory() as name:
            app=Application(name)
            try:
                data=runtime.SAMPLE.read_bytes();import hashlib
                digest=hashlib.sha256(data).hexdigest()
                native=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}],configurations={'maintask':read(body())})
                source={'name':'demo.L5X','content':base64.b64encode(data).decode()}
                app.command('load',{**source,'native_tasks':native.manifest()})
                for action in ('reset','configure'):
                    app.command(action,{})
                    self.assertEqual(app.native_tasks.manifest(),native.manifest())
                    self.assertEqual(app.native_tasks.description()['configuration_tasks'],1)
                app.command('load',source);self.assertIsNone(app.native_tasks)
            finally:app.close()


class StoredTaskWireTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare

    def test_signed_mixed_stored_and_unknown_fields_preserve_order_and_deny_writes(self):
        self.prepare();project=self.app.engine.project;digest=project.sha256
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}],configurations={'maintask':read(body())})
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        before=copy.deepcopy(self.app.state());numbers=(2,4,5,17,21,24,25,4)
        request=bytes.fromhex('030220702401')+struct.pack('<9H',8,*numbers)
        fields=decode_attribute_list(self.signed(4,request),numbers,0x70,include_payloads=True)['attributes']
        self.assertEqual([f['status'] for f in fields],[0,0,0,0,0,20,20,0])
        self.assertEqual(fields[1]['data_hex'],'05000000000000');self.assertEqual(fields[2]['data_hex'],'0400')
        self.assertEqual(self.signed(5,bytes.fromhex('0e03207024013002')),bytes.fromhex('8e00000010270000'))
        self.assertEqual(self.signed(6,bytes.fromhex('10032070240130050200'))[2],15)
        self.app.native_project_identity=None
        self.assertEqual(self.signed(7,bytes.fromhex('0e03207024013005'))[2],20)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])


if __name__=='__main__':unittest.main()
