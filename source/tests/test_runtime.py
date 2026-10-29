import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as ET

from logixlab.model import Memory, ModelError, Project, parse_rung
from logixlab.runtime import Engine
from logixlab.server import Application

SAMPLE = Path(__file__).resolve().parents[1] / 'samples' / 'ConveyorDemo.L5X'


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = ET.parse(SAMPLE).getroot()

    def engine(self, rungs=None, mutate=None, mode='project', routine=''):
        if rungs is not None:
            content = self.root.find('./Controller/Programs/Program/Routines/Routine/RLLContent')
            content.clear()
            for i, text in enumerate(rungs):
                rung = ET.SubElement(content, 'Rung', Number=str(i), Type='N')
                ET.SubElement(rung, 'Text').text = text
        if mutate: mutate(self.root)
        path = Path(self.tmp.name) / 'fixture.L5X'
        ET.ElementTree(self.root).write(path, encoding='utf-8', xml_declaration=True)
        return Engine(Project(path), mode, routine)

    def test_demo_seal_in_stop_and_timer(self):
        e = self.engine()
        self.assertEqual(e.blockers, [])
        e.memory.write('StartPB', True)
        e.step(10)
        e.memory.write('StartPB', False)
        for _ in range(99): e.step(10)
        self.assertFalse(e.memory.read('MotorRunning'))
        self.assertEqual(e.memory.read('StartDelay.ACC'), 990)
        e.step(10)
        self.assertTrue(e.memory.read('MotorRunning'))
        self.assertEqual(e.memory.read('SpeedCommand'), 50)
        e.memory.write('StopPB', True)
        e.step()
        self.assertFalse(e.memory.read('MotorRunning'))
        self.assertEqual(e.memory.read('StartDelay.ACC'), 0)
        self.assertEqual(e.memory.read('SpeedCommand'), 0)

    def test_branch_executes_false_path_output(self):
        e = self.engine(['[XIC(StartPB)OTE(RunLatch),XIO(StartPB)OTE(MotorRunning)];'])
        e.memory.write('StartPB', True); e.step()
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertFalse(e.memory.read('MotorRunning'))
        e.memory.write('StartPB', False); e.step()
        self.assertFalse(e.memory.read('RunLatch'))
        self.assertTrue(e.memory.read('MotorRunning'))

    def test_nested_branch_and_series(self):
        e = self.engine(['XIO(StopPB)[XIC(StartPB),[XIC(PartSensor),XIC(ResetPB)]XIO(BatchComplete)]OTE(RunLatch);'])
        e.memory.write('ResetPB', True); e.step()
        self.assertTrue(e.memory.read('RunLatch'))
        e.memory.write('StopPB', True); e.step()
        self.assertFalse(e.memory.read('RunLatch'))

    def test_prescan_blocks_spurious_ons_and_counter_edge(self):
        e = self.engine(['XIC(StartPB)ONS(SensorMemory)OTE(PartPulse);', 'XIC(StartPB)CTU(Parts,?,?);'])
        e.memory.write('StartPB', True); e.step()
        self.assertFalse(e.memory.read('PartPulse'))
        self.assertEqual(e.memory.read('Parts.ACC'), 0)
        e.memory.write('StartPB', False); e.step()
        e.memory.write('StartPB', True); e.step()
        self.assertTrue(e.memory.read('PartPulse'))
        self.assertEqual(e.memory.read('Parts.ACC'), 1)
        e.step()
        self.assertFalse(e.memory.read('PartPulse'))
        self.assertEqual(e.memory.read('Parts.ACC'), 1)

    def test_osr_and_osf(self):
        for instruction in ('OSR','OSF'):
            with self.subTest(instruction=instruction):
                e = self.engine([f'XIC(StartPB){instruction}(SensorMemory,PartPulse);'])
                e.step(); self.assertFalse(e.memory.read('PartPulse'))
                e.memory.write('StartPB', True); e.step()
                self.assertEqual(e.memory.read('PartPulse'), instruction == 'OSR')
                e.step(); self.assertFalse(e.memory.read('PartPulse'))
                e.memory.write('StartPB', False); e.step()
                self.assertEqual(e.memory.read('PartPulse'), instruction == 'OSF')

    def test_latch_unlatch_and_afi(self):
        e = self.engine(['XIC(StartPB)OTL(RunLatch);','XIC(StopPB)OTU(RunLatch);','AFI()OTE(MotorRunning);','NOP();'])
        e.memory.write('StartPB', True); e.step()
        e.memory.write('StartPB', False); e.step()
        self.assertTrue(e.memory.read('RunLatch'))
        self.assertFalse(e.memory.read('MotorRunning'))
        e.memory.write('StopPB', True); e.step()
        self.assertFalse(e.memory.read('RunLatch'))

    def test_rto_retains_and_reset_clears(self):
        e = self.engine(['XIC(StartPB)RTO(StartDelay,?,?);','XIC(ResetPB)RES(StartDelay);'])
        e.memory.write('StartPB', True); e.step(100); e.step(100)
        e.memory.write('StartPB', False); e.step(100)
        self.assertEqual(e.memory.read('StartDelay.ACC'), 100)
        e.memory.write('StartPB', True); e.step(100)
        self.assertEqual(e.memory.read('StartDelay.ACC'), 100)
        e.step(100); self.assertEqual(e.memory.read('StartDelay.ACC'), 200)
        e.memory.write('ResetPB', True); e.step(100)
        self.assertEqual(e.memory.read('StartDelay.ACC'), 0)

    def test_tof_delays_falling_edge(self):
        e = self.engine(['XIC(StartPB)TOF(StartDelay,?,?);'])
        e.memory.write('StartDelay.PRE', 100)
        e.memory.write('StartPB', True); e.step(50)
        self.assertTrue(e.memory.read('StartDelay.DN'))
        e.memory.write('StartPB', False); e.step(50)
        self.assertTrue(e.memory.read('StartDelay.TT'))
        e.step(50); self.assertTrue(e.memory.read('StartDelay.DN'))
        e.step(50); self.assertFalse(e.memory.read('StartDelay.DN'))

    def test_counter_down_wrap_and_reset(self):
        e = self.engine(['XIC(StartPB)CTD(Parts,?,?);','XIC(ResetPB)RES(Parts);'])
        e.step(); e.memory.write('Parts.ACC', -2147483648)
        e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('Parts.ACC'), 2147483647)
        self.assertTrue(e.memory.read('Parts.UN'))
        e.memory.write('ResetPB', True); e.step()
        self.assertEqual(e.memory.read('Parts.ACC'), 0)
        self.assertFalse(e.memory.read('Parts.UN'))

    def test_counter_up_wrap(self):
        e = self.engine(['XIC(StartPB)CTU(Parts,?,?);'])
        e.step(); e.memory.write('Parts.ACC', 2147483647)
        e.memory.write('StartPB', True); e.step()
        self.assertEqual(e.memory.read('Parts.ACC'), -2147483648)
        self.assertTrue(e.memory.read('Parts.OV'))

    def test_arithmetic_known_vectors(self):
        cases=[('ADD(7,-3,SpeedCommand);',4),('SUB(7,3,SpeedCommand);',4),
               ('MUL(-7,3,SpeedCommand);',-21),('DIV(7,2,SpeedCommand);',3),
               ('DIV(5,2,SpeedCommand);',2),('MOD(-7,3,SpeedCommand);',-1),
               ('NEG(7,SpeedCommand);',-7),('ABS(-7,SpeedCommand);',7),
               ('AND(15,6,SpeedCommand);',6),('OR(8,6,SpeedCommand);',14),
               ('XOR(15,6,SpeedCommand);',9),('NOT(0,SpeedCommand);',-1),
               ('MOV(42,SpeedCommand);',42),('CLR(SpeedCommand);',0)]
        for rung,expected in cases:
            with self.subTest(rung=rung):
                e=self.engine([rung]); self.assertEqual(e.blockers,[]); e.step()
                self.assertEqual(e.memory.read('SpeedCommand'),expected)

    def test_comparison_vectors(self):
        cases=[('EQU(3,3)',True),('NEQ(3,3)',False),('LES(2,3)',True),
               ('LEQ(3,3)',True),('GRT(4,3)',True),('GEQ(3,3)',True),
               ('LIM(2,3,4)',True),('LIM(8,3,2)',False),('LIM(8,9,2)',True)]
        for compare, expected in cases:
            with self.subTest(compare=compare):
                e=self.engine([compare+'OTE(RunLatch);']);e.step()
                self.assertEqual(e.memory.read('RunLatch'),expected)

    def test_false_arithmetic_does_not_write(self):
        e=self.engine(['XIC(StartPB)ADD(5,2,SpeedCommand);'])
        e.memory.write('SpeedCommand',99);e.step()
        self.assertEqual(e.memory.read('SpeedCommand'),99)

    def test_divide_fault_rolls_back_earlier_writes_and_time(self):
        e=self.engine(['MOV(99,SpeedCommand);','DIV(1,0,DisplayedPartCount);'])
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'rolled back'): e.step()
        self.assertEqual(e.memory.values,before)
        self.assertEqual((e.scan_count,e.time_ms),(0,0))
        self.assertTrue(e.memory.first_scan)
        self.assertEqual(e.last_timer,{})

    def test_overflow_stops_and_rolls_back(self):
        e=self.engine(['ADD(2147483647,1,SpeedCommand);'])
        with self.assertRaisesRegex(ModelError,'overflow'): e.step()
        self.assertEqual(e.memory.read('SpeedCommand'),0)

    def test_unknown_instruction_in_false_path_blocks(self):
        e=self.engine(['AFI()SECRET(RunLatch);'])
        self.assertTrue(any('unsupported SECRET' in b for b in e.blockers))
        with self.assertRaises(ModelError):e.step()

    def test_unknown_operand_in_false_path_blocks(self):
        e=self.engine(['AFI()MOV(Missing,SpeedCommand);'])
        self.assertTrue(any('Unknown tag' in b for b in e.blockers))

    def test_malformed_rung_blocks(self):
        for text in ['[XIC(StartPB),XIO(StopPB);','XIC(StartPB) garbage;','MOV(1,SpeedCommand);extra']:
            with self.subTest(text=text):self.assertTrue(self.engine([text]).blockers)

    def test_alias_case_and_signed_bit(self):
        def mutate(root):
            ET.SubElement(root.find('./Controller/Tags'),'Tag',Name='CmdBit',TagType='Alias',AliasFor='SpeedCommand.31')
        e=self.engine(['OTL(CmdBit);'],mutate)
        self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('speedCOMMAND'),-2147483648)
        self.assertTrue(e.memory.read('cmdbit'))

    def test_constant_destination_blocked(self):
        def mutate(root):root.find("./Controller/Tags/Tag[@Name='SpeedCommand']").set('Constant','true')
        e=self.engine(['MOV(1,SpeedCommand);'],mutate)
        self.assertTrue(any('Read-only' in b for b in e.blockers))

    def test_parameterless_jsr_and_return(self):
        e=self.engine(['MOV(25,Parts.ACC);','JSR(Reporting,0);','TND();','MOV(99,DisplayedPartCount);'])
        e.step();self.assertEqual(e.memory.read('DisplayedPartCount'),25)

    def test_jsr_recursion_blocks(self):
        def mutate(root):
            content=root.find('./Controller/Programs/Program/Routines/Routine[@Name="Reporting"]/RLLContent')
            content.clear();rung=ET.SubElement(content,'Rung',Number='0',Type='N');ET.SubElement(rung,'Text').text='JSR(Reporting,0);'
        e=self.engine(['JSR(Reporting,0);'],mutate)
        self.assertTrue(any('Recursive' in b for b in e.blockers))

    def test_multiple_tasks_execute_and_harness_bypasses_scheduling(self):
        def mutate(root): ET.SubElement(root.find('./Controller/Tasks'),'Task',Name='Other',Type='PERIODIC',Class='Standard')
        e=self.engine(['NOP();'],mutate)
        self.assertEqual(e.blockers,[]);e.step(10)
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],1)
        harness=Engine(e.project,'routine','MainProgram/MainRoutine')
        self.assertEqual(harness.blockers,[]);harness.step()
        self.assertEqual(harness.report()['mode'],'routine')

    def test_periodic_task_interval_enforced(self):
        def mutate(root):
            t=root.find('./Controller/Tasks/Task');t.set('Type','PERIODIC');t.set('Rate','20')
        e=self.engine(['NOP();'],mutate)
        self.assertEqual(e.blockers,[])
        with self.assertRaisesRegex(ModelError,'20 ms'):e.step(10)
        e.step(20);self.assertEqual(e.time_ms,20)

    def test_safety_harness_blocked(self):
        def mutate(root):root.find('./Controller/Programs/Program').set('Class','Safety')
        e=self.engine(['NOP();'],mutate,mode='routine',routine='MainProgram/MainRoutine')
        self.assertTrue(any('safety' in b for b in e.blockers))

    def test_local_tag_shadows_global(self):
        def mutate(root):
            t=copy.deepcopy(root.find("./Controller/Tags/Tag[@Name='SpeedCommand']"))
            root.find('./Controller/Programs/Program/Tags').append(t)
        e=self.engine(['MOV(7,SpeedCommand);'],mutate);e.step()
        self.assertEqual(e.memory.read('SpeedCommand'),0)
        self.assertEqual(e.memory.read('Program:MainProgram.SpeedCommand'),7)

    def test_indirect_array_bounds_faults(self):
        def mutate(root):
            t=root.find("./Controller/Tags/Tag[@Name='SpeedCommand']")
            t.set('Dimensions','3');d=t.find('Data');d.clear();d.set('Format','Decorated')
            array=ET.SubElement(d,'Array',DataType='DINT',Dimensions='3')
            for i in range(3):ET.SubElement(array,'Element',Index=f'[{i}]',Value='0')
        e=self.engine(['MOV(7,SpeedCommand[Parts.ACC]);'],mutate)
        self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('SpeedCommand[0]'),7)
        e.memory.write('Parts.ACC',3)
        with self.assertRaisesRegex(ModelError,'bounds'):e.step()
        self.assertEqual(e.scan_count,1)

    def test_first_scan_flag(self):
        e=self.engine(['XIC(S:FS)OTE(RunLatch);'])
        e.step();self.assertTrue(e.memory.read('RunLatch'))
        e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_snapshot_and_reset_are_separate_from_source(self):
        app=Application(self.tmp.name)
        result=app.command('demo',{})
        source_hash=app.engine.project.sha256
        app.command('write',{'tag':'StartPB','value':True})
        app.command('step',{'dt':10})
        self.assertEqual(app.command('snapshot',{})['scan'],1)
        result=app.command('reset',{})
        self.assertEqual(result['scan'],0)
        self.assertFalse(app.engine.memory.read('StartPB'))
        self.assertEqual(Project(SAMPLE).sha256,source_hash)

    def test_inhibited_task_remains_idle_without_blocking_clock_advancement(self):
        def mutate(root):root.find('./Controller/Tasks/Task').set('InhibitTask','true')
        e=self.engine(['MOV(99,SpeedCommand);'],mutate)
        self.assertEqual(e.blockers,[]);e.step(10)
        self.assertEqual(e.memory.read('SpeedCommand'),0)
        self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],0)

    def test_missing_initial_data_is_not_silently_zeroed(self):
        def mutate(root):
            tag=root.find("./Controller/Tags/Tag[@Name='SpeedCommand']")
            tag.remove(tag.find('Data'))
        e=self.engine(['MOV(1,SpeedCommand);'],mutate)
        self.assertTrue(any('Initial data missing' in b for b in e.blockers))

    def test_udt_member_type_and_value_are_preserved(self):
        def mutate(root):
            dtype=ET.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='MachineState')
            members=ET.SubElement(dtype,'Members')
            ET.SubElement(members,'Member',Name='Count',DataType='DINT',Dimension='0',Hidden='false')
            tag=ET.SubElement(root.find('./Controller/Tags'),'Tag',Name='State',TagType='Base',DataType='MachineState')
            data=ET.SubElement(tag,'Data',Format='Decorated')
            struct=ET.SubElement(data,'Structure',DataType='MachineState')
            ET.SubElement(struct,'DataValueMember',Name='Count',DataType='DINT',Value='12')
        e=self.engine(['ADD(State.Count,3,State.Count);'],mutate)
        self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('State.Count'),15)
        self.assertEqual(e.memory.resolve('State.Count')[2],'DINT')

    def test_constant_timer_is_rejected_before_direct_mutation(self):
        def mutate(root):root.find("./Controller/Tags/Tag[@Name='StartDelay']").set('Constant','true')
        e=self.engine(['TON(StartDelay,?,?);'],mutate)
        self.assertTrue(any('Constant timer' in b for b in e.blockers))


if __name__=='__main__':unittest.main(verbosity=2)
