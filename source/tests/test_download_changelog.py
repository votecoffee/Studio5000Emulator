"""Change Log proposals have backed private handles and preserve active UIDs."""
import copy
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch

from logixlab.download_changelog import ADDRESS,CREATE,WIDTHS,DownloadChangelog
from logixlab.download_image import ImageError
import test_download_map as maps
from test_download_namespace import NamespaceFixture,ENUM
import test_programming_preparation as prep

CREATE_REQUEST=bytes.fromhex('080220ac2401')+CREATE
CONFIG_REQUEST=bytes.fromhex('040220ac2401')
LIST_REQUEST=bytes.fromhex('030220ac2401')+struct.pack('<H',len(WIDTHS))+b''.join(struct.pack('<H',n) for n in WIDTHS)
COMMIT=bytes.fromhex('6102208e2401')


def payload(values):return struct.pack('<H',len(values))+b''.join(struct.pack('<H',n)+v for n,v in values.items())


class ChangelogSignedTests(NamespaceFixture,unittest.TestCase):
    setUp=maps.MapSignedTests.setUp
    complete_tasks=maps.MapSignedTests.complete_tasks
    configure=maps.MapSignedTests.configure
    ready_setup=maps.MapSignedTests.ready_setup
    ready_routines=maps.MapSignedTests.ready_routines
    next_routines=maps.MapSignedTests.next_routines
    ready_map=maps.MapSignedTests.ready_map

    def bindings(self):return self.endpoint.router.download_changelog_bindings(self.endpoint.programming_lease)

    def ready_log(self):
        self.ready_map();self.assertEqual(self.send(maps.WRITE)[2],0)

    def proposal(self,uid=0x12345678):
        values=self.app.native_project_identity.attributes()
        return {n:struct.pack('<I',uid) if n==3 else values[n] for n in WIDTHS}

    def test_create_configure_read_and_backed_handle_preserve_original_header_and_memory(self):
        self.ready_log();identity=self.app.native_project_identity;original=identity.attributes()
        before=copy.deepcopy(self.app.engine.memory.values);values=self.proposal()
        for _ in range(2):self.assertEqual(self.send(CREATE_REQUEST),b'\x88\0\0\0'+struct.pack('<II',1,ADDRESS))
        stage=self.namespace.change_log;bindings=self.bindings()
        self.assertEqual(stage.resolve(ADDRESS,bindings)[6],struct.pack('<H',1000))
        for address in (True,ADDRESS+1,ADDRESS-1):
            with self.assertRaises(ImageError):stage.resolve(address,bindings)
        for _ in range(2):
            self.assertEqual(self.send(CONFIG_REQUEST+payload(values)),b'\x84\0\0\0'+struct.pack('<H',7)+b''.join(struct.pack('<HH',n,0) for n in WIDTHS))
        expected=struct.pack('<H',7)+b''.join(struct.pack('<HH',n,0)+v for n,v in values.items())
        self.assertEqual(self.send(LIST_REQUEST),b'\x83\0\0\0'+expected)
        self.assertEqual(self.send(bytes.fromhex('0e0320ac24013003')),b'\x8e\0\0\0'+values[3])
        self.assertEqual(self.cip(bytes.fromhex('0e0320ac24013003')),b'\x8e\0\0\0'+original[3])
        self.assertEqual(stage.resolve(ADDRESS,bindings)[3],values[3])
        self.assertEqual(self.send(bytes.fromhex('010220ac2401'))[4:],b''.join(stage.read(bindings)[n] for n in range(1,11)))
        self.assertEqual(identity.attributes(),original);self.assertIs(self.app.native_project_identity,identity)
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        description=stage.description();self.assertTrue(description['created'] and description['configured'])
        for key in ('active_correlation_changed','physical_address_imported','native_authentication','commit'):
            self.assertFalse(description[key])
        self.assertEqual(self.send(ENUM)[2],0)
        self.assertEqual(self.send(prep.END)[2],0);self.assertIsNone(self.endpoint.programming_lease.download_namespace)

    def test_create_requires_prepared_map_and_configure_requires_create(self):
        self.assertEqual(self.send(CREATE_REQUEST)[2],12);self.ready_map()
        self.assertEqual(self.send(CREATE_REQUEST)[2],12)
        self.assertEqual(self.send(maps.WRITE)[2],0)
        self.assertEqual(self.send(CONFIG_REQUEST+payload(self.proposal()))[2],12)
        self.assertEqual(self.send(CREATE_REQUEST)[2],0)

    def test_wrong_source_anchors_unknown_fields_extents_and_changed_uid_do_not_publish(self):
        self.ready_log();stage=DownloadChangelog();bindings=self.bindings()
        for raw in (CREATE[:-1],CREATE+b'X',struct.pack('<HHH',1,6,999),struct.pack('<HHH',1,5,1000)):
            with self.assertRaises(ImageError):stage.create(raw,bindings)
        stage.create(CREATE,bindings);original=stage.read(bindings);raw=payload(self.proposal())
        for length in range(len(raw)):
            with self.assertRaises(ImageError):stage.configure(raw[:length],bindings)
        for n in WIDTHS:
            if n==3:continue
            values=self.proposal();value=values[n];values[n]=bytes((value[0]^1,))+value[1:]
            with self.subTest(n=n),self.assertRaises(ImageError):stage.configure(payload(values),bindings)
        for bad in (raw+b'X',raw[:2]+b'\xff\xff'+raw[4:],raw[:8]+raw[2:8]+raw[14:]):
            with self.assertRaises(ImageError):stage.configure(bad,bindings)
        self.assertEqual(stage.read(bindings),original);self.assertFalse(stage.description()['configured'])
        stage.configure(payload(dict(reversed(list(self.proposal().items())))),bindings)
        with self.assertRaises(ImageError):stage.configure(payload(self.proposal(uid=99)),bindings)

    def test_foreign_unsigned_run_wrong_scope_and_small_budget_do_not_create(self):
        self.ready_log();self.assertNotEqual(self.cip(CREATE_REQUEST)[2],0)
        first=self.client;second=self.second_client()
        try:
            self.client=second;self.assertEqual(self.signed(4,CREATE_REQUEST)[2],15)
        finally:self.client=first;second.close()
        with patch.object(self.app,'controller_state',return_value={'mode':'Run'}):self.assertEqual(self.send(CREATE_REQUEST)[2],12)
        for request in (bytes.fromhex('08042068240220ac2401')+CREATE,bytes.fromhex('080320ac24013006')+CREATE):
            self.assertEqual(self.send(request)[2],4)
        original=self.endpoint.router.native_read
        def limited(inner,session,native,depth,limit,budget,**kwargs):return original(inner,session,native,depth,11,budget,**kwargs)
        with patch.object(self.endpoint.router,'native_read',side_effect=limited):self.assertEqual(self.send(CREATE_REQUEST)[2],0x1B)
        self.assertFalse(self.namespace.change_log.description()['created'])

    def test_changed_source_identity_earlier_effects_and_header_integrity_revoke_reads(self):
        self.ready_log();self.send(CREATE_REQUEST);self.send(CONFIG_REQUEST+payload(self.proposal()))
        stage=self.namespace.change_log;identity=self.app.native_project_identity
        self.app.native_project_identity=replace(identity,timeline_uid=identity.timeline_uid+1)
        self.assertEqual(self.send(LIST_REQUEST)[2],12);self.app.native_project_identity=identity
        self.assertEqual(self.send(LIST_REQUEST)[2],0)
        values=stage._values;stage._values={**values,6:b'\0\0'};self.assertEqual(self.send(LIST_REQUEST)[2],12);stage._values=values
        self.namespace.local_map._value=b'\5\0';self.assertEqual(self.send(ENUM)[2],12)
        self.assertEqual(self.send(prep.END)[2],0)

    def test_atomic_binding_changes_and_commit_boundary_do_not_install_or_rebase(self):
        self.ready_log();bindings=self.bindings();stage=DownloadChangelog()
        with patch.object(bindings,'stamp',side_effect=('first','second')),self.assertRaises(ImageError):stage.create(CREATE,bindings)
        self.assertFalse(stage.description()['created'])
        self.assertEqual(self.send(COMMIT)[2],12);self.send(CREATE_REQUEST)
        self.assertEqual(self.send(COMMIT)[2],12);self.send(CONFIG_REQUEST+payload(self.proposal()))
        identity=self.app.native_project_identity;before=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.send(COMMIT)[2],12)
        self.assertIn('download_initial_complete_tag_source_required',[r['reason'] for r in self.app.state()['connectivity']['native_rejections']])
        self.assertIs(self.app.native_project_identity,identity);self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.app.engine.scan_count,0);self.assertEqual(self.send(prep.END)[2],0)


if __name__=='__main__':unittest.main()
