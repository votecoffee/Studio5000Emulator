"""Closed Controller metadata survives routine-only edits without stale records."""
from dataclasses import replace
import unittest
from unittest.mock import patch

from logixlab import metadata_query
from logixlab.native_metadata_values import encode_records
import test_accepted_routine_source as sources
import test_download_installation as installation
import test_native_metadata_values as metadata
import test_programming_lease as leases


class EditedControllerMetadataTests(sources.wire.logs.NamespaceFixture,unittest.TestCase):
    complete_tasks=installation.CommittedMetadataTests.complete_tasks
    configure=installation.CommittedMetadataTests.configure
    ready_setup=installation.CommittedMetadataTests.ready_setup
    ready_routines=installation.CommittedMetadataTests.ready_routines
    next_routines=installation.CommittedMetadataTests.next_routines
    ready_map=installation.CommittedMetadataTests.ready_map
    ready_log=installation.CommittedMetadataTests.ready_log
    proposal=installation.CommittedMetadataTests.proposal
    ready_install=installation.CommittedMetadataTests.ready_install
    stage=installation.CommittedMetadataTests.stage
    edit=sources.AcceptedRoutineSourceTests.edit

    def setUp(self):
        installation.CommittedMetadataTests.setUp(self)
        stored=replace(self.number,definition=36,data=bytes(4))
        rows=tuple(stored if row is self.number else row for row in self.catalog.rows if row is not self.text)
        self.catalog=replace(self.catalog,rows=tuple(replace(row,record_word=n) for n,row in enumerate(rows,1)))
        self.app.native_metadata_values=self.catalog
        self.number=stored

    def installed(self):
        self.stage();self.assertEqual(self.send(installation.logs.COMMIT)[2],0)
        self.send(installation.logs.prep.END);self.send(leases.RELEASE)

    def query(self,selection='controller-all',position=0):return self.send(metadata.query(selection,position))

    def test_controller_serial_and_profile_stream_remain_exact_after_a_real_detached_edit(self):
        self.installed();before=self.app.engine.installed_download.metadata._controller;self.edit()
        original=self.endpoint.router.read_metadata_values
        def limited(payload,native,limit):return original(payload,native,min(limit,64))
        with patch.object(self.endpoint.router,'read_metadata_values',side_effect=limited):
            assembly=metadata_query.Assembly();position=0
            while not assembly.complete:
                raw=metadata.query('controller-all',position);response=self.send(raw)
                query,chunk,status=metadata.frame(raw,response);self.assertEqual(status,0)
                assembly.accept(query,chunk);position+=len(chunk.data)
        self.assertGreater(assembly.frames,1);self.assertEqual(assembly.data(),before)
        rows=metadata_query.records(assembly.data())
        self.assertEqual({r.target.qualifier for r in rows},{b'ControllerSerialNumber',b'ProjectType'})
        self.assertEqual(self.query('all-objects')[2],12)
        query,chunk,status=metadata.frame(metadata.query('controller-attribute-26'),self.query('controller-attribute-26'))
        self.assertEqual(status,0);self.assertEqual(chunk.data,b'')

    def test_unknown_controller_property_is_not_misrepresented_as_unchanged_configuration(self):
        self.installed();self.edit();engine=self.app.engine;installed=engine.installed_download;view=installed.metadata
        unknown=replace(self.number,target=replace(self.number.target,qualifier=b'UnknownControllerSetting'))
        rows=view.rows+(unknown,);controller=tuple(r for r in rows if r.target.class_id==0x8E)
        changed=replace(view,rows=rows,_controller=encode_records(controller))
        engine.installed_download=replace(installed,metadata=changed)
        self.assertEqual(self.query()[2],12)

    def test_serial_identity_profile_tag_layout_and_missing_bindings_revoke_the_read(self):
        self.number=replace(self.number,data=self.endpoint.identity.serial.to_bytes(4,'little'))
        self.installed();self.edit();engine=self.app.engine;installed=engine.installed_download
        identity=self.endpoint.identity;self.endpoint.identity=replace(identity,serial=identity.serial+1)
        self.assertEqual(self.query()[2],12);self.endpoint.identity=identity
        engine.project.processor='1756-L85ES';self.assertEqual(self.query()[2],12);engine.project.processor='1756-L85E'
        engine.installed_download=replace(installed,tag_bindings=None);self.assertEqual(self.query()[2],12)
        engine.installed_download=installed;engine.project.tags['speedsetpoint'].external_access='None'
        self.assertEqual(self.query()[2],12)

    def test_original_serial_is_preserved_without_claiming_to_be_the_endpoint_serial(self):
        self.installed();self.edit()
        rows=metadata_query.records(metadata.frame(metadata.query('controller-all'),self.query())[1].data)
        serial=next(row for row in rows if row.target.qualifier==b'ControllerSerialNumber')
        self.assertEqual(serial.data,bytes(4));self.assertNotEqual(serial.data,self.endpoint.identity.serial.to_bytes(4,'little'))
        engine=self.app.engine;installed=engine.installed_download;view=installed.metadata
        changed=tuple(replace(row,data=b'BAD!') if row.target.qualifier==b'ControllerSerialNumber' else row for row in view.rows)
        engine.installed_download=replace(installed,metadata=replace(view,rows=changed,
            _controller=encode_records(tuple(row for row in changed if row.target.class_id==0x8E))))
        self.assertEqual(self.query()[2],12)

    def test_next_edit_revokes_a_controller_metadata_continuation(self):
        self.installed();self.edit();original=self.endpoint.router.read_metadata_values
        def limited(payload,native,limit):return original(payload,native,min(limit,64))
        with patch.object(self.endpoint.router,'read_metadata_values',side_effect=limited):
            raw=metadata.query('controller-all');query,chunk,status=metadata.frame(raw,self.send(raw))
            self.assertEqual(status,0);self.assertEqual(chunk.format,0x101)
            self.edit(region='43');self.assertEqual(self.query(position=len(chunk.data))[2],12)
            self.assertEqual(self.query()[2],0)


if __name__=='__main__':unittest.main()
