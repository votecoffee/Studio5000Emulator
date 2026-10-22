"""Serial Task status and independently registered execution slots."""
import copy
import struct
from types import SimpleNamespace
import unittest

import test_runtime as runtime
import test_programming_lease as leases
import test_program_reservations as reservations
from logixlab.model import Project
from logixlab.native_tasks import NativeTasks
from logixlab.native_symbols import NativeSymbols
from logixlab.runtime import Engine
from logixlab.runtime_references import RuntimeReferences
from tools.collection_inventory import decode_attribute_list


class TaskExecutionStateTests(unittest.TestCase):
    setUp=runtime.RuntimeTests.setUp
    engine=runtime.RuntimeTests.engine

    def test_serial_status_stays_clean_across_success_but_unknown_fault_history_requires_reset(self):
        engine=self.engine(['NOP();']);digest=engine.project.sha256
        read=lambda:engine.task_status_attributes('MainTask',source_sha256=digest)
        self.assertEqual(read(),{3:bytes(4),9:bytes(4)})
        engine.enter_run();engine.step();engine.step()
        self.assertEqual(read(),{3:bytes(4),9:bytes(4)})
        self.assertEqual(engine.task_status_description()['known_clean_tasks'],1)
        engine.fault='Unclassified simulator failure'
        self.assertEqual(read(),{})
        engine.fault='';engine.step()
        self.assertEqual(read(),{})
        self.assertTrue(engine.task_status_description()['unclassified_fault_seen_since_reset'])
        fresh=Engine(engine.project)
        self.assertEqual(fresh.task_status_attributes('MainTask',source_sha256=digest),{3:bytes(4),9:bytes(4)})

    def test_status_uses_current_task_and_source_and_rejects_routine_harness(self):
        engine=self.engine(['NOP();']);digest=engine.project.sha256
        self.assertEqual(engine.task_status_attributes('MainTask',source_sha256='f'*64),{})
        self.assertEqual(engine.task_status_attributes('Missing',source_sha256=digest),{})
        engine.project.tasks[0]=copy.deepcopy(engine.project.tasks[0])
        self.assertEqual(engine.task_status_attributes('MainTask',source_sha256=digest),{})
        self.assertEqual(engine.task_measurement_attributes('MainTask',source_sha256=digest),{})
        fresh=Engine(Project(engine.project.path),mode='routine',routine='MainProgram/MainRoutine')
        self.assertEqual(fresh.task_status_attributes('MainTask',source_sha256=digest),{})

    def test_slot_zero_resolves_the_current_object_and_replacement_revokes_old_registry(self):
        engine=self.engine(['NOP();']);project=engine.project;space=engine.runtime_references
        self.assertEqual(space.task_slot(project,'MAINTASK'),0)
        self.assertIs(space.resolve_task_slot(project,0),project.tasks[0])
        self.assertEqual(space.task_attributes(project,'MainTask')[16],bytes(4))
        self.assertIsNone(space.task_slot(Project(project.path),'MainTask'))
        for invalid in (True,-1,1,0.0,None):self.assertIsNone(space.resolve_task_slot(project,invalid))
        old=project.tasks[0];project.tasks[0]=copy.deepcopy(old)
        self.assertIsNone(space.resolve_task_slot(project,0))
        self.assertNotIn(16,space.task_attributes(project,'MainTask'))
        fresh=RuntimeReferences(project)
        self.assertIs(fresh.resolve_task_slot(project,0),project.tasks[0])
        self.assertIsNot(fresh.resolve_task_slot(project,0),old)

    def test_slot_limit_names_order_and_object_identity_are_independent_of_native_ids(self):
        project=SimpleNamespace(tasks=[{'name':'Task'+str(n),'id':1000+n} for n in range(32)])
        space=RuntimeReferences(project)
        self.assertEqual(space.task_slot(project,'Task31'),31)
        self.assertIs(space.resolve_task_slot(project,31),project.tasks[31])
        project.tasks.reverse();self.assertIsNone(space.resolve_task_slot(project,0))
        project.tasks.reverse();project.tasks[0]['name']='Changed'
        self.assertIsNone(space.resolve_task_slot(project,31))
        project.tasks.append({'name':'Task32'})
        self.assertIsNone(RuntimeReferences(project).task_slot(project,'Task32'))
        project.tasks=[{'name':'Main'},{'name':'MAIN'}]
        self.assertIsNone(RuntimeReferences(project).task_slot(project,'Main'))


class TaskExecutionStateWireTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare

    def test_signed_fields_have_independent_slot_identity_and_fault_history_framing(self):
        self.prepare();engine=self.app.engine;digest=engine.project.sha256
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':27}])
        numbers=(3,9,16,7,21)
        request=bytes.fromhex('03022070241b')+struct.pack('<6H',5,*numbers)
        def read(sequence):return decode_attribute_list(self.signed(sequence,request),numbers,0x70,include_payloads=True)['attributes']
        before=copy.deepcopy(self.app.state());fields=read(4)
        self.assertEqual([f['status'] for f in fields],[0,0,0,0,20])
        self.assertEqual([f['data_hex'] for f in fields[:3]],['00000000']*3)
        self.assertEqual(self.signed(5,bytes.fromhex('10032070241b301001000000'))[2],15)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])
        engine.fault='Unclassified';engine.fault=''
        fields=read(6)
        self.assertEqual([f['status'] for f in fields],[20,20,0,0,20])
        self.assertEqual(fields[2]['data_hex'],'00000000')

    def test_programming_scan_inhibit_withholds_slot_and_reference_together(self):
        self.prepare();digest=self.app.engine.project.sha256
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}])
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        request=bytes.fromhex('03022070240102000b001000')
        self.assertEqual(self.signed(4,request)[2],0)
        self.assertEqual(self.signed(5,reservations.CONTROLLER_ACQUIRE)[2],0)
        self.assertEqual(self.signed(6,reservations.message(program=26038))[2],0)
        fields=decode_attribute_list(self.signed(7,request),(11,16),0x70,include_payloads=True)['attributes']
        self.assertEqual([f['status'] for f in fields],[20,20])
        self.assertEqual(self.signed(8,reservations.message(0x4C,program=26038,payload=b''))[2],0)
        self.assertEqual(self.signed(9,reservations.CONTROLLER_RELEASE)[2],0)
        self.assertEqual(self.signed(10,request)[2],0)


if __name__=='__main__':unittest.main()
