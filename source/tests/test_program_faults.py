"""Clean model fault records never survive an unclassified fault as zeros."""
import base64
import copy
import unittest
from xml.etree import ElementTree as ET
from unittest.mock import patch
import test_runtime as fixtures
from logixlab.model import ModelError


def add_fault_dint_array(tags, name, values):
    size = len(values)
    tag = ET.SubElement(tags,'Tag',Name=name,DataType='DINT',Dimensions=str(size),TagType='Base')
    data = ET.SubElement(tag,'Data',Format='Decorated')
    array = ET.SubElement(data,'Array',DataType='DINT',Dimensions=str(size))
    for index,value in enumerate(values):
        ET.SubElement(array,'Element',Index=f'[{index}]',Value=str(value))


def ladder_fault_fixture(root, *, clear=True, handler_tail=None, main_tail=None, destination=False, copy_op=None,
                         fault_code=20):
    controller = root.find('Controller')
    program = controller.find('./Programs/Program')
    program.set('FaultRoutineName','RecoverMove')
    tags = controller.find('Tags')
    arrays = [('LabValues',[12,13]), ('FaultWords',[0]*11)]
    if copy_op:
        arrays.append(('LabCopy',[81,82]))
    for name, values in arrays:
        add_fault_dint_array(tags,name,values)
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
        handler.append(f'EQU(CapturedFault,{(fault_code << 16) | 4})CLR(FaultWords[2])'
                       'SSV(Program,MainProgram,MajorFaultRecord,FaultWords[0]);')
    rungs(ET.SubElement(recovery,'RLLContent'),handler+([handler_tail] if handler_tail else []))


def controller_fault_fallback_fixture(root, *, clear_at_program=False, clear_at_controller=True,
                                      program_tail=None, controller_tail=None, main_tail=None,
                                      copy_op=None, destination=False, fault_code=20):
    ladder_fault_fixture(root, clear=clear_at_program, handler_tail=program_tail, main_tail=main_tail,
                         copy_op=copy_op, destination=destination, fault_code=fault_code)
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

    add('Capture',[f'JSR(Report,1,{(fault_code << 16) | 4},SeenCode);'])
    lines = ['SBR(InputCode);','GSV(Program,THIS,MajorFaultRecord,FaultWords[0]);',
             'MOV(FaultWords[2],ReturnCode);']
    if clear_at_controller:
        lines.append('EQU(ReturnCode,InputCode)CLR(FaultWords[2])'
                     'SSV(Program,FaultHandler,MajorFaultRecord,FaultWords[0]);')
    if controller_tail:
        lines.append(controller_tail)
    add('Report',lines+['RET(ReturnCode);'])


def add_jsr_fault_call(root, *, return_destination=False):
    controller = root.find('Controller')
    tags = controller.find('Tags')
    for name,value in (('CallInput','70'),('CallRuns','0')):
        tag = ET.SubElement(tags,'Tag',Name=name,DataType='DINT',TagType='Base')
        ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value=value)
    routines = controller.find('./Programs/Program/Routines')
    args = '9,LabValues[LabIndex]' if return_destination else 'LabValues[LabIndex],SpeedCommand'
    routines.find('./Routine/RLLContent/Rung/Text').text = (
        f'XIC(StartPB)JSR(CallWork,1,{args})ADD(SpeedCommand,1,SpeedCommand);')
    routine = ET.SubElement(routines,'Routine',Name='CallWork',Type='RLL')
    content = ET.SubElement(routine,'RLLContent')
    for index,line in enumerate(('SBR(CallInput);','ADD(CallRuns,1,CallRuns);','RET(CallInput);')):
        rung = ET.SubElement(content,'Rung',Number=str(index),Type='N')
        ET.SubElement(rung,'Text').text = line


def set_fault_instruction(root, instruction):
    text = root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text')
    text.text = f'XIC(StartPB){instruction}ADD(SpeedCommand,1,SpeedCommand);'


def add_fault_record_array(root, dtype, name='LabRecords', **initial):
    members = {
        'TIMER':dict(PRE=100,ACC=4,EN=False,TT=False,DN=False),
        'COUNTER':dict(PRE=3,ACC=7,CU=False,CD=False,DN=True,OV=False,UN=False),
        'CONTROL':dict(LEN=9,POS=1,EN=True,EU=True,DN=True,EM=True,ER=True,UL=True,IN=True,FD=True),
    }[dtype] | initial
    tags = root.find('./Controller/Tags')
    tag = ET.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base',Dimensions='2')
    array = ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions='2')
    for index in range(2):
        obj = ET.SubElement(ET.SubElement(array,'Element',Index=f'[{index}]'),'Structure',DataType=dtype)
        for member,value in members.items():
            data_type = 'BOOL' if type(value) is bool else 'DINT'
            ET.SubElement(obj,'DataValueMember',Name=member,DataType=data_type,Value=str(int(value)))


def add_bit_diagnostic_tags(root, *, single=False):
    from logixlab.control_operations import default

    add_fault_record_array(root,'CONTROL',**(default()|dict(LEN=4,ER=True,IN=single)))
    tags = root.find('./Controller/Tags')
    add_fault_dint_array(tags,'LabQueue',[0,0,99])
    add_fault_dint_array(tags,'LabResults',[-1,-1,88])


def bit_result_slot_fault_fixture(root, name):
    ladder_fault_fixture(root, handler_tail='MOV(1,LabIndex);')
    add_bit_diagnostic_tags(root)
    tags = root.find('./Controller/Tags')
    tags.find('Tag[@Name="LabIndex"]/Data/DataValue').set('Value', '2')
    tags.find('Tag[@Name="FaultWitness"]/Data/DataValue').set('Value', '0')
    tags.find('Tag[@Name="LabRecords"]/Data/Array/Element[@Index="[1]"]/Structure/'
              'DataValueMember[@Name="LEN"]').set('Value', '2')
    root.find('.//Routine[@Name="RecoverMove"]/RLLContent/Rung/Text').text = (
        'EQU(LabResults[2],88)EQU(LabQueue[0],0)OTE(FaultWitness);')
    set_fault_instruction(root, f'{name}(LabValues[0],LabQueue[0],LabResults[LabIndex],'
                               'LabRecords[0],?,?,LabRecords[1],?,?)')


def add_array_calculation_tags(root):
    from logixlab.control_operations import default

    add_fault_record_array(root,'CONTROL',**(default()|dict(LEN=3)))
    tags = root.find('./Controller/Tags')
    add_fault_dint_array(tags,'LabQueue',[99,6,2,4,77])
    tag = ET.SubElement(tags,'Tag',Name='LabStats',TagType='Base',DataType='REAL',Dimensions='2')
    array = ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='REAL',Dimensions='2')
    for index,value in enumerate(('11','22')):
        ET.SubElement(array,'Element',Index=f'[{index}]',Value=value)


def add_string_recovery_tags(root):
    from test_string_operations import string_data

    tags = root.find('./Controller/Tags')
    for name, texts in (('LabText',['AbC123AbC','XY']), ('LabTextResults',['KEEP','TAIL'])):
        tag = ET.SubElement(tags,'Tag',Name=name,DataType='STRING',TagType='Base',Dimensions='2')
        array = ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='STRING',Dimensions='2')
        for index, value in enumerate(texts):
            element = ET.SubElement(array,'Element',Index=f'[{index}]')
            data = string_data(element,value).find('ArrayMember')
            if name == 'LabTextResults':
                data.find('Element[@Index="[81]"]').set('Value','33')
                data.remove(data.find('Element[@Index="[20]"]'))
    add_fault_dint_array(tags,'LabPositions',[1,1])
    tag = ET.SubElement(tags,'Tag',Name='LabReals',DataType='REAL',TagType='Base',Dimensions='2')
    array = ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='REAL',Dimensions='2')
    for index, value in enumerate(('2.5','6.25')):
        ET.SubElement(array,'Element',Index=f'[{index}]',Value=value)


def add_system_value_recovery_tags(root):
    tags = root.find('./Controller/Tags')
    add_fault_dint_array(tags,'LabClockWords',[77]*9)
    add_fault_dint_array(tags,'LabSetpoints',[600000,650000])


def add_stateful_recovery_tags(root, mnemonic):
    from test_ladder_alarm import SAMPLE as ALARM_SAMPLE
    from test_ladder_pid import SAMPLE as PID_SAMPLE

    sample,name = {
        'PID':(PID_SAMPLE,'Loop'), 'ALMD':(ALARM_SAMPLE,'MotorAlarm'),
        'ALMA':(ALARM_SAMPLE,'PressureAlarm'),
    }[mnemonic]
    tags = root.find('./Controller/Tags')
    tags.append(ET.parse(sample).find(f'./Controller/Tags/Tag[@Name="{name}"]'))
    if mnemonic == 'PID':
        add_fault_dint_array(tags,'LabOutputs',[77,88])


def add_fault_pid_array(root):
    add_stateful_recovery_tags(root, 'PID')
    tag = root.find('./Controller/Tags/Tag[@Name="Loop"]')
    tag.set('Dimensions', '2')
    data = tag.find('Data')
    record = data.find('Structure')
    data.remove(record)
    array = ET.SubElement(data, 'Array', DataType='PID', Dimensions='2')
    for index in range(2):
        ET.SubElement(array, 'Element', Index=f'[{index}]').append(copy.deepcopy(record))
    return array


def configure_for_recovery(root, *lines):
    tags = root.find('./Controller/Tags')
    add_fault_dint_array(tags,'LoopIndex',[77,88])
    add_fault_dint_array(tags,'LoopBounds',[1,2])
    content = root.find('./Controller/Programs/Program/Routines/Routine[@Name="Reporting"]/RLLContent')
    content.clear()
    for index,line in enumerate(lines):
        rung = ET.SubElement(content,'Rung',Number=str(index),Type='N')
        ET.SubElement(rung,'Text').text = line


def add_fault_queue_start(root, *, member):
    controller = root.find('Controller')
    tags = controller.find('Tags')
    add_fault_dint_array(tags, 'LabQueue', [31, 47, 99])
    target = 'LabQueue'
    if member:
        datatype = ET.SubElement(controller.find('DataTypes'), 'DataType', Name='QueuePacket',
                                 Family='NoFamily', Class='User')
        members = ET.SubElement(datatype, 'Members')
        ET.SubElement(members, 'Member', Name='Slots', DataType='DINT', Dimension='3')
        ET.SubElement(members, 'Member', Name='Guard', DataType='DINT', Dimension='0')
        tag = tags.find('Tag[@Name="LabQueue"]')
        tag.set('DataType', 'QueuePacket')
        del tag.attrib['Dimensions']
        data = tag.find('Data')
        array = data.find('Array')
        data.remove(array)
        record = ET.SubElement(data, 'Structure', DataType='QueuePacket')
        array.tag = 'ArrayMember'
        array.set('Name', 'Slots')
        record.append(array)
        ET.SubElement(record, 'DataValueMember', Name='Guard', DataType='DINT', Value='777')
        target += '.Slots'
    tags.find('Tag[@Name="LabIndex"]/Data/DataValue').set('Value', '1')
    ET.SubElement(tags, 'Tag', Name='QueueStart', DataType='DINT', TagType='Alias',
                  AliasFor=f'{target}[LabIndex]')


def queue_load_slot_fixture(root, name, *, member=False):
    ladder_fault_fixture(root, handler_tail='CLR(LabRecords[0].POS)MOV(66,LabValues[0]);')
    add_fault_record_array(root, 'CONTROL', LEN=4, POS=1, ER=False)
    add_fault_queue_start(root, member=member)
    set_fault_instruction(root, f'{name}(LabValues[0],QueueStart,LabRecords[0],?,?)')


def member_extent_fault_fixture(root, name):
    shift = name == 'BSL'
    length, repaired_length = (65, 4) if shift else (3, 2)
    ladder_fault_fixture(root, handler_tail=f'MOV({repaired_length},LabRecords[0].LEN);')
    add_fault_record_array(root, 'CONTROL', LEN=length, POS=2, ER=False)
    add_fault_queue_start(root, member=True)
    root.find('.//Routine[@Name="RecoverMove"]/RLLContent/Rung/Text').text = (
        'XIC(LabRecords[0].ER)OTE(FaultWitness);')
    operands = 'QueueStart,LabRecords[0],LabValues[0].0,?' if shift else 'QueueStart,LabValues[0],LabRecords[0],?,?'
    set_fault_instruction(root, f'{name}({operands})')


def sql_row_fault_fixture(root, *, member):
    ladder_fault_fixture(root, handler_tail='CLR(LabIndex)MOV(66,LabValues[1]);')
    add_fault_record_array(root, 'CONTROL', LEN=4, POS=1, ER=False)
    add_fault_queue_start(root, member=member)
    set_fault_instruction(root, 'SQL(QueueStart,LabValues[LabIndex+1],LabRecords[0],?,?)')


def sequencer_read_rows_fixture(root):
    ladder_fault_fixture(root)
    add_fault_record_array(root, 'CONTROL', LEN=4, POS=1, ER=False)
    add_fault_queue_start(root, member=True)
    set_fault_instruction(root, 'SQO(QueueStart,255,LabValues[LabIndex],LabRecords[0],?,?)')
    content = root.find('./Controller/Programs/Program/Routines/Routine/RLLContent')
    ET.SubElement(ET.SubElement(content, 'Rung', Number='2', Type='N'), 'Text').text = (
        'XIC(StartPB)SQI(QueueStart,255,LabValues[LabIndex],LabRecords[1],?,?)OTE(FaultWitness);')


