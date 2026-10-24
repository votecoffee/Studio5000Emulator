"""Source-equivalent download publication, correlation and cleanup lifecycle."""
import copy
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from logixlab.change_detection import ChangeDetection
from logixlab.model import ModelError
import test_download_values as values
import test_download_changelog as logs
import test_programming_lease as leases
import test_download_properties as properties
import test_native_metadata_values as metadata


class InstallationSignedTests(logs.NamespaceFixture,unittest.TestCase):
    setUp=values.ValuesSignedTests.setUp
    complete_tasks=logs.ChangelogSignedTests.complete_tasks
    configure=logs.ChangelogSignedTests.configure
    ready_setup=logs.ChangelogSignedTests.ready_setup
    ready_routines=logs.ChangelogSignedTests.ready_routines
    next_routines=logs.ChangelogSignedTests.next_routines
    ready_map=logs.ChangelogSignedTests.ready_map
    ready_log=logs.ChangelogSignedTests.ready_log
    proposal=logs.ChangelogSignedTests.proposal

    def ready_install(self):
        self.ready_log();self.assertEqual(self.send(logs.CREATE_REQUEST)[2],0)
        self.assertEqual(self.send(logs.CONFIG_REQUEST+logs.payload(self.proposal()))[2],0)

    def test_install_resets_values_and_counters_preserves_source_handles_and_is_idempotent(self):
        self.ready_install();old=self.app.engine;identity=self.app.native_project_identity
        old.memory.write('SpeedSetpoint',99);old.scan_count=5;old.time_ms=50
        original=copy.deepcopy(old.memory.values);refs=dict(old.runtime_references._addresses)
        previous=old.change_detection.attributes(old.project.sha256)
        token=self.app.device_io.write_token;generation=self.app.generation
        self.assertEqual(self.send(logs.COMMIT),bytes.fromhex('e1000000'))
        new=self.app.engine
        self.assertIsNot(new,old);self.assertEqual(old.memory.values,original)
        self.assertEqual(new.memory.read('SpeedSetpoint'),0)
        self.assertEqual((new.scan_count,new.time_ms,new.prescan_count),(0,0,0));self.assertTrue(new.memory.first_scan)
        self.assertEqual(self.app.generation,generation);self.assertNotEqual(self.app.device_io.write_token,token)
        self.assertEqual(new.runtime_references._addresses,refs)
        self.assertIsNot(new.runtime_references._addresses,old.runtime_references._addresses)
        if previous:self.assertNotEqual(new.change_detection.attributes(new.project.sha256),previous)
        self.assertIs(self.app.native_project_identity,identity)
        self.assertNotEqual(new.installed_download.identity.download_uid,identity.download_uid)
        self.assertEqual(self.send(logs.prep.SINGLE),bytes.fromhex('8e00000000000000'))
        self.assertEqual(self.send(logs.ENUM)[2],0)
        epoch=new.change_detection.attributes(new.project.sha256)
        self.assertEqual(self.send(logs.COMMIT),bytes.fromhex('e1000000'))
        self.assertIs(self.app.engine,new);self.assertEqual(new.change_detection.attributes(new.project.sha256),epoch)

    def test_end_disconnect_and_new_scans_keep_installed_header_until_model_reset(self):
        self.ready_install();original=self.app.native_project_identity;self.send(logs.COMMIT)
        engine=self.app.engine;header=engine.installed_download.attributes(original,engine.project)
        self.assertEqual(self.send(logs.prep.END)[2],0)
        self.assertEqual(self.send(leases.RELEASE)[2],0)
        self.assertIsNone(self.endpoint.programming_lease.download_namespace)
        self.assertEqual(self.cip(bytes.fromhex('0e0320ac24013003')),b'\x8e\0\0\0'+header[3])
        self.assertEqual(self.send(logs.prep.SINGLE),bytes.fromhex('8e00000000000000'))
        self.assertNotEqual(self.send(logs.COMMIT)[2],0)
        self.app.command('step',{'count':1,'dt':10})
        self.assertEqual(engine.scan_count,1);self.assertEqual(engine.prescan_count,1)
        self.assertIs(self.app.native_project_identity,original)
        self.client.close();self.assertIs(self.app.engine,engine)
        self.app.command('reset',{});self.assertIsNone(getattr(self.app.engine,'installed_download',None))

    def test_candidate_or_publication_validation_failure_leaves_old_model_epoch_and_token(self):
        self.ready_install();engine=self.app.engine;token=self.app.device_io.write_token
        epoch=engine.change_detection.attributes(engine.project.sha256)
        with patch.object(self.app,'default_scan_interval',side_effect=ModelError('failed validation')):
            self.assertEqual(self.send(logs.COMMIT)[2],12)
        self.assertIs(self.app.engine,engine);self.assertIsNone(self.namespace.initial_values)
        self.assertFalse(self.endpoint.programming_lease.download_committed)
        self.assertEqual(engine.change_detection.attributes(engine.project.sha256),epoch)
        self.assertEqual(self.app.device_io.write_token,token)

    def test_pending_external_input_is_cancelled_at_installation(self):
        self.ready_install();io=self.app.device_io;io.configure(True)
        io.enqueue(dict(request_id='before-download',instance_id=self.app.instance_id,
            project_generation=self.app.generation,writes=[dict(tag='SpeedSetpoint',value=123)]))
        self.assertEqual(io.receipt('before-download')['status'],'queued')
        self.assertEqual(self.send(logs.COMMIT)[2],0)
        self.assertEqual(io.receipt('before-download')['status'],'rejected')
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'),0)

    def test_foreign_unsigned_run_scope_and_reply_budget_cannot_install(self):
        self.ready_install();engine=self.app.engine
        self.assertNotEqual(self.cip(logs.COMMIT)[2],0)
        first=self.client;second=self.second_client()
        try:
            self.client=second;self.assertEqual(self.signed(4,logs.COMMIT)[2],15)
        finally:self.client=first;second.close()
        with patch.object(self.app,'controller_state',return_value={'mode':'Run'}):self.assertEqual(self.send(logs.COMMIT)[2],12)
        self.assertEqual(self.send(bytes.fromhex('6103208e24013001'))[2],4)
        original=self.endpoint.router.native_read
        def limited(inner,session,native,depth,limit,budget,**kwargs):return original(inner,session,native,depth,3,budget,**kwargs)
        with patch.object(self.endpoint.router,'native_read',side_effect=limited):self.assertEqual(self.send(logs.COMMIT)[2],0x1B)
        self.assertIs(self.app.engine,engine);self.assertFalse(self.endpoint.programming_lease.download_committed)

    def test_changed_original_catalog_does_not_fall_back_to_unrelated_active_identity(self):
        self.ready_install();self.send(logs.COMMIT);self.send(logs.prep.END)
        original=self.app.native_project_identity
        self.app.native_project_identity=replace(original,copy_uid=original.copy_uid+1)
        self.assertEqual(self.cip(bytes.fromhex('0e0320ac24013003'))[2],12)

    def test_detached_routine_edits_keep_committed_header_without_claiming_unchanged_source(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        self.ready_install();self.send(logs.COMMIT);self.send(logs.prep.END);self.send(leases.RELEASE)
        original=self.app.native_project_identity;old=self.app.engine
        old.memory.write('SpeedSetpoint',77);old.scan_count=3
        header=old.installed_download.attributes(original,old.project)
        source=decode(container(ET.tostring(xml_source(text='NOP();'))))
        first,receipt=prepare(old,source,('NOP();',),'MainProgram',0)
        self.assertIs(self.app.engine,old);self.assertEqual(receipt['revision'],1)
        self.assertEqual(first.installed_download.attributes(original,first.project),header)
        self.assertIs(first.installed_download.namespace,old.installed_download.namespace)
        self.assertIs(first.installed_download.values,old.installed_download.values)
        self.assertFalse(first.installed_download.description()['source_equivalent'])
        self.assertEqual(first.installed_download.description()['routine_revision'],1)
        self.assertTrue(old.installed_download.description()['source_equivalent'])
        self.assertEqual(first.memory.values,old.memory.values);self.assertEqual(first.scan_count,3)
        self.assertEqual(first.change_detection.attributes(first.project.sha256),old.change_detection.attributes(old.project.sha256))
        self.app.engine=first
        self.assertEqual(self.cip(bytes.fromhex('0e0320ac24013003')),b'\x8e\0\0\0'+header[3])
        second,_=prepare(first,source,('NOP();',),'MainProgram',1)
        self.assertEqual(second.installed_download.attributes(original,second.project),header)
        self.assertEqual(second.installed_download.description()['routine_revision'],2)
        self.assertEqual(first.installed_download.description()['routine_revision'],1)
        from logixlab.download_image import ImageError
        with self.assertRaises(ImageError):old.installed_download.attributes(original,first.project)
        with self.assertRaises(ImageError):first.installed_download.attributes(replace(original,copy_uid=original.copy_uid+1),first.project)

    def test_stale_download_binding_blocks_detached_edit_without_changing_active_model(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        self.ready_install();self.send(logs.COMMIT);self.send(logs.prep.END);self.send(leases.RELEASE)
        engine=self.app.engine;installed=engine.installed_download
        engine.installed_download=replace(installed,project=copy.copy(engine.project))
        source=decode(container(ET.tostring(xml_source())))
        values=copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError,'installed_download_source_changed'):
            prepare(engine,source,('NOP();',),'MainProgram',0)
        self.assertIs(self.app.engine,engine);self.assertEqual(engine.memory.values,values)
        self.assertEqual(getattr(engine.project,'runtime_revision',0),0)


class RoutineClassRevisionTests(logs.NamespaceFixture,unittest.TestCase):
    setUp=InstallationSignedTests.setUp

    def revision(self,scoped=False):
        return self.send(bytes.fromhex('0e0520682402206d24003001' if scoped else '0e03206d24003001'))

    def test_native_v35_typed_unprotected_rll_class_uses_revision_11_without_flattening_instances(self):
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.revision(),bytes.fromhex('8e0000000b00'))
        self.assertEqual(self.revision(True),bytes.fromhex('8e0000000b00'))
        self.assertEqual(self.send(bytes.fromhex('0302206d24000300010002000300'))[2],10)
        self.assertEqual(self.send(bytes.fromhex('0e0520682402206d24003003')),bytes.fromhex('8e00000002000000'))
        for key in ('tags','scan','ms','controller','routines'):self.assertEqual(self.app.state()[key],before[key])

    def test_partial_stale_edited_and_non_native_layouts_keep_the_legacy_revision(self):
        identity=self.app.native_project_identity;binding=self.app.native_routines;project=self.app.engine.project
        for case in ('identity','catalog','key','type','version','processor','edited','generic'):
            with self.subTest(case=case):
                if case=='identity':self.app.native_project_identity=replace(identity,source_acd_sha256='c'*64)
                elif case=='catalog':self.app.native_routines=None
                elif case in ('key','type'):
                    rows=[{**row.manifest(),**({'type_word':0x7FC} if case=='type' else {})} for row in binding.rows]
                    if case=='key':
                        for row in rows:row.pop('source_key_hex',None)
                    self.app.native_routines=type(binding)(binding.source_acd_sha256,binding.source_l5x_sha256,rows)
                elif case=='version':project.version='34'
                elif case=='processor':project.processor='1756-L85ES'
                elif case=='edited':project.runtime_revision=1
                else:self.endpoint.native_read_only=False
                self.assertEqual(self.endpoint.router.routine_class_revision(),1)
                self.app.native_project_identity=identity;self.app.native_routines=binding
                project.version='35';project.processor='1756-L85E';project.runtime_revision=0;self.endpoint.native_read_only=True
        self.assertEqual(self.revision(),bytes.fromhex('8e0000000b00'))


