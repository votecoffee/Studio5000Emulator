"""No-AOI allocation policy must not hide unknown or populated source stacks."""
import copy
import struct
import unittest
from xml.etree import ElementTree as E

import test_runtime as runtime
from logixlab.runtime import Engine
from logixlab.native_tasks import NativeTasks
import test_task_runtime as measurements
from tools.collection_inventory import decode_attribute_list


class TaskStackTests(unittest.TestCase):
    setUp=runtime.RuntimeTests.setUp
    engine=runtime.RuntimeTests.engine

    def test_no_aoi_allocation_is_independent_of_execution_and_reset(self):
        engine=self.engine(['NOP();']);digest=engine.project.sha256
        read=lambda:engine.task_stack_attributes('MainTask',source_sha256=digest)
        self.assertEqual(read(),{22:bytes(4),23:bytes(4)})
        self.assertEqual(engine.task_measurement_description()['successful_task_executions'],0)
        engine.enter_run();engine.step();engine.step()
        self.assertEqual(read(),{22:bytes(4),23:bytes(4)})
        fresh=Engine(engine.project)
        self.assertEqual(fresh.task_stack_attributes('MainTask',source_sha256=digest),read())
        info=engine.task_stack_description()
        self.assertEqual((info['pending_allocation_bytes'],info['active_allocation_bytes']),(0,0))
        self.assertFalse(info['physical_stack_imported'])

    def test_absent_unknown_and_nonempty_declarations_are_not_zero_stacks(self):
        original=copy.deepcopy(self.root)
        for kind in ('missing','unknown','definition','protected','duplicate','context'):
            self.root=copy.deepcopy(original)
            def mutate(root):
                controller=root.find('Controller');section=controller.find('AddOnInstructionDefinitions')
                if kind=='missing':controller.remove(section)
                elif kind=='unknown':E.SubElement(section,'VendorDefinition')
                elif kind=='definition':E.SubElement(section,'AddOnInstructionDefinition',Name='Example')
                elif kind=='protected':E.SubElement(controller,'ProtectedContent')
                elif kind=='duplicate':E.SubElement(controller,'AddOnInstructionDefinitions')
                else:root.set('ContainsContext','true')
            with self.subTest(kind=kind):
                engine=self.engine(['NOP();'],mutate=mutate)
                self.assertEqual(engine.task_stack_attributes('MainTask',source_sha256=engine.project.sha256),{})
                self.assertIsNone(engine.task_stack_description()['active_allocation_bytes'])

    def test_source_registration_mode_and_fault_history_guards(self):
        engine=self.engine(['NOP();']);digest=engine.project.sha256
        self.assertEqual(engine.task_stack_attributes('MainTask',source_sha256='f'*64),{})
        self.assertEqual(engine.task_stack_attributes('Missing',source_sha256=digest),{})
        harness=Engine(engine.project,mode='routine',routine='MainProgram/MainRoutine')
        self.assertEqual(harness.task_stack_attributes('MainTask',source_sha256=digest),{})
        engine.fault='Unknown simulator failure';engine.fault='';engine.step()
        self.assertEqual(engine.task_stack_attributes('MainTask',source_sha256=digest),{})
        fresh=Engine(engine.project);fresh.project.tasks[0]=copy.deepcopy(fresh.project.tasks[0])
        self.assertEqual(fresh.task_stack_attributes('MainTask',source_sha256=digest),{})

    def test_runtime_aoi_frames_cannot_bypass_source_guard(self):
        engine=self.engine(['NOP();']);digest=engine.project.sha256
        engine.addons.active.add('Unexpected')
        self.assertEqual(engine.task_stack_attributes('MainTask',source_sha256=digest),{})
        engine.addons.active.clear();engine.addons.instances['Unexpected']={}
        self.assertEqual(engine.task_stack_attributes('MainTask',source_sha256=digest),{})


class TaskStackWireTests(unittest.TestCase):
    setUp=measurements.TaskMeasurementWireTests.setUp
    tearDown=measurements.TaskMeasurementWireTests.tearDown
    signed=measurements.TaskMeasurementWireTests.signed
    cip=measurements.TaskMeasurementWireTests.cip
    begin=measurements.TaskMeasurementWireTests.begin
    bind=measurements.TaskMeasurementWireTests.bind
    prepare=measurements.TaskMeasurementWireTests.prepare

    def test_signed_initialized_list_repeats_mixes_and_denies_writes_without_scanning(self):
        self.prepare();engine=self.app.engine;digest=engine.project.sha256
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}])
        before=copy.deepcopy(self.app.state());requested=(23,13,22,23,24)
        response=self.signed(4,bytes.fromhex('030220702401')+struct.pack('<6H',5,*requested))
        fields=decode_attribute_list(response,requested,0x70,include_payloads=True)['attributes']
        self.assertEqual([row['status'] for row in fields],[0,0,0,0,20])
        self.assertEqual([row['data_hex'] for row in fields[:4]],['00'*4,'00'*8,'00'*4,'00'*4])
        self.assertEqual(fields[0],fields[3])
        for sequence,number in enumerate((22,23),5):
            self.assertEqual(self.signed(sequence,bytes.fromhex('10032070240130')+bytes((number,))+bytes(4))[2],15)
        for key in ('tags','routines','tasks','scan','ms','controller'):
            self.assertEqual(self.app.state()[key],before[key])
        info=self.app.state()['connectivity']['task_aoi_stack']
        self.assertEqual(info['tasks_available'],1)


if __name__=='__main__':unittest.main()
