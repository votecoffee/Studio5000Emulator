"""Later source-equivalent routines retain exact bytes and separate ledgers."""
import copy
from dataclasses import replace
import json
import struct
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E
import zlib

from logixlab.download_image import ImageError
from logixlab.download_routines import RoutineBindings,RoutineBatch
from logixlab.ethernetip import logical
from logixlab.resilient_transport import ResilientTransport,TransportError
import test_download_headers as headers
import test_download_setup as setup
import test_incremental_completion as completion
from test_download_metadata import request
from test_download_namespace import NamespaceFixture,STATUS,ENUM
import test_device_payload as payloads
import test_object_staging as objects
import test_resilient_transport as transport
import test_routine_source as sources
import test_programming_preparation as prep


ORIGINAL_ROUTE=headers.io_tests.IOMapTests.local_route


def nop_route(self):
    result=ORIGINAL_ROUTE(self)
    for content in result[1].findall('./Programs/Program/Routines/Routine/RLLContent'):
        content.clear();E.SubElement(E.SubElement(content,'Rung',Type='N',Number='0'),'Text').text='NOP();'
    return result


def component(instance,data,size,program=2):
    path=logical(0x20,0x68)+logical(0x24,program)+logical(0x20,0x6D)+logical(0x24,instance)
    inner=bytes((0x5C,len(path)//2))+path+data
    return request(2,1,struct.pack('<II',0x301,size)+inner,0x33)


def routine(instance=1,name='MainRoutine',text='NOP();',marker=100):
    elf=b'\x7fELF'+bytes(60)
    code=struct.pack('<4I',3,1,marker,0)+struct.pack('<5I',9,0,0,0,len(elf))+elf
    source=struct.pack('<II',1,3)+sources.container(E.tostring(sources.xml_source(name,text)))
    attachment=struct.pack('<5I',2,5,0,1,marker)
    return (component(instance,code,len(code)-16),component(instance,source,len(source)-8),component(instance,attachment,8))


def batch():
    acquire=objects.coordinate()
    acquire=replace(acquire,request=acquire.request[:-1]+b'\0')
    return (acquire,*routine(),*routine(2,'Reporting',marker=101),objects.coordinate(acquire=False))


def empty_route(self):
    root,controller,*rest=nop_route(self)
    controller.find('./Programs/Program/Routines/Routine[@Name="MainRoutine"]/RLLContent').clear()
    return root,controller,*rest


def empty_routine(instance=1,name='MainRoutine'):
    root=sources.xml_source(name);root.remove(root[0])
    source=struct.pack('<II',1,3)+sources.container(E.tostring(root))
    return component(instance,source,len(source)-8),component(instance,struct.pack('<4I',2,5,0,0),4)


def empty_batch():
    rows=batch()
    return rows[:1]+empty_routine()+rows[4:]


class EmptyRoutineTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.app=headers.Application(folder.name);self.addCleanup(self.app.close)
        with patch.object(headers.io_tests.IOMapTests,'local_route',empty_route):
            self.namespace,self.hb=headers.fixture(self.app)
        self.bindings=RoutineBindings(self.hb,self.app.native_types)

    def test_empty_download_has_exact_source_zero_count_attachment_and_no_code_effect(self):
        engine=self.app.engine;before=copy.deepcopy(engine.memory.values);rows=empty_batch()
        stage=RoutineBatch.prepare(rows,self.bindings);stage.verify_effects(self.bindings)
        self.assertEqual((stage.records,stage.description()['empty_routines'],stage.description()['source_rungs']),(7,1,1))
        self.assertEqual([r.kind for r in stage._effects],['coordination','source','attachment','code','source','attachment','coordination'])
        raw=stage.read(2,1,'source',self.bindings)
        self.assertEqual(self.bindings.source((2,1),raw[8:]).rungs,())
        self.assertEqual(stage.read(2,1,'attachment',self.bindings),struct.pack('<4I',2,5,0,0))
        self.assertEqual(raw,rows[1].request[2+2*rows[1].request[1]+8+2+8:])
        with self.assertRaisesRegex(ImageError,'code_unavailable'):stage.read(2,1,'code',self.bindings)
        self.assertIs(self.app.engine,engine);self.assertEqual(engine.memory.values,before)
        self.assertEqual((engine.scan_count,engine.time_ms),(0,0));self.assertFalse(engine.project.routines['mainprogram/mainroutine'].rungs)

    def test_empty_and_nonempty_profiles_cannot_replace_each_other_or_fabricate_code(self):
        rows=empty_batch()
        cases=(batch(),rows[:1]+(routine()[0],)+rows[1:],rows[:2]+(routine()[2],)+rows[3:],
               rows[:3]+empty_routine(2,'Reporting')+rows[-1:],rows[:2]+rows[1:2]+rows[2:],rows[:2]+rows[3:])
        for value in cases:
            with self.subTest(count=len(value)),self.assertRaises(ImageError):RoutineBatch.prepare(value,self.bindings)
        self.assertIsNone(self.namespace._routine_batch)


class RoutineTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.app=headers.Application(folder.name);self.addCleanup(self.app.close)
        with patch.object(headers.io_tests.IOMapTests,'local_route',nop_route):
            self.namespace,self.hb=headers.fixture(self.app)
        self.bindings=RoutineBindings(self.hb,self.app.native_types)

    def prepare(self,rows=None):return RoutineBatch.prepare(batch() if rows is None else rows,self.bindings)

    def test_source_equivalence_exact_readback_and_separate_ledgers_preserve_runtime(self):
        before=copy.deepcopy(self.app.engine.memory.values);base=self.namespace._image
        stage=self.prepare();stage.verify_effects(self.bindings)
        self.assertEqual((stage.records,len(stage._effects)),(8,8))
        for instance,name in ((1,'MainRoutine'),(2,'Reporting')):
            for kind,row in zip(('code','source','attachment'),routine(instance,name,marker=99+instance),strict=True):
                inner=row.request[2+2*row.request[1]+8:]
                self.assertEqual(stage.read(2,instance,kind,self.bindings),inner[2+2*inner[1]:])
        state=stage.description();self.assertEqual((state['routines'],state['source_rungs']),(2,2))
        for flag in ('compiled_code_verified','compiled_code_executed','active_project_changed','commit','payloads_exposed'):
            self.assertFalse(state[flag])
        self.assertNotIn('MainRoutine',json.dumps(state));self.assertIs(self.namespace._image,base)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        for args in ((True,1,'code'),(2,True,'source'),(2,3,'code'),(2,1,'other')):
            with self.assertRaises(ImageError):stage.read(*args,self.bindings)

    def test_missing_duplicate_out_of_order_unreserved_and_foreign_components_are_atomic(self):
        rows=batch()
        cases=(rows[1:],rows[:-1],rows[:4]+rows[-1:],rows[:2]+rows[3:4]+rows[2:3]+rows[4:],
               (objects.coordinate(),)+rows[1:],
               rows[:4]+rows[1:4]+rows[4:],rows[:1]+routine(99)+rows[4:],rows[:1]+routine(text='XIC(Missing)NOP();')+rows[4:],
               rows[:1]+routine(name='Other')+rows[4:],rows[:1]+routine(text='NOP();NOP();')+rows[4:])
        for value in cases:
            with self.subTest(count=len(value)),self.assertRaises(ImageError):self.prepare(value)
        self.assertIsNone(self.namespace._routine_batch)

    def test_payload_lengths_selectors_markers_code_extent_and_scopes_are_enforced(self):
        rows=batch();row=rows[1];offset=2+2*row.request[1]
        for where in (offset,offset+4,offset+8,offset+8+2+8+12,offset+8+2+8+16+16):
            raw=bytearray(row.request);raw[where]^=1
            # Reparse the complete wire record independently from the staged object.
            changed=payloads.dp.records(struct.pack('<I',len(raw))+bytes(raw))[0]
            with self.subTest(where=where),self.assertRaises(ImageError):self.prepare(rows[:1]+(changed,)+rows[2:])
        inner=rows[3].request;bad=inner[:-1]+bytes((inner[-1]^1,))
        changed=payloads.dp.records(struct.pack('<I',len(bad))+bad)[0]
        with self.assertRaises(ImageError):self.prepare(rows[:3]+(changed,)+rows[4:])
        with self.assertRaises(ImageError):self.prepare((replace(rows[0],scopes=()),)+rows[1:])
        with patch('logixlab.download_routines.MAX_COMPONENT',32),self.assertRaises(ImageError):self.prepare()
        with patch('logixlab.download_routines.MAX_STORAGE',32),self.assertRaises(ImageError):self.prepare()

    def test_source_type_runtime_and_each_retained_effect_remain_bound(self):
        stage=self.prepare()
        for case in ('values','ledger','digest','record'):
            altered=copy.copy(stage)
            if case=='values':altered._values={}
            elif case=='ledger':altered._effects=()
            elif case=='digest':altered._digest='0'*64
            else:altered.record_sha256='0'*64
            with self.subTest(case=case),self.assertRaises(ImageError):altered.verify_effects(self.bindings)
        self.app.native_types.type_ids['inner']=0x301
        with self.assertRaises(ImageError):stage.verify_effects(self.bindings)
        self.app.engine.project.runtime_revision=1
        with self.assertRaises(ImageError):self.prepare()

    def test_transport_start_status_expiry_and_changed_coverage_are_separate_from_second_batch(self):
        clock=[0];transport_stage=ResilientTransport(clock=lambda:clock[0]);rows=batch()
        expanded=b''.join(payloads.record(r.request) for r in rows)
        payloads.fill(transport_stage,payloads.container(zlib.compress(expanded)),expanded)
        with self.assertRaises(TransportError):transport_stage.routine_execution_status(self.bindings)
        state=transport_stage.start_routine_payload(self.bindings);self.assertEqual(state['effects_verified'],8)
        for _ in range(2):
            raw,_=transport_stage.routine_execution_status(self.bindings)
            self.assertEqual(raw,struct.pack('<BIH',0,len(expanded),0))
        self.assertFalse(transport_stage.incremental_started or transport_stage.incremental_status_reported)
        transport_stage.incremental_inspection['expanded_bytes']+=1
        with self.assertRaises(TransportError):transport_stage.routine_execution_status(self.bindings)
        clock[0]=31;transport_stage.expire()
        self.assertIsNone(transport_stage.routine_batch);self.assertFalse(transport_stage.routine_status_reported)


class RoutineSignedTests(NamespaceFixture,unittest.TestCase):
    complete_tasks=setup.SetupSignedTests.complete_tasks
    configure=setup.SetupSignedTests.configure
    ready_setup=setup.SetupSignedTests.ready_setup

    def setUp(self):
        with patch.object(headers.io_tests.IOMapTests,'local_route',nop_route):setup.SetupSignedTests.setUp(self)

    def ready_routines(self):
        self.ready_setup()
        for cls,payload in self.payloads.items():self.assertEqual(self.send(setup.request(cls,payload))[2],0)
        return self.namespace._image,self.namespace._incremental

    def next_routines(self):return completion.CompletionSignedTests.next_batch(self,batch())

    def test_owner_retains_third_batch_only_after_status_and_preserves_prior_ledgers(self):
        base,updates=self.ready_routines();before=copy.deepcopy(self.app.engine.memory.values);size=self.next_routines()
        self.assertEqual(self.send(STATUS)[2],12);self.assertEqual(self.send(payloads.INSPECT)[2],0)
        self.assertEqual(self.send(STATUS),b'\xcd\0\0\0'+struct.pack('<BIH',0,size,0))
        self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertIs(self.namespace._image,base);self.assertIs(self.namespace._incremental,updates)
        self.assertEqual(self.namespace._routine_batch.records,8);self.assertEqual(self.send(ENUM)[2],0)
        self.next_routines();self.assertEqual(self.send(payloads.INSPECT)[2],15)
        self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        self.assertEqual(self.send(prep.END)[2],0);self.assertIsNone(self.endpoint.programming_lease.download_namespace)

    def test_incomplete_setup_unreported_result_and_foreign_client_never_retain(self):
        self.next_routines();self.assertEqual(self.send(payloads.INSPECT)[2],12)
        self.assertEqual(self.send(transport.DELETE)[2],0);self.ready_routines();self.next_routines()
        first=self.client;second=self.second_client()
        try:
            self.client=second;self.assertEqual(self.signed(4,payloads.INSPECT)[2],15)
        finally:self.client=first;second.close()
        self.assertEqual(self.send(payloads.INSPECT)[2],0);self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertIsNone(self.namespace._routine_batch)
        self.assertEqual(self.send(ENUM)[2],0)

    def test_retained_source_or_effect_change_revokes_later_namespace_requests(self):
        self.ready_routines();self.next_routines();self.send(payloads.INSPECT);self.send(STATUS);self.send(transport.DELETE)
        stage=self.namespace._routine_batch;self.assertIsNotNone(stage)
        stage._values={};self.assertEqual(self.send(ENUM)[2],12)
        self.assertEqual(self.send(prep.END)[2],0)


if __name__=='__main__':unittest.main()
