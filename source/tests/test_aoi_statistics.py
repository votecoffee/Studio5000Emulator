"""AVE/STD numeric InOut and saved local arrays, dimensions and AOI lifecycle."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine

SAMPLE=Path(__file__).resolve().parents[1]/'samples/AOIStatsLab.L5X'


class AOIStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,mutate=None,*,harness=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'statistics.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),mode='routine' if harness else 'project',routine='MainProgram/MainRoutine' if harness else '')

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def write(self,e,**values):
        for tag,value in values.items():e.memory.write(tag.replace('__','.'),value)

    def snapshot(self,e):return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved,e.addons.instances,e.scan_count,e.time_ms,e.trace,e.scheduler_description()))

    def rearm(self,e):self.write(e,Calculate=False);e.step();self.write(e,Calculate=True)

    def test_independent_instances_numeric_arrays_and_saved_locals(self):
        e=self.checked();self.write(e,Calculate=True);e.step()
        for tag,value in {'DriverA.Mean':4,'DriverA.Deviation':2,'DriverA.LocalMean':4,'DriverA.LocalDeviation':2,'DriverB.Mean':20,'DriverB.Deviation':10,'DriverB.LocalMean':6,'DriverB.LocalDeviation':2}.items():self.assertEqual(e.memory.read(tag),value,tag)
        self.assertTrue(e.memory.read('DriverA.Ready'));self.assertTrue(e.memory.read('DriverB.Ready'));self.assertEqual(len(e.addons.instances),2)

    def test_two_and_three_dimensional_inout_axes_do_not_flatten(self):
        e=self.checked();self.write(e,Calculate=True);e.step()
        self.assertEqual(tuple(e.memory.read(t) for t in ('DriverA.ColumnMean','DriverA.RowMean','DriverA.PlaneMean','DriverB.ColumnMean','DriverB.RowMean','DriverB.PlaneMean')),(7,10,7,19,14,20))

    def test_completed_controls_skip_invalid_live_indices_while_inputs_are_known(self):
        e=self.checked();self.write(e,Calculate=True);e.step();self.write(e,IndexA=999,RowA=999,ColumnA=999);e.step()
        self.assertEqual(e.memory.read('DriverA.Mean'),4);self.assertTrue(e.memory.read('DriverA.Ready'))

    def test_false_instructions_rearm_without_consuming_bad_array_indices(self):
        e=self.checked();self.write(e,Calculate=True);e.step();self.write(e,Calculate=False,IndexA=999,RowA=999,ColumnA=999);e.step()
        self.assertFalse(e.memory.read('MeanA.EN'));self.assertEqual(e.memory.read('MeanA.POS'),0)
        self.write(e,Calculate=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_rearmed_dynamic_window_recalculates_external_and_local_results(self):
        e=self.checked();self.write(e,Calculate=True);e.step();self.rearm(e);self.write(e,IndexA=2,ColumnA=0,RowA=0);e.step()
        self.assertEqual((e.memory.read('DriverA.Mean'),e.memory.read('DriverA.LocalMean'),e.memory.read('DriverA.PlaneMean')),(6,6,8))

    def test_authored_false_aoi_rearms_one_instance_only(self):
        e=self.checked();self.write(e,Calculate=True);e.step();self.write(e,EnabledA=False,IndexA=2);e.step()
        self.assertFalse(e.memory.read('MeanA.DN'));self.assertFalse(e.memory.read('DriverA.Ready'));self.assertTrue(e.memory.read('MeanB.DN'))
        self.write(e,EnabledA=True);e.step();self.assertEqual((e.memory.read('DriverA.Mean'),e.memory.read('DriverB.Mean')),(6,20))

    def test_skipped_body_without_false_routine_retains_completed_latches(self):
        def skip(root):root.find('.//AddOnInstructionDefinition').set('ExecuteEnableInFalse','false')
        e=self.checked(skip);self.write(e,Calculate=True);e.step();self.write(e,EnabledA=False,IndexA=2);e.step();self.assertTrue(e.memory.read('MeanA.DN'))
        self.write(e,EnabledA=True);e.step();self.assertEqual(e.memory.read('DriverA.Mean'),4)

    def test_late_failure_restores_results_controls_frames_and_time(self):
        e=self.checked();self.write(e,Calculate=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('DriverB.Mean'),20)

    def test_second_mean_extent_error_retains_first_instance_work_and_rearms_with_res(self):
        def reset(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='ResetMeanB',DataType='BOOL',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='BOOL',Value='0')
            content=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number=str(len(content)),Type='N'),'Text').text='XIC(ResetMeanB)RES(MeanB);'
        e=self.checked(reset)
        saved=e.memory.read('DriverB.Mean')
        available=len(e.memory.read('SamplesB'))-e.memory.read('IndexB')
        self.write(e,Calculate=True,MeanB__LEN=available+1)
        e.step()
        self.assertEqual(e.memory.read('DriverA.Mean'),4)
        self.assertTrue(e.memory.read('MeanA.DN'))
        self.assertEqual(e.memory.read('DriverB.Mean'),saved)
        self.assertEqual([e.memory.read('MeanB.'+n) for n in ('EN','DN','ER','POS')],
                         [True,False,True,available])
        self.write(e,Calculate=False)
        e.step()
        self.assertTrue(e.memory.read('MeanB.ER'))
        self.write(e,ResetMeanB=True)
        e.step()
        self.assertFalse(e.memory.read('MeanB.ER'))
        self.write(e,ResetMeanB=False,Calculate=True,MeanB__LEN=3)
        e.step()
        self.assertEqual(e.memory.read('DriverB.Mean'),20)
        self.assertTrue(e.memory.read('MeanB.DN'))

    def test_one_std_instance_extent_error_retains_output_and_other_instance_work(self):
        e = self.checked()
        source = copy.deepcopy(e.memory.read('SamplesB'))
        saved = e.memory.read('DriverB.Deviation')
        available = len(source)-e.memory.read('IndexB')
        self.write(e,Calculate=True,DeviationB__LEN=available+1)
        e.step()
        self.assertEqual(e.memory.read('DriverA.Deviation'),2)
        self.assertEqual(e.memory.read('DriverB.Mean'),20)
        self.assertEqual(e.memory.read('DriverB.Deviation'),saved)
        self.assertTrue(e.memory.read('DeviationA.DN'))
        self.assertEqual([e.memory.read('DeviationB.'+n) for n in ('EN','DN','ER','POS')],
                         [True,False,True,available])
        self.assertEqual(e.memory.read('SamplesB'),source)
        self.assertIsNone(e.last_cleared_program_fault)
        self.rearm(e)
        self.write(e,DeviationB__LEN=3)
        e.step()
        self.assertEqual(e.memory.read('DriverB.Deviation'),10)
        self.assertTrue(e.memory.read('DeviationB.DN'))

    def test_unknown_saved_local_sample_faults_only_when_consumed(self):
        def hidden(root):
            arr=root.find('./Controller/Tags/Tag[@Name="DriverA"]/Data/Structure/ArrayMember');arr.remove(arr.find('Element[@Index="[2]"]'))
        e=self.checked(hidden);e.step();self.write(e,Calculate=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_saved_partial_local_control_position_stays_unqualified(self):
        def active(root):root.find('./Controller/Tags/Tag[@Name="DriverA"]/Data/Structure/StructureMember[@Name="LocalMeanState"]/DataValueMember[@Name="POS"]').set('Value','1')
        e=self.checked(active);self.write(e,Calculate=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'POS zero'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_exact_inout_type_shape_and_constant_actuals_remain_blocked(self):
        for field,value in (('DataType','DINT'),('Dimensions','5'),('Constant','true')):
            def wrong(root):root.find('./Controller/Tags/Tag[@Name="SamplesB"]').set(field,value)
            self.assertTrue(self.engine(wrong).blockers)

    def test_control_pos_index_inside_aoi_is_blocked(self):
        def cursor(root):
            for t in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):t.text=t.text.replace('Samples[Index]','Samples[MeanState.POS]')
        self.assertTrue(any('CONTROL.POS' in b for b in self.engine(cursor).blockers))

    def test_local_result_cannot_overlap_local_source_array(self):
        def overlap(root):
            for t in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):t.text=t.text.replace('0,LocalMean,LocalMeanState','0,Scratch[0],LocalMeanState')
        self.assertTrue(self.engine(overlap).blockers)

    def test_false_aoi_still_consumes_required_copied_inputs(self):
        e=self.checked();self.write(e,EnabledA=False);e.memory.values['indexa']=None;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_run_prescan_retains_pos_and_requires_explicit_rearm(self):
        e=self.checked();self.write(e,Calculate=True);e.step();e.enter_run();self.assertEqual(e.memory.read('MeanA.POS'),3);self.assertFalse(e.memory.read('MeanA.DN'))
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'POS zero'):e.step()
        self.assertEqual(self.snapshot(e),before);self.rearm(e)
        # AVE false with DN already clear retains POS; reset it explicitly.
        for suffix in ('A','B'):
            for ref in ('Mean','Deviation','Column','Row','Plane'):
                e.memory.write((ref+suffix+'State' if ref in ('Column','Row') else ref+suffix)+'.POS',0)
            for name in ('LocalMeanState','LocalDeviationState'):e.memory.write('Driver'+suffix+'.'+name+'.POS',0)
        e.step();self.assertEqual(e.memory.read('DriverA.Mean'),4)

    def test_selected_routine_and_periodic_execution(self):
        e=self.checked(harness=True);self.write(e,Calculate=True);e.step();self.assertEqual(e.memory.read('DriverA.Mean'),4)
        def periodic(root):root.find('.//Task').attrib.update(Type='PERIODIC',Rate='20')
        e=self.checked(periodic);self.write(e,Calculate=True);e.step(20);self.assertEqual(e.memory.read('DriverB.Mean'),20)

    def test_exact_numeric_inout_source_types(self):
        for dtype in ('SINT','INT','DINT','REAL'):
            def typed(root):
                root.find('.//AddOnInstructionDefinition/Parameters/Parameter[@Name="Samples"]').set('DataType',dtype)
                root.find('./Controller/Tags/Tag[@Name="SampleView"]').set('DataType',dtype)
                for suffix in ('A','B'):
                    tag=root.find(f'./Controller/Tags/Tag[@Name="Samples{suffix}"]');tag.set('DataType',dtype);arr=tag.find('Data/Array');arr.set('DataType',dtype);arr.find('Element[@Index="[5]"]').set('Value','99')
            with self.subTest(dtype=dtype):
                e=self.checked(typed);self.write(e,Calculate=True);e.step();self.assertEqual((e.memory.read('DriverA.Mean'),e.memory.read('DriverB.Mean')),(4,20))

    def test_multi_dimensional_saved_local_arrays(self):
        import itertools
        for shape,source,expected in (((2,3),'Scratch[0,Column]',(7,9)),((2,2,3),'Scratch[0,1,Index]',(7,8))):
            def multi(root):
                dims=','.join(map(str,shape));root.find('.//AddOnInstructionDefinition/LocalTags/LocalTag[@Name="Scratch"]').set('Dimensions',dims)
                for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('Scratch[Index]',source)
                for suffix in ('A','B'):
                    obj=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure');arr=obj.find('ArrayMember');arr.clear();arr.attrib.update(Name='Scratch',DataType='REAL',Dimensions=dims)
                    for index,value in zip(itertools.product(*(range(n) for n in shape)),(2,4,6,8,10,12) if len(shape)==2 else range(12),strict=True):E.SubElement(arr,'Element',Index='['+','.join(map(str,index))+']',Value=str(value))
                    for name in ('LocalMeanState','LocalDeviationState'):obj.find(f'StructureMember[@Name="{name}"]/DataValueMember[@Name="LEN"]').set('Value','2')
            e=self.checked(multi);self.write(e,Calculate=True);e.step();self.assertEqual((e.memory.read('DriverA.LocalMean'),e.memory.read('DriverB.LocalMean')),expected)

    def test_nested_instances_isolate_local_results_and_controls(self):
        def nested(root):
            defs=root.find('./Controller/AddOnInstructionDefinitions');wrapper=copy.deepcopy(defs[0]);wrapper.set('Name','StatsWrapper');defs.append(wrapper)
            locals=wrapper.find('LocalTags');locals.clear();E.SubElement(locals,'LocalTag',Name='Inner',DataType='LabStatsDriver')
            for routine in wrapper.findall('Routines/Routine'):
                content=routine.find('RLLContent');content.clear();prefix='AFI()' if routine.get('Name')=='EnableInFalse' else ''
                E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text=prefix+'LabStatsDriver(Inner,Calculate,Index,Row,Column,Samples,Grid,Cube,MeanState,DeviationState,ColumnState,RowState,PlaneState);'
            for suffix in ('A','B'):
                tag=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]');tag.set('DataType','StatsWrapper');obj=tag.find('Data/Structure');inner=copy.deepcopy(obj);inner.tag='StructureMember';inner.set('Name','Inner')
                for local in list(obj):
                    if local.tag in ('ArrayMember','StructureMember'):obj.remove(local)
                obj.set('DataType','StatsWrapper');obj.append(inner)
            for text in root.findall('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('LabStatsDriver(','StatsWrapper(')
        e=self.checked(nested);self.write(e,Calculate=True);e.step();self.assertEqual((e.memory.read('DriverA.Inner.Mean'),e.memory.read('DriverB.Inner.Mean'),e.memory.read('DriverA.Inner.LocalMean')),(4,20,4));self.assertEqual(len(e.addons.instances),4)

    def test_indirect_inout_rebinding_and_failed_frame_restore(self):
        def bank(root):
            dt=E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='StatsBank',Family='NoFamily',Class='User');E.SubElement(E.SubElement(dt,'Members'),'Member',Name='Rows',DataType='REAL',Dimension='6')
            tags=root.find('./Controller/Tags');tag=E.SubElement(tags,'Tag',Name='BankIndex',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
            tag=E.SubElement(tags,'Tag',Name='Banks',DataType='StatsBank',TagType='Base',Dimensions='2');arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='StatsBank',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='StatsBank');rows=copy.deepcopy(tags.find('Tag[@Name="SamplesA"]/Data/Array'));rows.tag='ArrayMember';rows.set('Name','Rows')
                if i:
                    for j,value in enumerate((10,20,30),1):rows.find(f'Element[@Index="[{j}]"]').set('Value',str(value))
                obj.append(rows)
            text=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text');text.text=text.text.replace('SampleView','Banks[BankIndex].Rows')
        e=self.checked(bank);self.write(e,Calculate=True);e.step();self.rearm(e);self.write(e,BankIndex=1,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('DriverA.Mean'),20)

    def test_event_dispatch_failure_rolls_back_both_instances(self):
        def event(root):
            content=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent');calls=[copy.deepcopy(row) for row in list(content)[:2]]
            for row in list(content)[:2]:content.remove(row)
            rung=E.Element('Rung',Number='0',Type='N');E.SubElement(rung,'Text').text='EVENT(StatisticsEvent);';content.insert(0,rung)
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='EventRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags');body=E.SubElement(E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='EventRoutine',Type='RLL'),'RLLContent')
            for row in calls:body.append(row)
            task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='StatisticsEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(event);self.write(e,Calculate=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('DriverB.PlaneMean'),20)

    def test_aoi_sort_can_feed_a_following_statistics_operation(self):
        def sort(root):
            root.find('.//AddOnInstructionDefinition/Routines/Routine[@Name="Logic"]/RLLContent/Rung/Text').text='SRT(Samples[Index],0,MeanState,?,?);'
            arr=root.find('./Controller/Tags/Tag[@Name="SamplesA"]/Data/Array')
            for index,value in enumerate((6,2,4),1):arr.find(f'Element[@Index="[{index}]"]').set('Value',str(value))
        e=self.checked(sort);self.write(e,Calculate=True);e.step();self.assertEqual(e.memory.read('SamplesA')[1:4],[2,4,6]);self.assertEqual(e.memory.read('DriverA.Deviation'),2)


if __name__=='__main__':unittest.main()
