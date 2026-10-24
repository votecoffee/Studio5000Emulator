"""Native signed readback uses installed source bytes and revokes stale streams."""
import copy
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from logixlab import read_transport as rt,routine_read,upload_routine_source
from logixlab.ethernetip import logical
from logixlab.routine_source import decode
from logixlab.download_image import ImageError
import test_download_installation as installation
import test_download_changelog as logs
import test_programming_lease as leases
import test_download_headers as headers
import test_incremental_completion as components
from test_signed_messages import KEY
from test_routine_source import container,xml_source
import test_download_routines as routine_components


def inner(program=2,routine=1,selector=3):
    path=logical(0x20,0x68)+logical(0x24,program)+logical(0x20,0x6D)+logical(0x24,routine)
    return bytes((0x5D,len(path)//2))+path+struct.pack('<II',1,selector)


class EmptyRoutineReadWireTests(logs.NamespaceFixture,unittest.TestCase):
    complete_tasks=installation.InstallationSignedTests.complete_tasks
    configure=installation.InstallationSignedTests.configure
    ready_setup=installation.InstallationSignedTests.ready_setup
    ready_routines=installation.InstallationSignedTests.ready_routines
    ready_map=installation.InstallationSignedTests.ready_map
    ready_log=installation.InstallationSignedTests.ready_log
    proposal=installation.InstallationSignedTests.proposal
    ready_install=installation.InstallationSignedTests.ready_install

    def setUp(self):
        route=logs.maps.map_route
        def empty(test):
            result=route(test)
            result[1].find('./Programs/Program/Routines/Routine[@Name="MainRoutine"]/RLLContent').clear()
            return result
        with patch.object(logs.maps,'map_route',empty):RoutineReadWireTests.setUp(self)

    def next_routines(self):
        return components.CompletionSignedTests.next_batch(self,routine_components.empty_batch())

    def test_committed_empty_source_is_read_byte_for_byte_and_bound_to_empty_runtime(self):
        self.ready_install();self.assertEqual(self.send(logs.COMMIT)[2],0)
        self.send(logs.prep.END);self.send(leases.RELEASE)
        engine=self.app.engine;batch=engine.installed_download.namespace._routine_batch
        expected=batch._values[2,1].source[8:];before=copy.deepcopy(engine.memory.values)
        self.assertEqual(routine_read.source(self.app,2,1),expected)
        request=rt.ReadRequest(self.sequence,0x101,0,inner());self.sequence+=1
        raw=self.cip(rt.encode_request(request,KEY));assembly=rt.Assembly()
        assembly.accept(request,rt.verify_response(raw,KEY,request=request))
        self.assertTrue(assembly.complete);self.assertEqual(assembly.value(),expected)
        self.assertEqual(engine.memory.values,before);self.assertEqual(engine.scan_count,0)
        self.assertFalse(engine.project.routines['mainprogram/mainroutine'].rungs)
        engine.project.routines['mainprogram/mainroutine'].problems.append('RLL content is missing or protected')
        with self.assertRaises(ImageError):routine_read.source(self.app,2,1)


class RoutineReadWireTests(logs.NamespaceFixture,unittest.TestCase):
    def setUp(self):
        original=headers.HeaderTests.batch
        def batch(case):
            rows=list(original(case));rows[10:10]=[components.component(),components.component(instance=2)]
            return tuple(rows)
        with patch.object(headers.HeaderTests,'batch',batch):installation.InstallationSignedTests.setUp(self)
    complete_tasks=installation.InstallationSignedTests.complete_tasks
    configure=installation.InstallationSignedTests.configure
    ready_setup=installation.InstallationSignedTests.ready_setup
    ready_routines=installation.InstallationSignedTests.ready_routines
    next_routines=installation.InstallationSignedTests.next_routines
    ready_map=installation.InstallationSignedTests.ready_map
    ready_log=installation.InstallationSignedTests.ready_log
    proposal=installation.InstallationSignedTests.proposal
    ready_install=installation.InstallationSignedTests.ready_install

    def installed(self):
        self.ready_install();self.assertEqual(self.send(logs.COMMIT)[2],0)
        self.send(logs.prep.END);self.send(leases.RELEASE)

    def read(self,position=0,request_inner=None):
        request=rt.ReadRequest(self.sequence,1 if position else 0x101,position,
            b'' if position else inner() if request_inner is None else request_inner)
        self.sequence+=1;raw=rt.encode_request(request,KEY)
        return request,self.cip(raw)

    def test_full_and_fragmented_reads_return_upload_view_without_changing_retained_source_or_model(self):
        self.installed();before=copy.deepcopy(self.app.state());expected=routine_read.source(self.app,2,1)
        self.assertEqual(upload_routine_source.decode(expected).records[0].text_ioi,'NOP();')
        retained=self.app.engine.installed_download.namespace._routine_batch._values[2,1].source
        self.assertEqual(decode(retained[8:]).rungs[0].text_ioi,'NOP();')
        for maximum in (480,88):
            original=self.endpoint.router.dispatch
            def limited(raw,session,depth=0,limit=480,budget=None):return original(raw,session,depth,min(limit,maximum) if raw[0]==0x3A else limit,budget)
            assembly=rt.Assembly();position=0
            with patch.object(self.endpoint.router,'dispatch',side_effect=limited):
                while not assembly.complete:
                    request,raw=self.read(position);self.assertLessEqual(len(raw),maximum)
                    response=rt.verify_response(raw,KEY,request=request)
                    assembly.accept(request,response);position+=len(response.data)
            self.assertEqual(assembly.value(),expected)
            if maximum==88:self.assertGreater(assembly.frames,1)
        for key in ('tags','scan','ms','routines','controller','routine_edits'):
            self.assertEqual(self.app.state()[key],before[key])
        self.assertEqual(self.app.engine.installed_download.namespace._routine_batch._values[2,1].source,retained)
        self.assertFalse(self.endpoint.programming_lease.description(self.app.generation,self.app.engine.project.sha256)['owned'])

    def test_wrong_selectors_writes_unknown_targets_and_missing_installation_never_return_source(self):
        self.assertEqual(self.read()[1][2],12)
        self.installed()
        for raw in (inner(selector=5),inner(selector=0),inner(program=3),inner(routine=3),
                    bytes.fromhex('5d02206d2401')+struct.pack('<II',1,3),
                    bytes.fromhex('4d03206b24013001')+struct.pack('<II',1,3)):
            self.assertNotEqual(self.read(request_inner=raw)[1][2],0)
        self.assertEqual(self.read()[1][2],0)

    def test_selector_four_is_one_empty_signed_stream_then_source_read_can_follow(self):
        self.installed();before=copy.deepcopy(self.app.state())
        request,raw=self.read(request_inner=inner(selector=4))
        self.assertEqual(len(raw),36)
        response=rt.verify_response(raw,KEY,request=request);assembly=rt.Assembly()
        assembly.accept(request,response)
        self.assertTrue(assembly.complete);self.assertEqual(assembly.value(),b'')
        self.assertFalse(any(s.read_stream is not None for s in self.endpoint.native_sessions.values()))
        request,raw=self.read()
        self.assertEqual(rt.verify_response(raw,KEY,request=request).data,
                         routine_read.source(self.app,2,1)[:444])
        for key in ('tags','scan','ms','routines','controller','routine_edits'):
            self.assertEqual(self.app.state()[key],before[key])

    def test_selector_four_revalidates_retained_source_and_requires_original_unprotected_profile(self):
        self.installed();original=self.app.native_routines
        from logixlab.native_routines import NativeRoutines
        rows=[row.manifest() for row in original.rows];rows[0]['type_word']=0
        self.app.native_routines=NativeRoutines(original.source_acd_sha256,original.source_l5x_sha256,rows)
        self.assertNotEqual(self.read(request_inner=inner(selector=4))[1][2],0)
        self.app.native_routines=original
        self.app.engine.project.runtime_revision=1
        self.assertEqual(self.read(request_inner=inner(selector=4))[1][2],12)

    def test_opaque_component_read_returns_stored_bytes_and_changed_effects_revoke_continuation(self):
        self.installed();ns=self.app.engine.installed_download.namespace
        expected=ns._incremental._routine_data[(2,1)];self.assertEqual(len(expected),13)
        original=self.endpoint.router.dispatch
        def limited(raw,session,depth=0,limit=480,budget=None):return original(raw,session,depth,40 if raw[0]==0x3A else limit,budget)
        with patch.object(self.endpoint.router,'dispatch',side_effect=limited):
            assembly=rt.Assembly();position=0
            while not assembly.complete:
                request,raw=self.read(position,inner(selector=9));response=rt.verify_response(raw,KEY,request=request)
                assembly.accept(request,response);position+=len(response.data)
            self.assertEqual(assembly.value(),expected);self.assertEqual(assembly.frames,4)
            request,raw=self.read(request_inner=inner(selector=9));position=len(rt.verify_response(raw,KEY,request=request).data)
            ns._incremental._routine_data={(2,1):b'X'*13}
            self.assertEqual(self.read(position)[1][2],12)
            self.assertEqual(self.read(position)[1][2],12)
        self.assertEqual(self.app.engine.scan_count,0)

    def test_foreign_context_missing_start_bad_offset_and_new_start_cannot_steal_a_stream(self):
        self.installed();original=self.endpoint.router.dispatch
        def limited(raw,session,depth=0,limit=480,budget=None):return original(raw,session,depth,88 if raw[0]==0x3A else limit,budget)
        with patch.object(self.endpoint.router,'dispatch',side_effect=limited):
            request,raw=self.read();position=len(rt.verify_response(raw,KEY,request=request).data)
            first=self.client;sequence=self.sequence;other=self.second_client()
            try:
                self.client=other;self.sequence=4
                self.assertEqual(self.read(position)[1][2],12)
            finally:self.client=first;self.sequence=sequence;other.close()
            request,raw=self.read(position);self.assertEqual(raw[2],0)
            self.assertEqual(self.read(request_inner=inner(routine=2))[1][2],12)
            self.assertEqual(self.read(position)[1][2],12)
            self.read();self.assertEqual(self.read(position+1)[1][2],12)
            self.assertEqual(self.read(position)[1][2],12)

    def test_catalog_change_between_chunks_discards_the_old_stream(self):
        self.installed();original=self.endpoint.router.dispatch
        def limited(raw,session,depth=0,limit=480,budget=None):return original(raw,session,depth,88 if raw[0]==0x3A else limit,budget)
        with patch.object(self.endpoint.router,'dispatch',side_effect=limited):
            request,raw=self.read();position=len(rt.verify_response(raw,KEY,request=request).data)
            identity=self.app.native_project_identity
            self.app.native_project_identity=replace(identity,copy_uid=identity.copy_uid+1)
            self.assertEqual(self.read(position)[1][2],12)
            self.app.native_project_identity=identity
            self.assertEqual(self.read(position)[1][2],12)
            self.assertEqual(self.read()[1][2],0)

    def test_catalog_change_engine_edit_and_active_programming_revoke_readback(self):
        self.installed();original=self.app.native_project_identity
        self.app.native_project_identity=replace(original,copy_uid=original.copy_uid+1)
        self.assertEqual(self.read()[1][2],12);self.app.native_project_identity=original
        self.send(leases.ACQUIRE)
        self.assertEqual(self.read()[1][2],12);self.send(leases.RELEASE)
        from logixlab.routine_edits import prepare
        engine=self.app.engine;source=decode(container(ET.tostring(xml_source())))
        candidate,_=prepare(engine,source,('NOP();',),'MainProgram',0);self.app.engine=candidate
        self.assertEqual(self.read()[1][2],12)

    def test_bad_mac_and_counter_replay_clear_key_and_pending_source(self):
        self.installed();request=rt.ReadRequest(self.sequence,0x101,0,inner())
        raw=rt.encode_request(request,KEY);self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
        self.assertEqual(self.cip(raw)[2],15)

    def test_small_reply_budget_and_frame_limit_do_not_advance_or_leave_partial_stream(self):
        self.installed();original=self.endpoint.router.dispatch
        def limited(raw,session,depth=0,limit=480,budget=None):return original(raw,session,depth,36 if raw[0]==0x3A else limit,budget)
        with patch.object(self.endpoint.router,'dispatch',side_effect=limited):self.assertEqual(self.read()[1][2],0x1B)
        request,raw=self.read();self.assertEqual(raw[2],0)
        stream=routine_read.Stream.begin(self.app,2,1);stream.frames=rt.MAX_FRAMES
        with self.assertRaisesRegex(ValueError,'frame_limit'):stream.reply(self.app,request,KEY,480)


if __name__=='__main__':unittest.main()
