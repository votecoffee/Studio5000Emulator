"""Unassigned mains execute no stored subroutine; explicit missing names block."""
import base64
import copy
import struct
import unittest
from xml.etree import ElementTree as E

from logixlab.model import ModelError
from logixlab.runtime import Engine
from logixlab.native_routines import NativeRoutines
from logixlab.native_symbols import NativeSymbols
from logixlab.native_tasks import NativeTasks
from tools.collection_inventory import decode_attribute_list
from tools.upload_inventory import logical_path
from test_ethernetip import Client
import test_runtime as runtime
import test_empty_programs as empty


def unassign(root):
    program=root.find('./Controller/Programs/Program')
    program.attrib.pop('MainRoutineName',None)
    for key,value in (('TestEdits','false'),('UseAsFolder','false'),('Disabled','false'),
                      ('SynchronizeRedundancyDataAfterExecution','true')):program.set(key,value)


class UnassignedMainTests(unittest.TestCase):
    setUp=runtime.RuntimeTests.setUp
    engine=runtime.RuntimeTests.engine

    def test_scans_advance_without_running_stored_routines_or_main_timings(self):
        engine=self.engine(['MOV(987,SpeedCommand);'],mutate=unassign)
        self.assertEqual(engine.blockers,[]);self.assertEqual(engine.entries,[])
        self.assertEqual(len(engine.project.routines),2)
        before=copy.deepcopy(engine.memory.values);engine.enter_run()
        for _ in range(3):engine.step(10)
        self.assertEqual(engine.memory.values,before)
        self.assertEqual((engine.scan_count,engine.time_ms),(3,30));self.assertEqual(engine.trace,[])
        info=engine.program_timing_description()
        self.assertEqual(info['successful_program_executions'],0)
        self.assertEqual(info['empty_programs_available'],0);self.assertEqual(info['unassigned_main_programs_available'],1)
        self.assertEqual(engine.program_timing_attributes('MainProgram',source_sha256=engine.project.sha256),{2:bytes(4),3:bytes(4)})
        harness=Engine(engine.project,'routine','MainProgram/MainRoutine')
        self.assertEqual(harness.blockers,[]);harness.step();self.assertEqual(harness.memory.read('SpeedCommand'),987)

    def test_prescan_still_visits_stored_routines_without_running_them_each_scan(self):
        engine=self.engine(['XIC(StartPB)OTE(MotorRunning);'],mutate=unassign)
        self.assertEqual(engine.blockers,[])
        engine.memory.write('MotorRunning',True);engine.enter_run()
        self.assertFalse(engine.memory.read('MotorRunning'))
        engine.memory.write('MotorRunning',True);engine.step()
        self.assertTrue(engine.memory.read('MotorRunning'))

    def test_mixed_schedule_runs_only_the_assigned_main(self):
        def mutate(root):
            original=root.find('./Controller/Programs/Program');worker=copy.deepcopy(original)
            worker.set('Name','Worker');root.find('./Controller/Programs').append(worker)
            E.SubElement(root.find('./Controller/Tasks/Task/ScheduledPrograms'),'ScheduledProgram',Name='Worker')
            unassign(root)
        engine=self.engine(['ADD(SpeedCommand,1,SpeedCommand);'],mutate=mutate)
        self.assertEqual(engine.blockers,[]);self.assertEqual(engine.entries,['worker/mainroutine'])
        before=engine.memory.read('SpeedCommand');engine.step()
        self.assertEqual(engine.memory.read('SpeedCommand'),before+1)
        self.assertEqual(engine.program_timing_description()['successful_program_executions'],1)

    def test_incomplete_hidden_ambiguous_and_named_missing_main_are_not_skipped(self):
        for kind in ('named','fault','context','folder','missing-folder','missing-tests','tested','disabled-missing','alias','namespace','protected','signature','root-signature','unknown-routine','ST','unsupported'):
            self.root=E.parse(runtime.SAMPLE).getroot()
            def mutate(root):
                unassign(root);p=root.find('./Controller/Programs/Program');routine=p.find('./Routines/Routine')
                if kind=='named':p.set('MainRoutineName','Missing')
                elif kind=='fault':p.set('FaultRoutineName','Missing')
                elif kind=='context':root.set('ContainsContext','true')
                elif kind=='folder':p.set('UseAsFolder','true')
                elif kind=='missing-folder':p.attrib.pop('UseAsFolder')
                elif kind=='missing-tests':p.attrib.pop('TestEdits')
                elif kind=='tested':p.set('TestEdits','true')
                elif kind=='disabled-missing':p.attrib.pop('Disabled')
                elif kind=='alias':p.set('mainroutinename','Hidden')
                elif kind=='namespace':p.set('{test}MainRoutineName','Hidden')
                elif kind=='protected':routine.set('SourceProtection','opaque')
                elif kind=='signature':routine.set('Signature','unknown')
                elif kind=='root-signature':root.set('Signature','unknown')
                elif kind=='unknown-routine':routine.set('VendorData','unknown')
                elif kind=='ST':routine.set('Type','ST');routine.find('RLLContent').tag='STContent'
                else:routine.find('./RLLContent/Rung/Text').text='UNSUPPORTED();'
            engine=self.engine(['NOP();'],mutate=mutate)
            with self.subTest(kind=kind):
                self.assertTrue(engine.blockers)
                with self.assertRaises(ModelError):engine.step()
                if kind!='unsupported':self.assertFalse(engine.project.program_diagnostics.has_no_main('MainProgram',source_sha256=engine.project.sha256))

    def test_null_main_reference_requires_matching_complete_routine_inventory(self):
        engine=self.engine(['NOP();'],mutate=unassign);project=engine.project;space=engine.runtime_references
        values=space.program_attributes(project,'MainProgram');self.assertEqual(values[5],bytes(4))
        address=int.from_bytes(values[16],'little');self.assertIs(space.resolve(project,address,'program'),project.programs['MainProgram'])
        self.assertFalse(project.program_diagnostics.is_empty('MainProgram',source_sha256=project.sha256))
        self.assertTrue(project.program_diagnostics.has_no_main('MAINPROGRAM',source_sha256=project.sha256))
        self.assertFalse(project.program_diagnostics.has_no_main('MainProgram',source_sha256='b'*64))
        extra=copy.deepcopy(project.routines['mainprogram/mainroutine']);extra.name='Extra';project.routines['mainprogram/extra']=extra
        self.assertEqual(space.program_attributes(project,'MainProgram'),{})
        del project.routines['mainprogram/extra'];project.programs['MainProgram']['main']='Missing'
        self.assertEqual(space.program_attributes(project,'MainProgram'),{})


