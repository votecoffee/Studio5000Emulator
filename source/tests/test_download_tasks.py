"""Source-bound temporary Task Create/configuration and strict owner cleanup."""
import copy
from dataclasses import replace
import json
import struct
import tempfile
import unittest
from unittest.mock import patch

from logixlab.download_image import ImageError
from logixlab.download_tasks import DownloadTasks,TaskBindings,TASK_BASE,attributes
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_tasks import NativeTasks
from logixlab.native_task_configuration import StoredTaskConfiguration
from logixlab.native_symbols import NativeSymbols
from logixlab.native_routines import NativeRoutines
from logixlab.incremental_download import IncrementalDownload
from logixlab.ethernetip import Endpoint
from test_ethernetip import Client
from test_download_namespace import NamespaceFixture,STATUS,ENUM
import test_download_headers as headers
import test_incremental_completion as updates
import test_download_metadata as metadata
import test_device_payload as payloads
import test_resilient_transport as transport
import test_programming_preparation as prep
import test_programming_lease as leases

CREATE=bytes.fromhex('080220702401')
LINK=struct.pack('<HHIH',2,3,TASK_BASE,13)+bytes.fromhex('0220702401')
CLEAR=bytes.fromhex('01000d0000')
HTTP_DISABLE=bytes.fromhex('100320f52400306500')


def configuration(values=None):
    values=values or {2:struct.pack('<I',10000),4:b'\5\0'+bytes(5),5:b'\4\0',6:b'\x0a\0',
        12:struct.pack('<I',500000),17:bytes(4),18:bytes(4),19:bytes(4),1:struct.pack('<HI',1,2)}
    return struct.pack('<H',len(values))+b''.join(struct.pack('<H',n)+raw for n,raw in values.items())


def task_catalog(app):
    source=app.engine.project.sha256;acd=app.native_symbols.source_acd_sha256
    app.native_project_identity=NativeProjectIdentity(acd,source,0,1,0,1,2,3)
    app.native_tasks=NativeTasks(acd,source,[dict(name='MainTask',instance=1)],configurations={
        'maintask':StoredTaskConfiguration((2,),10000,4,10,500000,False,False)})


class TaskModelTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.app=headers.Application(folder.name);self.namespace,_=headers.fixture(self.app);task_catalog(self.app)
        self.bindings=TaskBindings(self.app.engine,self.namespace,self.app.native_tasks,
            self.app.native_project_identity,self.app.native_symbols)
        self.stage=self.namespace.tasks

    def test_creation_allocates_an_owned_header_and_configuration_has_actual_private_readback(self):
        before=copy.deepcopy(self.app.engine.project.tasks)
        self.assertEqual(self.stage.create(1,self.bindings),struct.pack('<II',1,TASK_BASE))
        self.assertEqual(self.stage._headers[0].name,'MainTask')
        reply=self.stage.configure(1,configuration(),self.bindings)
        self.assertEqual(reply,struct.pack('<H',9)+b''.join(struct.pack('<HH',n,0) for n in (2,4,5,6,12,17,18,19,1)))
        self.assertEqual(dict(self.stage._attributes[1])[1],struct.pack('<HI',1,2))
        self.stage.validate(self.bindings)
        state=self.stage.description();self.assertEqual((state['created'],state['configured'],state['configuration_attributes']),(1,1,9))
        self.assertFalse(state['physical_addresses'] or state['active_scheduler_changed'] or state['commit'])
        self.assertNotIn('MainTask',json.dumps(state));self.assertEqual(self.app.engine.project.tasks,before)

    def test_configure_before_create_unknown_boolean_duplicate_and_foreign_programs_reject(self):
        with self.assertRaises(ImageError):self.stage.configure(1,configuration(),self.bindings)
        for instance in (True,0,2,65536):
            with self.subTest(instance=instance),self.assertRaises(ImageError):self.stage.create(instance,self.bindings)
        self.stage.create(1,self.bindings)
        with self.assertRaises(ImageError):self.stage.create(1,self.bindings)
        for n,value in ((1,struct.pack('<HI',1,99)),(2,struct.pack('<I',25000)),(4,b'\5\0'+b'\1'+bytes(4)),
                        (5,b'\2\0'),(6,b'\1\0'),(12,struct.pack('<I',400000)),(17,b'\1\0\0\0'),(18,b'\1\0\0\0'),(19,b'\1\0\0\0')):
            fields=attributes(configuration());fields[n]=value
            with self.subTest(attribute=n),self.assertRaises(ImageError):self.stage.configure(1,configuration(fields),self.bindings)
            self.assertEqual(self.stage.description()['configured'],0)

    def test_truncated_duplicate_unknown_excessive_and_trailing_fields_reject_atomically(self):
        self.stage.create(1,self.bindings);raw=configuration()
        for count in range(len(raw)):
            with self.subTest(length=count),self.assertRaises(ImageError):self.stage.configure(1,raw[:count],self.bindings)
        for bad in (raw+b'X',b'\x08\0'+raw[2:],raw[:2]+b'\3\0'+raw[4:],raw[:2]+b'\1\0\xff\xff'+raw[6:]):
            with self.assertRaises(ImageError):self.stage.configure(1,bad,self.bindings)
        self.assertFalse(self.stage._attributes)
        fields=attributes(raw);reversed_fields=dict(reversed(list(fields.items())))
        self.stage.configure(1,configuration(reversed_fields),self.bindings)
        self.assertEqual(self.stage.configure(1,raw,self.bindings),struct.pack('<H',9)+b''.join(struct.pack('<HH',n,0) for n in fields))

    def test_current_catalog_source_runtime_schedule_and_stored_effects_are_rechecked(self):
        for case in ('source','catalog','programs','runtime','runtime-list','effect'):
            with self.subTest(case=case):
                self.setUp();self.stage.create(1,self.bindings);self.stage.configure(1,configuration(),self.bindings)
                if case=='source':self.bindings.identity=None
                elif case=='catalog':self.bindings.tasks=NativeTasks('b'*64,self.app.engine.project.sha256,[dict(name='MainTask',instance=1)])
                elif case=='programs':self.bindings.programs.programs['mainprogram']=7
                elif case=='runtime':self.app.engine.project.runtime_revision=1
                elif case=='runtime-list':self.app.engine.project.tasks[0]['programs']=[]
                else:self.stage._attributes={}
                with self.assertRaises(ImageError):self.stage.validate(self.bindings)

    def link_ready(self):
        self.bindings.auxiliary=self.app.native_auxiliary_symbols
        case=headers.HeaderTests();case.app=self.app
        hb=headers.HeaderBindings(self.app.engine,self.namespace,self.app.native_symbols,self.app.native_routines,
            self.app.native_auxiliary_symbols,self.app.native_tasks)
        case.bindings=hb
        self.namespace._incremental=IncrementalDownload.prepare(case.batch(),self.namespace._image,self.namespace._source,header_bindings=hb)
        self.stage.create(1,self.bindings)

    def test_task_symbol_link_and_clear_use_owned_header_and_preserve_initial_batch_ledger(self):
        self.link_ready();original=self.namespace._incremental._headers
        self.assertEqual(self.stage.link_symbol(4,LINK,self.bindings),bytes.fromhex('0200030000000d000000'))
        self.assertEqual((self.stage._symbols[4].address,self.stage._symbols[4].logical_path),(TASK_BASE,bytes.fromhex('0220702401')))
        self.assertEqual(self.stage.description()['symbol_links'],1)
        self.assertEqual(self.stage.link_symbol(4,CLEAR,self.bindings),bytes.fromhex('01000d000000'))
        self.assertEqual((self.stage._symbols[4].address,self.stage._symbols[4].logical_path),(TASK_BASE,b'\0'))
        self.assertEqual(self.stage.description()['symbol_links'],0);self.assertIs(self.namespace._incremental._headers,original)
        self.assertEqual(dict(original[0x6B,0,4])[3],bytes(4))

    def test_foreign_address_wrong_task_unrelated_symbol_and_bad_frames_have_no_partial_effect(self):
        self.link_ready()
        bad=[LINK[:-1],LINK+b'X',LINK[:4]+struct.pack('<I',TASK_BASE+32)+LINK[8:],LINK[:-1]+b'\2',
            LINK[:2]+b'\x0c\0'+LINK[4:],bytes.fromhex('0100030000000075'),CLEAR+b'X']
        for raw in bad:
            with self.subTest(raw=raw.hex()),self.assertRaises(ImageError):self.stage.link_symbol(4,raw,self.bindings)
            self.assertFalse(self.stage._symbols)
        for instance in (True,1,3,99):
            with self.subTest(instance=instance),self.assertRaises(ImageError):self.stage.link_symbol(instance,LINK,self.bindings)

    def test_equivalent_logical_widths_are_retained_and_link_effect_corruption_revokes(self):
        self.link_ready();raw=LINK[:-5]+bytes.fromhex('042100700025000100')
        self.stage.link_symbol(4,raw,self.bindings)
        self.assertEqual(self.stage._symbols[4].logical_path,bytes.fromhex('042100700025000100'))
        self.stage._symbols={4:replace(self.stage._symbols[4],address=TASK_BASE+1)}
        with self.assertRaises(ImageError):self.stage.validate(self.bindings)


