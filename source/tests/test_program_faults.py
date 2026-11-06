"""Clean model fault records never survive an unclassified fault as zeros."""
import base64
import copy
import unittest
from xml.etree import ElementTree as ET
from unittest.mock import patch
import test_runtime as fixtures
from logixlab.model import ModelError


def ladder_fault_fixture(root, *, clear=True, handler_tail=None, main_tail=None, destination=False):
    controller = root.find('Controller')
    program = controller.find('./Programs/Program')
    program.set('FaultRoutineName','RecoverMove')
    tags = controller.find('Tags')
    for name, size in (('LabValues',2), ('FaultWords',11)):
        tag = ET.SubElement(tags,'Tag',Name=name,DataType='DINT',Dimensions=str(size),TagType='Base')
        data = ET.SubElement(tag,'Data',Format='Decorated')
        array = ET.SubElement(data,'Array',DataType='DINT',Dimensions=str(size))
        for index in range(size):
            ET.SubElement(array,'Element',Index=f'[{index}]',Value=str(12+index) if name=='LabValues' else '0')
    for name, dtype, value in (('LabIndex','DINT','0'), ('CapturedFault','DINT','0'), ('FaultWitness','BOOL','1')):
        tag = ET.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base')
        ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=value)

    def rungs(content, lines):
        content.clear()
        for index, line in enumerate(lines):
            rung = ET.SubElement(content,'Rung',Number=str(index),Type='N')
            ET.SubElement(rung,'Text').text = line

    routines = program.find('Routines')
    move = 'MOV(93,LabValues[LabIndex])' if destination else 'MOV(LabValues[LabIndex],SpeedCommand)'
    rungs(routines.find('./Routine/RLLContent'),
          ['XIC(StartPB)'+move+'ADD(SpeedCommand,1,SpeedCommand);','MOV(91,SpeedSetpoint);']
          + ([main_tail] if main_tail else []))
    recovery = ET.SubElement(routines,'Routine',Name='RecoverMove',Type='RLL')
    handler = ['OTE(FaultWitness);', 'GSV(Program,THIS,MajorFaultRecord,FaultWords[0]);',
               'MOV(FaultWords[2],CapturedFault);']
    if clear:
        handler.append('EQU(CapturedFault,1310724)CLR(FaultWords[2])'
                       'SSV(Program,MainProgram,MajorFaultRecord,FaultWords[0]);')
    rungs(ET.SubElement(recovery,'RLLContent'),handler+([handler_tail] if handler_tail else []))


def ladder_fault_load(**options):
    root = ET.parse(fixtures.SAMPLE).getroot()
    root.set('TargetName','LadderFaultLab')
    root.find('Controller').set('Name','LadderFaultLab')
    ladder_fault_fixture(root, **options)
    return {'name':'LadderProgramFault.L5X', 'content':base64.b64encode(ET.tostring(root)).decode()}


