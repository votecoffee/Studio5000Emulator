"""Saved Task Inhibit reads use source-backed IDs and four-byte booleans."""
import base64
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from logixlab.ethernetip import Endpoint, Session
from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_tasks import NativeTasks
from logixlab.native_symbols import NativeSymbols
from logixlab.server import Application
from logixlab.importers import convert_acd
from test_native_tasks import container, database, record
import test_programming_lease as leases

READ=bytes.fromhex('03022070240101001300')


class TaskMetadataWireTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare

    def test_standard_memory_single_list_and_write_denial_preserve_the_model(self):
        self.prepare();digest=self.app.engine.project.sha256
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}])
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.signed(4,bytes.fromhex('0e03207024013014')),bytes.fromhex('8e0000000000'))
        self.assertEqual(self.signed(5,bytes.fromhex('030220702401020014000600')),bytes.fromhex('830000000200140000000000060000000a00'))
        self.assertEqual(self.signed(6,bytes.fromhex('10032070240130140000'))[2],15)
        self.app.native_tasks=NativeTasks('a'*64,'b'*64,[{'name':'MainTask','instance':1}])
        self.assertEqual(self.signed(7,bytes.fromhex('0e03207024013014'))[2],12)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_captured_edit_reads_and_task_discovery_return_exact_source_values(self):
        self.prepare();project=self.app.engine.project
        self.app.native_tasks=NativeTasks('a'*64,project.sha256,[{'name':'MainTask','instance':1}])
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.signed(4,READ),bytes.fromhex('8300000001001300000000000000'))
        self.assertEqual(self.signed(5,bytes.fromhex('0e03207024013013')),bytes.fromhex('8e00000000000000'))
        self.assertEqual(self.signed(6,bytes.fromhex('0302207024010300130006001200')),
                         bytes.fromhex('8300000003001300000000000000060000000a001200000000000000'))
        self.assertEqual(self.signed(7,bytes.fromhex('4b0220702400')),bytes.fromhex('cb00000001000000'))
        self.assertEqual(self.signed(8,bytes.fromhex('100320702401301301000000'))[2],15)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_unbound_stale_incomplete_and_wrong_native_ids_cannot_supply_a_task_value(self):
        self.prepare();digest=self.app.engine.project.sha256
        self.assertEqual(self.signed(4,READ)[2],12)
        self.app.native_tasks=NativeTasks('a'*64,'b'*64,[{'name':'MainTask','instance':1}])
        self.assertEqual(self.signed(5,READ)[2],12)
        self.app.native_tasks=NativeTasks('a'*64,digest,[])
        self.assertEqual(self.signed(6,READ)[2],12)
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':20}])
        self.assertEqual(self.signed(7,READ)[2],5)

    def test_partial_attributes_and_bad_requests_preserve_framing_and_denials(self):
        self.prepare();self.app.native_tasks=NativeTasks('a'*64,self.app.engine.project.sha256,[{'name':'MainTask','instance':1}])
        self.assertEqual(self.signed(4,bytes.fromhex('0302207024010300130063001300')),
                         bytes.fromhex('83000a0003001300000000000000630014001300000000000000'))
        self.assertEqual(self.signed(5,bytes.fromhex('0e0320702401301f'))[2],20)
        self.assertEqual(self.signed(6,READ+b'x')[2],21)
        self.assertEqual(self.signed(7,bytes.fromhex('4b03207024003013'))[2],4)
        self.assertEqual(self.signed(8,bytes.fromhex('010220702401'))[2],8)

    def test_program_list_uses_matching_native_ids_and_preserves_mixed_field_alignment(self):
        self.prepare();digest=self.app.engine.project.sha256
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}])
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.signed(4,bytes.fromhex('0e03207024013001')),bytes.fromhex('8e0000000100b6650000'))
        self.assertEqual(self.signed(5,bytes.fromhex('030220702401040001000c0006001500')),
                         bytes.fromhex('83000a000400010000000100b66500000c00000020a10700060000000a0015001400'))
        self.assertEqual(self.signed(6,bytes.fromhex('10032070240130010000'))[2],15)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_unavailable_or_foreign_program_binding_never_becomes_an_empty_schedule(self):
        self.prepare();digest=self.app.engine.project.sha256
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}])
        read=bytes.fromhex('0e03207024013001')
        self.assertEqual(self.signed(4,read)[2],20)
        for sequence,native in enumerate((NativeSymbols('b'*64,digest,[],[{'name':'MainProgram','instance':4}]),
                NativeSymbols('a'*64,'c'*64,[],[{'name':'MainProgram','instance':4}]),
                NativeSymbols('a'*64,digest,[])),5):
            self.app.native_symbols=native
            self.assertEqual(self.signed(sequence,read)[2],20)


class TaskBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        source=(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').read_bytes()
        self.digest=hashlib.sha256(source).hexdigest()
        self.data={'name':'demo.L5X','content':base64.b64encode(source).decode()}
        self.native=NativeTasks('a'*64,self.digest,[{'name':'MainTask','instance':10}])

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def test_loaded_binding_is_retained_for_reset_and_cleared_for_plain_source_import(self):
        self.app.command('load',{**self.data,'native_tasks':self.native.manifest()})
        self.app.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e').start()
        self.assertEqual(self.app.endpoint.router.tasks(),[{'name':'MainTask','id':10}])
        self.assertEqual(self.app.endpoint.router.handle(bytes.fromhex('4b0220702400'),Session()),
                         bytes.fromhex('cb0000000a000000'))
        self.assertEqual(self.app.endpoint.router.handle(bytes.fromhex('0302207024000300010002000300'),Session()),
                         bytes.fromhex('830000000300010000000200020000000a0000000300000001000000'))
        for action in ('reset','configure'):
            self.app.command(action,{})
            self.assertEqual(self.app.native_tasks.manifest(),self.native.manifest())
        self.app.command('load',self.data)
        self.assertIsNone(self.app.native_tasks)
        self.assertIsNone(self.app.endpoint.state()['native_tasks'])

    def test_stale_foreign_missing_and_extra_tasks_fail_before_replacing_the_project(self):
        self.app.command('load',self.data);before=self.app.engine;generation=self.app.generation
        manifests=[{**self.native.manifest(),'source_l5x_sha256':'b'*64},
                   NativeTasks('a'*64,self.digest,[]).manifest(),
                   NativeTasks('a'*64,self.digest,[{'name':'Other','instance':1}]).manifest()]
        for manifest in manifests:
            with self.subTest(manifest=manifest),self.assertRaises(ModelError):
                self.app.command('load',{**self.data,'native_tasks':manifest})
            self.assertIs(self.app.engine,before);self.assertEqual(self.app.generation,generation)
        identity=NativeProjectIdentity('b'*64,self.digest,0,1,0,1,2,3)
        with self.assertRaisesRegex(ModelError,'different ACD'):
            self.app.command('load',{**self.data,'native_tasks':self.native.manifest(),'native_project_identity':identity.manifest()})
        self.assertIs(self.app.engine,before)

    def test_mocked_conversion_retains_task_ids_without_any_native_sdk_operation(self):
        folder=Path(self.tmp.name);source=folder/'synthetic.ACD'
        source.write_bytes(container(database(record(instance=7))))
        original=source.read_bytes();converter=folder/'fake-converter.exe';converter.write_bytes(b'test double')
        destination=folder/'converted/project.L5X'
        def convert(*args,**kwargs):
            from types import SimpleNamespace
            destination.write_bytes(base64.b64decode(self.data['content']))
            return SimpleNamespace(returncode=0,stdout='mocked conversion',stderr='')
        with patch('logixlab.importers.subprocess.run',side_effect=convert):
            receipt=convert_acd(source,destination,converter)
        self.assertEqual(receipt['native_tasks']['tasks'],[{'name':'MainTask','instance':7}])
        self.assertEqual(receipt['native_tasks']['source_acd_sha256'],hashlib.sha256(original).hexdigest())
        self.assertEqual(source.read_bytes(),original)


if __name__=='__main__':unittest.main()