def ladder_fault_load(*, controller_fallback=False, call_fault=None, instruction=None,
                      record_type=None, record_members=None, queue_values=None, **options):
    root = ET.parse(fixtures.SAMPLE).getroot()
    root.set('TargetName','LadderFaultLab')
    root.find('Controller').set('Name','LadderFaultLab')
    build = controller_fault_fallback_fixture if controller_fallback else ladder_fault_fixture
    build(root, **options)
    if record_type is not None:
        add_fault_record_array(root,record_type,**(record_members or {}))
    if queue_values is not None:
        add_fault_dint_array(root.find('./Controller/Tags'),'LabQueue',queue_values)
    if call_fault is not None:
        add_jsr_fault_call(root, return_destination=call_fault=='return')
    if instruction is not None:
        set_fault_instruction(root, instruction)
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
                visit = next(row for row in engine.trace if 'recovery_source' in row)
                source = engine.project.routines['mainprogram/mainroutine'].rungs[0]['text']
                self.assertEqual((visit['rung_index'],visit['recovery_source']),(0,source))
                event = next(event for event in visit['events'] if 'recovered_fault' in event)
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

    def test_jsr_argument_fault_skips_call_and_preserves_transfers(self):
        for return_destination,index in ((False,2),(True,-1)):
            with self.subTest(return_destination=return_destination):
                self.setUp()

                def configure(root):
                    if return_destination:
                        controller_fault_fallback_fixture(root)
                    else:
                        ladder_fault_fixture(root,handler_tail='CLR(LabIndex);')
                    add_jsr_fault_call(root,return_destination=return_destination)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write('LabIndex',index)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                engine.memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,'JSR'))
                expected_handler = 'FaultHandler/Capture' if return_destination else 'MainProgram/RecoverMove'
                self.assertEqual(fault['handler']['routine'],expected_handler)
                self.assertEqual(engine.memory.read('CallInput'),70)
                self.assertEqual(engine.memory.read('CallRuns'),0)
                self.assertEqual(engine.memory.read('LabValues'),[12,13])
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                self.assertFalse(any(row['routine']=='MainProgram/CallWork' for row in engine.trace))
                event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                self.assertEqual((event['instruction'],event['out']),('JSR',True))
                self.assertEqual(engine.calls.stack,[])
                if return_destination:
                    engine.memory.write('LabIndex',0)
                else:
                    self.assertEqual(engine.memory.read('LabIndex'),0)
                engine.step()
                self.assertIs(engine.last_cleared_program_fault,fault)
                self.assertEqual(engine.memory.read('CallRuns'),1)
                self.assertEqual(engine.memory.read('CallInput'),9 if return_destination else 12)
                self.assertEqual(engine.memory.read('LabValues'),[9,13] if return_destination else [12,13])
                self.assertEqual(engine.memory.read('SpeedCommand'),52 if return_destination else 13)

    def test_jsr_argument_recovery_does_not_intercept_callee_errors(self):
        for mnemonic in ('FOR','GSV','SQR','FRD','EQU','MOV'):
            with self.subTest(mnemonic=mnemonic):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root)
                    add_jsr_fault_call(root)
                    content = root.find('./Controller/Programs/Program/Routines/Routine[@Name="CallWork"]/RLLContent')
                    content[2].set('Number','4')
                    set_index = ET.Element('Rung',Number='2',Type='N')
                    ET.SubElement(set_index,'Text').text = 'MOV(2,LabIndex);'
                    content.insert(2,set_index)
                    faulting = ET.Element('Rung',Number='3',Type='N')
                    line = {
                        'FOR':'FOR(LoopBody,CallInput,0,0,1);',
                        'GSV':'GSV(Task,THIS,LastScanTime,LabValues[LabIndex]);',
                        'SQR':'SQR(LabValues[LabIndex],CallInput);',
                        'FRD':'FRD(LabValues[LabIndex],CallInput);',
                        'EQU':'EQU(LabValues[LabIndex],1)NOP();',
                        'MOV':'MOV(LabValues[LabIndex],CallInput);',
                    }[mnemonic]
                    ET.SubElement(faulting,'Text').text = line
                    content.insert(3,faulting)
                    if mnemonic=='FOR':
                        routines = root.find('./Controller/Programs/Program/Routines')
                        body = ET.SubElement(routines,'Routine',Name='LoopBody',Type='ST')
                        st = ET.SubElement(body,'STContent')
                        ET.SubElement(st,'Line',Number='0').text = 'SpeedCommand := LabValues[LabIndex];'

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write('StartPB',True)
                before = copy.deepcopy(engine.memory.values)
                if mnemonic=='FOR':
                    with self.assertRaisesRegex(ModelError,'Scan rolled back: MainProgram/LoopBody, ST line 1: Array index outside bounds'):
                        engine.step()
                    self.assertEqual(engine.memory.values,before)
                    self.assertIsNone(engine.last_cleared_program_fault)
                else:
                    engine.step()
                    record = engine.last_cleared_program_fault
                    self.assertEqual((record['instruction'],record['routine']),(mnemonic,'MainProgram/CallWork'))
                    self.assertEqual(engine.memory.read('CallRuns'),1)
                    self.assertEqual(engine.memory.read('SpeedCommand'),13)
                self.assertEqual(engine.calls.stack,[])

    def test_structured_text_argument_fault_is_not_recovered_as_a_ladder_call(self):
        def configure(root):
            ladder_fault_fixture(root)
            add_jsr_fault_call(root)
            routines = root.find('./Controller/Programs/Program/Routines')
            routines.find('./Routine/RLLContent/Rung/Text').text = 'JSR(Bridge,0);'
            bridge = ET.SubElement(routines,'Routine',Name='Bridge',Type='ST')
            content = ET.SubElement(bridge,'STContent')
            ET.SubElement(content,'Line',Number='0').text = 'JSR(CallWork,1,LabValues[LabIndex],SpeedCommand);'

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('LabIndex',2)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError,'Bridge, ST line 1: Array index outside bounds'):
            engine.step()
        self.assertEqual(engine.memory.values,before)
        self.assertIsNone(engine.last_cleared_program_fault)
        self.assertEqual(engine.calls.stack,[])

    def test_arithmetic_array_faults_skip_the_write_and_resume_the_rung(self):
        expected = {'ADD':17,'SUB':7,'MUL':60,'DIV':2,'MOD':2,'NEG':-12,'ABS':12,'CPT':25}
        for mnemonic,result in expected.items():
            for destination,index in ((False,2),(True,-1)):
                with self.subTest(mnemonic=mnemonic,destination=destination):
                    self.setUp()
                    source = '12' if destination else 'LabValues[LabIndex]'
                    target = 'LabValues[LabIndex]' if destination else 'SpeedCommand'
                    if mnemonic=='CPT':
                        instruction = f'CPT({target},{source}*2+1)'
                    elif mnemonic in ('NEG','ABS'):
                        instruction = f'{mnemonic}({source},{target})'
                    else:
                        instruction = f'{mnemonic}({source},5,{target})'

                    def configure(root):
                        ladder_fault_fixture(root,handler_tail='CLR(LabIndex);')
                        set_fault_instruction(root,instruction)

                    engine = self.engine(mutate=configure)
                    self.assertEqual(engine.blockers, [])
                    engine.memory.write('LabIndex',index)
                    engine.memory.write('SpeedCommand',50)
                    engine.step()
                    self.assertIsNone(engine.last_cleared_program_fault)
                    engine.memory.write('StartPB',True)
                    engine.step()
                    record = engine.last_cleared_program_fault
                    self.assertEqual((record['type'],record['code'],record['instruction']),(4,20,mnemonic))
                    self.assertEqual(engine.memory.read('LabIndex'),0)
                    self.assertEqual(engine.memory.read('LabValues'),[12,13])
                    self.assertEqual(engine.memory.read('SpeedCommand'),51)
                    event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                    self.assertEqual((event['instruction'],event['out']),(mnemonic,True))
                    engine.step()
                    self.assertIs(engine.last_cleared_program_fault,record)
                    self.assertEqual(engine.memory.read('LabValues'),[result,13] if destination else [12,13])
                    self.assertEqual(engine.memory.read('SpeedCommand'),52 if destination else result+1)

    def test_arithmetic_errors_keep_existing_scan_rollback(self):
        for instruction,message in (
            ('DIV(12,0,SpeedCommand)','divide by zero'),
            ('ADD(2147483647,LabValues[LabIndex],SpeedCommand)','DINT overflow'),
            ('CPT(SpeedCommand,LabValues[LabIndex]/0)','divide by zero'),
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    controller_fault_fallback_fixture(root)
                    set_fault_instruction(root,'MOV(44,SpeedCommand)'+instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write('StartPB',True)
                before = copy.deepcopy(engine.memory.values)
                with self.assertRaisesRegex(ModelError,message):
                    engine.step()
                self.assertEqual(engine.memory.values,before)
                self.assertEqual((engine.scan_count,engine.time_ms,engine.trace),(0,0,[]))
                self.assertIsNone(engine.last_cleared_program_fault)

    def test_bitwise_array_faults_preserve_the_destination_and_resume(self):
        expected = {'AND':(4,5),'OR':(13,5),'XOR':(9,0),'NOT':(-13,-6),'MVM':(52,13),'BTD':(60,5)}
        for mnemonic,(source_result,dest_result) in expected.items():
            for destination,index in ((False,2),(True,-1)):
                with self.subTest(mnemonic=mnemonic,destination=destination):
                    self.setUp()
                    source = '5' if destination else 'LabValues[LabIndex]'
                    target = 'LabValues[LabIndex]' if destination else 'SpeedCommand'
                    if mnemonic=='BTD':
                        instruction = f'BTD({source},0,{target},0,4)'
                    elif mnemonic=='MVM':
                        instruction = f'MVM({source},7,{target})'
                    elif mnemonic=='NOT':
                        instruction = f'NOT({source},{target})'
                    else:
                        instruction = f'{mnemonic}({source},5,{target})'

                    def configure(root):
                        ladder_fault_fixture(root,handler_tail='CLR(LabIndex);')
                        set_fault_instruction(root,instruction)

                    engine = self.engine(mutate=configure)
                    self.assertEqual(engine.blockers, [])
                    engine.memory.write('LabIndex',index)
                    engine.memory.write('SpeedCommand',50)
                    engine.step()
                    self.assertIsNone(engine.last_cleared_program_fault)
                    engine.memory.write('StartPB',True)
                    engine.step()
                    record = engine.last_cleared_program_fault
                    self.assertEqual((record['type'],record['code'],record['instruction']),(4,20,mnemonic))
                    self.assertEqual(engine.memory.read('LabIndex'),0)
                    self.assertEqual(engine.memory.read('LabValues'),[12,13])
                    self.assertEqual(engine.memory.read('SpeedCommand'),51)
                    event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                    self.assertEqual((event['instruction'],event['out']),(mnemonic,True))
                    engine.step()
                    self.assertIs(engine.last_cleared_program_fault,record)
                    self.assertEqual(engine.memory.read('LabValues'),[dest_result,13] if destination else [12,13])
                    self.assertEqual(engine.memory.read('SpeedCommand'),52 if destination else source_result+1)

    def test_mvm_mask_index_can_escalate_and_unknown_source_still_rolls_back(self):
        def configure(root):
            controller_fault_fallback_fixture(root)
            set_fault_instruction(root,'MVM(LabValues[0],LabValues[LabIndex],SpeedCommand)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('LabIndex',2)
        engine.memory.write('StartPB',True)
        engine.memory.write('SpeedCommand',50)
        engine.step()
        record = engine.last_cleared_program_fault
        self.assertEqual((record['instruction'],record['handler']['routine']),('MVM','FaultHandler/Capture'))
        self.assertEqual(engine.memory.read('SpeedCommand'),51)
        engine.memory.write('LabIndex',1)
        engine.memory.values['labvalues'][0] = None
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError,'Unknown initial'):
            engine.step()
        self.assertEqual(engine.memory.values,before)
        self.assertIs(engine.last_cleared_program_fault,record)
        self.assertEqual(engine.scan_count,1)

    def test_fill_clear_and_swap_operand_faults_skip_writes(self):
        cases = (
            ('FLL(LabValues[LabIndex],LabValues[0],2)',[13,13],52),
            ('FLL(7,LabValues[LabIndex],100000)',[12,7],52),
            ('FLL(7,LabValues[0],LabValues[LabIndex])',[7,7],52),
            ('FLL(7,LabValues[LabIndex],0)',[12,13],52),
            ('CLR(LabValues[LabIndex])',[12,0],52),
            ('SWPB(LabValues[LabIndex],REVERSE,SpeedCommand)',[12,13],0x0d000001),
            ('SWPB(LabValues[0],REVERSE,LabValues[LabIndex])',[12,0x0c000000],52),
        )
        for instruction,expected_values,expected_speed in cases:
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write('LabIndex',2)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                engine.memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'],fault['code'],fault['instruction']),
                                 (4,20,instruction.split('(',1)[0]))
                self.assertEqual(engine.memory.read('LabIndex'),1)
                self.assertEqual(engine.memory.read('LabValues'),[12,13])
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                engine.step()
                self.assertIs(engine.last_cleared_program_fault,fault)
                self.assertEqual(engine.memory.read('LabValues'),expected_values)
                self.assertEqual(engine.memory.read('SpeedCommand'),expected_speed)

    def test_contact_and_comparison_faults_preserve_incoming_power(self):
        for instruction in (
            'XIC(LabValues[LabIndex].1)', 'XIO(LabValues[LabIndex].0)',
            'EQU(LabValues[LabIndex],12)', 'NEQ(LabValues[LabIndex],13)',
            'LES(LabValues[LabIndex],13)', 'LEQ(LabValues[LabIndex],12)',
            'GRT(LabValues[LabIndex],13)', 'GEQ(LabValues[LabIndex],14)',
            'LIM(1,LabValues[LabIndex],12)', 'MEQ(15,LabValues[LabIndex],12)',
            'CMP(LabValues[LabIndex]+1=13)',
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabIndex',2)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertEqual(engine.memory.read('LabIndex'),2)
                engine.memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'],fault['code'],fault['instruction']),
                                 (4,20,instruction.split('(',1)[0]))
                self.assertEqual(engine.memory.read('LabIndex'),1)
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                self.assertEqual((event['in'],event['out']),(True,True))
                engine.step()
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                self.assertIs(engine.last_cleared_program_fault,fault)
                self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_bit_write_faults_leave_packed_bits_intact(self):
        for instruction,expected in (
            ('OTE(LabValues[LabIndex].1)',15), ('OTL(LabValues[LabIndex].1)',15),
            ('OTU(LabValues[LabIndex].0)',12), ('ONS(LabValues[LabIndex].1)',15),
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.step()
                engine.memory.write('LabIndex',-1)
                engine.memory.write('StartPB',True)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                self.assertEqual(engine.last_cleared_program_fault['instruction'],instruction[:3])
                self.assertEqual(engine.memory.read('LabValues'),[12,13])
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                engine.step()
                self.assertEqual(engine.memory.read('LabValues'),[12,expected])
                self.assertEqual(engine.memory.read('SpeedCommand'),52)
                if instruction.startswith('ONS'):
                    engine.step()
                    self.assertEqual(engine.memory.read('SpeedCommand'),52)

    def test_false_ote_fault_resumes_false_through_controller_handler(self):
        def configure(root):
            controller_fault_fallback_fixture(root,controller_tail='MOV(1,LabIndex);')
            set_fault_instruction(root,'OTE(LabValues[LabIndex].1)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.step()
        engine.memory.write('LabIndex',2)
        engine.memory.write('LabValues[1]',15)
        engine.memory.write('SpeedCommand',50)
        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['instruction'],fault['handler']['routine']),('OTE','FaultHandler/Capture'))
        event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
        self.assertEqual((event['in'],event['out']),(False,False))
        self.assertEqual(engine.memory.read('LabValues'),[12,15])
        self.assertEqual(engine.memory.read('SpeedCommand'),50)
        engine.step()
        self.assertEqual(engine.memory.read('LabValues'),[12,13])
        self.assertEqual(engine.memory.read('SpeedCommand'),50)

    def test_one_shot_output_fault_preserves_edge_and_packed_bits(self):
        for name, rising in (('OSR',True),('OSF',False)):
            with self.subTest(instruction=name):
                self.setUp()

                def configure(root):
                    handler = 'MOV(LabValues[0],FaultWords[3])MOV(1,LabIndex);'
                    if rising:
                        ladder_fault_fixture(root,handler_tail=handler)
                    else:
                        controller_fault_fallback_fixture(root,controller_tail=handler)
                    set_fault_instruction(root,f'{name}(LabValues[0].1,LabValues[LabIndex].1)')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabIndex',1)
                engine.memory.write('StartPB',not rising)
                engine.step()
                saved = 12 if rising else 14
                self.assertEqual(engine.memory.read('LabValues'),[saved,13])
                engine.memory.write('LabIndex',2)
                engine.memory.write('StartPB',rising)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,name))
                self.assertEqual(fault['handler']['routine'],
                                 'MainProgram/RecoverMove' if rising else 'FaultHandler/Capture')
                self.assertEqual(engine.memory.read('FaultWords[3]'),saved)
                self.assertEqual(engine.memory.read('LabValues'),[saved,13])
                self.assertEqual(engine.memory.read('SpeedCommand'),51 if rising else 50)
                event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                self.assertEqual((event['in'],event['out']),(rising,rising))
                engine.step()
                self.assertEqual(engine.memory.read('LabValues'),[14 if rising else 12,15])
                self.assertFalse(any('recovery_source' in row for row in engine.trace))
                engine.step()
                self.assertEqual(engine.memory.read('LabValues'),[14 if rising else 12,13])

    def test_one_shot_storage_fault_leaves_the_existing_pulse(self):
        def configure(root):
            ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
            set_fault_instruction(root,'OSR(LabValues[LabIndex].1,LabValues[0].0)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.step()
        engine.memory.write('LabValues[0].0',True)
        engine.memory.write('LabIndex',2)
        engine.step()
        self.assertEqual(engine.last_cleared_program_fault['instruction'],'OSR')
        self.assertEqual(engine.memory.read('LabValues'),[13,13])
        engine.step()
        self.assertEqual(engine.memory.read('LabValues'),[12,13])

    def test_one_shot_recovery_restores_unknown_lazy_storage(self):
        def configure(root):
            ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
            set_fault_instruction(root,'OSR(RunLatch,LabValues[LabIndex].1)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.step()
        key, parts, _ = engine.memory.resolve('RunLatch')
        engine.memory.store(key,parts,None)
        engine.memory.write('LabIndex',2)
        engine.step()
        self.assertEqual(engine.last_cleared_program_fault['instruction'],'OSR')
        self.assertIsNone(engine.memory.at(key,parts))
        engine.step()
        self.assertFalse(engine.memory.read('RunLatch'))

    def test_one_shot_output_index_observes_the_storage_write(self):
        def configure(root):
            ladder_fault_fixture(root,handler_tail='MOV(LabIndex,FaultWords[3])CLR(LabIndex);')
            set_fault_instruction(root,'OSR(LabIndex.0,LabValues[LabIndex].1)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.step()
        engine.memory.write('LabIndex',2)
        engine.memory.write('StartPB',True)
        engine.step()
        self.assertEqual(engine.last_cleared_program_fault['instruction'],'OSR')
        self.assertEqual(engine.memory.read('FaultWords[3]'),2)
        self.assertEqual(engine.memory.read('LabValues'),[12,13])
        engine.step()
        self.assertEqual(engine.memory.read('LabIndex'),1)
        self.assertEqual(engine.memory.read('LabValues'),[12,15])

    def test_timer_and_counter_prescan_skips_bad_index_and_continues_to_valid_record(self):
        for name in ('TON', 'TOF', 'RTO', 'CTU', 'CTD'):
            with self.subTest(instruction=name):
                self.setUp()
                is_timer = name in ('TON', 'TOF', 'RTO')

                def configure(root):
                    ladder_fault_fixture(root, handler_tail='CLR(LabIndex);')
                    controller = root.find('Controller')
                    controller.find('./Tags/Tag[@Name="LabIndex"]/Data/DataValue').set('Value', '2')
                    if is_timer:
                        add_fault_record_array(root, 'TIMER', EN=True, TT=True, DN=True)
                    else:
                        add_fault_record_array(root, 'COUNTER')
                    set_fault_instruction(root, f'{name}(LabRecords[LabIndex],?,?)')
                    next_rung = controller.find('./Programs/Program/Routines/Routine/RLLContent/Rung[@Number="1"]/Text')
                    next_rung.text = f'AFI(){name}(LabRecords[1],?,?);'

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                engine.enter_run()
                initial = engine.project.initial['labrecords']
                records = engine.memory.read('LabRecords')
                self.assertEqual(records[0], initial[0])
                expected = dict(initial[1])
                if is_timer:
                    expected.update(EN=False, TT=False)
                    if name != 'RTO':
                        expected.update(DN=False, ACC=100 if name == 'TOF' else 0)
                else:
                    expected['CU' if name == 'CTU' else 'CD'] = True
                self.assertEqual(records[1], expected)
                self.assertEqual(engine.scan_count, 0)
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertFalse(engine.last_timer)

                engine.memory.write('StartPB', True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 20, name))
                self.assertEqual(engine.memory.read('LabIndex'), 0)
                self.assertEqual(engine.memory.read('LabRecords')[0], initial[0])

    def test_timer_array_fault_preserves_records_and_last_execution_time(self):
        for name in ('TON','TOF','RTO'):
            with self.subTest(instruction=name):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='CLR(LabIndex);')
                    add_fault_record_array(root,'TIMER')
                    set_fault_instruction(root,f'{name}(LabRecords[LabIndex],?,?)')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('StartPB',True)
                engine.step()
                power = name != 'TOF'
                engine.memory.write('StartPB',power)
                engine.step()
                before = copy.deepcopy(engine.memory.read('LabRecords'))
                clock = engine.last_timer.copy()
                engine.memory.write('LabIndex',2)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,name))
                self.assertEqual(engine.memory.read('LabRecords'),before)
                self.assertEqual(engine.last_timer,clock)
                self.assertEqual(engine.memory.read('SpeedCommand'),51 if power else 50)
                event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                self.assertEqual((event['in'],event['out']),(power,power))
                engine.step()
                self.assertEqual(engine.memory.read('LabRecords[0].ACC'),before[0]['ACC']+20)
                self.assertEqual(engine.memory.read('LabRecords')[1],before[1])
                self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_negative_timer_fields_recover_without_advancing_the_clock(self):
        for name in ('TON', 'TOF', 'RTO'):
            for member, correction in (('PRE', 100), ('ACC', 4)):
                with self.subTest(instruction=name, member=member):
                    self.setUp()

                    def configure(root):
                        repair = (f'MOV(LabRecords[0].{member},LabIndex)'
                                  f'MOV({correction},LabRecords[0].{member});')
                        if name == 'TOF':
                            controller_fault_fallback_fixture(root, fault_code=34, controller_tail=repair)
                        else:
                            ladder_fault_fixture(root, fault_code=34, handler_tail=repair)
                        add_fault_record_array(root, 'TIMER')
                        set_fault_instruction(root, f'{name}(LabRecords[0],?,?)')

                    engine = self.engine(mutate=configure)
                    self.assertEqual(engine.blockers, [])
                    engine.memory.write('StartPB', True)
                    engine.step()
                    power = name != 'TOF'
                    engine.memory.write('StartPB', power)
                    engine.step()
                    expected = copy.deepcopy(engine.memory.read('LabRecords'))
                    expected[0][member] = correction
                    clock = engine.last_timer.copy()
                    engine.memory.write(f'LabRecords[0].{member}', -1)
                    engine.memory.write('SpeedCommand', 50)
                    engine.step()

                    fault = engine.last_cleared_program_fault
                    self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 34, name))
                    handler = 'MainProgram/RecoverMove' if power else 'FaultHandler/Capture'
                    self.assertEqual(fault['handler']['routine'], handler)
                    self.assertEqual(engine.memory.read('CapturedFault'), 2228228)
                    self.assertEqual(engine.memory.read('LabIndex'), -1)
                    self.assertEqual(engine.memory.read('LabRecords'), expected)
                    self.assertEqual(engine.last_timer, clock)
                    self.assertEqual(engine.memory.read('SpeedCommand'), 51 if power else 50)
                    event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                    self.assertEqual((event['in'], event['out'], event['recovered_fault']),
                                     (power, power, {'type': 4, 'code': 34}))
                    engine.step()
                    self.assertEqual(engine.memory.read('LabRecords[0].ACC'), expected[0]['ACC'] + 20)

    def test_uncleared_timer_fault_and_other_invalid_timer_values_roll_back(self):
        cases = ((True, -1, 'Program fault 4/34.*without clearing'),
                 (False, -1, 'outside nonnegative DINT$'),
                 (True, None, 'outside nonnegative DINT$'))
        for power, value, detail in cases:
            with self.subTest(power=power, value=value):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root, fault_code=20)
                    add_fault_record_array(root, 'TIMER')
                    set_fault_instruction(root, 'TON(LabRecords[0],?,?)')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write('StartPB', power)
                engine.memory.values['labrecords'][0]['PRE'] = value
                before = copy.deepcopy(engine.memory.values)
                with self.assertRaisesRegex(ModelError, detail):
                    engine.step()
                self.assertEqual(engine.memory.values, before)
                self.assertEqual((engine.scan_count, engine.time_ms), (0, 0))
                self.assertFalse(engine.last_timer)
                self.assertIsNone(engine.last_cleared_program_fault)

    def test_counter_array_fault_preserves_the_next_counting_edge(self):
        for name,edge,delta in (('CTU','CU',1),('CTD','CD',-1)):
            with self.subTest(instruction=name):
                self.setUp()

                def configure(root):
                    controller_fault_fallback_fixture(root,controller_tail='CLR(LabIndex);')
                    add_fault_record_array(root,'COUNTER')
                    set_fault_instruction(root,f'{name}(LabRecords[LabIndex],?,?)')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.step()
                before = copy.deepcopy(engine.memory.read('LabRecords'))
                engine.memory.write('LabIndex',-1)
                engine.memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['instruction'],fault['handler']['routine']),(name,'FaultHandler/Capture'))
                self.assertEqual(engine.memory.read('LabRecords'),before)
                engine.step()
                self.assertTrue(engine.memory.read(f'LabRecords[0].{edge}'))
                self.assertEqual(engine.memory.read('LabRecords[0].ACC'),7+delta)
                engine.step()
                self.assertEqual(engine.memory.read('LabRecords[0].ACC'),7+delta)
                self.assertEqual(engine.memory.read('LabRecords')[1],before[1])

    def test_reset_array_fault_retains_records_and_incremental_progress(self):
        for dtype in ('TIMER','COUNTER','CONTROL'):
            with self.subTest(type=dtype):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='CLR(LabIndex);')
                    add_fault_record_array(root,dtype)
                    set_fault_instruction(root,'RES(LabRecords[LabIndex])')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                before = copy.deepcopy(engine.memory.read('LabRecords'))
                selected,sibling = (('labrecords',(i,)) for i in range(2))
                if dtype == 'CONTROL':
                    engine._file_incremental.update((selected,sibling))
                progress = engine._file_incremental.copy()
                engine.memory.write('LabIndex',2)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertEqual(engine.memory.read('LabIndex'),2)
                engine.memory.write('StartPB',True)
                engine.step()
                self.assertEqual(engine.last_cleared_program_fault['instruction'],'RES')
                self.assertEqual(engine.memory.read('LabRecords'),before)
                self.assertEqual(engine._file_incremental,progress)
                engine.step()
                retained, cleared = ('LEN','POS') if dtype == 'CONTROL' else ('PRE','ACC')
                self.assertEqual(engine.memory.read('LabRecords')[0],{
                    field: value if field == retained else 0 if field == cleared else False
                    for field,value in before[0].items()
                })
                self.assertEqual(engine.memory.read('LabRecords')[1],before[1])
                self.assertEqual(engine._file_incremental,progress-{selected})

    def test_control_reset_keeps_address_when_it_changes_its_own_index(self):
        for offset in (1,2):
            with self.subTest(offset=offset):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root)
                    add_fault_record_array(root,'CONTROL')
                    set_fault_instruction(root,f'RES(LabRecords[{offset}-LabRecords[0].POS])')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabRecords[0].POS',offset)
                selected,sibling = (('labrecords',(i,)) for i in range(2))
                engine._file_incremental.update((selected,sibling))
                engine.memory.write('StartPB',True)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertEqual(engine.memory.read('LabRecords[0].POS'),0)
                self.assertEqual(engine.memory.read('LabRecords[1].POS'),1)
                self.assertEqual(engine._file_incremental,{sibling})

    def test_control_prescan_skips_out_of_bounds_without_mutating_any_control(self):
        instructions = (
            'BSL(LabQueue[0],LabRecords[LabIndex],StartPB,?)',
            'BSR(LabQueue[0],LabRecords[LabIndex],StartPB,?)',
            'FFL(12,LabQueue[0],LabRecords[LabIndex],?,?)',
            'FFU(LabQueue[0],LabValues[0],LabRecords[LabIndex],?,?)',
            'LFL(12,LabQueue[0],LabRecords[LabIndex],?,?)',
            'LFU(LabQueue[0],LabValues[0],LabRecords[LabIndex],?,?)',
            'SQL(LabQueue[0],12,LabRecords[LabIndex],?,?)',
            'SQO(LabQueue[0],255,LabValues[0],LabRecords[LabIndex],?,?)',
            'AVE(LabQueue[0],0,LabStats[0],LabRecords[LabIndex],?,?)',
            'STD(LabQueue[0],0,LabStats[0],LabRecords[LabIndex],?,?)',
            'FBC(LabValues[0],LabQueue[0],LabResults[0],LabRecords[1],?,?,LabRecords[LabIndex],?,?)',
            'DDT(LabValues[0],LabQueue[0],LabResults[0],LabRecords[1],?,?,LabRecords[LabIndex],?,?)',
        )
        for instruction in instructions:
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root)
                    add_array_calculation_tags(root)
                    tags = root.find('./Controller/Tags')
                    add_fault_dint_array(tags, 'LabResults', [-1, -1, 88])
                    tags.find('./Tag[@Name="LabIndex"]/Data/DataValue').set('Value', '2')
                    compare = tags.find('./Tag[@Name="LabRecords"]/Data/Array/Element[@Index="[1]"]/Structure')
                    for member in ('EN', 'DN', 'FD', 'POS'):
                        compare.find(f'DataValueMember[@Name="{member}"]').set('Value', '1')
                    set_fault_instruction(root, instruction)
                    later = root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung[@Number="1"]/Text')
                    later.text = 'OTE(FaultWitness);'

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                engine.enter_run()
                self.assertEqual(engine.memory.read('LabRecords'), engine.project.initial['labrecords'])
                self.assertFalse(engine.memory.read('FaultWitness'))
                self.assertEqual(engine.memory.read('LabIndex'), 2)
                self.assertEqual(engine.scan_count, 0)
                self.assertIsNone(engine.last_cleared_program_fault)

    def test_shift_array_faults_preserve_words_and_rearm_the_same_edge(self):
        for instruction,expected in (
            ('BSL(LabValues[0],LabRecords[0],LabValues[LabIndex].0,?)',[9,13]),
            ('BSR(LabValues[LabIndex],LabRecords[0],LabValues[0].2,?)',[12,14]),
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
                    add_fault_record_array(root,'CONTROL')
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabRecords[0].LEN',4)
                engine.memory.write('LabIndex',2)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                controls = copy.deepcopy(engine.memory.read('LabRecords'))
                engine.memory.write('StartPB',True)
                engine.step()
                self.assertEqual(engine.last_cleared_program_fault['instruction'],instruction[:3])
                self.assertEqual(engine.memory.read('LabRecords'),controls)
                self.assertEqual(engine.memory.read('LabValues'),[12,13])
                engine.step()
                self.assertEqual(engine.memory.read('LabRecords[0].POS'),4)
                self.assertEqual(engine.memory.read('LabValues'),expected)
                engine.step()
                self.assertEqual(engine.memory.read('LabValues'),expected)

    def test_shift_length_fault_sets_error_before_handler_and_retries_without_rearming(self):
        for op, start, expected in (
            ('BSL', 'LabValues[LabIndex]', 11),
            ('BSR', 'ShiftStart', 14),
        ):
            with self.subTest(op=op):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root, handler_tail='MOV(4,LabRecords[0].LEN);')
                    add_fault_record_array(root, 'CONTROL', LEN=33)
                    tags = root.find('./Controller/Tags')
                    tags.find('Tag[@Name="LabIndex"]/Data/DataValue').set('Value', '1')
                    ET.SubElement(tags, 'Tag', Name='ShiftStart', DataType='DINT', TagType='Alias',
                                  AliasFor='LabValues[LabIndex]')
                    root.find('.//Routine[@Name="RecoverMove"]/RLLContent/Rung/Text').text = (
                        'XIC(LabRecords[0].ER)OTE(FaultWitness);')
                    set_fault_instruction(root, f'{op}({start},LabRecords[0],LabValues[0].2,?)')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                memory = engine.memory
                memory.write('SpeedCommand', 50)
                engine.step()
                saved = memory.read('LabRecords')
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertFalse(saved[0]['ER'])

                memory.write('StartPB', True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 20, op))
                self.assertIn('remaining array bits', fault['detail'])
                self.assertEqual(memory.read('LabValues'), [12, 13])
                self.assertEqual(memory.read('LabRecords'), [saved[0] | dict(LEN=4, ER=True), saved[1]])
                self.assertTrue(memory.read('FaultWitness'))
                self.assertEqual(memory.read('SpeedCommand'), 51)

                engine.step()
                self.assertEqual(memory.read('LabValues'), [12, expected])
                self.assertEqual(memory.read('LabRecords[0].POS'), 4)
                self.assertFalse(memory.read('LabRecords[0].ER'))
                engine.step()
                self.assertEqual(memory.read('LabValues'), [12, expected])

    def test_queue_load_bounds_preserve_position_and_skip_full_payload_reads(self):
        for instruction,expected in (
            ('FFL(LabValues[LabIndex],LabQueue[0],LabRecords[0],?,?)',[31,13,99]),
            ('LFL(LabValues[0],LabQueue[LabIndex],LabRecords[0],?,?)',[31,47,12]),
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
                    add_fault_record_array(root,'CONTROL')
                    add_fault_dint_array(root.find('./Controller/Tags'),'LabQueue',[31,47,99])
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabRecords[0].LEN',2)
                engine.memory.write('LabIndex',3)
                engine.step()
                controls = copy.deepcopy(engine.memory.read('LabRecords'))
                engine.memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual(fault['instruction'],instruction[:3])
                self.assertEqual(engine.memory.read('LabRecords'),controls)
                self.assertEqual(engine.memory.read('LabQueue'),[31,47,99])
                engine.step()
                self.assertEqual(engine.memory.read('LabRecords[0].POS'),2)
                self.assertEqual(engine.memory.read('LabQueue'),expected)
                engine.memory.write('LabIndex',3)
                engine.memory.write('StartPB',False)
                engine.step()
                engine.memory.write('StartPB',True)
                engine.step()
                self.assertIs(engine.last_cleared_program_fault,fault)
                self.assertEqual(engine.memory.read('LabQueue'),expected)

    def test_queue_load_checks_only_the_reached_slot_and_retries_after_repair(self):
        for name, member in (('FFL', False), ('LFL', False), ('FFL', True), ('LFL', True)):
            with self.subTest(name=name, member=member):
                self.setUp()
                queue = 'LabQueue.Slots' if member else 'LabQueue'
                engine = self.engine(mutate=lambda root: queue_load_slot_fixture(root, name, member=member))
                self.assertEqual(engine.blockers, [])
                memory = engine.memory
                engine.step()
                memory.write('StartPB', True)
                engine.step()
                self.assertEqual(memory.read(queue), [31, 47, 12])
                self.assertEqual(memory.read('LabRecords[0].POS'), 2)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertEqual(memory.read('LabRecords[0].POS'), 2)

                memory.write('StartPB', False)
                engine.step()
                saved = memory.read('LabRecords')
                memory.values['labvalues'][0] = None
                memory.write('StartPB', True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 20, name))
                self.assertIn('load position', fault['detail'])
                self.assertEqual(memory.read(queue), [31, 47, 12])
                self.assertEqual(memory.read('LabRecords'), [saved[0] | dict(POS=0), saved[1]])
                if member:
                    self.assertEqual(memory.read('LabQueue.Guard'), 777)

                engine.step()
                self.assertEqual(memory.read(queue), [31, 66, 12])
                self.assertEqual(memory.read('LabRecords[0].POS'), 1)
                if member:
                    self.assertEqual(memory.read('LabQueue.Guard'), 777)

    def test_queue_unload_bounds_restore_queue_and_control_before_handlers(self):
        for name,value,shifted in (('FFU',31,[47,0,99]),('LFU',47,[31,0,99])):
            for position in (0,2):
                with self.subTest(name=name,position=position):
                    self.setUp()

                    def configure(root):
                        handler = 'MOV(LabQueue[1],FaultWords[3])MOV(1,LabIndex);'
                        controller_fault_fallback_fixture(root,controller_tail=handler)
                        add_fault_record_array(root,'CONTROL')
                        add_fault_dint_array(root.find('./Controller/Tags'),'LabQueue',[31,47,99])
                        set_fault_instruction(root,f'{name}(LabQueue[0],LabValues[LabIndex],LabRecords[0],?,?)')

                    engine = self.engine(mutate=configure)
                    self.assertEqual(engine.blockers,[])
                    engine.memory.write('LabRecords[0].LEN',2)
                    engine.memory.write('LabRecords[0].POS',position)
                    engine.step()
                    controls = copy.deepcopy(engine.memory.read('LabRecords'))
                    engine.memory.write('LabIndex',2)
                    engine.memory.write('StartPB',True)
                    engine.step()
                    fault = engine.last_cleared_program_fault
                    self.assertEqual((fault['instruction'],fault['handler']['routine']),(name,'FaultHandler/Capture'))
                    self.assertEqual(engine.memory.read('FaultWords[3]'),47)
                    self.assertEqual(engine.memory.read('LabQueue'),[31,47,99])
                    self.assertEqual(engine.memory.read('LabValues'),[12,13])
                    self.assertEqual(engine.memory.read('LabRecords'),controls)
                    engine.step()
                    self.assertEqual(engine.memory.read('LabQueue'),shifted if position else [31,47,99])
                    self.assertEqual(engine.memory.read('LabValues'),[12,value if position else 0])
                    self.assertEqual(engine.memory.read('LabRecords[0].POS'),max(position-1,0))

    def test_queue_unload_extent_fault_preserves_data_until_the_repaired_edge(self):
        for name, value, unloaded in (('FFU', 47, [31, 99, 0]), ('LFU', 99, [31, 47, 0])):
            for position in (0, 2):
                with self.subTest(name=name, position=position):
                    self.setUp()

                    def configure(root):
                        ladder_fault_fixture(root, handler_tail='MOV(2,LabRecords[0].LEN);')
                        add_fault_record_array(root, 'CONTROL', LEN=3, POS=position, ER=False)
                        tags = root.find('./Controller/Tags')
                        add_fault_dint_array(tags, 'LabQueue', [31, 47, 99])
                        tags.find('Tag[@Name="LabIndex"]/Data/DataValue').set('Value', '1')
                        ET.SubElement(tags, 'Tag', Name='QueueStart', DataType='DINT', TagType='Alias',
                                      AliasFor='LabQueue[LabIndex]')
                        root.find('.//Routine[@Name="RecoverMove"]/RLLContent/Rung/Text').text = (
                            'XIC(LabRecords[0].ER)OTE(FaultWitness);')
                        set_fault_instruction(root, f'{name}(QueueStart,LabValues[0],LabRecords[0],?,?)')

                    engine = self.engine(mutate=configure)
                    self.assertEqual(engine.blockers, [])
                    memory = engine.memory
                    engine.step()
                    saved = memory.read('LabRecords')
                    self.assertIsNone(engine.last_cleared_program_fault)

                    memory.write('StartPB', True)
                    engine.step()
                    fault = engine.last_cleared_program_fault
                    self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 20, name))
                    self.assertIn('remaining array elements', fault['detail'])
                    self.assertEqual(memory.read('LabQueue'), [31, 47, 99])
                    self.assertEqual(memory.read('LabValues'), [12, 13])
                    self.assertEqual(memory.read('LabRecords'), [saved[0] | dict(LEN=2, ER=name == 'LFU'), saved[1]])
                    self.assertIs(memory.read('FaultWitness'), name == 'LFU')

                    engine.step()
                    self.assertEqual(memory.read('LabQueue'), unloaded if position else [31, 47, 99])
                    self.assertEqual(memory.read('LabValues'), [value if position else 0, 13])
                    self.assertEqual(memory.read('LabRecords[0].POS'), max(position - 1, 0))

    def test_member_shift_and_unload_extent_faults_preserve_the_neighboring_field(self):
        for name, length, slots, output in (('BSL', 4, [31, 46, 99], 12), ('LFU', 2, [31, 47, 0], 99)):
            with self.subTest(name=name):
                self.setUp()
                engine = self.engine(mutate=lambda root: member_extent_fault_fixture(root, name))
                self.assertEqual(engine.blockers, [])
                memory = engine.memory
                engine.step()
                saved = memory.read('LabRecords')
                self.assertIsNone(engine.last_cleared_program_fault)

                memory.write('StartPB', True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 20, name))
                self.assertEqual(memory.read('LabQueue'), dict(Slots=[31, 47, 99], Guard=777))
                self.assertEqual(memory.read('LabValues'), [12, 13])
                self.assertEqual(memory.read('LabRecords'), [saved[0] | dict(LEN=length, ER=True), saved[1]])
                self.assertTrue(memory.read('FaultWitness'))

                engine.step()
                self.assertEqual(memory.read('LabQueue'), dict(Slots=slots, Guard=777))
                self.assertEqual(memory.read('LabValues'), [output, 13])
                self.assertEqual(memory.read('LabRecords[0].POS'), 4 if name == 'BSL' else 1)
                engine.step()
                self.assertEqual(memory.read('LabQueue'), dict(Slots=slots, Guard=777))

    def test_queue_unload_recovery_restores_aggregate_fields_with_unknown_values(self):
        def configure(root):
            ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
            add_fault_record_array(root,'CONTROL')
            add_fault_record_array(root,'TIMER','QueueTimers')
            add_fault_record_array(root,'TIMER','OutputTimers')
            set_fault_instruction(root,'FFU(QueueTimers[0],OutputTimers[LabIndex],LabRecords[0],?,?)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.memory.write('LabRecords[0].LEN',2)
        engine.memory.write('LabRecords[0].POS',2)
        engine.memory.write('QueueTimers[1].ACC',27)
        engine.memory.read('QueueTimers')[0]['DN'] = None
        engine.step()
        queue = copy.deepcopy(engine.memory.read('QueueTimers'))
        outputs = copy.deepcopy(engine.memory.read('OutputTimers'))
        engine.memory.write('LabIndex',2)
        engine.memory.write('StartPB',True)
        engine.step()
        self.assertEqual(engine.last_cleared_program_fault['instruction'],'FFU')
        self.assertEqual(engine.memory.read('QueueTimers'),queue)
        self.assertEqual(engine.memory.read('OutputTimers'),outputs)
        engine.step()
        self.assertEqual(engine.memory.read('QueueTimers')[0],queue[1])
        self.assertEqual(engine.memory.read('OutputTimers')[1],queue[0])

    def test_fifo_unload_keeps_destination_index_evaluation_after_the_shift(self):
        def configure(root):
            ladder_fault_fixture(root,handler_tail='MOV(1,LabQueue[1]);')
            add_fault_record_array(root,'CONTROL')
            add_fault_dint_array(root.find('./Controller/Tags'),'LabQueue',[0,3,99])
            set_fault_instruction(root,'FFU(LabQueue[0],LabValues[LabQueue[0]],LabRecords[0],?,?)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.memory.write('LabRecords[0].LEN',2)
        engine.memory.write('LabRecords[0].POS',2)
        engine.step()
        engine.memory.write('StartPB',True)
        engine.step()
        self.assertEqual(engine.last_cleared_program_fault['instruction'],'FFU')
        self.assertEqual(engine.memory.read('LabQueue'),[0,1,99])
        self.assertEqual(engine.memory.read('LabValues'),[12,13])
        engine.step()
        self.assertEqual(engine.memory.read('LabQueue'),[1,0,99])
        self.assertEqual(engine.memory.read('LabValues'),[12,0])

    def test_sequencer_array_faults_preserve_state_and_retry_with_the_same_position(self):
        for instruction,table,values in (
            ('SQI(LabQueue[0],255,LabValues[LabIndex],LabRecords[0],?,?)',[31,47,99],[12,13]),
            ('SQO(LabQueue[0],LabValues[LabIndex],LabValues[0],LabRecords[0],?,?)',[31,47,99],[13,13]),
            ('SQO(LabQueue[0],255,LabValues[LabIndex],LabRecords[0],?,?)',[31,47,99],[12,47]),
            ('SQO(LabQueue[0],16#FFFFFFFF,LabValues[LabIndex],LabRecords[0],?,?)',[31,47,99],[12,47]),
            ('SQL(LabQueue[0],LabValues[LabIndex],LabRecords[0],?,?)',[31,13,99],[12,13]),
            ('SQL(LabQueue[LabIndex],12,LabRecords[0],?,?)',[31,47,12],[12,13]),
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
                    add_fault_record_array(root,'CONTROL')
                    add_fault_dint_array(root.find('./Controller/Tags'),'LabQueue',[31,47,99])
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                comparison = instruction.startswith('SQI')
                engine.memory.write('LabRecords[0].LEN',1)
                engine.memory.write('LabRecords[0].POS',int(comparison))
                engine.memory.write('LabIndex',3)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                controls = copy.deepcopy(engine.memory.read('LabRecords'))
                engine.memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,instruction[:3]))
                self.assertEqual(engine.memory.read('LabRecords'),controls)
                self.assertEqual(engine.memory.read('LabQueue'),[31,47,99])
                self.assertEqual(engine.memory.read('LabValues'),[12,13])
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                engine.step()
                self.assertEqual(engine.memory.read('LabRecords[0].POS'),1)
                self.assertEqual(engine.memory.read('LabRecords')[1],controls[1])
                self.assertFalse(engine.memory.read('LabRecords[0].ER'))
                self.assertEqual(engine.memory.read('LabQueue'),table)
                self.assertEqual(engine.memory.read('LabValues'),values)
                self.assertEqual(engine.memory.read('SpeedCommand'),51 if comparison else 52)
                self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_held_sqo_array_fault_keeps_position_without_rearming_edge(self):
        def configure(root):
            controller_fault_fallback_fixture(root,controller_tail='MOV(1,LabIndex);')
            add_fault_record_array(root,'CONTROL')
            add_fault_dint_array(root.find('./Controller/Tags'),'LabQueue',[31,47,99])
            set_fault_instruction(root,'SQO(LabQueue[0],255,LabValues[LabIndex],LabRecords[0],?,?)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.memory.write('LabRecords[0].LEN',2)
        engine.memory.write('LabRecords[0].POS',0)
        engine.step()
        engine.memory.write('StartPB',True)
        engine.step()
        controls = copy.deepcopy(engine.memory.read('LabRecords'))
        self.assertEqual(engine.memory.read('LabValues'),[47,13])
        engine.memory.write('LabIndex',2)
        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['instruction'],fault['handler']['routine']),('SQO','FaultHandler/Capture'))
        self.assertEqual(engine.memory.read('LabRecords'),controls)
        self.assertEqual(engine.memory.read('LabValues'),[47,13])
        engine.step()
        self.assertEqual(engine.memory.read('LabRecords'),controls)
        self.assertEqual(engine.memory.read('LabValues'),[47,47])

    def test_sql_row_fault_precedes_source_read_and_retries_without_crossing_the_table(self):
        for member in (False, True):
            with self.subTest(member=member):
                self.setUp()
                engine = self.engine(mutate=lambda root: sql_row_fault_fixture(root, member=member))
                self.assertEqual(engine.blockers, [])
                memory = engine.memory
                table = 'LabQueue.Slots' if member else 'LabQueue'
                engine.step()
                saved = memory.read('LabRecords')
                memory.write('StartPB', True)

                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 20, 'SQL'))
                self.assertIn('SQL position exceeds the selected table boundary', fault['detail'])
                self.assertEqual(memory.read('LabRecords'), saved)
                self.assertEqual(memory.read(table), [31, 47, 99])
                self.assertEqual(memory.read('LabIndex'), 0)

                engine.step()
                self.assertEqual(memory.read(table), [31, 47, 66])
                updated = [saved[0] | dict(POS=2, EN=True, DN=False), saved[1]]
                self.assertEqual(memory.read('LabRecords'), updated)

                memory.write('LabIndex', 1)
                engine.step()
                self.assertIsNot(engine.last_cleared_program_fault, fault)
                self.assertEqual(memory.read('LabRecords'), updated)
                self.assertEqual(memory.read(table), [31, 47, 66])

                memory.write('LabValues[1]', 77)
                engine.step()
                self.assertEqual(memory.read(table), [31, 47, 77])
                self.assertEqual(memory.read('LabRecords'), updated)
                if member:
                    self.assertEqual(memory.read('LabQueue.Guard'), 777)

    def test_sequencer_reads_check_reached_member_row_before_live_payload(self):
        engine = self.engine(mutate=sequencer_read_rows_fixture)
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        memory.write('StartPB', True)

        engine.step()
        self.assertEqual(memory.read('LabValues'), [12, 99])
        self.assertTrue(memory.read('FaultWitness'))
        self.assertFalse(memory.read('LabRecords[0].ER'))
        self.assertFalse(memory.read('LabRecords[1].ER'))

        memory.write('LabIndex', 2)
        engine.step()
        self.assertEqual(memory.read('LabValues'), [12, 99])
        self.assertTrue(memory.read('LabRecords[0].ER'))
        self.assertTrue(memory.read('LabRecords[1].ER'))
        self.assertFalse(memory.read('FaultWitness'))
        self.assertIsNone(engine.last_cleared_program_fault)

        memory.write('LabIndex', 1)
        memory.write('LabValues[1]', 13)
        engine.step()
        self.assertEqual(memory.read('LabValues'), [12, 99])
        self.assertTrue(memory.read('FaultWitness'))
        self.assertTrue(memory.read('LabRecords[0].ER'))
        self.assertFalse(memory.read('LabRecords[1].ER'))
        self.assertEqual(memory.read('LabRecords[0].POS'), 1)
        self.assertEqual(memory.read('LabRecords[1].POS'), 1)
        self.assertEqual(memory.read('LabQueue'), dict(Slots=[31, 47, 99], Guard=777))

    def test_sequencer_row_errors_remain_separate_from_subscript_recovery(self):
        for instruction in (
            'SQI(LabQueue[LabIndex],0,LabValues[SpeedSetpoint],LabRecords[0],?,?)',
            'SQO(LabQueue[LabIndex],0,LabValues[SpeedSetpoint],LabRecords[0],?,?)',
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
                    add_fault_record_array(root,'CONTROL')
                    add_fault_dint_array(root.find('./Controller/Tags'),'LabQueue',[31,47,99])
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabRecords[0].LEN',1)
                engine.memory.write('SpeedSetpoint',99)
                engine.memory.write('StartPB',True)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertEqual(engine.memory.read('LabValues'),[12,13])
                engine.memory.write('LabIndex',3)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual(fault['instruction'],instruction[:3])
                engine.memory.write('LabRecords[0].LEN',2)
                engine.memory.write('LabIndex',2)
                engine.step()
                self.assertTrue(engine.memory.read('LabRecords[0].ER'))
                self.assertEqual(engine.memory.read('LabValues'),[12,13])
                self.assertFalse(any('recovery_source' in row for row in engine.trace))
                self.assertIs(engine.last_cleared_program_fault,fault)

    def test_negative_file_cursor_reaches_program_handler_in_all_modes(self):
        from logixlab.control_operations import default

        for name in ('FAL', 'FSC'):
            for mode, member in (('ALL', 'LEN'), ('2', 'POS'), ('INC', 'POS')):
                with self.subTest(instruction=name, mode=mode):
                    self.setUp()

                    def configure(root):
                        handler = (f'MOV(LabRecords[0].{member},FaultWords[3])'
                                   f'MOV({2 if member == "LEN" else 0},LabRecords[0].{member});')
                        ladder_fault_fixture(root, handler_tail=handler, fault_code=21)
                        add_fault_record_array(root, 'CONTROL', **(default() | dict(LEN=2)))
                        args = 'LabValues[0],99' if name == 'FAL' else 'LabValues[0]=12'
                        set_fault_instruction(root, f'{name}(LabRecords[0],?,?,{mode},{args})')

                    engine = self.engine(mutate=configure)
                    self.assertEqual(engine.blockers, [])
                    engine.memory.write(f'LabRecords[0].{member}', -1)
                    engine.memory.write('SpeedCommand', 50)
                    engine.step()
                    self.assertIsNone(engine.last_cleared_program_fault)
                    engine.memory.write('StartPB', True)
                    engine.step()

                    fault = engine.last_cleared_program_fault
                    self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 21, name))
                    self.assertEqual(fault['handler']['routine'], 'MainProgram/RecoverMove')
                    self.assertEqual(engine.memory.read('CapturedFault'), 1376260)
                    self.assertEqual(engine.memory.read('FaultWords[3]'), -1)
                    self.assertEqual(engine.memory.read('LabRecords')[0], default() | dict(LEN=2))
                    self.assertEqual(engine.memory.read('LabValues'), [12, 13])
                    self.assertEqual(engine.memory.read('SpeedCommand'), 51)
                    self.assertFalse(engine._file_incremental)
                    event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                    self.assertEqual((event['in'], event['out'], event['recovered_fault']),
                                     (True, True, {'type': 4, 'code': 21}))
                    engine.step()
                    self.assertEqual(engine.memory.read('LabValues'), [99, 13] if name == 'FAL' else [12, 13])
                    self.assertEqual(engine.memory.read('LabRecords[0].FD'), name == 'FSC')

    def test_negative_file_cursor_reaches_controller_handler_on_active_false_numeric_rung(self):
        from logixlab.control_operations import default

        def configure(root):
            controller_fault_fallback_fixture(root, fault_code=21, controller_tail='MOV(3,LabRecords[0].LEN);')
            add_fault_record_array(root, 'CONTROL', **(default() | dict(LEN=3)))
            set_fault_instruction(root, 'FSC(LabRecords[0],?,?,1,LabRecords[0].POS=2)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('StartPB', True)
        engine.memory.write('SpeedCommand', 50)
        engine.step()
        self.assertEqual(engine.memory.read('LabRecords')[0], default() | dict(LEN=3, EN=True))
        engine.memory.write('StartPB', False)
        engine.memory.write('LabRecords[0].LEN', -1)
        engine.step()

        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['type'], fault['code'], fault['handler']['routine']), (4, 21, 'FaultHandler/Capture'))
        self.assertEqual(engine.memory.read('Program:FaultHandler.SeenCode'), 1376260)
        self.assertEqual(engine.memory.read('CapturedFault'), 1376260)
        self.assertEqual(engine.memory.read('LabRecords')[0], default() | dict(LEN=3, EN=True))
        self.assertEqual(engine.memory.read('SpeedCommand'), 51)
        event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
        self.assertEqual((event['in'], event['out']), (False, False))
        engine.step()
        self.assertEqual(engine.memory.read('LabRecords[0].POS'), 1)

    def test_uncleared_negative_cursor_and_positive_position_past_length_roll_back(self):
        from logixlab.control_operations import default

        for position, detail in ((-1, 'Program fault 4/21.*without clearing'), (3, 'POS no greater than LEN')):
            with self.subTest(position=position):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root, fault_code=20)
                    add_fault_record_array(root, 'CONTROL', **(default() | dict(LEN=2)))
                    set_fault_instruction(root, 'FAL(LabRecords[0],?,?,ALL,LabValues[0],99)')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write('StartPB', True)
                engine.memory.write('LabRecords[0].POS', position)
                before = copy.deepcopy(engine.memory.values)
                with self.assertRaisesRegex(ModelError, detail):
                    engine.step()
                self.assertEqual(engine.memory.values, before)
                self.assertEqual((engine.scan_count, engine.time_ms), (0, 0))
                self.assertIsNone(engine.last_cleared_program_fault)

    def test_fal_all_restores_repeated_and_indirect_writes_before_handler(self):
        from logixlab.control_operations import default

        for dest,source,expected_queue,expected_values in (
            ('LabQueue[0]','LabQueue[0]+LabValues[LabRecords[0].POS]',[56,47,99],[12,13]),
            ('LabValues[LabRecords[0].POS]','LabQueue[LabRecords[0].POS]+1',[31,47,99],[32,48]),
        ):
            with self.subTest(destination=dest):
                self.setUp()

                def configure(root):
                    handler = ('MOV(LabQueue[0],FaultWords[3])MOV(LabValues[0],FaultWords[4])'
                               'MOV(LabRecords[0].POS,FaultWords[5])MOV(2,LabRecords[0].LEN);')
                    ladder_fault_fixture(root,handler_tail=handler)
                    add_fault_record_array(root,'CONTROL',**(default()|dict(LEN=3)))
                    add_fault_dint_array(root.find('./Controller/Tags'),'LabQueue',[31,47,99])
                    set_fault_instruction(root,f'FAL(LabRecords[0],?,?,ALL,{dest},{source})')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,'FAL'))
                self.assertEqual(engine.memory.read('FaultWords')[3:6],[31,12,0])
                self.assertEqual(engine.memory.read('LabQueue'),[31,47,99])
                self.assertEqual(engine.memory.read('LabValues'),[12,13])
                self.assertEqual(engine.memory.read('LabRecords')[0],default()|dict(LEN=2))
                engine.step()
                self.assertEqual(engine.memory.read('LabQueue'),expected_queue)
                self.assertEqual(engine.memory.read('LabValues'),expected_values)
                self.assertTrue(engine.memory.read('LabRecords[0].DN'))
                self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_numeric_file_fault_keeps_prior_chunk_and_false_rung_state(self):
        from logixlab.control_operations import default

        for name in ('FAL','FSC'):
            with self.subTest(instruction=name):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='MOV(3,LabRecords[0].LEN);')
                    add_fault_record_array(root,'CONTROL',**(default()|dict(LEN=4)))
                    add_fault_dint_array(root.find('./Controller/Tags'),'LabQueue',[31,47,99])
                    current = 'LabQueue[LabRecords[0].POS]'
                    args = f'{current},{current}+1' if name=='FAL' else f'{current}=0'
                    set_fault_instruction(root,f'{name}(LabRecords[0],?,?,2,{args})')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('StartPB',True)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                before = copy.deepcopy(engine.memory.read('LabQueue'))
                self.assertEqual(before,[32,48,99] if name=='FAL' else [31,47,99])
                control = dict(engine.memory.read('LabRecords')[0],LEN=3)
                engine.memory.write('StartPB',False)
                engine.step()
                self.assertEqual(engine.last_cleared_program_fault['instruction'],name)
                self.assertEqual(engine.memory.read('LabQueue'),before)
                self.assertEqual(engine.memory.read('LabRecords')[0],control)
                event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                self.assertEqual((event['in'],event['out']),(False,False))
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                engine.step()
                self.assertEqual(engine.memory.read('LabQueue'),[32,48,100] if name=='FAL' else before)
                self.assertEqual(engine.memory.read('LabRecords[0].POS'),2)
                self.assertTrue(engine.memory.read('LabRecords[0].DN'))

    def test_file_inc_faults_preserve_pending_edge_and_hidden_progress(self):
        from logixlab.control_operations import default

        for name in ('FAL','FSC'):
            with self.subTest(instruction=name):
                self.setUp()

                def configure(root):
                    controller_fault_fallback_fixture(root,controller_tail='CLR(LabIndex);')
                    add_fault_record_array(root,'CONTROL',**(default()|dict(LEN=2)))
                    add_fault_dint_array(root.find('./Controller/Tags'),'LabQueue',[31,47,99])
                    source = 'LabValues[LabIndex+LabRecords[0].POS]'
                    args = f'LabQueue[LabRecords[0].POS],{source}' if name=='FAL' else f'{source}=13'
                    set_fault_instruction(root,f'{name}(LabRecords[0],?,?,INC,{args})')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                for position in (0,1):
                    control = dict(engine.memory.read('LabRecords')[0])
                    progress = engine._file_incremental.copy()
                    engine.memory.write('LabIndex',2)
                    engine.memory.write('StartPB',True)
                    engine.step()
                    fault = engine.last_cleared_program_fault
                    self.assertEqual((fault['instruction'],fault['handler']['routine']),(name,'FaultHandler/Capture'))
                    self.assertEqual(engine.memory.read('LabRecords')[0],control)
                    self.assertEqual(engine._file_incremental,progress)
                    engine.step()
                    self.assertEqual(engine.memory.read('LabRecords[0].POS'),position)
                    self.assertEqual(engine._file_incremental,{('labrecords',(0,))})
                    if position==0:
                        engine.memory.write('StartPB',False)
                        engine.step()
                self.assertTrue(engine.memory.read('LabRecords[0].DN'))
                self.assertEqual(engine.memory.read('LabRecords[0].FD'),name=='FSC')
                self.assertEqual(engine.memory.read('LabQueue'),[12,13,99] if name=='FAL' else [31,47,99])

    def test_completed_inc_clears_progress_for_the_original_control_address(self):
        from logixlab.control_operations import default

        def configure(root):
            ladder_fault_fixture(root)
            add_fault_record_array(root,'CONTROL',**(default()|dict(LEN=2)))
            set_fault_instruction(root,'FSC(LabRecords[1-LabRecords[0].POS],?,?,INC,LabValues[0]=0)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.memory.write('LabRecords[0].POS',1)
        engine.memory.write('LabRecords[0].DN',True)
        engine.memory.write('LabRecords[0].EN',True)
        engine._file_incremental.update({('labrecords',(0,)),('labrecords',(1,))})
        engine.step()
        self.assertEqual(engine.memory.read('LabRecords[0].POS'),0)
        self.assertFalse(engine.memory.read('LabRecords[0].DN'))
        self.assertEqual(engine._file_incremental,{('labrecords',(1,))})

    def test_bit_diagnostic_result_fault_restores_both_cursors_before_handler(self):
        for name,single in (('FBC',False),('DDT',True)):
            with self.subTest(instruction=name):
                self.setUp()

                def configure(root):
                    handler = ('MOV(LabRecords[0].POS,FaultWords[3])'
                               'MOV(LabRecords[1].POS,FaultWords[4])MOV(1,LabIndex);')
                    controller_fault_fallback_fixture(root,controller_tail=handler)
                    add_bit_diagnostic_tags(root,single=single)
                    set_fault_instruction(root,f'{name}(LabValues[0],LabQueue[0],LabResults[LabIndex],'
                                              'LabRecords[0],?,?,LabRecords[1],?,?)')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabRecords[1].LEN',2)
                engine.memory.write('LabRecords[1].POS',2)
                engine.memory.write('LabRecords[1].DN',True)
                engine.memory.write('LabIndex',3)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                before = copy.deepcopy(engine.memory.read('LabRecords'))
                engine.memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['instruction'],fault['handler']['routine']),(name,'FaultHandler/Capture'))
                self.assertEqual(engine.memory.read('FaultWords')[3:5],[0,2])
                self.assertEqual(engine.memory.read('LabRecords'),before)
                self.assertEqual(engine.memory.read('LabQueue'),[0,0,99])
                self.assertEqual(engine.memory.read('LabResults'),[-1,-1,88])
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                engine.step()
                self.assertEqual(engine.memory.read('LabRecords[0].POS'),3 if single else 4)
                self.assertEqual(engine.memory.read('LabResults'),[-1,2,88 if single else 3])
                self.assertEqual(engine.memory.read('LabQueue'),[4 if single else 0,0,99])
                if single:
                    engine.memory.write('StartPB',False)
                    engine.step()
                    before = copy.deepcopy(engine.memory.read('LabRecords'))
                    engine.memory.write('LabIndex',3)
                    engine.memory.write('StartPB',True)
                    engine.step()
                    self.assertEqual(engine.memory.read('FaultWords')[3:5],[3,1])
                    self.assertEqual(engine.memory.read('LabRecords'),before)
                    self.assertEqual(engine.memory.read('LabResults'),[-1,2,88])
                    self.assertEqual(engine.memory.read('LabQueue'),[4,0,99])
                    engine.step()
                    self.assertEqual(engine.memory.read('LabResults'),[-1,2,3])
                    self.assertEqual(engine.memory.read('LabQueue'),[12,0,99])
                    self.assertTrue(engine.memory.read('LabRecords[0].DN'))

    def test_bit_diagnostic_input_fault_does_not_consume_enable(self):
        for name,source,reference in (
            ('FBC','LabValues[LabIndex]','LabQueue[0]'),
            ('DDT','LabValues[0]','LabQueue[LabIndex]'),
        ):
            with self.subTest(instruction=name):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='CLR(LabIndex);')
                    add_bit_diagnostic_tags(root)
                    set_fault_instruction(root,f'{name}({source},{reference},LabResults[0],'
                                              'LabRecords[0],?,?,LabRecords[1],?,?)')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabRecords[1].LEN',2)
                engine.memory.write('LabIndex',3)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                before = copy.deepcopy(engine.memory.read('LabRecords'))
                engine.memory.write('StartPB',True)
                engine.step()
                self.assertEqual(engine.last_cleared_program_fault['instruction'],name)
                self.assertEqual(engine.memory.read('LabRecords'),before)
                self.assertEqual(engine.memory.read('LabResults'),[-1,-1,88])
                engine.step()
                self.assertTrue(engine.memory.read('LabRecords[0].DN'))
                self.assertEqual(engine.memory.read('LabResults'),[2,3,88])
                self.assertEqual(engine.memory.read('LabQueue'),[12 if name=='DDT' else 0,0,99])

    def test_bit_diagnostic_result_slot_fault_restores_earlier_writes_before_handler(self):
        for name in ('FBC', 'DDT'):
            with self.subTest(name=name):
                self.setUp()
                engine = self.engine(mutate=lambda root: bit_result_slot_fault_fixture(root, name))
                self.assertEqual(engine.blockers, [])
                memory = engine.memory
                engine.step()
                saved = memory.read('LabRecords')
                memory.write('StartPB', True)

                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 20, name))
                self.assertIn('result position exceeds the selected array boundary', fault['detail'])
                self.assertEqual(memory.read('LabRecords'), saved)
                self.assertEqual(memory.read('LabResults'), [-1, -1, 88])
                self.assertEqual(memory.read('LabQueue'), [0, 0, 99])
                self.assertTrue(memory.read('FaultWitness'))
                self.assertEqual(memory.read('LabIndex'), 1)

                engine.step()
                self.assertEqual(memory.read('LabResults'), [-1, 2, 3])
                self.assertEqual(memory.read('LabQueue'), [12 if name == 'DDT' else 0, 0, 99])
                self.assertTrue(memory.read('LabRecords[0].DN'))
                self.assertTrue(memory.read('LabRecords[1].DN'))

    def test_bit_diagnostic_skips_unused_result_and_keeps_short_input_window_rollback(self):
        def configure(root):
            ladder_fault_fixture(root)
            add_bit_diagnostic_tags(root)
            set_fault_instruction(root,'DDT(LabValues[0],LabQueue[0],LabResults[LabIndex],'
                                       'LabRecords[0],?,?,LabRecords[1],?,?)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.memory.write('LabRecords[1].LEN',2)
        engine.memory.write('LabIndex',3)
        engine.memory.write('LabQueue[0]',12)
        engine.memory.write('StartPB',True)
        engine.step()
        self.assertTrue(engine.memory.read('LabRecords[0].DN'))
        self.assertIsNone(engine.last_cleared_program_fault)
        engine.memory.write('StartPB',False)
        engine.step()
        engine.memory.write('StartPB',True)
        engine.memory.write('LabQueue[0]',0)
        engine.memory.write('LabRecords[0].LEN',65)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError,'exceeds the modeled array/member boundary'):
            engine.step()
        self.assertEqual(engine.memory.values,before)
        self.assertIsNone(engine.last_cleared_program_fault)

    def test_dtr_array_fault_preserves_reference_on_both_rung_states(self):
        for power in (False,True):
            with self.subTest(power=power):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root, handler_tail='MOV(1,LabIndex);')
                    root.find('./Controller/Tags/Tag[@Name="LabIndex"]/Data/DataValue').set('Value', '2')
                    set_fault_instruction(root, 'DTR(7,255,LabValues[LabIndex])')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                self.assertEqual(engine.memory.read('LabValues'), [12, 13])
                self.assertIsNone(engine.last_cleared_program_fault)
                engine.memory.write('StartPB',power)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                self.assertEqual(engine.last_cleared_program_fault['instruction'],'DTR')
                self.assertEqual(engine.memory.read('LabValues'),[12,13])
                self.assertEqual(engine.memory.read('SpeedCommand'),51 if power else 50)
                event = next(event for row in engine.trace for event in row['events'] if 'recovered_fault' in event)
                self.assertEqual((event['in'],event['out']),(power,power))
                engine.step()
                self.assertEqual(engine.memory.read('LabValues'),[12,7])
                self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_sort_array_fault_preserves_array_until_the_selected_window_is_valid(self):
        def configure(root):
            ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
            add_array_calculation_tags(root)
            set_fault_instruction(root,'SRT(LabQueue[LabIndex],0,LabRecords[0],?,?)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.memory.write('LabIndex',5)
        engine.memory.write('SpeedCommand',50)
        engine.step()
        self.assertIsNone(engine.last_cleared_program_fault)
        before = copy.deepcopy(engine.memory.read('LabRecords'))
        engine.memory.write('StartPB',True)
        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,'SRT'))
        self.assertEqual(engine.memory.read('LabRecords'),before)
        self.assertEqual(engine.memory.read('LabQueue'),[99,6,2,4,77])
        self.assertEqual(engine.memory.read('SpeedCommand'),51)
        engine.step()
        self.assertEqual(engine.memory.read('LabQueue'),[99,2,4,6,77])
        self.assertTrue(engine.memory.read('LabRecords[0].DN'))
        self.assertEqual(engine.memory.read('LabRecords[0].POS'),0)
        self.assertEqual(engine.memory.read('LabRecords')[1],before[1])
        engine.memory.write('LabIndex',5)
        engine.step()
        self.assertIs(engine.last_cleared_program_fault,fault)
        self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_statistics_array_faults_preserve_result_and_control_for_the_next_scan(self):
        for name,expected in (('AVE',4.0),('STD',2.0)):
            for source,dest,output in (
                ('LabQueue[LabIndex]','LabStats[0]',0),
                ('LabQueue[1]','LabStats[LabIndex]',1),
            ):
                with self.subTest(instruction=name,source=source):
                    self.setUp()

                    def configure(root):
                        controller_fault_fallback_fixture(root,controller_tail='MOV(1,LabIndex);')
                        add_array_calculation_tags(root)
                        set_fault_instruction(root,f'{name}({source},0,{dest},LabRecords[0],?,?)')

                    engine = self.engine(mutate=configure)
                    self.assertEqual(engine.blockers,[])
                    engine.memory.write('LabIndex',5)
                    engine.step()
                    self.assertIsNone(engine.last_cleared_program_fault)
                    before = copy.deepcopy(engine.memory.read('LabRecords'))
                    engine.memory.write('StartPB',True)
                    engine.step()
                    fault = engine.last_cleared_program_fault
                    self.assertEqual((fault['instruction'],fault['handler']['routine']),(name,'FaultHandler/Capture'))
                    self.assertEqual(engine.memory.read('LabRecords'),before)
                    self.assertEqual(engine.memory.read('LabStats'),[11.0,22.0])
                    engine.step()
                    results = [11.0,22.0]
                    results[output] = expected
                    self.assertEqual(engine.memory.read('LabStats'),results)
                    self.assertEqual(engine.memory.read('LabRecords[0].POS'),3)
                    self.assertTrue(engine.memory.read('LabRecords[0].DN'))
                    self.assertEqual(engine.memory.read('LabRecords')[1],before[1])
                    self.assertEqual(engine.memory.read('LabQueue'),[99,6,2,4,77])
                    engine.memory.write('LabIndex',5)
                    engine.step()
                    self.assertIs(engine.last_cleared_program_fault,fault)
                    self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_std_negative_cursor_clears_through_program_handler(self):
        for member, correction in (('LEN', 3), ('POS', 0)):
            with self.subTest(member=member):
                self.setUp()

                def configure(root):
                    repair = f'MOV(LabRecords[0].{member},FaultWords[3])MOV({correction},LabRecords[0].{member});'
                    ladder_fault_fixture(root, fault_code=21, handler_tail=repair)
                    add_array_calculation_tags(root)
                    set_fault_instruction(root, 'STD(LabQueue[1],0,LabStats[0],LabRecords[0],?,?)')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                control = dict(engine.memory.read('LabRecords')[0])
                engine.memory.write(f'LabRecords[0].{member}', -1)
                engine.memory.write('StartPB', True)
                engine.step()

                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 21, 'STD'))
                self.assertEqual(fault['handler']['routine'], 'MainProgram/RecoverMove')
                self.assertEqual(engine.memory.read('FaultWords[3]'), -1)
                self.assertEqual(engine.memory.read('LabRecords')[0], control)
                self.assertEqual(engine.memory.read('LabStats'), [11.0, 22.0])
                engine.step()
                self.assertEqual(engine.memory.read('LabStats'), [2.0, 22.0])
                self.assertTrue(engine.memory.read('LabRecords[0].DN'))

    def test_sort_negative_cursor_latches_error_before_controller_handler(self):
        for member, correction in (('LEN', 3), ('POS', 0)):
            with self.subTest(member=member):
                self.setUp()

                def configure(root):
                    repair = f'MOV({correction},LabRecords[0].{member});'
                    controller_fault_fallback_fixture(root, fault_code=21,
                        program_tail='XIC(LabRecords[0].ER)MOV(1,LabIndex);',
                        controller_tail=repair)
                    add_array_calculation_tags(root)
                    set_fault_instruction(root, 'SRT(LabQueue[1],0,LabRecords[0],?,?)')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write(f'LabRecords[0].{member}', -1)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertFalse(engine.memory.read('LabRecords[0].ER'))
                engine.memory.write('StartPB', True)
                engine.memory.write('SpeedCommand', 50)
                engine.step()

                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 21, 'SRT'))
                self.assertEqual(fault['handler']['routine'], 'FaultHandler/Capture')
                self.assertEqual(engine.memory.read('LabIndex'), 1)
                self.assertEqual(engine.memory.read(f'LabRecords[0].{member}'), correction)
                self.assertTrue(engine.memory.read('LabRecords[0].ER'))
                self.assertEqual(engine.memory.read('LabQueue'), [99, 6, 2, 4, 77])
                self.assertEqual(engine.memory.read('SpeedCommand'), 51)
                engine.step()
                self.assertEqual(engine.memory.read('LabQueue'), [99, 6, 2, 4, 77])
                engine.memory.write('LabRecords[0].ER', False)
                engine.step()
                self.assertEqual(engine.memory.read('LabQueue'), [99, 2, 4, 6, 77])
                self.assertTrue(engine.memory.read('LabRecords[0].DN'))

    def test_uncleared_sort_fault_and_ave_negative_length_roll_back(self):
        cases = (
            ('SRT(LabQueue[1],0,LabRecords[0],?,?)', 'Program fault 4/21.*without clearing'),
            ('AVE(LabQueue[1],0,LabStats[0],LabRecords[0],?,?)', 'AVE requires at least one'),
        )
        for instruction, detail in cases:
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root, fault_code=20)
                    add_array_calculation_tags(root)
                    set_fault_instruction(root, instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers, [])
                engine.memory.write('LabRecords[0].LEN', -1)
                engine.memory.write('StartPB', True)
                before = copy.deepcopy(engine.memory.values)
                with self.assertRaisesRegex(ModelError, detail):
                    engine.step()
                self.assertEqual(engine.memory.values, before)
                self.assertEqual((engine.scan_count, engine.time_ms), (0, 0))
                self.assertIsNone(engine.last_cleared_program_fault)

    def test_sort_and_statistics_short_windows_keep_scan_rollback(self):
        for instruction in (
            'SRT(LabQueue[LabIndex],0,LabRecords[0],?,?)',
            'AVE(LabQueue[LabIndex],0,LabStats[0],LabRecords[0],?,?)',
            'STD(LabQueue[LabIndex],0,LabStats[0],LabRecords[0],?,?)',
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root)
                    add_array_calculation_tags(root)
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabIndex',4)
                engine.memory.write('StartPB',True)
                before = copy.deepcopy(engine.memory.values)
                with self.assertRaisesRegex(ModelError,'selected dimension/member boundary'):
                    engine.step()
                self.assertEqual(engine.memory.values,before)
                self.assertIsNone(engine.last_cleared_program_fault)

    def test_bcd_size_and_truncate_array_faults_skip_the_result_write(self):
        cases = (
            ('FRD(LabValues[LabIndex],SpeedCommand)',0x23,[12,0x23],24),
            ('FRD(16#1234,LabValues[LabIndex])',13,[12,1234],52),
            ('TOD(LabValues[LabIndex],SpeedCommand)',13,[12,13],20),
            ('TOD(1234,LabValues[LabIndex])',13,[12,0x1234],52),
            ('TRN(LabStats[LabIndex],LabValues[0])',13,[-6,13],52),
            ('TRN(-12.75L,LabValues[LabIndex])',13,[12,-12],52),
            ('SIZE(LabValues[LabIndex],0,SpeedCommand)',13,[12,13],3),
            ('SIZE(LabValues,LabValues[LabIndex],LabValues[0])',0,[2,0],52),
            ('SIZE(LabValues,0,LabValues[LabIndex])',13,[12,2],52),
        )
        for instruction,saved,values,speed in cases:
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    controller_fault_fallback_fixture(root,controller_tail='MOV(1,LabIndex);')
                    add_array_calculation_tags(root)
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabValues[1]',saved)
                engine.memory.write('LabStats[1]',-6.75)
                engine.memory.write('LabIndex',2)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                engine.memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                mnemonic = instruction.split('(',1)[0]
                self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,mnemonic))
                self.assertEqual(fault['handler']['routine'],'FaultHandler/Capture')
                self.assertEqual(engine.memory.read('LabValues'),[12,saved])
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                engine.step()
                self.assertEqual(engine.memory.read('LabValues'),values)
                self.assertEqual(engine.memory.read('LabStats'),[11.0,-6.75])
                self.assertEqual(engine.memory.read('SpeedCommand'),speed)
                self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_conversion_range_and_size_dimension_errors_keep_scan_rollback(self):
        for instruction,message in (
            ('TOD(-1,LabValues[0])','TOD source outside'),
            ('SIZE(LabValues,LabIndex,LabValues[0])','SIZE dimension exceeds array rank'),
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root)
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabIndex',1)
                engine.memory.write('StartPB',True)
                before = copy.deepcopy(engine.memory.values)
                with self.assertRaisesRegex(ModelError,message):
                    engine.step()
                self.assertEqual(engine.memory.values,before)
                self.assertIsNone(engine.last_cleared_program_fault)

    def test_standalone_math_array_faults_preserve_result_and_continue_rung(self):
        cases = (
            ('SQR(LabValues[LabIndex],LabValues[0])',[4,13],[11.0,22.0]),
            ('SQR(2147483648L,LabValues[LabIndex])',[12,46341],[11.0,22.0]),
            ('XPY(LabValues[LabIndex],2,LabValues[0])',[169,13],[11.0,22.0]),
            ('XPY(2L,LabValues[LabIndex],LabValues[0])',[8192,13],[11.0,22.0]),
            ('LN(LabStats[LabIndex],LabValues[0])',[3,13],[11.0,22.0]),
            ('LOG(100,LabValues[LabIndex])',[12,2],[11.0,22.0]),
            ('DEG(1,LabValues[LabIndex])',[12,57],[11.0,22.0]),
            ('RAD(180,LabValues[LabIndex])',[12,3],[11.0,22.0]),
            ('SIN(1.5707963267948966L,LabStats[LabIndex])',[12,13],[11.0,1.0]),
            ('COS(0,LabStats[LabIndex])',[12,13],[11.0,1.0]),
            ('TAN(0,LabValues[LabIndex])',[12,0],[11.0,22.0]),
            ('ASN(1,LabValues[LabIndex])',[12,2],[11.0,22.0]),
            ('ACS(1,LabValues[LabIndex])',[12,0],[11.0,22.0]),
            ('ATN(0,LabValues[LabIndex])',[12,0],[11.0,22.0]),
        )
        for instruction,values,stats in cases:
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    controller_fault_fallback_fixture(root,controller_tail='MOV(1,LabIndex);')
                    add_array_calculation_tags(root)
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabIndex',2)
                engine.memory.write('SpeedCommand',50)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                engine.memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                name = instruction.split('(',1)[0]
                self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,name))
                self.assertEqual(fault['handler']['routine'],'FaultHandler/Capture')
                self.assertEqual(engine.memory.read('LabValues'),[12,13])
                self.assertEqual(engine.memory.read('LabStats'),[11.0,22.0])
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                engine.step()
                self.assertEqual(engine.memory.read('LabValues'),values)
                self.assertEqual(engine.memory.read('LabStats'),stats)
                self.assertEqual(engine.memory.read('SpeedCommand'),52)
                self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_standalone_math_domain_and_overflow_keep_scan_rollback(self):
        for instruction,message in (
            ('LN(-1,LabValues[0])','LN outside the finite'),
            ('ACS(2,LabValues[0])','ACS outside the finite'),
            ('XPY(2L,64,LabValues[0])','DINT overflow in XPY'),
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root)
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('StartPB',True)
                before = copy.deepcopy(engine.memory.values)
                with self.assertRaisesRegex(ModelError,message):
                    engine.step()
                self.assertEqual(engine.memory.values,before)
                self.assertIsNone(engine.last_cleared_program_fault)

    def test_string_array_faults_skip_result_and_continue_the_rung(self):
        cases = (
            ('CONCAT(LabText[0],LabText[1],LabTextResults[LabIndex])','LabTextResults[1]','AbC123AbCXY'),
            ('MID(LabText[0],3,LabPositions[LabIndex],LabTextResults[1])','LabTextResults[1]','AbC'),
            ('DTOS(LabValues[LabIndex],LabTextResults[1])','LabTextResults[1]','13'),
            ('STOD(LabText[0],LabValues[LabIndex])','LabValues[1]',123),
            ('FIND(LabText[0],LabText[1],LabPositions[LabIndex],LabValues[0])','LabValues[0]',0),
            ('INSERT(LabText[0],LabText[LabIndex],1,LabTextResults[1])','LabTextResults[1]','XYAbC123AbC'),
            ('DELETE(LabText[0],LabPositions[LabIndex],1,LabTextResults[1])','LabTextResults[1]','bC123AbC'),
            ('LOWER(LabText[0],LabTextResults[LabIndex])','LabTextResults[1]','abc123abc'),
            ('UPPER(LabText[LabIndex],LabTextResults[1])','LabTextResults[1]','XY'),
            ('STOR(LabText[0],LabReals[LabIndex])','LabReals[1]',123.0),
            ('RTOS(LabReals[LabIndex],LabTextResults[1])','LabTextResults[1]','6.25'),
        )
        for instruction, target, expected in cases:
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
                    add_string_recovery_tags(root)
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabIndex',2)
                engine.memory.write('SpeedCommand',50)
                results = ('LabTextResults','LabValues','LabReals')
                saved = {name:copy.deepcopy(engine.memory.read(name)) for name in results}
                self.assertIsNone(saved['LabTextResults'][1]['DATA'][20])
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertEqual(engine.memory.read('LabIndex'),2)

                engine.memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                name = instruction.split('(',1)[0]
                self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,name))
                self.assertEqual(engine.memory.read('LabIndex'),1)
                self.assertEqual(engine.memory.read('SpeedCommand'),51)
                for result in results:
                    self.assertEqual(engine.memory.read(result),saved[result])

                engine.step()
                if isinstance(expected,str):
                    self.assertEqual(engine.memory.string(target),expected)
                    data = engine.memory.read(target)['DATA']
                    self.assertEqual(data[len(expected):],saved['LabTextResults'][1]['DATA'][len(expected):])
                else:
                    self.assertEqual(engine.memory.read(target),expected)
                    self.assertEqual(engine.memory.read('LabTextResults'),saved['LabTextResults'])
                self.assertEqual(engine.memory.read('LabTextResults[0]'),saved['LabTextResults'][0])
                self.assertEqual(engine.memory.read('SpeedCommand'),52)
                self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_string_operand_and_capacity_errors_keep_scan_rollback(self):
        for instruction, updates, message in (
            ('MID(LabText[0],3,LabPositions[0],LabTextResults[0])',{'LabPositions[0]':80},'(?i)MID.*(range|window|LEN)'),
            ('CONCAT(LabText[0],LabText[1],LabTextResults[0])',{'LabText[0]':'A'*82},'exceeds capacity'),
            ('STOR(LabText[1],LabReals[0])',{},'(?i)decimal|digit'),
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
                    add_string_recovery_tags(root)
                    set_fault_instruction(root,instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('StartPB',True)
                for ref,value in updates.items():
                    engine.memory.write(ref,value)
                before = copy.deepcopy(engine.memory.values)
                with self.assertRaisesRegex(ModelError,message):
                    engine.step()
                self.assertEqual(engine.memory.values,before)
                self.assertEqual(engine.scan_count,0)
                self.assertIsNone(engine.last_cleared_program_fault)

    def test_gsv_array_fault_preserves_the_complete_clock_window(self):
        from test_gsv_wall_clock import FIELDS, MICROSECONDS

        def configure(root):
            controller_fault_fallback_fixture(root,controller_tail='CLR(LabIndex);')
            add_system_value_recovery_tags(root)
            set_fault_instruction(root,'GSV(WallClockTime,,DateTime,LabClockWords[LabIndex])')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.memory.write('LabIndex',9)
        engine.memory.write('SpeedCommand',50)
        engine.step()
        self.assertIsNone(engine.last_cleared_program_fault)
        self.assertEqual(engine.memory.read('LabIndex'),9)
        engine.memory.write('StartPB',True)
        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,'GSV'))
        self.assertEqual(fault['handler']['routine'],'FaultHandler/Capture')
        self.assertEqual(engine.memory.read('LabClockWords'),[77]*9)
        self.assertEqual(engine.memory.read('SpeedCommand'),51)

        with patch('logixlab.wall_clock.time.time_ns',return_value=MICROSECONDS*1000):
            engine.step()
        self.assertEqual(engine.memory.read('LabClockWords'),[*FIELDS,77,77])
        self.assertEqual(engine.memory.read('SpeedCommand'),52)
        self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_ssv_array_fault_keeps_the_live_task_setting_until_a_later_scan(self):
        def configure(root):
            ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
            add_system_value_recovery_tags(root)
            set_fault_instruction(root,'SSV(Task,THIS,Watchdog,LabSetpoints[LabIndex])'
                                       'GSV(Task,THIS,Watchdog,LabValues[0])')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.memory.write('LabIndex',2)
        engine.memory.write('SpeedCommand',50)
        engine.step()
        self.assertIsNone(engine.last_cleared_program_fault)
        self.assertEqual(engine.memory.read('LabIndex'),2)
        engine.memory.write('StartPB',True)
        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,'SSV'))
        self.assertEqual(engine.memory.read('LabValues'),[500000,13])
        self.assertEqual(engine.memory.read('SpeedCommand'),51)

        engine.step()
        self.assertEqual(engine.memory.read('LabValues'),[650000,13])
        self.assertEqual(engine.memory.read('SpeedCommand'),52)
        self.assertFalse(any('recovery_source' in row for row in engine.trace))

    def test_system_value_short_window_and_invalid_setting_keep_scan_rollback(self):
        for instruction,index,message in (
            ('GSV(WallClockTime,,DateTime,LabClockWords[LabIndex])',8,'modeled array/member boundary'),
            ('SSV(Task,THIS,Watchdog,LabSetpoints[LabIndex])',0,'SSV Watchdog requires'),
        ):
            with self.subTest(instruction=instruction):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail='CLR(LabIndex);')
                    add_system_value_recovery_tags(root)
                    set_fault_instruction(root,'MOV(42,SpeedSetpoint)'+instruction)

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                engine.memory.write('LabIndex',index)
                engine.memory.write('LabSetpoints[0]',999)
                engine.memory.write('StartPB',True)
                before = copy.deepcopy(engine.memory.values)
                schedule = engine.scheduler_description()
                with self.assertRaisesRegex(ModelError,message):
                    engine.step()
                self.assertEqual(engine.memory.values,before)
                self.assertEqual(engine.scheduler_description(),schedule)
                self.assertEqual(engine.scan_count,0)
                self.assertIsNone(engine.last_cleared_program_fault)

    def test_pid_prescan_and_false_rung_skip_unused_indexed_operands(self):
        def configure(root):
            ladder_fault_fixture(root)
            add_stateful_recovery_tags(root,'PID')
            set_fault_instruction(root,'PID(Loop,LabValues[LabIndex],0,LabOutputs[LabIndex],0,0,0)')
            tags = root.find('./Controller/Tags')
            tags.find('Tag[@Name="LabIndex"]/Data/DataValue').set('Value','2')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        self.assertEqual(engine.prescan_count,1)
        engine.memory.write('Loop.EN',True)
        engine.step()
        self.assertFalse(engine.memory.read('Loop.EN'))
        self.assertEqual(engine.memory.read('LabOutputs'),[77,88])
        self.assertEqual(engine.last_timer,{})
        self.assertEqual(engine.memory.read('LabIndex'),2)
        self.assertIsNone(engine.last_cleared_program_fault)

    def test_pid_prescan_skips_saved_out_of_bounds_record_but_false_scan_faults(self):
        def configure(root):
            ladder_fault_fixture(root, main_tail='OTE(FaultWitness);', handler_tail='MOV(1,LabIndex);')
            records = add_fault_pid_array(root)
            for ctl in records.findall('./Element/Structure/DataValueMember[@Name="CTL"]'):
                ctl.set('Value', '-2147483648')
            tags = root.find('./Controller/Tags')
            tags.find('Tag[@Name="LabIndex"]/Data/DataValue').set('Value', '2')
            ET.SubElement(tags, 'Tag', Name='LoopView', DataType='PID', TagType='Alias', AliasFor='Loop[LabIndex]')
            set_fault_instruction(root, 'PID(LoopView,LabValues[0],0,LabOutputs[LabIndex],0,0,0)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers, [])
        memory = engine.memory
        saved = copy.deepcopy(memory.read('Loop'))
        self.assertEqual(saved, engine.project.initial['loop'])
        self.assertFalse(memory.read('FaultWitness'))
        self.assertIsNone(engine.last_cleared_program_fault)
        self.assertEqual(engine.prescan_count, 1)

        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['type'], fault['code'], fault['instruction']), (4, 20, 'PID'))
        self.assertEqual(memory.read('Loop'), saved)
        self.assertEqual(memory.read('LabIndex'), 1)
        self.assertEqual(memory.read('LabOutputs'), [77, 88])
        self.assertEqual(engine.last_timer, {})

        engine.enter_run()
        self.assertTrue(memory.read('Loop[0].EN'))
        self.assertFalse(memory.read('Loop[1].EN'))
        self.assertEqual(memory.read('LabOutputs'), [77, 88])

    def test_pid_load_rejects_out_of_bounds_constant_record_subscripts(self):
        source = self.root
        for subscript in ('2', '-1', '1 + 1'):
            with self.subTest(subscript=subscript):
                self.root = copy.deepcopy(source)

                def configure(root):
                    ladder_fault_fixture(root)
                    add_fault_pid_array(root)
                    set_fault_instruction(root, f'PID(Loop[{subscript}],LabValues[0],0,LabOutputs[0],0,0,0)')

                engine = self.engine(mutate=configure)
                self.assertTrue(any('outside bounds' in blocker for blocker in engine.blockers), engine.blockers)

    def test_pid_checks_overlap_at_the_live_index(self):
        def configure(root):
            ladder_fault_fixture(root)
            add_fault_pid_array(root)
            set_fault_instruction(root,'PID(Loop[0],LabValues[0],0,Loop[LabIndex].OUT,0,0,0)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        memory = engine.memory
        memory.write('LabIndex',1)
        memory.write('StartPB',True)
        engine.step()
        self.assertEqual(memory.read('Loop[1].OUT'),57)

        memory.write('LabIndex',0)
        saved = copy.deepcopy((memory.values,engine.last_timer))
        with self.assertRaisesRegex(ModelError,'operands cannot overlap'):
            engine.step()
        self.assertEqual((memory.values,engine.last_timer),saved)
        self.assertEqual(engine.scan_count,1)
        self.assertIsNone(engine.last_cleared_program_fault)

    def test_pid_array_fault_preserves_control_record_cv_and_integral(self):
        def configure(root):
            controller_fault_fallback_fixture(root,controller_tail='CLR(LabIndex);')
            add_stateful_recovery_tags(root,'PID')
            set_fault_instruction(root,'PID(Loop,LabValues[0],0,LabOutputs[LabIndex],0,0,0)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        memory = engine.memory
        memory.write('StartPB',True)
        memory.write('SpeedCommand',50)
        engine.step()
        self.assertEqual(memory.read('LabOutputs'),[57,88])
        self.assertEqual(memory.read('Loop.DATA[0]'),19)
        saved = copy.deepcopy((memory.read('Loop'),engine.last_timer))
        memory.write('LabIndex',2)
        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,'PID'))
        self.assertEqual(fault['handler']['routine'],'FaultHandler/Capture')
        self.assertEqual((memory.read('Loop'),engine.last_timer),saved)
        self.assertEqual(memory.read('LabOutputs'),[57,88])
        self.assertEqual(memory.read('SpeedCommand'),52)

        engine.step()
        self.assertEqual(memory.read('LabOutputs'),[76,88])
        self.assertEqual(memory.read('Loop.DATA[0]'),38)
        self.assertEqual(memory.read('SpeedCommand'),53)

    def test_digital_alarm_false_rung_fault_preserves_pending_acknowledgment(self):
        def configure(root):
            ladder_fault_fixture(root,handler_tail='MOV(1,LabIndex);')
            add_stateful_recovery_tags(root,'ALMD')
            set_fault_instruction(root,'ALMD(MotorAlarm,LabValues[LabIndex].0,0,0,0)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        memory = engine.memory
        memory.write('StartPB',True)
        for _ in range(3):
            engine.step()
        self.assertTrue(memory.read('MotorAlarm.InAlarmUnack'))
        memory.write('MotorAlarm.OperAck',True)
        memory.write('StartPB',False)
        memory.write('SpeedCommand',50)
        memory.write('LabIndex',2)
        saved = copy.deepcopy((memory.read('MotorAlarm'),engine.last_timer))
        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,'ALMD'))
        self.assertEqual((memory.read('MotorAlarm'),engine.last_timer),saved)
        self.assertEqual(memory.read('SpeedCommand'),50)
        self.assertFalse(next(event['out'] for row in engine.trace for event in row['events']
                              if event.get('recovered_fault')))

        engine.step()
        self.assertTrue(memory.read('MotorAlarm.Acked'))
        self.assertFalse(memory.read('MotorAlarm.OperAck'))
        self.assertTrue(memory.read('MotorAlarm.InAlarm'))
        self.assertEqual(memory.read('MotorAlarm.AlarmCount'),1)

    def test_analog_alarm_skips_sample_without_interrupting_qualification(self):
        def configure(root):
            ladder_fault_fixture(root,handler_tail='CLR(LabIndex);')
            add_stateful_recovery_tags(root,'ALMA')
            set_fault_instruction(root,'ALMA(PressureAlarm,LabValues[LabIndex],0,0,0)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        memory = engine.memory
        memory.write('LabIndex',2)
        memory.write('SpeedCommand',50)
        engine.step()
        self.assertIsNone(engine.last_cleared_program_fault)
        memory.write('LabIndex',0)
        memory.write('LabValues[0]',90)
        memory.write('StartPB',True)
        engine.step()
        self.assertFalse(memory.read('PressureAlarm.HInAlarm'))
        memory.write('LabIndex',2)
        saved = copy.deepcopy((memory.read('PressureAlarm'),engine.last_timer))
        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,'ALMA'))
        self.assertEqual((memory.read('PressureAlarm'),engine.last_timer),saved)
        self.assertEqual(memory.read('SpeedCommand'),52)

        engine.step()
        self.assertTrue(memory.read('PressureAlarm.HInAlarm'))
        self.assertTrue(memory.read('PressureAlarm.HHInAlarm'))
        self.assertEqual(memory.read('PressureAlarm.HAlarmCount'),1)
        self.assertEqual(memory.read('SpeedCommand'),53)

    def test_for_entry_array_fault_preserves_index_until_a_valid_scan(self):
        cases = (
            ('LoopIndex[LabIndex],0,1,1',[77,2],2),
            ('LoopIndex[0],LoopBounds[LabIndex],2,1',[3,88],1),
            ('LoopIndex[0],0,LoopBounds[LabIndex],1',[3,88],3),
            ('LoopIndex[0],0,1,LoopBounds[LabIndex]',[2,88],1),
        )
        for operands,indices,visits in cases:
            with self.subTest(operands=operands):
                self.setUp()

                def configure(root):
                    controller_fault_fallback_fixture(root,controller_tail=(
                        'MOV(LoopIndex[0],FaultWords[3])MOV(LoopIndex[1],FaultWords[4])MOV(1,LabIndex);'))
                    configure_for_recovery(root,'ADD(DisplayedPartCount,1,DisplayedPartCount);')
                    set_fault_instruction(root,f'FOR(Reporting,{operands})')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                memory = engine.memory
                memory.write('LabIndex',2)
                memory.write('SpeedCommand',50)
                engine.step()
                self.assertIsNone(engine.last_cleared_program_fault)
                self.assertEqual(memory.read('LabIndex'),2)

                memory.write('StartPB',True)
                engine.step()
                fault = engine.last_cleared_program_fault
                self.assertEqual((fault['type'],fault['code'],fault['instruction']),(4,20,'FOR'))
                self.assertEqual(fault['handler']['routine'],'FaultHandler/Capture')
                self.assertEqual(memory.read('LoopIndex'),[77,88])
                self.assertEqual(memory.read('FaultWords')[3:5],[77,88])
                self.assertEqual(memory.read('DisplayedPartCount'),0)
                self.assertEqual(memory.read('SpeedCommand'),51)
                self.assertEqual(engine.calls.stack,[])
                event = next(event for visit in engine.trace for event in visit['events'] if event['instruction']=='FOR')
                self.assertEqual(event['loop_trace'],{'visits':0,'exit':'bounds'})
                if operands.startswith('LoopIndex[LabIndex]'):
                    self.assertEqual(event['operand_samples'],[None]*5)
                else:
                    self.assertEqual(event['operand_samples'][1],{'address':'LoopIndex[0]','type':'DINT','value':77})
                    missing = operands.split(',').index('LoopBounds[LabIndex]') + 1
                    self.assertIsNone(event['operand_samples'][missing])

                engine.step()
                self.assertEqual(memory.read('LoopIndex'),indices)
                self.assertEqual(memory.read('DisplayedPartCount'),visits)
                self.assertEqual(memory.read('SpeedCommand'),52)
                self.assertEqual(engine.calls.stack,[])

    def test_for_late_operand_fault_retains_completed_body_work(self):
        cases = (
            ('LoopBounds[LabIndex],1',1,2,3,5),
            ('4,LoopBounds[LabIndex]',0,1,5,7),
        )
        for bounds,slot,stopped,finished,count in cases:
            with self.subTest(bounds=bounds):
                self.setUp()

                def configure(root):
                    ladder_fault_fixture(root,handler_tail=(
                        'MOV(LoopIndex[0],FaultWords[3])'
                        f'MOV(DisplayedPartCount,FaultWords[4])MOV({slot},LabIndex);'))
                    configure_for_recovery(root,'ADD(DisplayedPartCount,1,DisplayedPartCount);',
                                           'EQU(DisplayedPartCount,2)MOV(2,LabIndex);')
                    set_fault_instruction(root,f'FOR(Reporting,LoopIndex[0],0,{bounds})')

                engine = self.engine(mutate=configure)
                self.assertEqual(engine.blockers,[])
                memory = engine.memory
                memory.write('LabIndex',slot)
                memory.write('SpeedCommand',50)
                memory.write('StartPB',True)
                engine.step()
                self.assertEqual(engine.last_cleared_program_fault['instruction'],'FOR')
                self.assertEqual(memory.read('LoopIndex'),[stopped,88])
                self.assertEqual(memory.read('FaultWords')[3:5],[stopped,2])
                self.assertEqual(memory.read('DisplayedPartCount'),2)
                self.assertEqual(memory.read('SpeedCommand'),51)
                self.assertEqual(engine.calls.stack,[])
                event = next(event for visit in engine.trace for event in visit['events'] if event['instruction']=='FOR')
                self.assertEqual(event['loop_trace'],{'visits':2,'exit':'bounds'})
                self.assertEqual(event['operand_samples'][1],{'address':'LoopIndex[0]','type':'DINT','value':stopped})
                read_position = 3 if slot else 4
                self.assertEqual(event['operand_samples'][read_position],
                                 {'address':f'LoopBounds[{slot}]','type':'DINT','value':slot+1})

                engine.step()
                self.assertEqual(memory.read('LoopIndex'),[finished,88])
                self.assertEqual(memory.read('DisplayedPartCount'),count)
                self.assertEqual(memory.read('SpeedCommand'),52)

    def test_for_body_array_fault_is_recovered_at_the_body_instruction(self):
        def configure(root):
            ladder_fault_fixture(root,handler_tail='CLR(LabIndex);')
            configure_for_recovery(root,'MOV(LabValues[LabIndex],DisplayedPartCount)'
                                   'ADD(DisplayedPartCount,1,DisplayedPartCount);')
            set_fault_instruction(root,'FOR(Reporting,LoopIndex[0],0,0,1)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers,[])
        engine.memory.write('LabIndex',2)
        engine.memory.write('StartPB',True)
        engine.memory.write('SpeedCommand',50)
        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['instruction'],fault['routine']),('MOV','MainProgram/Reporting'))
        self.assertEqual(engine.memory.read('DisplayedPartCount'),1)
        self.assertEqual(engine.memory.read('LoopIndex'),[1,88])
        self.assertEqual(engine.memory.read('SpeedCommand'),51)
        self.assertEqual(engine.calls.stack,[])

    def test_aggregate_fill_preserves_records_until_a_valid_start(self):
        from test_aggregate_fill import AggregateFillTests

        def configure(root):
            controller_fault_fallback_fixture(root)
            AggregateFillTests.fields(root)
            set_fault_instruction(root,'FLL(0,Records[LabIndex],100000)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('LabIndex',3)
        engine.memory.write('StartPB',True)
        engine.memory.write('Records[2].Count',73)
        before = copy.deepcopy(engine.memory.read('Records'))
        engine.step()
        fault = engine.last_cleared_program_fault
        self.assertEqual((fault['instruction'],fault['handler']['routine']),('FLL','FaultHandler/Capture'))
        self.assertEqual(engine.memory.read('Records'),before)
        engine.memory.write('LabIndex',2)
        engine.step()
        self.assertEqual(engine.memory.read('Records')[:2],before[:2])
        self.assertEqual(engine.memory.read('Records[2].Count'),0)
        self.assertIs(engine.last_cleared_program_fault,fault)

    def test_fill_keeps_lazy_zero_length_and_invalid_length_behavior(self):
        def configure(root):
            ladder_fault_fixture(root)
            set_fault_instruction(root,'FLL(LabValues[LabIndex],LabValues[0],SpeedCommand)')

        engine = self.engine(mutate=configure)
        self.assertEqual(engine.blockers, [])
        engine.memory.write('StartPB',True)
        engine.memory.write('LabIndex',2)
        engine.memory.write('SpeedCommand',0)
        engine.step()
        self.assertEqual(engine.memory.read('LabValues'),[12,13])
        self.assertEqual(engine.memory.read('SpeedCommand'),1)
        self.assertIsNone(engine.last_cleared_program_fault)
        engine.memory.write('SpeedCommand',-1)
        before = copy.deepcopy(engine.memory.values)
        with self.assertRaisesRegex(ModelError,'Numeric FLL length'):
            engine.step()
        self.assertEqual(engine.memory.values,before)
        self.assertEqual(engine.scan_count,1)
        self.assertIsNone(engine.last_cleared_program_fault)