class CommittedMetadataTests(logs.NamespaceFixture,unittest.TestCase):
    complete_tasks=InstallationSignedTests.complete_tasks
    configure=InstallationSignedTests.configure
    ready_setup=InstallationSignedTests.ready_setup
    ready_routines=InstallationSignedTests.ready_routines
    next_routines=InstallationSignedTests.next_routines
    ready_map=InstallationSignedTests.ready_map
    ready_log=InstallationSignedTests.ready_log
    proposal=InstallationSignedTests.proposal
    ready_install=InstallationSignedTests.ready_install

    def setUp(self):
        InstallationSignedTests.setUp(self)
        self.catalog,self.number,self.text=properties.catalog(self.namespace._source)
        self.app.native_metadata_definitions=self.catalog.definitions;self.app.native_metadata_values=self.catalog
        self.marker=replace(self.number,definition=36,target=replace(self.number.target,qualifier=b'ProjectType'),data=b'L\0\0\0')

    def stage(self):
        self.ready_install()
        self.assertEqual(self.send(properties.request((self.number,)))[2],0)
        self.assertEqual(self.send(properties.request((self.marker,)))[2],0)

    def read(self,selection='controller-all',position=0,native=None,limit=480):
        from logixlab.native_session import NativeSession
        native=NativeSession() if native is None else native
        return self.endpoint.router.read_metadata_values(metadata.query(selection,position)[8:],native,limit)

    def test_commit_exposes_accepted_properties_without_mutating_original_catalog_or_identity(self):
        self.stage();before=self.catalog.body('all-objects');identity=self.app.native_project_identity
        self.assertEqual(metadata.frame(metadata.query('controller-all'),self.read())[1].data,self.catalog.body('controller-all'))
        self.assertEqual(self.send(logs.COMMIT)[2],0)
        self.send(logs.prep.END);self.send(leases.RELEASE)
        installed=self.app.engine.installed_download
        self.assertTrue(installed.description()['committed_metadata'])
        self.assertEqual(installed.description()['added_controller_properties'],1)
        for selection in ('all-objects','controller-all','controller-attribute-26'):
            assembly=metadata.wire.Assembly();position=0
            while not assembly.complete:
                raw=metadata.query(selection,position);response=self.send(raw)
                query,chunk,status=metadata.frame(raw,response)
                self.assertEqual(status,0);assembly.accept(query,chunk);position+=len(chunk.data)
            rows=metadata.wire.records(assembly.data()) if assembly.data() else ()
            if selection=='controller-attribute-26':self.assertEqual(rows,())
            else:
                self.assertEqual(sum(r.target.qualifier==b'ProjectType' for r in rows),1)
                serial=next(r for r in rows if r.target.qualifier==self.number.target.qualifier)
                self.assertEqual(properties.value_identity(serial),properties.value_identity(self.number))
            if selection=='all-objects':
                self.assertEqual([r.record_word for r in rows],list(range(1,len(rows)+1)))
        self.assertIs(self.app.native_metadata_values,self.catalog);self.assertEqual(self.catalog.body('all-objects'),before)
        self.assertIs(self.app.native_project_identity,identity);self.assertEqual(self.app.engine.scan_count,0)

    def test_commit_invalidates_existing_cursor_and_snapshot_is_detached_from_staging(self):
        from logixlab.native_session import NativeSession
        from logixlab.ethernetip import CIPError
        self.stage();native=NativeSession();generation=self.app.generation
        first=metadata.frame(metadata.query(),self.read('all-objects',native=native,limit=50))[1]
        self.assertIsNotNone(native.metadata_query)
        self.assertEqual(self.send(logs.COMMIT)[2],0);self.assertEqual(self.app.generation,generation)
        with self.assertRaises(CIPError):self.read('all-objects',len(first.data),native)
        self.assertIsNone(native.metadata_query)
        before=self.read();self.namespace.properties._values={};self.namespace.properties._packets=()
        self.assertEqual(self.read(),before)
        self.app.native_metadata_values=replace(self.catalog)
        with self.assertRaises(CIPError):self.read()

    def test_failed_publication_does_not_expose_properties_and_reset_discards_committed_view(self):
        self.stage();original=self.read()
        with patch.object(self.app,'default_scan_interval',side_effect=ModelError('failed publication')):
            self.assertEqual(self.send(logs.COMMIT)[2],12)
        self.assertEqual(self.read(),original);self.assertIsNone(getattr(self.app.engine,'installed_download',None))
        self.assertEqual(self.send(logs.COMMIT)[2],0);self.assertNotEqual(self.read(),original)
        self.send(logs.prep.END);self.send(leases.RELEASE);self.app.command('reset',{})
        self.assertEqual(self.read(),original)

    def test_source_rows_or_definitions_changed_after_commit_revoke_metadata_readback(self):
        from logixlab.ethernetip import CIPError
        self.stage();self.assertEqual(self.send(logs.COMMIT)[2],0)
        rows=self.catalog.rows
        object.__setattr__(self.catalog,'rows',rows[:-1])
        with self.assertRaises(CIPError):self.read()
        object.__setattr__(self.catalog,'rows',rows)
        object.__setattr__(self.catalog.definitions,'rows',self.catalog.definitions.rows[:-1])
        with self.assertRaises(CIPError):self.read()


class DownloadAuditTests(unittest.TestCase):
    def test_unmasked_download_epoch_is_distinct_even_when_random_draw_collides(self):
        for mask in (0,(1<<64)-1,None):
            with patch('logixlab.change_detection.secrets.randbits',return_value=42):
                old=ChangeDetection('a'*64,mask);new=ChangeDetection('a'*64,mask)
            before=old.attributes('a'*64);new.prepare_download_epoch(old)
            self.assertEqual(old.attributes('a'*64),before)
            if mask is not None:self.assertNotEqual(new.attributes('a'*64),before)
            else:self.assertEqual(new.attributes('a'*64),{})
            self.assertEqual(new.description()['updates'],0)
        with self.assertRaises(ValueError):old.prepare_download_epoch(old)


if __name__=='__main__':unittest.main()
