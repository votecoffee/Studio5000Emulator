"""Real signed TCP replacement without SDK keys, service calls or a controller."""
import base64
import copy
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

from logixlab.native_routines import NativeRoutines
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.native_types import NativeTypes
from tools.anonymous_client import AnonymousClient,ProbeError
from tools.routine_edit_probe import replace_routine
import test_anonymous_client as clients


@unittest.skipUnless(importlib.util.find_spec('cryptography'),'optional independent client key generator')
class RoutineProbeTests(unittest.TestCase):
    setUp=clients.AnonymousClientTests.setUp
    tearDown=clients.AnonymousClientTests.tearDown

    def bind(self):
        sha=self.app.engine.project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,sha,[Symbol('',0,'SpeedSetpoint',5)],
            programs=[{'name':'MainProgram','instance':300}])
        self.app.native_types=NativeTypes('a'*64,sha,[])
        config=self.app.engine.project.executable_configuration
        self.app.native_routines=NativeRoutines('a'*64,sha,[dict(program='MainProgram',name=name,
            program_instance=300,instance=700+index) for index,name in enumerate(
                config.routine_names('MainProgram',source_sha256=sha))])
        self.app.command('routine-edits-configure',{'allow_writes':True})

    def apply(self,value=123):
        return replace_routine(self.endpoint,program='MainProgram',routine='MainRoutine',tag='SpeedSetpoint',value=value)

    def assert_closed(self):
        state=self.endpoint.state()
        self.assertEqual(state['active_tcp_clients'],0)
        lease=state['native_programming_lease']
        self.assertFalse(lease['owned']);self.assertFalse(lease['scan_inhibited'])
        self.assertEqual(lease['edit_transfer']['status'],'idle')

    def test_commit_preserves_values_then_executes_reconnects_and_exports_reproducible_logic(self):
        self.bind();before=copy.deepcopy(self.app.state());report=self.apply(-123)
        self.assertEqual(len(report['checks']),15)
        self.assertTrue(report['cleanup_confirmed']);self.assertTrue(report['synthetic_compiled_container'])
        self.assertEqual(report['native_sdk_acceptance'],'NOT ASSESSED')
        self.assertEqual(report['revision_after'],1)
        for key in ('tags','scan','ms','controller','tasks'):self.assertEqual(self.app.state()[key],before[key])
        with AnonymousClient(self.endpoint) as client:
            client.bind();self.assertEqual(client.request(bytes.fromhex('0e03200124013001')),bytes.fromhex('8e0000000100'))
        self.app.command('step',{'count':1})
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'),-123)
        exported=self.app.command('export-edited-l5x',{})
        from logixlab.server import Application
        with tempfile.TemporaryDirectory() as folder:
            other=Application(folder)
            try:
                other.command('load',{'name':'edited.L5X','content':base64.b64encode(exported['content'].encode()).decode()})
                other.command('step',{'count':1});self.assertEqual(other.engine.memory.read('SpeedSetpoint'),-123)
            finally:other.close()
        self.assert_closed()

    def test_second_connection_replaces_same_routine_and_increments_revision_only_once(self):
        self.bind();self.apply(123);self.app.command('step',{'count':1});before=copy.deepcopy(self.app.state())
        report=self.apply(456)
        self.assertEqual((report['revision_before'],report['revision_after']),(1,2))
        self.assertEqual(self.app.state()['tags'],before['tags']);self.assertEqual(self.app.engine.scan_count,1)
        self.app.command('step',{'count':1});self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'),456)
        self.assert_closed()

    def test_disabled_invalid_or_unbound_targets_send_no_signed_programming_requests(self):
        with self.assertRaises(ProbeError):self.apply()
        self.assert_closed();self.bind()
        for kwargs in ({'value':True},{'value':1<<31},{'program':'Missing'},
                       {'routine':'Missing'},{'tag':'StartPB'},{'tag':'Missing'}):
            options={'program':'MainProgram','routine':'MainRoutine','tag':'SpeedSetpoint',**kwargs}
            count=self.endpoint.counts['native_verified']
            with self.subTest(options=options),self.assertRaises(ProbeError):replace_routine(self.endpoint,**options)
            self.assertEqual(self.endpoint.counts['native_verified'],count);self.assert_closed()
        self.assertEqual(self.app.state()['routine_edits']['revision'],0)
        binding=self.app.native_types;self.app.native_types=None
        with self.assertRaises(ProbeError):self.apply()
        self.app.native_types=binding;self.assert_closed()
        self.app.command('controller-mode',{'mode':'Run'})
        with self.assertRaises(ProbeError):self.apply()
        self.app.command('controller-mode',{'mode':'Program'});self.assert_closed()

    def test_generation_change_aborts_fragments_closes_lease_and_keeps_active_logic(self):
        self.bind();before=copy.deepcopy(self.app.state());original=AnonymousClient.fragment;calls=[]
        def changed(client,*args):
            response=original(client,*args);calls.append(args)
            if len(calls)==1:self.app.generation+=1
            return response
        with patch.object(AnonymousClient,'fragment',changed),self.assertRaises(ProbeError):self.apply()
        self.assert_closed();self.assertEqual(len(calls),1)
        for key in ('tags','routines','scan','routine_edits'):self.assertEqual(self.app.state()[key],before[key])

    def test_lost_commit_reply_is_never_retried_and_caller_can_discard_isolated_app(self):
        self.bind();original=AnonymousClient.request;commits=[]
        def changed(client,raw,*args,**kwargs):
            response=original(client,raw,*args,**kwargs)
            if raw[0]==0x59:
                commits.append(response[2])
                if response[2]==0:raise ProbeError('Simulated loss after applied commit')
            return response
        with patch.object(AnonymousClient,'request',changed),self.assertRaisesRegex(ProbeError,'Simulated loss'):
            self.apply()
        self.assertEqual(commits,[12,0]);self.assertEqual(self.app.state()['routine_edits']['revision'],1)
        self.assertEqual(self.app.engine.scan_count,0);self.assert_closed()


if __name__=='__main__':unittest.main()