class TaskSignedTests(NamespaceFixture,unittest.TestCase):
    def ready_tasks(self,complete=True):
        self.object_source_fixture();old=self.app.native_symbols
        self.app.native_symbols=NativeSymbols(old.source_acd_sha256,old.source_l5x_sha256,
            [replace(row,scope='MainProgram') if row.program_instance else row for row in old.by_key.values()],
            [dict(name='MainProgram',instance=2)])
        self.app.native_routines=NativeRoutines(old.source_acd_sha256,old.source_l5x_sha256,
            [dict(program='MainProgram',name='MainRoutine',program_instance=2,instance=1)])
        # Keep the session's original identity; task_catalog uses an equivalent
        # source pair without changing its native session/timeline identity.
        identity=self.app.native_project_identity;task_catalog(self.app);self.app.native_project_identity=identity
        self.assertEqual(self.send(payloads.INSPECT)[2],0);self.assertEqual(self.send(STATUS)[2],0)
        self.assertEqual(self.send(transport.DELETE)[2],0)
        if complete:
            updates.CompletionSignedTests.next_batch(self,(metadata.table(),))
            self.assertEqual(self.send(payloads.INSPECT)[2],0);self.assertEqual(self.send(STATUS)[2],0)
            self.assertEqual(self.send(transport.DELETE)[2],0)
        return self.endpoint.programming_lease.download_namespace

    def test_owner_create_reply_configuration_and_catalog_readback_preserve_active_scheduler(self):
        namespace=self.ready_tasks();before=copy.deepcopy(self.app.engine.project.tasks)
        self.assertEqual(self.send(CREATE),bytes.fromhex('88000000')+struct.pack('<II',1,TASK_BASE))
        body=configuration();result=self.send(bytes.fromhex('040220702401')+body)
        self.assertEqual(result[2],0);self.assertEqual(result[4:],struct.pack('<H',9)+b''.join(struct.pack('<HH',n,0) for n in attributes(body)))
        self.assertEqual(namespace.description()['tasks']['configured'],1)
        self.assertEqual(self.send(ENUM)[2],0)
        self.assertEqual(self.app.engine.project.tasks,before);self.assertEqual(self.app.engine.scan_count,0)
        self.assertEqual(self.send(CREATE)[2],12)
        self.assertEqual(self.send(prep.END)[2],0)
        self.assertIsNone(self.endpoint.programming_lease.download_namespace)


    def test_requires_completed_updates_exact_scope_empty_create_and_current_source(self):
        namespace=self.ready_tasks(complete=False)
        self.assertEqual(self.send(CREATE)[2],12);self.assertEqual(namespace.tasks.description()['created'],0)
        updates.CompletionSignedTests.next_batch(self,(metadata.table(),))
        self.send(payloads.INSPECT);self.send(STATUS);self.send(transport.DELETE)
        for raw in (CREATE+b'\0',bytes.fromhex('08042068240220702401'),bytes.fromhex('0803207024013001')):
            self.assertNotEqual(self.send(raw)[2],0)
        self.app.native_tasks=None
        self.assertEqual(self.send(CREATE)[2],12);self.assertEqual(namespace.tasks.description()['created'],0)

    def test_foreign_owner_and_unsigned_calls_cannot_create_or_configure(self):
        namespace=self.ready_tasks();self.assertNotEqual(self.cip(CREATE)[2],0)
        first=self.client;second=self.second_client()
        try:
            self.client=second
            for sequence,request in enumerate((CREATE,bytes.fromhex('040220702401')+configuration()),4):
                self.assertEqual(self.signed(sequence,request)[2],15)
        finally:self.client=first;second.close()
        self.assertEqual(namespace.tasks.description()['created'],0)
        self.assertEqual(self.send(CREATE)[2],0)
        self.app.native_tasks=None
        self.assertEqual(self.send(ENUM)[2],12)
        self.assertEqual(self.send(leases.RELEASE)[2],0)
        self.assertIsNone(self.endpoint.programming_lease.download_namespace)


