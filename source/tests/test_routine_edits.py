"""Signed Program-mode replacement changes execution only at a valid commit."""
import copy
import hashlib
import struct
import unittest
from xml.etree import ElementTree as ET
from logixlab.model import ModelError
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.native_types import NativeTypes
from logixlab import signed_messages as sm
from test_signed_messages import KEY
from test_signed_transfer import controlled_request
from test_edit_transfer import container,prefix,source_prefix
import test_edit_transfer as transfers
from test_routine_source import container as source_container,xml_source
import test_edit_preparation as edits
import test_program_reservations as reservations

COMMIT=bytes.fromhex('5902208e2401')+bytes(4)


class RoutineEditWireTests(unittest.TestCase):
    setUp=transfers.EditTransferSignedTests.setUp
    tearDown=transfers.EditTransferSignedTests.tearDown
    cip=transfers.EditTransferSignedTests.cip
    begin=transfers.EditTransferSignedTests.begin
    signed=transfers.EditTransferSignedTests.signed
    bind=transfers.EditTransferSignedTests.bind
    prepare=transfers.EditTransferSignedTests.prepare
    send=transfers.EditTransferSignedTests.send
    ready=transfers.EditTransferSignedTests.ready
    fragment=transfers.EditTransferSignedTests.fragment
    first=transfers.EditTransferSignedTests.first

    def stage(self):
        self.ready();sha=self.app.engine.project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,sha,[Symbol('',0,'SpeedSetpoint',5)],programs=[{'name':'MainProgram','instance':300}])
        self.app.native_types=NativeTypes('a'*64,sha,[])
        self.first();self.fragment(0x201,32,container()[32:])
        source=source_container(ET.tostring(xml_source(text='MOV(123,@107 5 0 0 0 0@);')))
        self.fragment(0x101,len(source),source_prefix(self.routine)+source[:48]);self.fragment(0x201,48,source[48:])
        body=prefix(routine=self.routine)[:14]+struct.pack('<5I',2,5,0,1,123)
        raw=controlled_request(body,self.sequence);self.sequence+=1
        self.assertEqual(sm.verify_response(self.cip(raw),KEY,request=sm.parse_request(raw)).inner,b'\xDC\0\0\0')

    def release_program(self):self.send(reservations.message(0x4C,payload=b''))

    def test_native_commit_retains_exact_source_after_temporary_transfer_is_cleared(self):
        from logixlab.accepted_routine_source import records
        self.app.allow_routine_edits=True;self.stage();raw=self.endpoint.programming_lease.edit_transfer.source_bytes()
        old=self.app.engine;self.release_program();self.assertEqual(self.send(COMMIT)[2],0)
        rows=records(self.app.engine.project)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0].data,raw)
        self.assertEqual(rows[0].sha256,hashlib.sha256(raw).hexdigest())
        self.assertEqual(records(old.project),())
        self.assertFalse(self.endpoint.programming_lease.edit_transfer.ready())
        self.assertEqual(self.app.state()['routine_edits']['native_source_readback']['retained_routines'],1)

    def test_retained_source_budget_failure_does_not_commit_or_discard_the_candidate(self):
        from unittest.mock import patch
        from logixlab import accepted_routine_source
        self.app.allow_routine_edits=True;self.stage();self.release_program();old=self.app.engine
        with patch.object(accepted_routine_source,'MAX_BYTES',1):self.assertEqual(self.send(COMMIT)[2],12)
        self.assertIs(self.app.engine,old)
        self.assertTrue(self.endpoint.programming_lease.edit_transfer.ready())

    def test_replacement_metadata_requires_supported_live_edit_context_and_does_not_write_active_metadata(self):
        from logixlab.ethernetip import logical
        self.stage();before=self.app.engine
        path=logical(0x20,0x349)+logical(0x24,1)
        payload=struct.pack('<IIHHHHIHHIIIH',0x301,30,0x68,300,0x6D,self.routine,2,0,0x7F,0,0,0,4)
        message=bytes((0x4F,len(path)//2))+path+payload
        self.assertEqual(self.send(message)[2],15)
        self.app.allow_routine_edits=True
        self.assertEqual(self.send(message),b'\xCF\0\0\0');self.assertEqual(self.send(message)[2],0)
        lease=self.endpoint.programming_lease
        self.assertEqual(lease.edit_transfer.description()['routine_metadata']['records'],1)
        self.assertEqual(lease.metadata.rows,{});self.assertEqual(lease.metadata.values,{})
        self.assertIs(self.app.engine,before)
        self.release_program();self.assertEqual(self.send(message)[2],12)
        self.assertEqual(self.send(COMMIT)[2],0)
        self.assertEqual(lease.edit_transfer.description()['routine_metadata']['records'],0)
        self.send(edits.CLOSE);self.send(reservations.CONTROLLER_RELEASE)

    def test_atomic_apply_preserves_values_scan_history_source_and_changes_next_execution(self):
        self.app.allow_routine_edits=True
        old=self.app.engine;old.memory.write('SpeedSetpoint',7);old.scan_count=12;old.time_ms=120
        old.prescan_count=3;old._initial_prescan_pending=False;old.memory.first_scan=False
        old.last_timer={('startdelay',()):100};old.changes=[{'scan':10,'tag':'SpeedSetpoint'}]
        from logixlab.program_timing import ProgramTiming
        old._program_timings['mainprogram']=ProgramTiming(5000,10000,12)
        from logixlab.task_runtime import TaskMeasurements
        old._task_measurements=TaskMeasurements().record(1000,10000,start_time_us=123456789).record(12000,15000,start_time_us=123456799)
        old._native_fault_history_uncertain=True
        source_hash=hashlib.sha256(old.project.path.read_bytes()).hexdigest()
        self.stage();before=copy.deepcopy(self.app.state())
        self.assertEqual(self.send(COMMIT)[2],12)
        self.release_program()
        self.assertTrue(self.endpoint.programming_lease.edit_transfer.program_released)
        with self.assertRaises(ModelError):self.app.command('controller-mode',{'mode':'Run'})
        self.assertEqual(self.send(COMMIT),b'\xD9\0\0\0')
        after=self.app.state();self.assertIsNot(self.app.engine,old)
        for key in ('tags','scan','ms','changes','controller','tasks','entry_routines'):self.assertEqual(before[key],after[key])
        self.assertEqual(self.app.engine.last_timer,old.last_timer)
        self.assertEqual(self.app.engine._program_timings,old._program_timings)
        self.assertEqual(self.app.engine._task_measurements,old._task_measurements)
        self.assertTrue(self.app.engine._native_fault_history_uncertain)
        current=self.app.engine
        self.assertEqual(current.task_status_attributes('MainTask',source_sha256=current.project.sha256),{})
        self.assertIs(current.runtime_references.resolve_task_slot(current.project,0),current.project.tasks[0])
        self.assertIsNone(old.runtime_references.resolve_task_slot(current.project,0))
        self.assertEqual(self.app.engine.memory.first_scan,old.memory.first_scan)
        self.assertEqual(after['routine_edits']['revision'],1);self.assertTrue(after['routine_edits']['modified'])
        self.assertIs(current.project.component_tracking,old.project.component_tracking)
        self.assertEqual(after['routine_edits']['edited_routines'],['mainprogram/mainroutine'])
        with self.assertRaisesRegex(ModelError,'transaction'):self.app.command('export-edited-l5x',{})
        self.assertEqual(self.app.engine.project.instruction_counts['MOV'],1)
        current=self.app.engine;self.assertEqual(self.send(COMMIT)[2],0)
        self.assertIs(self.app.engine,current);self.assertEqual(self.app.state()['routine_edits']['revision'],1)
        self.send(edits.CLOSE);self.send(reservations.CONTROLLER_RELEASE)
        self.assertEqual(self.app.command('export-edited-l5x',{})['logic_revision'],1)
        self.app.command('step',{'count':1})
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'),123)
        self.assertEqual(self.app.engine.scan_count,13)
        self.assertEqual(old.memory.read('SpeedSetpoint'),7)
        self.assertEqual(hashlib.sha256(old.project.path.read_bytes()).hexdigest(),source_hash)
        self.assertFalse(self.endpoint.programming_lease.edit_transfer.ready())

    def test_disabled_access_bad_payload_stale_logic_and_changed_bindings_never_replace_engine(self):
        self.stage();self.release_program();engine=self.app.engine;before=copy.deepcopy(self.app.state())
        self.assertEqual(self.send(COMMIT)[2],15)
        self.app.allow_routine_edits=True
        for raw in (COMMIT[:-1],COMMIT+b'X',COMMIT[:-4]+b'\1\0\0\0'):
            self.assertNotEqual(self.send(raw)[2],0);self.assertIs(self.app.engine,engine)
        self.endpoint.programming_lease.edit_transfer.base_revision=1
        self.assertEqual(self.send(COMMIT)[2],12);self.assertIs(self.app.engine,engine)
        self.endpoint.programming_lease.edit_transfer.base_revision=0
        self.app.native_types=None
        self.assertEqual(self.send(COMMIT)[2],12);self.assertIs(self.app.engine,engine)
        for key in ('tags','routines','scan','ms','changes','controller'):self.assertEqual(before[key],self.app.state()[key])

    def test_phase_close_and_absolute_expiry_cancel_released_complete_candidate(self):
        self.app.allow_routine_edits=True;self.stage();self.release_program();engine=self.app.engine
        self.endpoint.programming_lease.edit_transfer.deadline=-1
        self.assertEqual(self.send(COMMIT)[2],12);self.assertIs(self.app.engine,engine)
        self.send(edits.CLOSE);self.send(reservations.CONTROLLER_RELEASE)
        self.client.close()
        from test_ethernetip import Client
        self.client=Client(self.endpoint.port);self.client.register()
        self.stage();self.release_program();self.send(edits.CLOSE)
        self.assertEqual(self.send(COMMIT)[2],12);self.assertIs(self.app.engine,engine)
        self.assertEqual(self.app.state()['routine_edits']['revision'],0)

    def test_foreign_context_cannot_commit_or_discard_released_candidate(self):
        from test_ethernetip import Client
        self.app.allow_routine_edits=True;self.stage();self.release_program()
        first=self.client;sequence=self.sequence;engine=self.app.engine
        second=Client(self.endpoint.port);second.register()
        try:
            self.client=second;self.bind();self.sequence=4
            self.assertEqual(self.send(COMMIT)[2],15)
            self.assertTrue(self.endpoint.programming_lease.edit_transfer.ready())
            self.assertIs(self.app.engine,engine)
        finally:self.client=first;self.sequence=sequence;second.close()
        self.assertEqual(self.send(COMMIT)[2],0)

    def test_edit_access_setting_requires_disconnected_program_and_exact_boolean(self):
        for value in (None,1,'true'):
            with self.assertRaises(ModelError):self.app.command('routine-edits-configure',{'allow_writes':value})
        with self.assertRaises(ModelError):self.app.command('routine-edits-configure',{'allow_writes':True})
        self.client.close()
        import time
        deadline=time.monotonic()+1
        while self.endpoint.state()['active_tcp_clients'] and time.monotonic()<deadline:time.sleep(.01)
        state=self.app.command('routine-edits-configure',{'allow_writes':True})
        self.assertTrue(state['routine_edits']['enabled'])
        self.app.command('controller-mode',{'mode':'Run'})
        with self.assertRaises(ModelError):self.app.command('routine-edits-configure',{'allow_writes':False})
        self.app.command('controller-mode',{'mode':'Program'})
        self.assertFalse(self.app.command('routine-edits-configure',{'allow_writes':False})['routine_edits']['enabled'])


if __name__=='__main__':unittest.main()
