"""Program-to-Run initialization is separate from ordinary scans and imports."""
import base64
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine
from logixlab.server import Application
import test_native_session as native_tests
from logixlab.native_project import NativeProjectIdentity
from test_programming_lease import ACQUIRE
from test_controller_mode import wait_for

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def fixture(folder):
    root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot()
    tags=root.find('./Controller/Tags')
    for name in ('RetainedTimer','OffDelay'):
        timer=copy.deepcopy(tags.find("Tag[@Name='StartDelay']"))
        timer.set('Name',name);tags.append(timer)
    content=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent')
    content.clear()
    for index,text in enumerate((
            'XIC(S:FS)ADD(DisplayedPartCount,1,DisplayedPartCount);',
            'XIC(StartPB)OTE(MotorRunning);',
            'XIC(StartPB)ONS(SensorMemory)OTE(PartPulse);',
            'XIC(StartPB)CTU(Parts,?,?);',
            'XIC(StartPB)TON(StartDelay,?,?);',
            'XIC(StartPB)RTO(RetainedTimer,?,?);',
            'XIC(StartPB)TOF(OffDelay,?,?);',
            'XIC(StartPB)OTL(RunLatch);')):
        rung=E.SubElement(content,'Rung',Number=str(index),Type='N')
        E.SubElement(rung,'Text').text=text
    path=Path(folder)/'RunEntry.L5X';E.ElementTree(root).write(path,encoding='utf-8')
    return path


class RunEntryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=fixture(self.tmp.name)

    def test_import_preview_retains_saved_values_and_aoi_initializes_once(self):
        root=E.parse(SAMPLES/'AOILab.L5X').getroot()
        body=root.find("./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name='LabAccumulator']/Routines/Routine[@Name='Prescan']/RLLContent/Rung/Text")
        body.text='ADD(Shared,1,Shared)CLR(Count)MOV(Shared,Total);'
        path=Path(self.tmp.name)/'AOI.L5X';E.ElementTree(root).write(path,encoding='utf-8')
        e=Engine(Project(path),defer_prescan=True)
        self.assertEqual(e.blockers,[])
        self.assertEqual(e.memory.values,e.project.initial)
        self.assertEqual(e.prescan_count,0)
        initial=e.memory.read('SharedA')
        e.enter_run()
        self.assertEqual(e.memory.read('SharedA'),initial+1)
        self.assertEqual(e.memory.read('TotalA'),initial+1)
        self.assertEqual(e.prescan_count,1)
        e.enter_run()
        self.assertEqual(e.memory.read('SharedA'),initial+2)
        self.assertEqual(e.prescan_count,2)

    def test_each_run_rearms_first_scan_and_suppresses_ons_and_counter_false_edges(self):
        e=Engine(Project(self.path),defer_prescan=True)
        e.memory.write('StartPB',True)
        for count in range(1,4):
            e.memory.write('SensorMemory',False);e.memory.write('Parts.CU',False)
            before=(e.scan_count,e.time_ms)
            e.enter_run()
            self.assertEqual((e.scan_count,e.time_ms),before)
            self.assertTrue(e.memory.first_scan)
            self.assertTrue(e.memory.read('SensorMemory'));self.assertTrue(e.memory.read('Parts.CU'))
            self.assertFalse(e.memory.read('MotorRunning'))
            e.step(10)
            self.assertFalse(e.memory.first_scan)
            self.assertEqual(e.memory.read('DisplayedPartCount'),count)
            self.assertFalse(e.memory.read('PartPulse'))
            self.assertEqual(e.memory.read('Parts.ACC'),0)
            e.step(10)
            self.assertEqual(e.memory.read('DisplayedPartCount'),count)
        self.assertEqual(e.prescan_count,3)

    def test_prescan_resets_nonretentive_fields_and_retains_latch_counter_and_rto(self):
        e=Engine(Project(self.path),defer_prescan=True)
        e.memory.write('MotorRunning',True);e.memory.write('RunLatch',True)
        e.memory.write('Parts.ACC',3)
        for timer in ('StartDelay','OffDelay','RetainedTimer'):
            for field,value in (('EN',True),('TT',True),('DN',True),('ACC',23)):
                e.memory.write(timer+'.'+field,value)
        e.enter_run()
        self.assertFalse(e.memory.read('MotorRunning'));self.assertTrue(e.memory.read('RunLatch'))
        self.assertEqual(e.memory.read('Parts.ACC'),3)
        for timer in ('StartDelay','OffDelay','RetainedTimer'):
            self.assertFalse(e.memory.read(timer+'.EN'));self.assertFalse(e.memory.read(timer+'.TT'))
            self.assertEqual(e.memory.read(timer+'.PRE'),1000)
            self.assertEqual(e.memory.read(timer+'.ACC'),23 if timer=='RetainedTimer' else 0)
            self.assertEqual(e.memory.read(timer+'.DN'),timer=='RetainedTimer')

    def test_run_entry_has_a_fresh_budget_and_clears_timer_history_without_advancing_time(self):
        e=Engine(Project(self.path),defer_prescan=True)
        e.step();e.step()
        self.assertTrue(e.last_timer)
        e.budget=0
        before=(e.scan_count,e.time_ms,copy.deepcopy(e.changes))
        e.enter_run()
        self.assertEqual((e.scan_count,e.time_ms,e.changes),before)
        self.assertEqual(e.last_timer,{})
        self.assertEqual(e.trace,[])
        self.assertGreater(e.budget,0)

    def test_failed_prescan_restores_memory_context_time_and_pending_first_scan(self):
        e=Engine(Project(self.path),defer_prescan=True);e.step()
        original=e._prescan
        before=copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.last_timer,e.trace,e.memory.first_scan,e.budget,e.scan_count,e.time_ms))
        def fail():
            original();e.memory.write('RunLatch',True)
            e.memory.frames['broken']={};e.addons.instances['broken']={}
            raise RuntimeError('Synthetic prescan failure')
        with patch.object(e,'_prescan',side_effect=fail),self.assertRaisesRegex(ModelError,'Prescan rolled back'):
            e.enter_run()
        self.assertEqual((e.memory.values,e.memory.frames,e.addons.instances,e.last_timer,e.trace,e.memory.first_scan,e.budget,e.scan_count,e.time_ms),before)
        self.assertEqual(e.prescan_count,1)
        self.assertIn('Synthetic prescan failure',e.fault)

    def test_preview_reports_invalid_prescan_without_initializing_values(self):
        e=Engine(Project(self.path),defer_prescan=True)
        original=Engine._prescan
        def fail(obj):original(obj);raise ModelError('Initialization failed')
        with patch.object(Engine,'_prescan',fail):broken=Engine(e.project,defer_prescan=True)
        self.assertTrue(any('Prescan:' in item for item in broken.blockers))
        self.assertEqual(broken.memory.values,broken.project.initial)
        self.assertEqual(broken.prescan_count,0)
        self.assertFalse(broken.fault)

    def test_manual_step_initializes_once_and_run_after_stepping_initializes_again(self):
        e=Engine(Project(self.path),defer_prescan=True)
        e.step();e.step()
        self.assertEqual(e.prescan_count,1)
        self.assertEqual(e.memory.read('DisplayedPartCount'),1)
        e.enter_run();e.step()
        self.assertEqual(e.prescan_count,2)
        self.assertEqual(e.memory.read('DisplayedPartCount'),2)

    def test_project_prescans_uncalled_routines_while_harness_keeps_its_scope(self):
        root=E.parse(self.path).getroot()
        routines=root.find('./Controller/Programs/Program/Routines')
        routine=E.SubElement(routines,'Routine',Name='Uncalled',Type='RLL')
        rung=E.SubElement(E.SubElement(routine,'RLLContent'),'Rung',Number='0',Type='N')
        E.SubElement(rung,'Text').text='OTE(BatchComplete);'
        E.ElementTree(root).write(self.path,encoding='utf-8')
        for mode in ('project','routine'):
            e=Engine(Project(self.path),mode,'MainProgram/MainRoutine',defer_prescan=True)
            e.memory.write('BatchComplete',True);e.enter_run()
            self.assertEqual(e.memory.read('BatchComplete'),mode=='routine')

    def test_st_nonretentive_assignments_clear_on_each_run_even_in_false_branch(self):
        root=E.parse(self.path).getroot()
        routine=root.find('./Controller/Programs/Program/Routines/Routine')
        routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
        content=E.SubElement(routine,'STContent')
        E.SubElement(content,'Line',Number='0').text='IF StartPB THEN MotorRunning [:=] TRUE; END_IF; RunLatch := TRUE;'
        E.ElementTree(root).write(self.path,encoding='utf-8')
        e=Engine(Project(self.path),defer_prescan=True)
        self.assertEqual(e.blockers,[])
        for _ in range(2):
            e.memory.write('MotorRunning',True);e.memory.write('RunLatch',True)
            e.enter_run()
            self.assertFalse(e.memory.read('MotorRunning'))
            self.assertTrue(e.memory.read('RunLatch'))
            e.step()

    def test_aoi_prescan_arithmetic_failure_restores_copied_parameters_and_locals(self):
        root=E.parse(SAMPLES/'AOILab.L5X').getroot()
        body=root.find("./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition[@Name='LabAccumulator']/Routines/Routine[@Name='Prescan']/RLLContent/Rung/Text")
        body.text='MOV(42,Total)DIV(1,Step,Count);'
        path=Path(self.tmp.name)/'FaultingAOI.L5X';E.ElementTree(root).write(path,encoding='utf-8')
        e=Engine(Project(path),defer_prescan=True)
        self.assertEqual(e.blockers,[])
        e.enter_run();e.step()
        e.memory.write('StepA',0);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'Prescan rolled back'):e.enter_run()
        self.assertEqual(e.memory.values,before)
        self.assertEqual(e.prescan_count,1)

    def test_app_run_is_idempotent_but_program_run_initializes_again(self):
        app=Application(self.tmp.name);self.addCleanup(app.close)
        app.command('load',{'name':self.path.name,'content':base64.b64encode(self.path.read_bytes()).decode()})
        self.assertEqual(app.engine.memory.values,app.engine.project.initial)
        self.assertEqual(app.state()['controller']['prescan_count'],0)
        for count in range(1,4):
            app.command('controller-mode',{'mode':'Run','dt':10})
            wait_for(lambda:app.engine.memory.read('DisplayedPartCount')==count)
            app.command('controller-mode',{'mode':'Run','dt':20})
            self.assertEqual(app.state()['controller']['prescan_count'],count)
            self.assertFalse(app.engine.memory.first_scan)
            app.command('controller-mode',{'mode':'Program'})
            self.assertEqual(app.engine.memory.read('DisplayedPartCount'),count)

    def test_app_prescan_failure_never_reports_run_or_applies_device_inputs(self):
        app=Application(self.tmp.name);self.addCleanup(app.close);app.command('demo',{})
        app.command('device-io-configure',{'allow_writes':True})
        app.device_io.enqueue({'request_id':'startup','instance_id':app.instance_id,'project_generation':app.generation,
                               'writes':[{'tag':'StartPB','value':True}]})
        before=copy.deepcopy(app.engine.memory.values)
        def fail():app.engine.memory.write('StartPB',True);raise ModelError('Failed run entry')
        with patch.object(app.engine,'_prescan',side_effect=fail),self.assertRaises(ModelError):
            app.command('controller-mode',{'mode':'Run'})
        self.assertFalse(app.running);self.assertIsNone(app._scan_thread)
        self.assertEqual(app.engine.memory.values,before)
        self.assertEqual(app.state()['controller']['mode'],'Faulted')
        self.assertEqual(app.engine.scan_count,0);self.assertEqual(app.engine.prescan_count,0)
        self.assertEqual(app.device_io.receipt('startup')['status'],'queued')

    def test_initial_manual_step_does_not_drain_inputs_when_prescan_fails(self):
        app=Application(self.tmp.name);self.addCleanup(app.close);app.command('demo',{})
        app.command('device-io-configure',{'allow_writes':True})
        app.device_io.enqueue({'request_id':'startup','instance_id':app.instance_id,'project_generation':app.generation,
                               'writes':[{'tag':'StartPB','value':True}]})
        with patch.object(app.engine,'_prescan',side_effect=ModelError('Failed step initialization')):
            with self.assertRaises(ModelError):app.command('step',{})
        self.assertFalse(app.engine.memory.read('StartPB'))
        self.assertEqual(app.device_io.receipt('startup')['status'],'queued')
        self.assertEqual(app.engine.scan_count,0);self.assertEqual(app.engine.prescan_count,0)