class UnassignedMainWireTests(unittest.TestCase):
    setUp=empty.EmptyProgramWireTests.setUp
    tearDown=empty.EmptyProgramWireTests.tearDown
    cip=empty.EmptyProgramWireTests.cip
    begin=empty.EmptyProgramWireTests.begin
    signed=empty.EmptyProgramWireTests.signed
    bind=empty.EmptyProgramWireTests.bind
    prepare=empty.EmptyProgramWireTests.prepare

    def test_signed_program_null_main_and_stored_routine_metadata_remain_distinct(self):
        root=E.parse(self.app.engine.project.path).getroot();unassign(root)
        self.app.command('load',{'name':'unassigned.L5X','content':base64.b64encode(E.tostring(root)).decode()})
        self.client.close();self.client=Client(self.endpoint.port);self.client.register();self.prepare()
        project=self.app.engine.project;digest=project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[dict(name='MainProgram',instance=10)])
        names=project.executable_configuration.routine_names('MainProgram',source_sha256=digest)
        self.app.native_routines=NativeRoutines('a'*64,digest,[dict(program='MainProgram',name=name,program_instance=10,instance=7+i,type_word=0x7ff) for i,name in enumerate(names)])
        self.app.native_tasks=NativeTasks('a'*64,digest,[dict(name='MainTask',instance=77)])
        before=copy.deepcopy(self.app.state());order=(1,2,3,5,7,9,11,13,15,16,19,20,21,22,24,25,26,27,29,30,31,32)
        path=logical_path(0x68,10);raw=self.signed(4,bytes((3,len(path)//2))+path+struct.pack('<23H',22,*order))
        fields=decode_attribute_list(raw,order,0x68,include_payloads=True)['attributes']
        self.assertEqual([(row['attribute'],row['status']) for row in fields if row['status']],[])
        self.assertEqual(next(row['data_hex'] for row in fields if row['attribute']==5),'00000000')
        path=logical_path(0x6d,7,program=10);order=(1,2,8,9,24,25)
        raw=self.signed(5,bytes((3,len(path)//2))+path+struct.pack('<7H',6,*order))
        fields=decode_attribute_list(raw,order,0x6d,include_payloads=True)['attributes']
        self.assertEqual([(row['attribute'],row['status']) for row in fields if row['status']],[])
        self.assertEqual(next(row['data_hex'] for row in fields if row['attribute']==24),'02000000')
        after=self.app.state()
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(after[key],before[key])


if __name__=='__main__':unittest.main()
