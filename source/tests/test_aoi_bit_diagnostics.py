"""RLL FBC/DDT InOut and saved local arrays, controls and AOI state."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine

SAMPLE=Path(__file__).resolve().parents[1]/'samples/AOIBitLab.L5X'


class AOIBitDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,mutate=None,*,harness=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'bits.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),mode='routine' if harness else 'project',routine='MainProgram/MainRoutine' if harness else '')

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def write(self,e,**values):
        for tag,value in values.items():e.memory.write(tag.replace('__','.'),value)

    def snapshot(self,e):return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved,e.addons.instances,e.scan_count,e.time_ms,e.trace,e.scheduler_description()))

    def pulse(self,e):self.write(e,DetectEnable=False);e.step();self.write(e,DetectEnable=True);e.step()

    def test_independent_compare_detect_and_local_results(self):
        e=self.checked();self.write(e,CompareEnable=True,DetectEnable=True);e.step()
        self.assertEqual(e.memory.read('CompareResultsA'),[201,32,39,31,-1,299]);self.assertEqual(e.memory.read('CompareResultsB'),[201,-1,1,3,33,299])
        self.assertEqual((e.memory.read('LearnedA[1]'),e.memory.read('LearnedB[1]'),e.memory.read('DriverA.Scratch[1]'),e.memory.read('DriverB.Scratch[1]')),(1,2,1,2))
        self.assertEqual((e.memory.read('DetectA.POS'),e.memory.read('DetectB.POS')),(1,2));self.assertEqual(len(e.addons.instances),2)

    def test_one_mismatch_edges_resume_with_separate_controls(self):
        e=self.checked();self.write(e,DetectEnable=True);e.step();self.pulse(e)
        self.assertEqual((e.memory.read('DetectA.POS'),e.memory.read('DetectB.POS')),(6,4));self.assertEqual(e.memory.read('DetectResultsA')[1:3],[0,5]);self.assertEqual(e.memory.read('DetectResultsB')[2:4],[1,3])
        self.assertEqual(e.memory.read('DriverA.LocalResults')[1:3],[0,5]);self.assertEqual(e.memory.read('DriverB.Scratch[1]'),10)

    def test_held_instructions_skip_known_bad_indices(self):
        e=self.checked();self.write(e,CompareEnable=True,DetectEnable=True);e.step();self.write(e,SourceIndexA=999,ReferenceIndexA=999,ResultIndexA=999);e.step()
        self.assertEqual(e.memory.read('LearnedA[1]'),1);self.assertEqual(e.memory.read('CompareResultsA')[1:4],[32,39,31])

    def test_false_calls_rearm_and_do_not_consume_indices(self):
        e=self.checked();self.write(e,CompareEnable=True,DetectEnable=True);e.step();self.write(e,CompareEnable=False,DetectEnable=False,SourceIndexA=999);e.step()
        self.assertEqual(e.memory.read('CompareA.POS'),0);self.assertEqual(e.memory.read('DetectA.POS'),1);self.assertFalse(e.memory.read('DetectA.EN'))
        self.write(e,DetectEnable=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_authored_false_aoi_rearms_only_one_instance(self):
        e=self.checked();self.write(e,DetectEnable=True);e.step();self.write(e,EnabledA=False,SourceIndexA=999);e.step();self.assertFalse(e.memory.read('DetectA.EN'));self.assertTrue(e.memory.read('DetectB.EN'))
        self.write(e,EnabledA=True,SourceIndexA=1);e.step();self.assertEqual((e.memory.read('DetectA.POS'),e.memory.read('DetectB.POS')),(6,2))

    def test_skipped_aoi_without_false_body_retains_enable(self):
        def skip(root):root.find('.//AddOnInstructionDefinition').set('ExecuteEnableInFalse','false')
        e=self.checked(skip);self.write(e,DetectEnable=True);e.step();self.write(e,EnabledA=False,SourceIndexA=999);e.step();self.write(e,EnabledA=True);e.step();self.assertEqual(e.memory.read('DetectA.POS'),1)

    def test_run_prescan_rearms_partial_and_retains_learning(self):
        e=self.checked();self.write(e,DetectEnable=True);e.step();e.enter_run();self.assertFalse(e.memory.read('DetectA.EN'));self.assertEqual(e.memory.read('DetectA.POS'),1)
        e.step();self.assertEqual(e.memory.read('LearnedA[1]'),33);self.assertEqual(e.memory.read('DetectA.POS'),6)

    def test_all_mode_preserves_high_uncompared_bits_and_local_guards(self):
        e=self.checked();self.write(e,DetectEnable=True,DetectA__IN=False,DetectB__IN=False,DriverA__LocalCompare__IN=False,DriverB__LocalCompare__IN=False);e.step()
        self.assertEqual(e.memory.read('LearnedA'),[401,-2147483615,0x40000081,887]);self.assertEqual(e.memory.read('DriverA.Scratch'),[501,-2147483615,0x20000081,886])
        self.assertEqual(e.memory.read('DriverA.LocalResults'),[701,32,39,31,-1,799]);self.assertEqual(e.memory.read('LearnedB')[1:3],[10,0x40000002])

    def test_late_fault_restores_external_local_learning_and_bindings(self):
        e=self.checked();self.write(e,CompareEnable=True,DetectEnable=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('DriverA.Scratch[1]'),1)

    def test_second_instance_bad_result_window_rolls_back_first_work(self):
        e=self.checked();self.write(e,CompareEnable=True,ResultIndexB=5);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'boundary'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_omitted_local_reference_word_remains_unknown(self):
        def missing(root):
            arr=root.find('./Controller/Tags/Tag[@Name="DriverA"]/Data/Structure/ArrayMember[@Name="Scratch"]');arr.remove(arr.find('Element[@Index="[1]"]'))
        e=self.checked(missing);e.step();self.write(e,DetectEnable=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_same_local_array_and_control_roles_remain_blocked(self):
        for old,new in (('LocalResults[ResultIndex]','Scratch[ResultIndex]'),('LocalList,','LocalCompare,')):
            def overlap(root):
                for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace(old,new)
            self.assertTrue(self.engine(overlap).blockers)

    def test_control_pos_index_and_wrong_actual_type_or_shape_block(self):
        def cursor(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('Source[SourceIndex]','Source[CompareState.POS]')
        self.assertTrue(any('CONTROL.POS' in b for b in self.engine(cursor).blockers))
        for field,value in (('DataType','REAL'),('Dimensions','3'),('Constant','true')):
            def wrong(root):root.find('./Controller/Tags/Tag[@Name="SourceB"]').set(field,value)
            self.assertTrue(self.engine(wrong).blockers)

    def test_false_aoi_still_copies_required_unknown_inputs(self):
        e=self.checked();self.write(e,EnabledA=False);e.memory.values['sourceindexa']=None;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_aoi_whole_array_and_multidimensional_starts_stay_unqualified(self):
        def whole(root):
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('Source[SourceIndex]','Source')
        self.assertTrue(self.engine(whole).blockers)
        def multi(root):
            root.find('.//AddOnInstructionDefinition/Parameters/Parameter[@Name="Source"]').set('Dimensions','2,2');root.find('./Controller/Tags/Tag[@Name="SourceView"]').set('Dimensions','2,2')
            for suffix in ('A','B'):
                tag=root.find(f'./Controller/Tags/Tag[@Name="Source{suffix}"]');tag.set('Dimensions','2,2');arr=tag.find('Data/Array');arr.set('Dimensions','2,2')
                for i,node in enumerate(arr):node.set('Index',f'[{i//2},{i%2}]')
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('Source[SourceIndex]','Source[0,SourceIndex]')
        self.assertTrue(any('one-dimensional' in b for b in self.engine(multi).blockers))

    def test_selected_routine_and_periodic_task(self):
        e=self.checked(harness=True);self.write(e,CompareEnable=True);e.step();self.assertEqual(e.memory.read('CompareResultsA')[1],32)
        def periodic(root):root.find('.//Task').attrib.update(Type='PERIODIC',Rate='20')
        e=self.checked(periodic);self.write(e,DetectEnable=True);e.step(20);self.assertEqual(e.memory.read('LearnedA[1]'),1)

    def test_nested_instances_keep_local_controls_and_learning_isolated(self):
        def nested(root):
            defs=root.find('./Controller/AddOnInstructionDefinitions');wrapper=copy.deepcopy(defs[0]);wrapper.set('Name','BitWrapper');defs.append(wrapper)
            locals=wrapper.find('LocalTags');locals.clear();E.SubElement(locals,'LocalTag',Name='Inner',DataType='LabBitDiagnostics')
            for routine in wrapper.findall('Routines/Routine'):
                content=routine.find('RLLContent');content.clear();prefix='AFI()' if routine.get('Name')=='EnableInFalse' else ''
                E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text=prefix+'LabBitDiagnostics(Inner,CompareEnable,DetectEnable,SourceIndex,ReferenceIndex,ResultIndex,Source,Reference,Learned,CompareResults,DetectResults,CompareState,CompareListState,DetectState,DetectListState);'
            for suffix in ('A','B'):
                tag=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]');tag.set('DataType','BitWrapper');obj=tag.find('Data/Structure');inner=copy.deepcopy(obj);inner.tag='StructureMember';inner.set('Name','Inner')
                for local in list(obj):
                    if local.tag in ('ArrayMember','StructureMember'):obj.remove(local)
                obj.set('DataType','BitWrapper');obj.append(inner)
            for text in root.findall('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('LabBitDiagnostics(','BitWrapper(')
        e=self.checked(nested);self.write(e,CompareEnable=True,DetectEnable=True);e.step();self.assertEqual(e.memory.read('DriverA.Inner.Scratch[1]'),1);self.assertEqual(e.memory.read('DriverB.Inner.Scratch[1]'),2);self.assertEqual(len(e.addons.instances),4)

    def test_indirect_inout_rebinding_and_failed_frame_restore(self):
        def bank(root):
            dt=E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='BitBank',Family='NoFamily',Class='User');E.SubElement(E.SubElement(dt,'Members'),'Member',Name='Rows',DataType='DINT',Dimension='4')
            tags=root.find('./Controller/Tags');tag=E.SubElement(tags,'Tag',Name='BankIndex',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
            tag=E.SubElement(tags,'Tag',Name='Banks',DataType='BitBank',TagType='Base',Dimensions='2');arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='BitBank',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='BitBank');rows=copy.deepcopy(tags.find('Tag[@Name="SourceA"]/Data/Array'));rows.tag='ArrayMember';rows.set('Name','Rows')
                if i:
                    for j,value in enumerate((10,2),1):rows.find(f'Element[@Index="[{j}]"]').set('Value',str(value))
                obj.append(rows)
            text=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text');text.text=text.text.replace('SourceView','Banks[BankIndex].Rows')
        e=self.checked(bank);self.write(e,CompareEnable=True);e.step();self.write(e,CompareEnable=False);e.step();self.write(e,CompareEnable=True,BankIndex=1,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('CompareResultsA')[1:4],[1,3,33])

    def test_event_dispatch_later_fault_restores_results_and_learning(self):
        def event(root):
            content=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent');calls=[copy.deepcopy(row) for row in list(content)[:2]]
            for row in list(content)[:2]:content.remove(row)
            rung=E.Element('Rung',Number='0',Type='N');E.SubElement(rung,'Text').text='EVENT(BitEvent);';content.insert(0,rung)
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='EventRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags');body=E.SubElement(E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='EventRoutine',Type='RLL'),'RLLContent')
            for row in calls:body.append(row)
            task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='BitEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(event);self.write(e,CompareEnable=True,DetectEnable=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('DriverA.Scratch[1]'),1)


if __name__=='__main__':unittest.main()
