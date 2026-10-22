"""Whole-Task measurements, successful-scan commits and backed read-only references."""
import copy
from dataclasses import FrozenInstanceError
import struct
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_runtime as runtime
import test_programming_lease as leases
import test_program_reservations as reservations
from logixlab.model import ModelError,Project
from logixlab.native_tasks import NativeTasks
from logixlab.native_symbols import NativeSymbols
from logixlab.task_runtime import TaskMeasurements
from tools.collection_inventory import decode_attribute_list


class TaskMeasurementTests(unittest.TestCase):
    setUp=runtime.RuntimeTests.setUp
    engine=runtime.RuntimeTests.engine

    def test_exact_units_initial_intervals_and_independent_overflow_withholding(self):
        empty=TaskMeasurements();self.assertEqual(empty.attributes(),{7:bytes(4),8:bytes(4),13:bytes(8),14:bytes(8),15:bytes(8)})
        first=empty.record(100,4250)
        self.assertEqual(first.attributes(),{7:struct.pack('<I',4),8:struct.pack('<I',4),14:bytes(8),15:bytes(8)})
        final=first.record(10000,14000).record(15000,16099)
        self.assertEqual(final.attributes(),{7:struct.pack('<I',4),8:struct.pack('<I',1),14:struct.pack('<Q',5),15:struct.pack('<Q',9)})
        huge=TaskMeasurements().record(0,0x100000000*1000)
        self.assertEqual(huge.attributes(),{14:bytes(8),15:bytes(8)})
        huge=huge.record(0x100000000*1000+1000,0x100000000*1000+2000)
        self.assertNotIn(7,huge.attributes());self.assertEqual(huge.attributes()[8],struct.pack('<I',1))
        self.assertEqual(int.from_bytes(huge.attributes()[15],'little'),0x100000001)
        with self.assertRaises(FrozenInstanceError):final.executions=0
        for pair in ((True,1),(-1,0),(2,1),(0,None)):
            with self.subTest(pair=pair),self.assertRaises(ValueError):first.record(*pair)
        with self.assertRaises(ValueError):first.record(99,100)

    @staticmethod
    def second_program(root):
        programs=root.find('./Controller/Programs');other=copy.deepcopy(programs[0]);other.set('Name','Worker');programs.append(other)
        E.SubElement(root.find('./Controller/Tasks/Task/ScheduledPrograms'),'ScheduledProgram',Name='Worker')

    def test_whole_task_covers_all_programs_and_prescan_does_not_record_a_scan(self):
        engine=self.engine(['ADD(SpeedCommand,1,SpeedCommand);'],mutate=self.second_program);digest=engine.project.sha256
        before=engine.memory.read('SpeedCommand')
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(1000,16099,51000,54000)) as clock:
            with patch('logixlab.runtime.perf_counter_ns',side_effect=(2000,5000,6000,10000,52000,52500,53000,53500)),patch('logixlab.wall_clock.time.time_ns',return_value=123456789999):
                engine.enter_run();self.assertEqual(clock.call_count,0)
                engine.step();engine.step()
        self.assertEqual(engine.memory.read('SpeedCommand'),before+4)
        self.assertEqual(engine.task_measurement_attributes('MAINTASK',source_sha256=digest),
            {7:struct.pack('<I',15),8:struct.pack('<I',3),13:struct.pack('<q',123456789),14:struct.pack('<Q',50),15:struct.pack('<Q',50)})
        self.assertEqual(engine.task_measurement_description()['successful_task_executions'],2)
        self.assertEqual(engine.program_timing_attributes('MainProgram',source_sha256=digest)[3],struct.pack('<I',3))

    def test_failed_later_program_rolls_back_task_and_program_counters_and_next_interval(self):
        engine=self.engine(['ADD(SpeedCommand,1,SpeedCommand);'],mutate=self.second_program)
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(1000,5000)),patch('logixlab.wall_clock.time.time_ns',return_value=123456789000):engine.step()
        before=copy.deepcopy(engine.memory.values);task=engine._task_measurements;programs=dict(engine._program_timings);run=engine._routine
        def fail(key,depth):
            if key.startswith('worker/'):raise ModelError('worker fault')
            return run(key,depth)
        with patch.object(engine,'_routine',side_effect=fail),patch('logixlab.task_runtime.perf_counter_ns',return_value=10000):
            with self.assertRaisesRegex(ModelError,'Scan rolled back'):engine.step()
        self.assertEqual(engine._task_measurements,task);self.assertEqual(engine._program_timings,programs)
        self.assertEqual(engine.memory.values,before);self.assertEqual((engine.scan_count,engine.time_ms),(1,10))
        with patch('logixlab.task_runtime.perf_counter_ns',side_effect=(30000,33000)):engine.step()
        self.assertEqual(engine._task_measurements.minimum_interval_ns,29000)
        fresh=type(engine)(engine.project);self.assertEqual(fresh._task_measurements,TaskMeasurements())

    def test_start_time_uses_wallclock_epoch_at_start_and_accepts_clock_adjustments(self):
        from logixlab.wall_clock import WallClock
        engine=self.engine(['NOP();']);digest=engine.project.sha256
        self.assertEqual(engine.task_measurement_attributes('MainTask',source_sha256=digest)[13],bytes(8))
        self.assertTrue(engine.task_measurement_description()['start_time_available'])
        self.assertFalse(engine.task_measurement_description()['start_time_measured'])
        with patch('logixlab.wall_clock.time.time_ns',side_effect=(1_750_000_000_123_456_999,1_749_999_999_999_999_000)) as clock:
            engine.enter_run();self.assertEqual(clock.call_count,0)
            engine.step();self.assertEqual(clock.call_count,1)
            stamp=engine.task_measurement_attributes('MainTask',source_sha256=digest)[13]
            self.assertEqual(stamp,struct.pack('<q',1_750_000_000_123_456))
            self.assertEqual(WallClock().attributes(read_time=True)[6],struct.pack('<q',1_749_999_999_999_999))
        with patch('logixlab.wall_clock.time.time_ns',return_value=1000):engine.step()
        self.assertEqual(engine._task_measurements.start_time_us,1)
        self.assertEqual(engine.scan_count,2)
        self.assertTrue(engine.task_measurement_description()['start_time_available'])

    def test_invalid_clock_withholds_only_start_time_after_a_successful_scan(self):
        engine=self.engine(['NOP();']);digest=engine.project.sha256
        for invalid in (-1,True,None,1.5,'1',0x8000000000000000*1000,OSError('clock unavailable'),OverflowError('range'),ValueError('invalid')):
            with patch('logixlab.wall_clock.time.time_ns',return_value=1000):engine.step()
            self.assertEqual(engine._task_measurements.attributes()[13],struct.pack('<q',1))
            kwargs={'side_effect':invalid} if isinstance(invalid,Exception) else {'return_value':invalid}
            with self.subTest(invalid=invalid),patch('logixlab.wall_clock.time.time_ns',**kwargs):
                engine.step();self.assertNotIn(13,engine._task_measurements.attributes())
                self.assertEqual(set(engine._task_measurements.attributes()),{7,8,14,15})
                self.assertFalse(engine.task_measurement_description()['start_time_available'])
        self.assertEqual(engine.scan_count,18);self.assertFalse(engine.fault)

    def test_start_time_record_boundaries_and_reset_never_reuse_original_timestamps(self):
        for value in (0,0x7FFFFFFFFFFFFFFF):
            record=TaskMeasurements().record(0,1,start_time_us=value)
            self.assertEqual(record.attributes()[13],struct.pack('<q',value))
        for invalid in (-1,True,1.5,'1',0x8000000000000000):
            with self.subTest(value=invalid),self.assertRaises(ValueError):TaskMeasurements().record(0,1,start_time_us=invalid)
        with self.assertRaises(ValueError):TaskMeasurements(start_time_us=0)
        engine=self.engine(['NOP();'])
        with patch('logixlab.wall_clock.time.time_ns',return_value=1000):engine.step()
        fresh=type(engine)(engine.project)
        self.assertEqual(fresh.task_measurement_attributes('MainTask',source_sha256=fresh.project.sha256)[13],bytes(8))
        self.assertFalse(fresh.task_measurement_description()['start_time_measured'])
        self.assertEqual(fresh._task_measurements,TaskMeasurements())

    def test_source_task_mode_and_configuration_guards_withhold_measurements(self):
        for kind in ('routine','inhibited','unknown','missing-priority','missing-output','bad-schedule','context'):
            self.root=E.parse(runtime.SAMPLE).getroot()
            def mutate(root):
                task=root.find('./Controller/Tasks/Task')
                if kind=='inhibited':task.set('InhibitTask','true')
                elif kind=='unknown':task.set('OpaqueRuntime','unknown')
                elif kind=='missing-priority':task.attrib.pop('Priority')
                elif kind=='missing-output':task.attrib.pop('DisableUpdateOutputs')
                elif kind=='bad-schedule':task.find('ScheduledPrograms').append(copy.deepcopy(task.find('./ScheduledPrograms/ScheduledProgram')))
                elif kind=='context':root.set('ContainsContext','true')
            engine=self.engine(['NOP();'],mutate=mutate,mode='routine' if kind=='routine' else 'project',routine='MainProgram/MainRoutine')
            with self.subTest(kind=kind):self.assertEqual(engine.task_measurement_attributes('MainTask',source_sha256=engine.project.sha256),{})
            with self.subTest(status_kind=kind):self.assertEqual(engine.task_status_attributes('MainTask',source_sha256=engine.project.sha256),{})
        self.root=E.parse(runtime.SAMPLE).getroot();engine=self.engine(['NOP();'])
        self.assertEqual(engine.task_measurement_attributes('MainTask',source_sha256='f'*64),{})
        self.assertEqual(engine.task_measurement_attributes('Missing',source_sha256=engine.project.sha256),{})

    def test_task_reference_resolves_actual_object_and_replacement_revokes_the_old_one(self):
        engine=self.engine(['NOP();']);project=engine.project;space=engine.runtime_references
        values=space.task_attributes(project,'MainTask');address=int.from_bytes(values[11],'little')
        self.assertIs(space.resolve(project,address,'task'),project.tasks[0])
        self.assertEqual(space.reference(project,'task','MainTask'),address)
        self.assertEqual(values,space.task_attributes(project,'MainTask'))
        self.assertIsNone(space.resolve(project,address,'program'))
        project.tasks[0]=copy.deepcopy(project.tasks[0])
        self.assertIsNone(space.resolve(project,address,'task'))
        self.assertNotEqual(space.task_attributes(project,'MainTask'),values)
        self.assertEqual(space.task_attributes(project,'Missing'),{})
        self.assertEqual(space.task_attributes(Project(project.path),'MainTask'),{})


class TaskMeasurementWireTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare

    def test_signed_start_time_reads_are_committed_repeated_and_read_only(self):
        self.prepare();engine=self.app.engine;digest=engine.project.sha256
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}])
        self.assertEqual(self.signed(4,bytes.fromhex('0e0320702401300d')),bytes.fromhex('8e000000')+bytes(8))
        with patch('logixlab.wall_clock.time.time_ns',return_value=1_750_000_000_123_456_999):engine.step()
        before=copy.deepcopy(self.app.state());requested=(13,24,13,25)
        with patch('logixlab.wall_clock.time.time_ns',side_effect=AssertionError('Read must not resample Task start')):
            response=self.signed(5,bytes.fromhex('030220702401')+struct.pack('<5H',4,*requested))
            fields=decode_attribute_list(response,requested,0x70,include_payloads=True)['attributes']
            self.assertEqual([row['status'] for row in fields],[0,20,0,20])
            self.assertEqual(fields[0]['data_hex'],struct.pack('<q',1_750_000_000_123_456).hex())
            self.assertEqual(fields[0],fields[2])
            self.assertEqual(self.signed(6,bytes.fromhex('0e0320702401300d')),bytes.fromhex('8e000000')+bytes.fromhex(fields[0]['data_hex']))
            self.assertEqual(self.signed(7,bytes.fromhex('100320702401300d')+bytes(8))[2],15)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])
        engine.project.tasks[0]=copy.deepcopy(engine.project.tasks[0])
        self.assertEqual(self.signed(8,bytes.fromhex('0e0320702401300d'))[2],20)

    def test_signed_mixed_reads_resolve_task_reference_and_keep_unsupported_fields_and_writes_distinct(self):
        self.prepare();engine=self.app.engine;digest=engine.project.sha256
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}])
        before=copy.deepcopy(self.app.state());requested=(7,8,11,14,15,16)
        response=self.signed(4,bytes.fromhex('030220702401')+struct.pack('<7H',6,*requested))
        fields=decode_attribute_list(response,requested,0x70,include_payloads=True)['attributes']
        self.assertEqual([row['status'] for row in fields],[0,0,0,0,0,0])
        self.assertEqual(fields[-1]['data_hex'],'00000000')
        address=int.from_bytes(bytes.fromhex(fields[2]['data_hex']),'little')
        self.assertIs(engine.runtime_references.resolve(engine.project,address,'task'),engine.project.tasks[0])
        self.assertEqual(self.signed(5,bytes.fromhex('0e0320702401300b')),bytes.fromhex('8e000000')+struct.pack('<I',address))
        self.assertEqual(self.signed(6,bytes.fromhex('100320702401300701000000'))[2],15)
        self.assertEqual(self.signed(7,bytes.fromhex('0e03207024013003')),bytes.fromhex('8e00000000000000'))
        self.app.native_tasks=NativeTasks('b'*64,digest,[{'name':'MainTask','instance':1}])
        self.assertEqual(self.signed(8,bytes.fromhex('0e0320702401300b'))[2],20)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_programming_inhibit_withholds_task_reference_until_cleanup(self):
        self.prepare();digest=self.app.engine.project.sha256
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':1}])
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        self.assertEqual(self.signed(4,bytes.fromhex('0e0320702401300b'))[2],0)
        self.assertEqual(self.signed(5,reservations.CONTROLLER_ACQUIRE)[2],0)
        self.assertEqual(self.signed(6,reservations.message(program=26038))[2],0)
        self.assertEqual(self.signed(7,bytes.fromhex('0e0320702401300b'))[2],20)
        self.assertEqual(self.signed(8,reservations.message(0x4C,program=26038,payload=b''))[2],0)
        self.assertEqual(self.signed(9,reservations.CONTROLLER_RELEASE)[2],0)
        self.assertEqual(self.signed(10,bytes.fromhex('0e0320702401300b'))[2],0)


if __name__=='__main__':unittest.main()
