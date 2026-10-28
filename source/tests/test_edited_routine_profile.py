"""Retained profile reads survive edits; unknown, missing and stale bytes do not."""
from dataclasses import replace
import hashlib
import unittest
from unittest.mock import patch

from logixlab import read_transport as rt,routine_read
from logixlab.download_image import ImageError
from test_signed_messages import KEY
import test_accepted_routine_source as accepted
import test_routine_read as wire


class EditedRoutineProfileTests(accepted.wire.logs.NamespaceFixture,unittest.TestCase):
    setUp=accepted.AcceptedRoutineSourceTests.setUp
    installed=accepted.AcceptedRoutineSourceTests.installed
    complete_tasks=accepted.AcceptedRoutineSourceTests.complete_tasks
    configure=accepted.AcceptedRoutineSourceTests.configure
    ready_setup=accepted.AcceptedRoutineSourceTests.ready_setup
    ready_routines=accepted.AcceptedRoutineSourceTests.ready_routines
    next_routines=accepted.AcceptedRoutineSourceTests.next_routines
    ready_map=accepted.AcceptedRoutineSourceTests.ready_map
    ready_log=accepted.AcceptedRoutineSourceTests.ready_log
    proposal=accepted.AcceptedRoutineSourceTests.proposal
    ready_install=accepted.AcceptedRoutineSourceTests.ready_install
    read=accepted.AcceptedRoutineSourceTests.read
    edit=accepted.AcceptedRoutineSourceTests.edit

    def test_retained_profile_is_not_a_read_of_stale_compiled_code_or_mutable_staging(self):
        self.installed();before=self.app.engine.installed_download;self.edit()
        snapshot=before.routine_sources
        before.namespace._incremental._routine_data={}
        for target in (1,2):
            self.assertEqual(routine_read.source(self.app,2,target,9),wire.components.DATA)
            self.assertEqual(routine_read.source(self.app,2,target,4),b'')
        self.assertIs(self.app.engine.installed_download.routine_sources,snapshot)

    def test_missing_changed_or_wrongly_bound_profile_does_not_fall_back_to_a_constant(self):
        self.installed();self.edit();engine=self.app.engine;installed=engine.installed_download
        snapshot=installed.routine_sources;row=snapshot.sources[0]
        for changed in (replace(row,component=None,component_sha256=None),replace(row,component=b'bad'),
                replace(row,component_sha256='0'*64),replace(row,key='other/routine'),
                replace(row,component=b'bad',component_sha256=hashlib.sha256(b'bad').hexdigest())):
            engine.installed_download=replace(installed,routine_sources=replace(snapshot,sources=(changed,*snapshot.sources[1:])))
            with self.subTest(changed=changed),self.assertRaises(ImageError):routine_read.source(self.app,2,1,9)
        engine.installed_download=replace(installed,tag_bindings=None)
        with self.assertRaises(ImageError):routine_read.source(self.app,2,1,9)

    def test_current_source_and_catalog_checks_guard_profile_and_empty_stream(self):
        self.installed();self.edit();engine=self.app.engine
        engine.project.routines['mainprogram/mainroutine'].rungs[0]['nodes']=[]
        for selector in (4,9):
            with self.assertRaises(ImageError):routine_read.source(self.app,2,1,selector)

    def test_signed_profile_stream_is_exact_and_the_next_edit_revokes_its_continuation(self):
        self.installed();self.edit();original=self.endpoint.router.dispatch
        def limited(raw,session,depth=0,limit=480,budget=None):
            return original(raw,session,depth,40 if raw[0]==0x3A else limit,budget)
        with patch.object(self.endpoint.router,'dispatch',side_effect=limited):
            assembly=rt.Assembly();position=0
            while not assembly.complete:
                request,raw=self.read(position,wire.inner(selector=9));self.assertEqual(raw[2],0)
                response=rt.verify_response(raw,KEY,request=request);assembly.accept(request,response);position+=len(response.data)
            self.assertEqual(assembly.value(),wire.components.DATA);self.assertGreater(assembly.frames,1)
            request,raw=self.read(request_inner=wire.inner(selector=9));position=len(rt.verify_response(raw,KEY,request=request).data)
            self.edit(region='43');self.assertEqual(self.read(position)[1][2],12)
        request,raw=self.read(request_inner=wire.inner(selector=4));self.assertEqual(raw[2],0)
        self.assertEqual(rt.verify_response(raw,KEY,request=request).data,b'')

    def test_initial_profile_rejection_is_visible_with_actual_routine_scope(self):
        self.installed();self.edit();engine=self.app.engine;installed=engine.installed_download;snapshot=installed.routine_sources
        row=replace(snapshot.sources[0],component=None,component_sha256=None)
        engine.installed_download=replace(installed,routine_sources=replace(snapshot,sources=(row,*snapshot.sources[1:])))
        request,raw=self.read(request_inner=wire.inner(selector=9));self.assertEqual(raw[2],12)
        rows=self.endpoint.native_rejections.snapshot(self.app.generation)
        row,=rows;self.assertEqual((row['class_id'],row['program_instance'],row['instance'],row['service']),(0x6D,2,1,0x5D))
        self.assertEqual(row['reason'],'download_source_component_unavailable')


if __name__=='__main__':unittest.main()
