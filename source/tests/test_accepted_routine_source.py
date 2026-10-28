"""Accepted native edit containers remain exact, bounded and active-source bound."""
import copy
from dataclasses import replace
import hashlib
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from logixlab import accepted_routine_source as accepted,routine_read,upload_routine_source
from logixlab.routine_edits import prepare
from logixlab.routine_source import decode
from logixlab.download_image import ImageError
from logixlab.model import ModelError
from logixlab import read_transport as rt
from test_signed_messages import KEY
import test_routine_read as wire
from test_routine_source import container,xml_source


class AcceptedRoutineSourceTests(wire.logs.NamespaceFixture,unittest.TestCase):
    setUp=wire.RoutineReadWireTests.setUp
    installed=wire.RoutineReadWireTests.installed
    complete_tasks=wire.RoutineReadWireTests.complete_tasks
    configure=wire.RoutineReadWireTests.configure
    ready_setup=wire.RoutineReadWireTests.ready_setup
    ready_routines=wire.RoutineReadWireTests.ready_routines
    next_routines=wire.RoutineReadWireTests.next_routines
    ready_map=wire.RoutineReadWireTests.ready_map
    ready_log=wire.RoutineReadWireTests.ready_log
    proposal=wire.RoutineReadWireTests.proposal
    ready_install=wire.RoutineReadWireTests.ready_install
    read=wire.RoutineReadWireTests.read

    def edit(self,text='NOP();',region='42'):
        tree=xml_source(text=text);tree.find('./RLLContent/Rung').set('RegionId',region)
        raw=container(ET.tostring(tree));old=self.app.engine
        candidate,_=prepare(old,decode(raw),(text,),'MainProgram',getattr(old.project,'runtime_revision',0),
            native_source=raw,native_target=(2,1))
        self.app.engine=candidate
        return old,raw

    def test_exact_accepted_region_auxiliary_and_text_are_served_in_upload_profile(self):
        self.installed();old,raw=self.edit();before=copy.deepcopy(self.app.state())
        value=routine_read.source(self.app,2,1);decoded=upload_routine_source.decode(value)
        self.assertEqual([(r.region_id,r.text_ioi) for r in decoded.records],[(42,'NOP();')])
        self.assertEqual(decoded.auxiliary_sha256,decode(raw).auxiliary_sha256)
        row=accepted.records(self.app.engine.project)[0]
        self.assertEqual(row.data,raw);self.assertEqual(row.sha256,hashlib.sha256(raw).hexdigest())
        self.assertEqual(accepted.records(old.project),())
        self.assertEqual(self.app.state()['tags'],before['tags'])
        self.assertEqual(routine_read.source(self.app,2,1,4),b'')
        self.assertEqual(routine_read.source(self.app,2,1,9),wire.components.DATA)

    def test_latest_full_source_replaces_previous_record_without_mutating_old_engine(self):
        self.installed();_,first=self.edit(region='42');old,second=self.edit(region='43')
        self.assertEqual(len(accepted.records(self.app.engine.project)),1)
        self.assertEqual(accepted.records(old.project)[0].data,first)
        self.assertEqual(accepted.records(self.app.engine.project)[0].data,second)
        self.assertEqual(upload_routine_source.decode(routine_read.source(self.app,2,1)).records[0].region_id,43)

    def test_unrecorded_replacement_revokes_old_record_and_never_falls_back_to_download(self):
        self.installed();self.edit();old=self.app.engine;raw=container()
        candidate,_=prepare(old,decode(raw),('NOP();',),'MainProgram',1);self.app.engine=candidate
        self.assertEqual(accepted.records(candidate.project),())
        with self.assertRaisesRegex(ImageError,'accepted_source_unavailable'):routine_read.source(self.app,2,1)

    def test_changed_raw_hash_scope_revision_or_active_ladder_rejects(self):
        self.installed();self.edit();project=self.app.engine.project;row=accepted.records(project)[0]
        variants=[replace(row,data=row.data+b'X'),replace(row,target=(2,2)),replace(row,revision=9),replace(row,source_hash='0'*64)]
        for changed in variants:
            project.runtime_native_sources=(changed,)
            with self.subTest(changed=changed),self.assertRaises(ImageError):routine_read.source(self.app,2,1)
        project.runtime_native_sources=(row,)
        project.routines[row.key].rungs[0]['nodes']=[]
        with self.assertRaises(ImageError):routine_read.source(self.app,2,1)

    def test_storage_failure_keeps_active_engine_values_and_retained_history_unchanged(self):
        self.installed();self.edit();old=self.app.engine;raw=container();before=copy.deepcopy(old.memory.values)
        with patch.object(accepted,'MAX_BYTES',1),self.assertRaises(ModelError):
            prepare(old,decode(raw),('NOP();',),'MainProgram',1,native_source=raw,native_target=(2,1))
        self.assertIs(self.app.engine,old);self.assertEqual(old.memory.values,before)
        self.assertEqual(len(old.project.runtime_native_sources),1)

    def test_signed_fragmented_read_returns_accepted_source_and_next_edit_revokes_continuation(self):
        self.installed();self.edit();original=self.endpoint.router.dispatch
        def limited(raw,session,depth=0,limit=480,budget=None):
            return original(raw,session,depth,88 if raw[0]==0x3A else limit,budget)
        with patch.object(self.endpoint.router,'dispatch',side_effect=limited):
            assembly=rt.Assembly();position=0
            while not assembly.complete:
                request,raw=self.read(position);self.assertEqual(raw[2],0)
                response=rt.verify_response(raw,KEY,request=request);assembly.accept(request,response);position+=len(response.data)
            self.assertEqual(assembly.routine_source().records[0].region_id,42)
            self.assertGreater(assembly.frames,1)
            request,raw=self.read();position=len(rt.verify_response(raw,KEY,request=request).data)
            self.edit(region='43');self.assertEqual(self.read(position)[1][2],12)
            self.assertEqual(self.read()[1][2],0)

    def test_untouched_routine_keeps_exact_source_when_another_routine_is_edited(self):
        self.installed();before=routine_read.source(self.app,2,2)
        installed=self.app.engine.installed_download;snapshot=installed.routine_sources
        self.assertEqual(len(snapshot.sources),2)
        self.edit(text='MOV(7,SpeedSetpoint);')
        self.assertIs(self.app.engine.installed_download.routine_sources,snapshot)
        self.assertEqual(routine_read.source(self.app,2,2),before)
        self.assertEqual(upload_routine_source.decode(before).records[0].text_ioi,'NOP();')
        self.assertTrue(installed.description()['source_equivalent'])
        self.assertFalse(self.app.engine.installed_download.description()['source_equivalent'])
        self.assertEqual(routine_read.source(self.app,2,2,4),b'')
        self.assertEqual(routine_read.source(self.app,2,2,9),wire.components.DATA)

    def test_untouched_source_rechecks_catalog_bytes_active_logic_and_edit_inventory(self):
        self.installed();self.edit();engine=self.app.engine;installed=engine.installed_download
        snapshot=installed.routine_sources;row=snapshot.sources[1]
        variants=(replace(row,data=row.data+b'X'),replace(row,target=(2,3)),replace(row,key='other/mainroutine'))
        for changed in variants:
            engine.installed_download=replace(installed,routine_sources=replace(snapshot,sources=(snapshot.sources[0],changed)))
            with self.subTest(changed=changed),self.assertRaises(ImageError):routine_read.source(self.app,2,2)
        engine.installed_download=installed
        original=self.app.native_routines
        from logixlab.native_routines import NativeRoutines
        rows=[r.manifest() for r in original.rows];rows[1]['source_key_hex']='0008'+('42'*64)
        self.app.native_routines=NativeRoutines(original.source_acd_sha256,original.source_l5x_sha256,rows)
        with self.assertRaises(ImageError):routine_read.source(self.app,2,2)
        self.app.native_routines=original
        engine.project.runtime_edited_routines=()
        with self.assertRaises(ImageError):routine_read.source(self.app,2,2)
        engine.project.runtime_edited_routines=('mainprogram/mainroutine',)
        engine.project.routines['mainprogram/reporting'].rungs[0]['nodes']=[]
        with self.assertRaisesRegex(ImageError,'active_logic_changed'):routine_read.source(self.app,2,2)

    def test_edit_of_previously_untouched_routine_uses_new_source_and_cannot_fall_back(self):
        self.installed();self.edit();old=self.app.engine
        tree=xml_source(name='Reporting',text='NOP();');tree.find('./RLLContent/Rung').set('RegionId','99')
        raw=container(ET.tostring(tree));candidate,_=prepare(old,decode(raw),('NOP();',),'MainProgram',1,
            native_source=raw,native_target=(2,2));self.app.engine=candidate
        self.assertEqual(upload_routine_source.decode(routine_read.source(self.app,2,2)).records[0].region_id,99)
        candidate.project.runtime_native_sources=tuple(r for r in candidate.project.runtime_native_sources if r.target!=(2,2))
        with self.assertRaisesRegex(ImageError,'accepted_source_unavailable'):routine_read.source(self.app,2,2)

    def test_untouched_fragmented_stream_is_revoked_by_an_edit_to_its_target(self):
        self.installed();self.edit();original=self.endpoint.router.dispatch
        def limited(raw,session,depth=0,limit=480,budget=None):
            return original(raw,session,depth,88 if raw[0]==0x3A else limit,budget)
        with patch.object(self.endpoint.router,'dispatch',side_effect=limited):
            assembly=rt.Assembly();position=0;inner=wire.inner(routine=2)
            while not assembly.complete:
                request,raw=self.read(position,inner);response=rt.verify_response(raw,KEY,request=request)
                assembly.accept(request,response);position+=len(response.data)
            self.assertGreater(assembly.frames,1)
            self.assertEqual(assembly.value(),routine_read.source(self.app,2,2))
            request,raw=self.read(request_inner=inner);position=len(rt.verify_response(raw,KEY,request=request).data)
            raw=container(ET.tostring(xml_source(name='Reporting')));old=self.app.engine
            candidate,_=prepare(old,decode(raw),('NOP();',),'MainProgram',1,native_source=raw,native_target=(2,2))
            self.app.engine=candidate
            self.assertEqual(self.read(position,inner)[1][2],12)
            self.assertEqual(self.read(request_inner=inner)[1][2],0)

    def test_snapshot_storage_failure_rejects_install_before_publishing_any_candidate(self):
        from logixlab import download_source_snapshot
        self.ready_install();engine=self.app.engine;before=copy.deepcopy(engine.memory.values)
        with patch.object(download_source_snapshot,'MAX_STORAGE',0):
            self.assertEqual(self.send(wire.logs.COMMIT)[2],12)
        self.assertIs(self.app.engine,engine);self.assertEqual(engine.memory.values,before)
        self.assertIsNone(getattr(engine,'installed_download',None))

    def test_missing_snapshot_does_not_reuse_the_original_mutable_batch(self):
        self.installed();self.edit();engine=self.app.engine
        engine.installed_download=replace(engine.installed_download,routine_sources=None)
        with self.assertRaisesRegex(ImageError,'download_snapshot_required'):routine_read.source(self.app,2,2)
        self.assertEqual(upload_routine_source.decode(routine_read.source(self.app,2,1)).records[0].region_id,42)


if __name__=='__main__':unittest.main()
