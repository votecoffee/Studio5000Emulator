"""Clean model fault records never survive an unclassified fault as zeros."""
import base64
import copy
import unittest
from xml.etree import ElementTree as ET
from unittest.mock import patch
import test_runtime as fixtures
from logixlab.model import ModelError


def ladder_fault_fixture(root, *, clear=True, handler_tail=None, main_tail=None, destination=False, copy_op=None):
    controller = root.find('Controller')
    program = controller.find('./Programs/Program')
    program.set('FaultRoutineName','RecoverMove')
    tags = controller.find('Tags')
    arrays = [('LabValues',[12,13]), ('FaultWords',[0]*11)]
    if copy_op:
        arrays.append(('LabCopy',[81,82]))
    for name, values in arrays:
        size = len(values)
        tag = ET.SubElement(tags,'Tag',Name=name,DataType='DINT',Dimensions=str(size),TagType='Base')
        data = ET.SubElement(tag,'Data',Format='Decorated')
        array = ET.SubElement(data,'Array',DataType='DINT',Dimensions=str(size))
        for index,value in enumerate(values):
            ET.SubElement(array,'Element',Index=f'[{index}]',Value=str(value))
    scalars = [('LabIndex','DINT','0'), ('CapturedFault','DINT','0'), ('FaultWitness','BOOL','1')]
    if copy_op:
        scalars.append(('CopyLength','DINT','2'))
    for name, dtype, value in scalars:
        tag = ET.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base')
        ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=value)

    def rungs(content, lines):
        content.clear()
        for index, line in enumerate(lines):
            rung = ET.SubElement(content,'Rung',Number=str(index),Type='N')
            ET.SubElement(rung,'Text').text = line

    routines = program.find('Routines')
    if copy_op:
        operands = 'LabValues[0],LabCopy[LabIndex]' if destination else 'LabValues[LabIndex],LabCopy[0]'
        instruction = f'{copy_op}({operands},CopyLength)'
    else:
        instruction = 'MOV(93,LabValues[LabIndex])' if destination else 'MOV(LabValues[LabIndex],SpeedCommand)'
    rungs(routines.find('./Routine/RLLContent'),
          ['XIC(StartPB)'+instruction+'ADD(SpeedCommand,1,SpeedCommand);','MOV(91,SpeedSetpoint);']
          + ([main_tail] if main_tail else []))
    recovery = ET.SubElement(routines,'Routine',Name='RecoverMove',Type='RLL')
    handler = ['OTE(FaultWitness);', 'GSV(Program,THIS,MajorFaultRecord,FaultWords[0]);',
               'MOV(FaultWords[2],CapturedFault);']
    if clear:
        handler.append('EQU(CapturedFault,1310724)CLR(FaultWords[2])'
                       'SSV(Program,MainProgram,MajorFaultRecord,FaultWords[0]);')
    rungs(ET.SubElement(recovery,'RLLContent'),handler+([handler_tail] if handler_tail else []))


def controller_fault_fallback_fixture(root, *, clear_at_program=False, clear_at_controller=True,
                                      program_tail=None, controller_tail=None, main_tail=None,
                                      copy_op=None, destination=False):
    ladder_fault_fixture(root, clear=clear_at_program, handler_tail=program_tail, main_tail=main_tail,
                         copy_op=copy_op, destination=destination)
    controller = root.find('Controller')
    program = controller.find('./Programs/Program')
    if clear_at_program is None:
        del program.attrib['FaultRoutineName']
        routines = program.find('Routines')
        routines.remove(routines.find('./Routine[@Name="RecoverMove"]'))
    controller.set('MajorFaultProgram','FaultHandler')
    fault_handler = ET.SubElement(controller.find('Programs'),'Program',Name='FaultHandler',
                                  MainRoutineName='Capture',Disabled='false',Class='Standard')
    tags = ET.SubElement(fault_handler,'Tags')
    for name in ('SeenCode','InputCode','ReturnCode'):
        tag = ET.SubElement(tags,'Tag',Name=name,DataType='DINT',TagType='Base')
        ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
    routines = ET.SubElement(fault_handler,'Routines')

    def add(name, lines):
        routine = ET.SubElement(routines,'Routine',Name=name,Type='RLL')
        content = ET.SubElement(routine,'RLLContent')
        for index,line in enumerate(lines):
            rung = ET.SubElement(content,'Rung',Number=str(index),Type='N')
            ET.SubElement(rung,'Text').text = line

    add('Capture',['JSR(Report,1,1310724,SeenCode);'])
    lines = ['SBR(InputCode);','GSV(Program,THIS,MajorFaultRecord,FaultWords[0]);',
             'MOV(FaultWords[2],ReturnCode);']
    if clear_at_controller:
        lines.append('EQU(ReturnCode,InputCode)CLR(FaultWords[2])'
                     'SSV(Program,FaultHandler,MajorFaultRecord,FaultWords[0]);')
    if controller_tail:
        lines.append(controller_tail)
    add('Report',lines+['RET(ReturnCode);'])