class NativeRunEntryTests(unittest.TestCase):
    setUp=native_tests.NativeSessionTests.setUp
    tearDown=native_tests.NativeSessionTests.tearDown
    cip=native_tests.NativeSessionTests.cip
    begin=native_tests.NativeSessionTests.begin
    signed=native_tests.NativeSessionTests.signed
    bind=native_tests.NativeSessionTests.bind

    def test_native_start_uses_prescan_once_and_failed_reentry_reports_faulted(self):
        self.app.native_project_identity=NativeProjectIdentity('1'*64,self.app.engine.project.sha256,1,2,3,4,5,6)
        self.bind();self.signed(4,ACQUIRE)
        self.app.scan_interval_ms=60000
        self.assertEqual(self.signed(5,bytes.fromhex('0602208e2401'))[2],0)
        self.assertEqual(self.app.engine.prescan_count,1)
        self.assertTrue(self.app.engine.memory.first_scan)
        self.assertEqual(self.signed(6,bytes.fromhex('0602208e2401'))[2],0)
        self.assertEqual(self.app.engine.prescan_count,1)
        self.signed(7,bytes.fromhex('0702208e2401'))
        before=copy.deepcopy(self.app.engine.memory.values)
        def fail():self.app.engine.memory.write('StartPB',True);raise ModelError('Failed native prescan')
        with patch.object(self.app.engine,'_prescan',side_effect=fail):
            self.assertEqual(self.signed(8,bytes.fromhex('0602208e2401'))[2],0x0C)
        self.assertFalse(self.app.running)
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.cip(bytes.fromhex('0e03200124013005'))[4:],bytes.fromhex('5034'))
