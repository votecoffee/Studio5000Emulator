"""Aliases and bounded indirect starts for ladder shifts and FIFO/LIFO."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_control_operations as controls
import test_fifo_records as records
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


def scalar(parent,name,dtype,value):
    tag=E.SubElement(parent,'Tag',Name=name,DataType=dtype,TagType='Base')
    E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(value))


class QueueReferenceTests(unittest.TestCase):
    setUp=controls.ControlOperationTests.setUp

    def engine(self,rungs,*,mutate=None,**kwargs):
        def refs(root):
            tags=root.find('./Controller/Tags');scalar(tags,'Index','DINT',1)
            dtype=tags.find('Tag[@Name="Queue"]').get('DataType')
            for name,target in (('QueueAlias','Queue[1]'),('BitAlias','Words[1]'),('AliasChain','QueueAlias')):
                E.SubElement(tags,'Tag',Name=name,DataType='DINT' if name=='BitAlias' else dtype,TagType='Alias',AliasFor=target)
            if mutate:mutate(root)
        return controls.ControlOperationTests.engine(self,rungs,mutate=refs,**kwargs)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def snapshot(self,e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.scan_count,e.time_ms,e.scheduler_description(),e.trace,e.last_timer))

    def paired(self,*,start='Queue[Index]',stack=False,queue=(101,0,0,0,999),**kwargs):
        load,unload=('LFL','LFU') if stack else ('FFL','FFU')
        return self.checked([f'XIC(StartPB){load}(Incoming,{start},Ctl,?,?);',f'XIC(PartSensor){unload}({start},Outgoing,Ctl,?,?);'],length=3,queue=queue,**kwargs)

    def pulse(self,e,gate,value=None):
        e.memory.write(gate,False);e.step()
        if value is not None:e.memory.write('Incoming',value)
        e.memory.write(gate,True);e.step()

    def test_fifo_alias_chain_and_indirect_start_keep_guard_elements(self):
        for start in ('Queue[Index]','QueueAlias','AliasChain'):
            e=self.paired(start=start);e.step()
            for value in (11,22,33):self.pulse(e,'StartPB',value)
            self.assertEqual(e.memory.read('Queue'),[101,11,22,33,999]);self.assertTrue(e.memory.read('Ctl.DN'))
            e.memory.write('StartPB',False)
            for expected in (11,22,33):self.pulse(e,'PartSensor');self.assertEqual(e.memory.read('Outgoing'),expected)
            self.assertEqual(e.memory.read('Queue'),[101,0,0,0,999]);self.assertTrue(e.memory.read('Ctl.EM'))

    def test_lifo_alias_and_indirect_start_pop_in_reverse_order(self):
        for start in ('Queue[Index]','AliasChain'):
            e=self.paired(start=start,stack=True);e.step()
            for value in (11,22,33):self.pulse(e,'StartPB',value)
            e.memory.write('StartPB',False)
            for expected in (33,22,11):self.pulse(e,'PartSensor');self.assertEqual(e.memory.read('Outgoing'),expected)
            self.assertEqual(e.memory.read('Queue'),[101,0,0,0,999])

    def test_existing_numeric_payload_types_work_with_indirect_starts(self):
        for dtype in ('SINT','INT','DINT','REAL'):
            e=self.paired(dtype=dtype,queue=(101,0,0,0,99));e.step();self.pulse(e,'StartPB',12);e.memory.write('StartPB',False);self.pulse(e,'PartSensor')
            self.assertEqual(e.memory.read('Outgoing'),12);self.assertEqual(e.memory.read('Queue[0]'),101)

    def test_shifts_alias_and_indirect_start_preserve_partial_word(self):
        for start in ('Words[Index]','BitAlias'):
            e=self.checked([f'BSL({start},Ctl,BitIn,?);'],words=(111,-2147483648,0x12345678,777));e.step()
            self.assertEqual(e.memory.read('Words'),[111,1,0x12345679,777]);self.assertFalse(e.memory.read('Ctl.UL'))
            e=self.checked([f'BSR({start},Ctl,BitIn,?);'],words=(111,1,0x12345679,777));e.step()
            self.assertEqual(e.memory.read('Words'),[111,-2147483648,0x12345679,777]);self.assertTrue(e.memory.read('Ctl.UL'))

    def test_index_expression_is_resolved_on_each_data_moving_edge(self):
        e=self.checked(['XIC(StartPB)BSL(Words[Index+1],Ctl,BitIn,?);'],length=1,words=(100,0,0,777))
        e.memory.write('Index',0);self.pulse(e,'StartPB');self.assertEqual(e.memory.read('Words'),[100,1,0,777])
        e.memory.write('Index',1);self.pulse(e,'StartPB');self.assertEqual(e.memory.read('Words'),[100,1,1,777])

    def test_false_and_held_shift_do_not_consume_invalid_or_unknown_start_index(self):
        e=self.checked(['XIC(StartPB)BSL(Words[Index],Ctl,BitIn,?);'],length=1,words=(100,0,0,777))
        e.memory.values['index']=None;e.step();e.memory.write('Index',1);e.memory.write('StartPB',True);e.step()
        e.memory.write('Index',999);e.step();self.assertEqual(e.memory.read('Words'),[100,1,0,777])
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.assertFalse(e.memory.read('Ctl.EN'))
        e.memory.write('Index',2);e.step();self.assertEqual(e.memory.read('Words'),[100,1,1,777])

    def test_false_held_full_and_empty_queue_calls_skip_start_reads(self):
        e=self.paired();e.memory.write('Index',999);e.step();e.memory.write('Index',1);e.memory.write('StartPB',True);e.step()
        e.memory.write('Index',999);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)
        e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Ctl.POS'),2)
        self.pulse(e,'StartPB',33);e.memory.write('Index',999);self.pulse(e,'StartPB',44);self.assertEqual(e.memory.read('Ctl.POS'),3)
        e.memory.write('StartPB',False);e.memory.write('Index',1)
        for _ in range(3):self.pulse(e,'PartSensor')
        # Empty unload still establishes a typed zero; its existing profile
        # resolves the configured region before selecting the empty case.
        e.memory.write('Index',999);e.memory.write('PartSensor',False);e.step();e.memory.write('PartSensor',True);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_start_can_select_a_new_window_after_control_reset(self):
        e=self.paired();e.step();self.pulse(e,'StartPB',11);e.memory.write('StartPB',False);e.step()
        from logixlab.control_operations import reset
        reset(e.memory,'Ctl','MainProgram');e.memory.write('Index',2);e.memory.write('StartPB',True);e.step()
        self.assertEqual(e.memory.read('Queue'),[101,11,11,0,999]);self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_invalid_initial_dynamic_index_is_structural_until_first_edge(self):
        def invalid(root):root.find('./Controller/Tags/Tag[@Name="Index"]/Data/DataValue').set('Value','999')
        e=self.paired(mutate=invalid);e.step();self.assertEqual(e.memory.read('Ctl.POS'),0)
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_out_of_bounds_starts_and_load_slots_roll_back_earlier_writes(self):
        for index in (-1,4,5,2147483647):
            e=self.checked(['MOV(99,SpeedCommand);','XIC(StartPB)FFL(Incoming,Queue[Index],Ctl,?,?);'],length=3,queue=(101,0,0,0,999));e.step()
            e.memory.write('Index', index)
            e.memory.write('Ctl.POS', 1)
            e.memory.write('SpeedCommand', 17)
            e.memory.write('StartPB', True)
            before = self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_unknown_shift_data_and_numeric_queue_reads_fault_without_reading_guards(self):
        e=self.checked(['BSL(Words[Index],Ctl,BitIn,?);'],words=(111,0,0,777));e.memory.values['words'][0]=None;e.step()
        self.assertIsNone(e.memory.values['words'][0]);self.assertEqual(e.memory.read('Words[1]'),1)
        e=self.paired();e.step();e.memory.values['queue'][2]=None;e.memory.write('Ctl.POS',1);e.memory.write('PartSensor',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_program_local_alias_and_explicit_program_reference(self):
        def local(root):
            tags=root.find('./Controller/Programs/Program/Tags');scalar(tags,'LocalIndex','DINT',1)
            E.SubElement(tags,'Tag',Name='LocalAlias',TagType='Alias',DataType='DINT',AliasFor='Words[1]')
        for start in ('LocalAlias','Words[LocalIndex]','Program:MainProgram.LocalAlias'):
            e=self.checked([f'BSL({start},Ctl,BitIn,?);'],words=(111,0,0,777),mutate=local);e.step();self.assertEqual(e.memory.read('Words'),[111,1,0,777])

    def test_nested_udt_array_stays_inside_selected_member(self):
        def nested(root):
            c=root.find('Controller');m=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Window',Family='NoFamily',Class='User'),'Members')
            E.SubElement(m,'Member',Name='Data',DataType='DINT',Dimension='4');E.SubElement(m,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Window1',DataType='Window',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Window')
            a=E.SubElement(obj,'ArrayMember',Name='Data',DataType='DINT',Dimensions='4')
            for i,v in enumerate((101,0,0,999)):E.SubElement(a,'Element',Index=f'[{i}]',Value=str(v))
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777')
        e=self.checked(['XIC(StartPB)FFL(Incoming,Window1.Data[Index],Ctl,?,?);'],length=2,mutate=nested);e.step();self.pulse(e,'StartPB')
        self.assertEqual(e.memory.read('Window1.Data'),[101,11,0,999]);self.assertEqual(e.memory.read('Window1.Guard'),777)
        e.memory.write('Ctl.LEN', 4)
        self.pulse(e, 'StartPB', 22)
        self.assertEqual(e.memory.read('Window1.Data'), [101, 11, 22, 999])
        e.memory.write('Ctl.POS', 3)
        e.memory.write('StartPB', False)
        e.step()
        e.memory.write('StartPB', True)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'load position exceeds the array boundary'):
            e.step()
        self.assertEqual(self.snapshot(e), before)
        self.assertEqual(e.memory.read('Window1.Guard'), 777)

    def test_multidimensional_indirect_start_uses_existing_flat_region(self):
        def dimensions(root):
            tag=root.find('./Controller/Tags/Tag[@Name="Queue"]');tag.set('Dimensions','2,3');a=tag.find('./Data/Array');a.clear();a.attrib.update(DataType='DINT',Dimensions='2,3')
            for index,value in (((0,0),101),((0,1),102),((0,2),0),((1,0),0),((1,1),0),((1,2),999)):
                E.SubElement(a,'Element',Index='['+','.join(map(str,index))+']',Value=str(value))
        e=self.paired(start='Queue[0,Index+1]',mutate=dimensions);e.step()
        for value in (11,22,33):self.pulse(e,'StartPB',value)
        self.assertEqual(e.memory.read('Queue'),[[101,102,11],[22,33,999]])

    def test_scalar_members_of_record_arrays_are_not_flat_numeric_regions(self):
        def records(root):
            c=root.find('Controller');m=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Cell',Family='NoFamily',Class='User'),'Members')
            E.SubElement(m,'Member',Name='Word',DataType='DINT',Dimension='0')
            a=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Cells',DataType='Cell',TagType='Base',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='Cell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(a,'Element',Index=f'[{i}]'),'Structure',DataType='Cell');E.SubElement(obj,'DataValueMember',Name='Word',DataType='DINT',Value='0')
        for start in ('Cells[0].Word','Cells[Index].Word'):
            self.assertTrue(self.engine([f'FFL(Incoming,{start},Ctl,?,?);'],mutate=records).blockers)

    def test_constant_bases_scalar_aliases_bits_and_invalid_index_types_block(self):
        for name in ('Queue','Words'):
            def constant(root):root.find(f'./Controller/Tags/Tag[@Name="{name}"]').set('Constant','true')
            rung='FFL(Incoming,QueueAlias,Ctl,?,?);' if name=='Queue' else 'BSL(BitAlias,Ctl,BitIn,?);'
            self.assertTrue(self.engine([rung],mutate=constant).blockers)
        for start in ('Outgoing','Outgoing.0','Queue[BitIn]','Queue[1.0]','Queue[100]','Queue[Index MOD 2]'):
            self.assertTrue(self.engine([f'FFL(Incoming,{start},Ctl,?,?);']).blockers,start)
        for dtype in ('BOOL','REAL','LREAL'):
            def index(root):
                t=root.find('./Controller/Tags/Tag[@Name="Index"]');t.set('DataType',dtype);t.find('Data/DataValue').set('DataType',dtype)
            self.assertTrue(self.engine(['FFL(Incoming,Queue[Index],Ctl,?,?);'],mutate=index).blockers)

    def test_profile_gate_preserves_old_static_starts(self):
        for attr,value in (('MajorRev','34'),('ProcessorType','1756-L75'),('ProcessorType','5069-L340ERM')):
            def profile(root):root.find('Controller').set(attr,value)
            for start in ('QueueAlias','Queue[Index]'):
                self.assertTrue(self.engine([f'FFL(Incoming,{start},Ctl,?,?);'],mutate=profile).blockers)
            e=self.engine(['FFL(Incoming,Queue[0],Ctl,?,?);'],mutate=profile)
            from logixlab.control_operations import validate
            from logixlab.model import Op
            validate(e.memory,Op('FFL',['Incoming','Queue[0]','Ctl','?','?']),'MainProgram')

    def test_event_task_reference_fault_restores_scheduler_and_edge_state(self):
        def event(root):
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='EventShift',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            content=E.SubElement(E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='EventShift',Type='RLL'),'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='XIC(StartPB)BSL(Words[Index],Ctl,BitIn,?);'
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='ShiftEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(['EVENT(ShiftEvent);'],length=1,words=(100,0,0,777),mutate=event);e.step();self.pulse(e,'StartPB');self.assertEqual(e.memory.read('Words[1]'),1)
        e.memory.write('StartPB',False);e.step();e.memory.write('Index',999);e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_separate_file_consumers_stay_static_and_unbound_aoi_frames_are_rejected(self):
        e=self.checked(['NOP();'])
        from logixlab import control_operations as impl
        for start in ('QueueAlias','Queue[Index]'):
            with self.assertRaises(ModelError):impl.array_region(e.memory,start,1,'MainProgram')
        e.memory.frames['@test']={}
        with self.assertRaisesRegex(ModelError,'AOI'):impl.starting_array(e.memory,'Queue[0]','@test')

    def test_record_and_custom_string_aliases_preserve_payloads_and_guards(self):
        def refs(root):
            tags=root.find('./Controller/Tags');scalar(tags,'RecordIndex','DINT',0)
            for name,dtype,target in (('PartAlias','PartRecord','PartQueue[0]'),('TextAlias','LabelText','TextQueue[0]')):
                E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Alias',AliasFor=target)
        e=records.RecordQueueTests.engine(self,['XIC(LoadPart)FFL(IncomingPart,PartQueue[RecordIndex],PartControl,?,?);','XIC(UnloadPart)FFU(PartAlias,OutgoingPart,PartControl,?,?);',
                                               'XIC(LoadText)FFL(IncomingText,TextAlias,TextControl,?,?);','XIC(UnloadText)FFU(TextQueue[RecordIndex],OutgoingText,TextControl,?,?);'],mutate=refs)
        self.assertEqual(e.blockers,[]);e.step();e.memory.write('IncomingPart.Lot',9007199254740993);e.memory.values['incomingpart']['Readings'][1]=None
        value=copy.deepcopy(e.memory.read('IncomingPart'));text=copy.deepcopy(e.memory.read('IncomingText'))
        for tag in ('LoadPart','LoadText'):e.memory.write(tag,True)
        e.step()
        for tag in ('LoadPart','LoadText'):e.memory.write(tag,False)
        for tag in ('UnloadPart','UnloadText'):e.memory.write(tag,True)
        e.step();self.assertEqual(e.memory.read('OutgoingPart'),value);self.assertEqual(e.memory.read('OutgoingText'),text)
        self.assertEqual(e.memory.read('PartQueue[3].Id'),999);self.assertEqual(e.memory.string('TextQueue[3]'),'KEEP')

    def test_periodic_routine_harness_run_entry_and_budget(self):
        path=Path(__file__).resolve().parents[1]/'samples/QueueReferenceLab.L5X'
        xml=E.parse(path).getroot();task=xml.find('./Controller/Tasks/Task');task.set('Type','Periodic');task.set('Rate','10')
        p=Path(self.tmp.name)/'periodic.L5X';E.ElementTree(xml).write(p,encoding='utf8')
        for e in (Engine(Project(p)),Engine(Project(path),mode='routine',routine='MainProgram/MainRoutine')):
            self.assertEqual(e.blockers,[]);e.step(10);e.memory.write('Load',True);e.step(10);self.assertEqual(e.memory.read('Buffer[1]'),11)
            e.enter_run();e.step(10);self.assertEqual(e.memory.read('QueueControl.POS'),1)
        e=Engine(Project(path));e.step();e.memory.write('Load',True);e.instruction_limit=2;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_late_fault_rolls_back_queue_shift_and_edge_latches_then_retry(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/QueueReferenceLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        for tag in ('Load','Push','ShiftLeft'):e.memory.write(tag,True)
        e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual(e.memory.read('Buffer[1]'),11);self.assertEqual(e.memory.read('Stack[1]'),11);self.assertEqual(e.memory.read('Bits[1]'),1)

    def test_report_and_bundled_ladder_only_lab(self):
        from logixlab.server import SAMPLES
        self.assertIn('QueueReferenceLab',SAMPLES);e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/QueueReferenceLab.L5X'));self.assertEqual(e.blockers,[])
        self.assertEqual({r.kind for r in e.project.routines.values()},{'RLL'});e.step();self.assertEqual(e.memory.read('Steps'),1)
        p=e.report()['control_operations'];self.assertIn('indirect',p['starting_references']);self.assertFalse(p['native_control_layout'])


if __name__=='__main__':unittest.main()
