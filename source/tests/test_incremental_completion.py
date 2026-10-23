"""Temporary update processing requires complete coverage and actual readback."""
import copy
from dataclasses import replace
import struct
import tempfile
import unittest
from types import MappingProxyType
import zlib

from logixlab.server import Application
from logixlab.download_image import ImageError
from logixlab.incremental_download import IncrementalDownload
from logixlab.resilient_transport import ResilientTransport,TransportError
from logixlab.ethernetip import logical
from logixlab.download_namespace import VALUE_BASE
from test_download_namespace import NamespaceFixture,STATUS,ENUM
import test_download_headers as headers
import test_download_metadata as metadata
import test_native_metadata_values as original
import test_device_payload as payloads
import test_object_staging as objects
import test_resilient_transport as transport
import test_diagnostic_staging as diagnostics


DATA=bytes.fromhex('010d0000000d00000000000000')


def component(program=2,instance=1,data=DATA,selectors=(1,9),size=13):
    path=logical(0x20,0x68)+logical(0x24,program)+logical(0x20,0x6D)+logical(0x24,instance)
    inner=bytes((0x5C,len(path)//2))+path+struct.pack('<II',*selectors)+data
    return metadata.request(2,1,struct.pack('<II',0x301,size)+inner,0x33)


class ComponentTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.app=Application(folder.name);self.namespace,self.bindings=headers.fixture(self.app)
        self.image=self.namespace._image;self.source=self.image.source

    def prepare(self,rows):return IncrementalDownload.prepare(rows,self.image,self.source,header_bindings=self.bindings)

    def test_exact_opaque_component_is_stored_and_read_back_only_for_bound_routine(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        stage=self.prepare((objects.coordinate(),component(),objects.coordinate(acquire=False)))
        self.assertEqual(stage.read_routine_data(2,1,self.image,self.source,self.bindings),DATA)
        stage.verify_effects(self.image,self.source,header_bindings=self.bindings)
        state=stage.description()
        self.assertEqual((state['routine_data_records'],state['routine_data_bytes'],state['result_records']),(1,13,3))
        self.assertFalse(state['routine_data_interpreted'] or state['commit'])
        self.assertEqual(self.app.engine.memory.values,before)
        for program,instance in ((True,1),(2,True),(2,2)):
            with self.assertRaises(ImageError):stage.read_routine_data(program,instance,self.image,self.source,self.bindings)

    def test_bounds_selectors_payload_duplicates_and_unknown_targets_never_publish(self):
        for row in (component(data=DATA[:-1]),component(data=DATA+b'X'),component(size=12),component(selectors=(1,3)),
                    component(data=DATA[:-1]+b'\1'),component(program=3),component(instance=99)):
            with self.subTest(raw=row.request.hex()),self.assertRaises(ImageError):
                self.prepare((objects.coordinate(),row,objects.coordinate(acquire=False)))
        with self.assertRaises(ImageError):self.prepare((component(),))
        with self.assertRaises(ImageError):self.prepare((objects.coordinate(),component(),component(),objects.coordinate(acquire=False)))
        with self.assertRaises(ImageError):IncrementalDownload.prepare((objects.coordinate(),component(),objects.coordinate(acquire=False)),self.image,self.source)
        self.assertEqual(self.image.read_table(1,0,4,self.source),bytes(4))

    def test_original_routine_and_ledger_are_rechecked_including_current_runtime(self):
        stage=self.prepare((objects.coordinate(),component(),objects.coordinate(acquire=False)))
        stage._routine_data=MappingProxyType({(2,1):b'changed'})
        with self.assertRaises(ImageError):stage.verify_effects(self.image,self.source,header_bindings=self.bindings)
        stage._routine_data=MappingProxyType({(2,1):DATA})
        stage._effects=(replace(stage._effects[0],expected=(2,True,False)),)+stage._effects[1:]
        with self.assertRaises(ImageError):stage.verify_effects(self.image,self.source,header_bindings=self.bindings)
        self.app.engine.project.runtime_revision=1
        with self.assertRaises(ImageError):self.prepare((objects.coordinate(),component(),objects.coordinate(acquire=False)))

    def test_complete_headers_and_components_share_a_fully_verified_record_ledger(self):
        case=headers.HeaderTests();case.app=self.app;case.bindings=self.bindings
        rows=list(case.batch());rows[10:10]=[component(),component(instance=2)]
        stage=self.prepare(tuple(rows));stage.verify_effects(self.image,self.source,header_bindings=self.bindings)
        self.assertEqual((stage.records,len(stage._effects)),(14,14))
        stage._headers=MappingProxyType({})
        with self.assertRaises(ImageError):stage.verify_effects(self.image,self.source,header_bindings=self.bindings)


class CompletionTests(unittest.TestCase):
    def setUp(self):
        import test_download_image as images
        self.image=images.prepare();self.source=self.image.source
        self.stage=ResilientTransport()
        self.rows=(metadata.table(),diagnostics.request(b'\0\0',service=4))
        expanded=b''.join(payloads.record(r.request) for r in self.rows)
        self.expanded=expanded;payloads.fill(self.stage,payloads.container(zlib.compress(expanded)),expanded)

    def test_status_requires_start_then_returns_exact_expanded_coverage_and_is_repeatable(self):
        self.stage.prepare_incremental_payload(self.image,self.source)
        with self.assertRaises(TransportError):self.stage.incremental_execution_status(self.image,self.source)
        state=self.stage.start_incremental_payload(self.image,self.source)
        self.assertEqual(state['effects_verified'],2)
        for _ in range(2):
            raw,state=self.stage.incremental_execution_status(self.image,self.source)
            self.assertEqual(raw,struct.pack('<BIH',0,len(self.expanded),0))
        self.assertTrue(self.stage.incremental_status_reported)
        self.assertFalse(self.stage.execution_status_reported)
        self.assertEqual(self.image.read_table(1,0,4,self.source),bytes(4))
        self.stage.clear();self.assertFalse(self.stage.incremental_started or self.stage.incremental_status_reported)

    def test_changed_stored_effect_request_or_byte_coverage_denies_completion(self):
        for case in ('effect','request','expanded','ledger'):
            self.setUp();self.stage.start_incremental_payload(self.image,self.source)
            if case=='effect':self.stage.incremental._tables={}
            elif case=='request':self.stage.incremental.record_sha256='a'*64
            elif case=='expanded':self.stage.incremental_inspection['expanded_bytes']+=1
            else:self.stage.incremental._effects=()
            with self.subTest(case=case),self.assertRaises((TransportError,ImageError)):
                self.stage.incremental_execution_status(self.image,self.source)
            self.assertFalse(self.stage.incremental_status_reported)


class CompletionSignedTests(NamespaceFixture,unittest.TestCase):
    def next_batch(self,rows):
        from test_incremental_download import IncrementalSignedTests
        expanded=b''.join(payloads.record(r.request) for r in rows)
        IncrementalSignedTests.next_batch(self,expanded)
        return len(expanded)

    def test_owner_can_complete_delete_and_read_retained_overlay_without_changing_base_or_runtime(self):
        self.retain();ns=self.endpoint.programming_lease.download_namespace
        before=copy.deepcopy(self.app.engine.memory.values)
        size=self.next_batch((metadata.table(),diagnostics.request(b'\0\0',service=4)))
        self.assertEqual(self.send(STATUS)[2],12)
        self.assertEqual(self.send(payloads.INSPECT)[2],0)
        for _ in range(2):self.assertEqual(self.send(STATUS),bytes.fromhex('cd000000')+struct.pack('<BIH',0,size,0))
        self.assertEqual(ns.read_values(VALUE_BASE,4),bytes(4))
        self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertIs(self.endpoint.programming_lease.download_namespace,ns)
        self.assertEqual(ns.read_values(VALUE_BASE,4),b'\x32\0\0\0')
        self.assertEqual(ns._image.read_table(1,0,4,ns._source),bytes(4))
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(ns.description()['incremental_records'],2)
        self.assertFalse(self.description()['incremental_staging']['status_reported'])
        self.assertEqual(self.send(ENUM)[2],0)
        self.next_batch((metadata.table(b'\x63\0\0\0'),))
        self.assertEqual(self.send(payloads.INSPECT)[2],12)
        self.assertEqual(ns.read_values(VALUE_BASE,4),b'\x32\0\0\0')
        self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertEqual(ns.description()['incremental_records'],2)
        self.app.command('reset',{})
        self.assertIsNone(self.endpoint.programming_lease.download_namespace)

    def test_delete_without_status_does_not_retain_updates(self):
        self.retain();ns=self.endpoint.programming_lease.download_namespace
        self.next_batch((metadata.table(),))
        self.assertEqual(self.send(payloads.INSPECT)[2],0)
        self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertEqual(ns.description()['incremental_batches_retained'],0)

    def test_current_catalog_changes_revoke_completed_overlay(self):
        self.retain();ns=self.endpoint.programming_lease.download_namespace
        identity=self.app.native_project_identity
        self.app.native_metadata_values=original.catalog(acd=identity.source_acd_sha256,l5x=self.app.engine.project.sha256)
        self.next_batch((metadata.metadata(self.app.native_metadata_values.rows[3]),metadata.table()))
        self.assertEqual(self.send(payloads.INSPECT)[2],0)
        self.assertEqual(self.send(STATUS)[2],0)
        self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertEqual(ns.description()['incremental_batches_retained'],1)
        self.app.native_metadata_values=None
        self.assertEqual(self.send(ENUM)[2],12)