class ProgramFaultTests(unittest.TestCase):
    setUp=fixtures.RuntimeTests.setUp
    engine=fixtures.RuntimeTests.engine

    def test_normal_status_needs_real_owner_clean_whole_project_and_idle_untested_source(self):
        engine=self.engine(['NOP();'],mutate=lambda root:root.find('./Controller/Programs/Program').set('TestEdits','false'))
        args=dict(source_sha256=engine.project.sha256,task_owner=7,idle=True)
        self.assertEqual(engine.program_status_attributes('MainProgram',**args),{1:bytes(2)})
        for update in ({'task_owner':None},{'task_owner':0},{'task_owner':True},{'task_owner':65536},
                       {'idle':False},{'source_sha256':'a'*64}):
            self.assertEqual(engine.program_status_attributes('MainProgram',**{**args,**update}),{})
        engine.fault='unknown';engine.fault=''
        self.assertEqual(engine.program_status_attributes('MainProgram',**args),{})

    def test_clean_model_records_are_44_bytes_and_reads_do_not_scan(self):
        engine=self.engine(['NOP();']);digest=engine.project.sha256
        self.assertEqual(engine.program_fault_attributes('MAINPROGRAM',source_sha256=digest),{20:bytes(44),21:bytes(44)})
        self.assertEqual(engine.scan_count,0)
        engine.step();self.assertEqual(engine.program_fault_description()['known_clean_programs'],1)
        for name,sha in ((None,digest),('Missing',digest),('MainProgram','b'*64)):
            self.assertEqual(engine.program_fault_attributes(name,source_sha256=sha),{})

    def test_fault_history_stays_unknown_after_later_success_until_new_engine(self):
        engine=self.engine(['DIV(SpeedCommand,SpeedSetpoint,SpeedCommand);']);digest=engine.project.sha256
        engine.memory.write('SpeedSetpoint',0)
        with self.assertRaises(ModelError):engine.step()
        self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=digest),{})
        engine.memory.write('SpeedSetpoint',1);engine.step();self.assertEqual(engine.fault,'')
        self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=digest),{})
        self.assertTrue(engine.program_fault_description()['unclassified_fault_seen_since_reset'])
        reset=self.engine(['NOP();'])
        self.assertEqual(reset.program_fault_attributes('MainProgram',source_sha256=reset.project.sha256),{20:bytes(44),21:bytes(44)})

    def test_prescan_and_external_worker_fault_assignments_invalidate_clean_history(self):
        engine=self.engine(['NOP();'])
        with patch.object(engine,'_prescan',side_effect=ModelError('prescan failure')):
            with self.assertRaises(ModelError):engine.enter_run()
        engine.fault='';self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=engine.project.sha256),{})
        engine=self.engine(['NOP();']);engine.fault='external input failure';engine.fault=''
        self.assertEqual(engine.program_fault_description()['known_clean_programs'],0)

    def test_unexecutable_disabled_and_routine_harness_states_have_no_native_clean_record(self):
        for mode in ('blocked','disabled','routine'):
            def mutate(root):
                if mode=='disabled':root.find('./Controller/Programs/Program').set('Disabled','true')
            engine=self.engine(['Unsupported();'] if mode=='blocked' else ['NOP();'],mutate=mutate,
                mode='routine' if mode=='routine' else 'project',routine='MainProgram/MainRoutine')
            self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=engine.project.sha256),{})

    def test_empty_exception_message_still_invalidates_fault_record_history(self):
        engine=self.engine(['NOP();'])
        with patch.object(engine,'_routine',side_effect=ModelError('')):
            with self.assertRaises(ModelError):engine.step()
        self.assertEqual(engine.fault,'ModelError')
        self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=engine.project.sha256),{})

    def test_bounded_ladder_recovery_skips_move_and_continues_same_rung(self):
        for destination, index in ((False,2),(True,-1)):
            with self.subTest(destination=destination):
                self.setUp()
                engine = self.engine(mutate=lambda root:ladder_fault_fixture(root,destination=destination))
                self.assertEqual(engine.blockers, [])
                self.assertIs(engine.memory.read('FaultWitness'), True)
                engine.memory.write('LabIndex',index)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                engine.memory.write('StartPB',True)
                engine.step()
                record = engine.last_cleared_program_fault
                self.assertEqual((record['type'],record['code'],record['instruction']), (4,20,'MOV'))
                self.assertEqual(record['routine'],'MainProgram/MainRoutine')
                self.assertEqual(record['handler'],{'routine':'MainProgram/RecoverMove','status':'cleared'})
                self.assertEqual(engine.memory.read('CapturedFault'),1310724)
                self.assertEqual(engine.memory.read('FaultWords[2]'),0)
                self.assertIsNone(engine.memory.at(*engine.memory.resolve('FaultWords[3]')[:2]))
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                self.assertEqual(engine.memory.read('SpeedSetpoint'),91)
                self.assertEqual(engine.memory.read('LabValues'),[12,13])
                self.assertEqual((engine.fault,engine.scan_count,engine.time_ms),('',2,20))
                event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                self.assertEqual((event['instruction'],event['recovered_fault'],event['out']),
                                 ('MOV',{'type':4,'code':20},True))
                self.assertEqual(engine.program_fault_attributes('MainProgram',source_sha256=engine.project.sha256),{})
                self.assertTrue(engine.program_fault_description()['simulated_recovery_seen_since_reset'])
                engine.memory.write('LabIndex',1)
                engine.step()
                self.assertIs(engine.last_cleared_program_fault,record)
                self.assertEqual(engine.memory.read('LabValues[1]'),93 if destination else 13)
                self.assertEqual(engine.memory.read('SpeedCommand'),52 if destination else 14)

    def test_failed_program_fault_recovery_rolls_back_the_scan(self):
        cases = (
            ({'clear':False}, 'completed without clearing'),
            ({'handler_tail':'MOV(LabValues[LabIndex],SpeedSetpoint);'}, 'Program fault 4/20'),
            ({'main_tail':'DIV(1,0,SpeedCommand);'}, 'divide by zero'),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                self.setUp()
                engine = self.engine(mutate=lambda root:ladder_fault_fixture(root,**options))
                self.assertEqual(engine.blockers,[])
                engine.memory.write('StartPB',True)
                engine.memory.write('LabIndex',2)
                before = copy.deepcopy(engine.memory.values)
                with self.assertRaisesRegex(ModelError,expected):
                    engine.step()
                self.assertEqual(engine.memory.values,before)
                self.assertEqual((engine.scan_count,engine.time_ms,engine.trace,engine.changes),(0,0,[],[]))
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertIsNone(engine._program_fault)

    def test_program_fault_routine_stays_out_of_normal_call_and_harness_paths(self):
        for main_tail, expected in (
            ('JSR(RecoverMove,0);','Normal calls to a Program fault routine'),
            ('GSV(Program,THIS,MajorFaultRecord,FaultWords[0]);','MajorFaultRecord requires an assigned fault routine'),
        ):
            with self.subTest(main_tail=main_tail):
                self.setUp()
                engine = self.engine(mutate=lambda root:ladder_fault_fixture(root,main_tail=main_tail))
                self.assertTrue(any(expected in reason for reason in engine.blockers),engine.blockers)
        self.setUp()
        harness = self.engine(mutate=ladder_fault_fixture,mode='routine',routine='MainProgram/RecoverMove')
        self.assertIn('Program fault routine requires a scheduled ladder fault',harness.blockers)
        harness = self.engine(mode='routine',routine='MainProgram/MainRoutine')
        self.assertEqual(harness.blockers,[])
        harness.memory.write('StartPB',True)
        harness.memory.write('LabIndex',2)
        with self.assertRaisesRegex(ModelError,'Scan rolled back: Array index outside bounds'):
            harness.step()
        self.assertIsNone(harness.last_cleared_program_fault)
