"""Native signed readback uses installed source bytes and revokes stale streams."""
import copy
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

from logixlab import read_transport as rt,routine_read
from logixlab.ethernetip import logical
from logixlab.routine_source import decode
import test_download_installation as installation
import test_download_changelog as logs
import test_programming_lease as leases
from test_signed_messages import KEY
from test_routine_source import container,xml_source


def inner(program=2,routine=1,selector=3):
    path=logical(0x20,0x68)+logical(0x24,program)+logical(0x20,0x6D)+logical(0x24,routine)
    return bytes((0x5D,len(path)//2))+path+struct.pack('<II',1,selector)


class RoutineReadWireTests(logs.NamespaceFixture,unittest.TestCase):
    setUp=installation.InstallationSignedTests.setUp
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

    def test_full_and_fragmented_reads_return_exact_retained_container_without_changing_model(self):
        self.installed();before=copy.deepcopy(self.app.state());expected=routine_read.source(self.app,2,1)
        self.assertEqual(decode(expected).rungs[0].text_ioi,'NOP();')
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
        self.assertFalse(self.endpoint.programming_lease.description(self.app.generation,self.app.engine.project.sha256)['owned'])

    def test_wrong_selectors_writes_unknown_targets_and_missing_installation_never_return_source(self):
        self.assertEqual(self.read()[1][2],12)
        self.installed()
        for raw in (inner(selector=9),inner(selector=4),inner(program=3),inner(routine=3),
                    bytes.fromhex('5d02206d2401')+struct.pack('<II',1,3),
                    bytes.fromhex('4d03206b24013001')+struct.pack('<II',1,3)):
            self.assertNotEqual(self.read(request_inner=raw)[1][2],0)
        self.assertEqual(self.read()[1][2],0)

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
