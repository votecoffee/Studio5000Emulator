"""Explicit empty Programs scan without inventing a missing main Routine."""
import base64
import copy
import struct
import unittest
from xml.etree import ElementTree as E

import test_runtime as runtime
import test_programming_lease as leases
from test_ethernetip import Client
from logixlab.model import ModelError
from logixlab.native_routines import NativeRoutines
from logixlab.native_symbols import NativeSymbols
from logixlab.native_tasks import NativeTasks
from tools.collection_inventory import decode_attribute_list


def make_empty(root):
    program=root.find('./Controller/Programs/Program')
    program.attrib.pop('MainRoutineName',None)
    program.set('TestEdits','false');program.set('UseAsFolder','false')
    program.set('SynchronizeRedundancyDataAfterExecution','true')
    program.find('Routines').clear()


class EmptyProgramTests(unittest.TestCase):
    setUp=runtime.RuntimeTests.setUp
    engine=runtime.RuntimeTests.engine

    def test_empty_scheduled_program_scans_and_prescans_without_changing_values(self):
        engine=self.engine(mutate=make_empty);digest=engine.project.sha256
        self.assertEqual(engine.blockers,[]);self.assertEqual(engine.entries,[])
        before=copy.deepcopy(engine.memory.values);prescans=engine.prescan_count
        engine.enter_run()
        for _ in range(3):self.assertEqual(engine.step(10),[])
        self.assertEqual(engine.memory.values,before);self.assertEqual(engine.trace,[])
        self.assertEqual((engine.scan_count,engine.time_ms,engine.prescan_count),(3,30,prescans+1))
        self.assertEqual(engine.program_timing_attributes('MainProgram',source_sha256=digest),{2:bytes(4),3:bytes(4)})
        self.assertEqual(engine.program_timing_description()['successful_program_executions'],0)
        self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=digest),{20:bytes(44),21:bytes(44)})
        self.assertEqual(engine.program_status_attributes('MainProgram',source_sha256=digest,task_owner=7,idle=True),{1:bytes(2)})

    def test_source_proof_rejects_incomplete_hidden_or_noncanonical_empty_declarations(self):
        for kind in ('named-main','fault','missing-tests','tested','missing-folder','missing-disabled',
                     'missing-container','container-data','container-text','context','unknown-field','safety','protected','nested-edit'):
            self.root=E.parse(runtime.SAMPLE).getroot()
            def mutate(root):
                make_empty(root);p=root.find('./Controller/Programs/Program');section=p.find('Routines')
                if kind=='named-main':p.set('MainRoutineName','Missing')
                elif kind=='fault':p.set('FaultRoutineName','Missing')
                elif kind=='missing-tests':p.attrib.pop('TestEdits')
                elif kind=='tested':p.set('TestEdits','true')
                elif kind=='missing-folder':p.attrib.pop('UseAsFolder')
                elif kind=='missing-disabled':p.attrib.pop('Disabled')
                elif kind=='missing-container':p.remove(section)
                elif kind=='container-data':section.set('Unknown','data')
                elif kind=='container-text':section.text='unknown'
                elif kind=='context':root.set('ContainsContext','true')
                elif kind=='unknown-field':p.set('mainroutinename','hidden')
                elif kind=='safety':p.set('Class','Safety')
                elif kind=='nested-edit':p.find('Tags').set('TestEdits','true')
                else:section.set('SourceProtection','opaque')
            engine=self.engine(mutate=mutate)
            with self.subTest(kind=kind):
                self.assertTrue(engine.blockers)
                self.assertFalse(engine.project.program_diagnostics.is_empty('MainProgram',source_sha256=engine.project.sha256))
                self.assertEqual(engine.runtime_references.program_attributes(engine.project,'MainProgram'),{})

    def test_no_main_with_existing_routines_and_no_scheduled_programs_remain_blocked(self):
        engine=self.engine(mutate=lambda root:root.find('./Controller/Programs/Program').attrib.pop('MainRoutineName'))
        self.assertTrue(engine.blockers)
        self.root=E.parse(runtime.SAMPLE).getroot()
        def unschedule(root):
            make_empty(root);root.find('./Controller/Tasks/Task/ScheduledPrograms').clear()
        engine=self.engine(mutate=unschedule)
        self.assertIn('No scheduled main routine',engine.blockers)
        with self.assertRaises(ModelError):engine.step()

    def test_empty_and_executable_programs_share_one_scan_without_skipping_real_logic(self):
        def mutate(root):
            original=root.find('./Controller/Programs/Program');other=copy.deepcopy(original)
            other.set('Name','Worker');root.find('./Controller/Programs').append(other)
            E.SubElement(root.find('./Controller/Tasks/Task/ScheduledPrograms'),'ScheduledProgram',Name='Worker')
            make_empty(root)
        engine=self.engine(['ADD(SpeedCommand,1,SpeedCommand);'],mutate=mutate)
        self.assertEqual(engine.blockers,[]);self.assertEqual(engine.entries,['worker/mainroutine'])
        before=engine.memory.read('SpeedCommand');engine.step()
        self.assertEqual(engine.memory.read('SpeedCommand'),before+1)
        self.assertEqual(engine.program_timing_description()['successful_program_executions'],1)

    def test_empty_program_reference_is_backed_and_main_is_null_with_source_and_lifetime_guards(self):
        engine=self.engine(mutate=make_empty);project=engine.project;space=engine.runtime_references
        values=space.program_attributes(project,'MainProgram')
        self.assertEqual(values[5],bytes(4));address=int.from_bytes(values[16],'little')
        self.assertIs(space.resolve(project,address,'program'),project.programs['MainProgram'])
        self.assertIsNone(space.resolve(project,0,'routine'))
        self.assertEqual(space.program_attributes(project,'MainProgram'),values)
        self.assertFalse(project.program_diagnostics.is_empty('MainProgram',source_sha256='b'*64))
        project.programs['MainProgram']=copy.deepcopy(project.programs['MainProgram'])
        self.assertIsNone(space.resolve(project,address,'program'))
        self.assertNotEqual(space.program_attributes(project,'MainProgram')[16],values[16])
        project.programs['MainProgram']['main']='Missing'
        self.assertEqual(space.program_attributes(project,'MainProgram'),{})

    def test_empty_fault_history_still_withholds_normal_status_and_reset_recovers(self):
        engine=self.engine(mutate=make_empty);digest=engine.project.sha256
        engine.fault='unknown';engine.fault='';engine.step()
        self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=digest),{})
        self.assertEqual(engine.program_status_attributes('MainProgram',source_sha256=digest,task_owner=7,idle=True),{})
        self.assertTrue(engine.program_fault_description()['unclassified_fault_seen_since_reset'])
        fresh=type(engine)(engine.project)
        self.assertEqual(fresh.program_fault_attributes('MainProgram',source_sha256=digest),{20:bytes(44),21:bytes(44)})


class EmptyProgramWireTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare

    def test_complete_program_bulk_and_empty_routine_discovery_preserve_model(self):
        root=E.parse(self.app.engine.project.path).getroot();make_empty(root)
        self.app.command('load',{'name':'empty.L5X','content':base64.b64encode(E.tostring(root)).decode()})
        self.client.close();self.client=Client(self.endpoint.port);self.client.register();self.prepare()
        project=self.app.engine.project;digest=project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        self.app.native_routines=NativeRoutines('a'*64,digest,[])
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':77}])
        requested=(1,2,3,5,7,9,11,13,15,16,19,20,21,22,24,25,26,27,29,30,31,32)
        request=bytes.fromhex('030320682500b665')+struct.pack('<H',len(requested))+struct.pack('<22H',*requested)
        before=copy.deepcopy(self.app.state())
        response=self.signed(4,request);parsed=decode_attribute_list(response,requested,0x68,include_payloads=True)
        self.assertEqual(parsed['status'],0);self.assertTrue(all(row['status']==0 for row in parsed['attributes']))
        self.assertEqual(next(row['data_hex'] for row in parsed['attributes'] if row['attribute']==5),'00000000')
        self.assertEqual(self.signed(5,bytes.fromhex('4b0520682500b665206d2400')),bytes.fromhex('cb000000'))
        self.app.native_routines=NativeRoutines('b'*64,digest,[])
        self.assertEqual(self.signed(6,bytes.fromhex('0e0420682500b6653010'))[2],20)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])


if __name__=='__main__':unittest.main()