def ladder_fault_load(*, controller_fallback=False, **options):
    root = ET.parse(fixtures.SAMPLE).getroot()
    root.set('TargetName','LadderFaultLab')
    root.find('Controller').set('Name','LadderFaultLab')
    build = controller_fault_fallback_fixture if controller_fallback else ladder_fault_fixture
    build(root, **options)
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

    def test_unhandled_move_fault_reaches_controller_handler_and_resumes(self):
        for clear_at_program, expected in (
            (True,'MainProgram/RecoverMove'), (False,'FaultHandler/Capture'), (None,'FaultHandler/Capture')
        ):
            with self.subTest(clear_at_program=clear_at_program):
                self.setUp()
                engine = self.engine(mutate=lambda root:controller_fault_fallback_fixture(
                    root, clear_at_program=clear_at_program))
                self.assertEqual(engine.blockers, [])
                engine.memory.write('LabIndex',2)
                engine.memory.write('StartPB',True)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'],fault['code'],fault['program']), (4,20,'MainProgram'))
                self.assertEqual(fault['handler'], {'routine':expected,'status':'cleared'})
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                self.assertEqual(engine.memory.read('SpeedSetpoint'),91)
                self.assertEqual(engine.memory.read('FaultWords[2]'),0)
                self.assertEqual(engine.memory.read('CapturedFault'),0 if clear_at_program is None else 1310724)
                self.assertEqual(engine.memory.read('SeenCode','FaultHandler'),0 if clear_at_program else 1310724)
                expected_trace = [key for key,enabled in (
                    ('MainProgram/RecoverMove',clear_at_program is not None),
                    ('FaultHandler/Report',not clear_at_program),
                    ('FaultHandler/Capture',not clear_at_program),
                    ('MainProgram/MainRoutine',True),
                ) if enabled]
                self.assertEqual(list(dict.fromkeys(row['routine'] for row in engine.trace)),expected_trace)
                self.assertIsNone(engine.module_major_fault)
                self.assertIsNone(engine.last_cleared_module_fault)
                self.assertEqual(engine.calls.stack,[])

    def test_controller_fallback_rolls_back_both_handlers_on_failure(self):
        cases = (
            ({'clear_at_controller':False},'Controller Fault Handler completed without clearing'),
            ({'controller_tail':'DIV(1,0,SpeedSetpoint);'},'Controller Fault Handler: DIV divide by zero'),
            ({'program_tail':'MOV(LabValues[LabIndex],SpeedSetpoint);'},'Program fault routine: Array index outside bounds'),
            ({'main_tail':'DIV(1,0,SpeedCommand);'},'divide by zero'),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                self.setUp()
                engine = self.engine(mutate=lambda root:controller_fault_fallback_fixture(root,**options))
                self.assertEqual(engine.blockers, [])
                engine.memory.write('LabIndex',2)
                engine.memory.write('StartPB',True)
                before = copy.deepcopy(engine.memory.values)
                with self.assertRaisesRegex(ModelError,expected):
                    engine.step()
                self.assertEqual(engine.memory.values,before)
                self.assertEqual((engine.scan_count,engine.time_ms,engine.trace,engine.changes),(0,0,[],[]))
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertIsNone(engine._program_fault)
                self.assertFalse(engine._handler_clear_requested)
                self.assertEqual(engine.calls.stack,[])

    def test_controller_fallback_requires_proof_that_a_program_handler_is_absent(self):
        def configure(root):
            controller_fault_fallback_fixture(root,clear_at_program=None)
            root.find('./Controller/Programs/Program').set('FaultRoutineName','Unresolved')
        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('LabIndex',2)
        engine.memory.write('StartPB',True)
        with self.assertRaisesRegex(ModelError,'Scan rolled back: Array index outside bounds'):
            engine.step()
        self.assertEqual(engine.memory.read('SeenCode','FaultHandler'),0)
        self.assertIsNone(engine.last_cleared_program_fault)

    def test_controller_fallback_restores_the_interrupted_call_and_first_scan(self):
        def configure(root):
            controller_fault_fallback_fixture(root,clear_at_program=None)
            programs = root.find('./Controller/Programs')
            routines = programs.find('./Program/Routines')
            main = routines.find('./Routine/RLLContent')
            previous = [rung.findtext('Text') for rung in main]
            main.clear()
            sub = ET.SubElement(routines,'Routine',Name='FaultingCall',Type='RLL')
            content = ET.SubElement(sub,'RLLContent')
            lines = ['SBR(SpeedCommand);', *previous,
                     'XIC(S:FS)MOV(52,SpeedCommand);', 'RET(SpeedCommand);']
            for index,line in enumerate(lines):
                rung = ET.SubElement(content,'Rung',Number=str(index),Type='N')
                ET.SubElement(rung,'Text').text = line
            ET.SubElement(ET.SubElement(main,'Rung',Number='0',Type='N'),'Text').text = (
                'JSR(FaultingCall,1,50,SpeedSetpoint);')
            handler = programs.find('./Program[@Name="FaultHandler"]/Routines/Routine/RLLContent')
            rung = ET.SubElement(handler,'Rung',Number='1',Type='N')
            ET.SubElement(rung,'Text').text = 'XIC(S:FS)MOV(-1,SeenCode);'

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('LabIndex',2)
        engine.memory.write('StartPB',True)
        engine.step()
        self.assertEqual(engine.last_cleared_program_fault['routine'],'MainProgram/FaultingCall')
        self.assertEqual(engine.memory.read('SeenCode','FaultHandler'),1310724)
        self.assertEqual(engine.memory.read('SpeedSetpoint'),52)
        self.assertEqual(engine.calls.stack,[])

    def test_block_copies_clear_bad_starts_without_copying_or_retrying(self):
        for copy_op in ('COP','CPS'):
            for destination, index in ((False,2),(True,-1)):
                with self.subTest(copy_op=copy_op,destination=destination):
                    self.setUp()
                    engine = self.engine(mutate=lambda root:ladder_fault_fixture(
                        root, copy_op=copy_op, destination=destination, handler_tail='CLR(LabIndex);'))
                    self.assertEqual(engine.blockers, [])
                    engine.memory.write('LabIndex',index)
                    engine.memory.write('SpeedCommand',50)
                    engine.step()
                    self.assertEqual(engine.memory.read('LabCopy'),[81,82])
                    self.assertIsNone(engine.last_cleared_program_fault)
                    engine.memory.write('StartPB',True)
                    engine.step()
                    fault = engine.last_cleared_program_fault
                    self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,copy_op))
                    self.assertEqual(fault['handler']['routine'],'MainProgram/RecoverMove')
                    self.assertEqual(engine.memory.read('CapturedFault'),1310724)
                    self.assertEqual(engine.memory.read('LabIndex'),0)
                    self.assertEqual(engine.memory.read('LabCopy'),[81,82])
                    self.assertEqual(engine.memory.read('SpeedCommand'),51)
                    event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                    self.assertEqual((event['instruction'],event['out']),(copy_op,True))
                    engine.step()
                    self.assertIs(engine.last_cleared_program_fault,fault)
                    self.assertEqual(engine.memory.read('LabCopy'),[12,13])
                    self.assertEqual(engine.memory.read('SpeedCommand'),52)

    def test_aggregate_copy_start_fault_reaches_controller_handler(self):
        from test_aggregate_copy import AggregateCopyTests

        def configure(root):
            controller_fault_fallback_fixture(root)
            AggregateCopyTests.fields(root)
            text = root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text')
            text.text = 'CPS(Records[0],CopyRecords[LabIndex],2)ADD(SpeedCommand,1,SpeedCommand);'

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('LabIndex',3)
        engine.memory.write('Records[0].Count',27)
        engine.memory.write('CopyRecords[2].Count',73)
        before = copy.deepcopy(engine.memory.read('CopyRecords'))
        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['instruction'],fault['handler']['routine']),('CPS','FaultHandler/Capture'))
        self.assertEqual(engine.memory.read('SeenCode','FaultHandler'),1310724)
        self.assertEqual(engine.memory.read('CopyRecords'),before)
        self.assertEqual(engine.memory.read('SpeedCommand'),1)
        engine.memory.write('LabIndex',2)
        engine.step()
        self.assertEqual(engine.memory.read('CopyRecords')[:2],before[:2])
        self.assertEqual(engine.memory.read('CopyRecords[2].Count'),27)
        self.assertIs(engine.last_cleared_program_fault,fault)

    def test_invalid_copy_length_still_rolls_back_without_fault_recovery(self):
        engine = self.engine(mutate=lambda root:controller_fault_fallback_fixture(root,copy_op='COP'))
        self.assertEqual(engine.blockers, [])
        engine.memory.write('CopyLength',-1)
        engine.memory.write('StartPB',True)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError,'Scan rolled back: Block length'):
            engine.step()
        self.assertEqual(engine.memory.values,before)
        self.assertIsNone(engine.last_cleared_program_fault)
