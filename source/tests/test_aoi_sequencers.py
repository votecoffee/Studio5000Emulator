"""RLL AOI sequencers: exact array bindings, local state and rollback."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine

SAMPLE=Path(__file__).resolve().parents[1]/'samples/AOISequencerLab.L5X'


class AOISequencerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,mutate=None,*,harness=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'sequencers.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),mode='routine' if harness else 'project',routine='MainProgram/MainRoutine' if harness else '')

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def write(self,e,**values):
        for tag,value in values.items():e.memory.write(tag.replace('__','.'),value)

    def snapshot(self,e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved,e.addons.instances,e.scan_count,e.time_ms,e.trace,e.scheduler_description()))

    def pulse(self,e):
        self.write(e,Step=False,Teach=False);e.step();self.write(e,Step=True,Teach=True);e.step()

    def test_independent_inout_tables_controls_outputs_and_saved_locals(self):
        e=self.checked();self.pulse(e)
        self.assertEqual((e.memory.read('OutputsA'),e.memory.read('OutputsB')),(0x120001,0x340008))
        self.assertTrue(e.memory.read('DriverA.Matched'));self.assertTrue(e.memory.read('DriverB.Matched'))
        self.assertEqual((e.memory.read('LearnedA[2]'),e.memory.read('LearnedB[3]'),e.memory.read('DriverA.Scratch[2]'),e.memory.read('DriverB.Scratch[3]')),(11,22,11,22))
        self.assertEqual((e.memory.read('SequenceA.POS'),e.memory.read('TeachA.POS'),e.memory.read('DriverA.LocalState.POS')),(1,1,1))

    def test_held_calls_reapply_outputs_and_teach_new_values(self):
        e=self.checked();self.pulse(e);self.write(e,ValueA=33,ValueB=44);e.step()
        self.assertEqual((e.memory.read('LearnedA[2]'),e.memory.read('DriverB.Scratch[3]')),(33,44));self.assertEqual(e.memory.read('SequenceA.POS'),1)

    def test_live_aoi_subscripts_relocate_current_row_without_advancing(self):
        e=self.checked();self.pulse(e);self.write(e,IndexA=2,ValueA=55,FeedbackA=2);e.step()
        self.assertEqual(e.memory.read('OutputsA'),0x120002);self.assertTrue(e.memory.read('DriverA.Matched'))
        self.assertEqual((e.memory.read('LearnedA[2]'),e.memory.read('LearnedA[3]')),(11,55));self.assertEqual(e.memory.read('SequenceA.POS'),1)

    def test_false_instruction_calls_skip_bad_index_when_copied_index_is_known(self):
        e=self.checked();self.write(e,IndexA=999);e.step();self.assertFalse(e.memory.read('SequenceA.EN'))
        self.write(e,Step=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_authored_enable_in_false_clears_latches_and_rearms_only_one_instance(self):
        e=self.checked();self.pulse(e);self.write(e,EnabledA=False,IndexA=999);e.step()
        self.assertFalse(e.memory.read('SequenceA.EN'));self.assertFalse(e.memory.read('TeachA.EN'));self.assertFalse(e.memory.read('DriverA.LocalState.EN'));self.assertFalse(e.memory.read('DriverA.Matched'))
        self.assertTrue(e.memory.read('SequenceB.EN'));self.write(e,EnabledA=True,IndexA=1);e.step()
        self.assertEqual((e.memory.read('SequenceA.POS'),e.memory.read('SequenceB.POS')),(2,1));self.assertTrue(e.memory.read('SequenceA.DN'))

    def test_skipped_aoi_without_false_mode_retains_latches(self):
        def skip(root):root.find('.//AddOnInstructionDefinition').set('ExecuteEnableInFalse','false')
        e=self.checked(skip);self.pulse(e);self.write(e,EnabledA=False,IndexA=999);e.step()
        self.assertTrue(e.memory.read('SequenceA.EN'));self.write(e,EnabledA=True,IndexA=1);e.step();self.assertEqual(e.memory.read('SequenceA.POS'),1)

    def test_prescan_run_entry_retains_position_and_primes_enable(self):
        e=self.checked();self.pulse(e);e.enter_run();self.assertTrue(e.memory.read('SequenceA.EN'));self.assertEqual(e.memory.read('SequenceA.POS'),1)
        e.step();self.assertEqual(e.memory.read('SequenceA.POS'),1);self.assertEqual(e.memory.read('OutputsA'),0x120001)

    def test_sql_second_instance_fault_restores_all_prior_data_and_bindings(self):
        e=self.checked();e.step();self.write(e,Teach=True,IndexB=999);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,IndexB=2);e.step();self.assertEqual(e.memory.read('LearnedA[2]'),11)

    def test_late_fault_restores_external_local_and_position_effects(self):
        e=self.checked();e.step();self.write(e,Step=True,Teach=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('DriverA.Scratch[2]'),11)

    def test_sqo_local_disjoint_destination_permitted_but_same_table_rejected(self):
        def local(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('SQO(Table[Index],16#FF,Destination','SQO(Scratch[Index],16#FF,LocalValue')
        e=self.checked(local);self.pulse(e);self.assertEqual(e.memory.read('OutputsA'),0x120000)
        def overlap(root):
            local(root)
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('16#FF,LocalValue','16#FF,Scratch[0]')
        self.assertTrue(self.engine(overlap).blockers)

    def test_control_pos_reference_inside_aoi_table_is_blocked(self):
        def cursor(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('Table[Index]','Table[Sequence.POS]')
        self.assertTrue(any('CONTROL.POS' in b for b in self.engine(cursor).blockers))

    def test_missing_saved_local_control_flag_stays_unknown(self):
        def omit(root):
            obj=root.find('./Controller/Tags/Tag[@Name="DriverA"]/Data/Structure/StructureMember[@Name="LocalState"]');obj.remove(obj.find('DataValueMember[@Name="EN"]'))
        e=self.checked(omit);self.assertTrue(e.memory.read('DriverA.LocalState.EN'))
        # Prescan legitimately establishes EN; it does not fabricate POS.
        e.memory.values['drivera']['LocalState']['POS']=None;self.write(e,Teach=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'POS is unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_exact_array_type_shape_and_read_only_actuals_are_blocked(self):
        for field,value in (('DataType','REAL'),('Dimensions','5'),('Constant','true')):
            def wrong(root):root.find('./Controller/Tags/Tag[@Name="PatternsB"]').set(field,value)
            with self.subTest(field=field):self.assertTrue(self.engine(wrong).blockers)

    def test_aoi_whole_array_start_remains_outside_selected_element_profile(self):
        def whole(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('Table[Index]','Table')
        self.assertTrue(self.engine(whole).blockers)

    def test_false_aoi_copied_unknown_input_still_faults(self):
        e=self.checked();self.write(e,EnabledA=False);e.memory.values['indexa']=None;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_selected_routine_and_periodic_task_profiles(self):
        e=self.checked(harness=True);self.pulse(e);self.assertEqual(e.memory.read('OutputsA'),0x120001)
        def periodic(root):root.find('.//Task').attrib.update(Type='PERIODIC',Rate='20')
        e=self.checked(periodic);e.step(20);self.write(e,Step=True);e.step(20);self.assertEqual(e.memory.read('OutputsA'),0x120001)

    def test_indirect_inout_rebinding_is_atomic_and_invalidates_old_aliases(self):
        def bank(root):
            dtype=E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='TableBank',Family='NoFamily',Class='User')
            E.SubElement(E.SubElement(dtype,'Members'),'Member',Name='Rows',DataType='DINT',Dimension='6',Radix='Decimal',Hidden='false',ExternalAccess='Read/Write')
            tags=root.find('./Controller/Tags');tag=E.SubElement(tags,'Tag',Name='BankIndex',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
            tag=E.SubElement(tags,'Tag',Name='Banks',DataType='TableBank',Dimensions='2',TagType='Base');arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='TableBank',Dimensions='2')
            original=tags.find('Tag[@Name="PatternsA"]/Data/Array')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='TableBank');rows=copy.deepcopy(original);rows.tag='ArrayMember';rows.set('Name','Rows')
                if i:rows.find('Element[@Index="[2]"]').set('Value','4')
                obj.append(rows)
            node=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text');node.text=node.text.replace('PatternView','Banks[BankIndex].Rows')
        e=self.checked(bank);self.pulse(e);self.write(e,BankIndex=1,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('OutputsA'),0x120004)

    def test_nested_instances_preserve_local_array_and_control_identity(self):
        def nested(root):
            defs=root.find('./Controller/AddOnInstructionDefinitions');wrapper=copy.deepcopy(defs[0]);wrapper.set('Name','SequenceWrapper');defs.append(wrapper)
            locals=wrapper.find('LocalTags');locals.clear();E.SubElement(locals,'LocalTag',Name='Inner',DataType='LabSequencer')
            for routine in wrapper.findall('Routines/Routine'):
                content=routine.find('RLLContent');content.clear();prefix='AFI()' if routine.get('Name')=='EnableInFalse' else ''
                call=prefix+'LabSequencer(Inner,Step,Teach,Index,Value,Feedback,Table,Learned,Sequence,TeachState,Destination);'
                E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text=call
            for suffix in ('A','B'):
                tag=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]');tag.set('DataType','SequenceWrapper');obj=tag.find('Data/Structure');inner=copy.deepcopy(obj);inner.tag='StructureMember';inner.set('Name','Inner')
                obj.remove(obj.find('ArrayMember'));obj.remove(obj.find('StructureMember'));obj.set('DataType','SequenceWrapper');obj.append(inner)
            for text in root.findall('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('LabSequencer(','SequenceWrapper(')
        e=self.checked(nested);self.pulse(e);self.assertEqual(e.memory.read('DriverA.Inner.Scratch[2]'),11);self.assertEqual(e.memory.read('DriverB.Inner.Scratch[3]'),22)
        self.assertEqual(len(e.addons.instances),4);self.assertEqual(e.memory.read('OutputsA'),0x120001)

    def test_event_dispatch_later_fault_restores_all_sequencer_effects(self):
        def event(root):
            content=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent');calls=[copy.deepcopy(row) for row in list(content)[:2]]
            for row in list(content)[:2]:content.remove(row)
            rung=E.Element('Rung',Number='0',Type='N');E.SubElement(rung,'Text').text='EVENT(SequencerEvent);';content.insert(0,rung)
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='EventRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags');body=E.SubElement(E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='EventRoutine',Type='RLL'),'RLLContent')
            for row in calls:body.append(row)
            task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='SequencerEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(event);e.step();self.write(e,Step=True,Teach=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('DriverB.Scratch[3]'),22)


if __name__=='__main__':unittest.main()