class TaskLinkSignedTests(NamespaceFixture,unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=headers.Application(self.tmp.name)
        self.namespace,self.hb=headers.fixture(self.app);task_catalog(self.app)
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True).start();self.app.endpoint=self.endpoint
        self.client=Client(self.endpoint.port);self.client.register()
        self.ready();self.endpoint.programming_lease.download_namespace=self.namespace
        case=headers.HeaderTests();case.app=self.app;case.bindings=self.hb
        updates.CompletionSignedTests.next_batch(self,case.batch())
        self.assertEqual(self.send(payloads.INSPECT)[2],0);self.assertEqual(self.send(STATUS)[2],0)
        self.assertEqual(self.send(transport.DELETE)[2],0)

    def test_link_configuration_clear_and_end_preserve_active_tasks_and_original_effects(self):
        before=copy.deepcopy(self.app.engine.project.tasks)
        self.assertEqual(self.send(CREATE)[2],0)
        self.assertEqual(self.send(bytes.fromhex('0402206b2404')+LINK),bytes.fromhex('840000000200030000000d000000'))
        self.assertEqual(self.send(bytes.fromhex('040220702401')+configuration())[2],0)
        self.assertEqual(self.send(ENUM)[2],0)
        self.assertEqual(self.send(bytes.fromhex('0402206b2404')+CLEAR)[2],0)
        self.assertEqual(self.namespace.tasks.description()['symbol_links'],0)
        self.assertEqual(self.app.engine.project.tasks,before)
        self.assertEqual(self.send(prep.END)[2],0);self.assertIsNone(self.endpoint.programming_lease.download_namespace)

    def test_link_requires_task_creation_owned_scope_and_matching_source_symbol(self):
        self.assertEqual(self.send(bytes.fromhex('0402206b2404')+LINK)[2],15)
        self.assertEqual(self.send(CREATE)[2],0)
        self.assertEqual(self.send(bytes.fromhex('0402206b2403')+LINK)[2],12)
        self.assertEqual(self.send(bytes.fromhex('040420682402206b2404')+LINK)[2],4)
        self.app.native_auxiliary_symbols=None
        self.assertEqual(self.send(bytes.fromhex('0402206b2404')+LINK)[2],12)

    def complete_tasks(self):
        self.assertEqual(self.send(CREATE)[2],0)
        self.assertEqual(self.send(bytes.fromhex('0402206b2404')+LINK)[2],0)
        self.assertEqual(self.send(bytes.fromhex('040220702401')+configuration())[2],0)

    def test_download_retains_disabled_embedded_http_after_task_configuration(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.send(HTTP_DISABLE)[2],12)
        self.assertEqual(self.send(CREATE)[2],0)
        self.assertEqual(self.send(HTTP_DISABLE)[2],12)
        self.assertEqual(self.send(bytes.fromhex('0402206b2404')+LINK)[2],0)
        self.assertEqual(self.send(bytes.fromhex('040220702401')+configuration())[2],0)
        with patch('logixlab.ethernetip.interface_snapshot',side_effect=AssertionError('Unneeded network query')):
            self.assertEqual(self.send(HTTP_DISABLE),bytes.fromhex('90000000'))
            self.assertEqual(self.send(HTTP_DISABLE),bytes.fromhex('90000000'))
            self.assertEqual(self.send(bytes.fromhex('0e0320f524003065')),bytes.fromhex('8e00000000'))
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        self.assertEqual(getattr(self.app.engine.project,'runtime_revision',0),0)
        self.assertEqual(self.send(prep.END)[2],0)
        self.assertEqual(self.send(HTTP_DISABLE)[2],12)

    def test_http_disable_rejects_enable_wrong_scope_and_malformed_payloads(self):
        self.complete_tasks()
        for raw in (HTTP_DISABLE[:-1],HTTP_DISABLE+b'\0',HTTP_DISABLE[:-1]+b'\1',
                    bytes.fromhex('100320f52400306600'),bytes.fromhex('100320f52401306500'),
                    bytes.fromhex('10052068240220f52400306500')):
            with self.subTest(raw=raw.hex()):self.assertNotEqual(self.send(raw)[2],0)
        self.assertEqual(self.cip(HTTP_DISABLE)[2],8)
        self.assertEqual(self.send(HTTP_DISABLE)[2],0)

    def test_http_disable_rechecks_owner_mode_source_and_stored_task_effects(self):
        self.complete_tasks();first=self.client;second=self.second_client()
        try:
            self.client=second
            self.assertEqual(self.signed(4,HTTP_DISABLE)[2],15)
        finally:self.client=first;second.close()
        with patch.object(self.app,'controller_state',return_value={'mode':'Run'}):
            self.assertEqual(self.send(HTTP_DISABLE)[2],12)
        self.assertEqual(self.send(HTTP_DISABLE)[2],0)
        catalog=self.app.native_tasks;self.app.native_tasks=None
        self.assertEqual(self.send(HTTP_DISABLE)[2],12)
        self.app.native_tasks=catalog
        self.namespace.tasks._attributes={}
        self.assertEqual(self.send(HTTP_DISABLE)[2],12)
