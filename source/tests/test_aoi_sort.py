"""SRT numeric InOut/local arrays and AOI bindings/lifecycle."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine

SAMPLE=Path(__file__).resolve().parents[1]/'samples/AOISortLab.L5X'


class AOISortTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,mutate=None,*,harness=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'sort.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),mode='routine' if harness else 'project',routine='MainProgram/MainRoutine' if harness else '')

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def write(self,e,**values):
        for tag,value in values.items():e.memory.write(tag.replace('__','.'),value)

    def snapshot(self,e):return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved,e.addons.instances,e.scan_count,e.time_ms,e.trace,e.scheduler_description()))

    def test_independent_inout_and_saved_local_sorting(self):
        e=self.checked();self.write(e,Sort=True);e.step()
        self.assertEqual(e.memory.read('SamplesA'),[101,2,4,6,8,999]);self.assertEqual(e.memory.read('SamplesB'),[102,103,10,20,30,998])
        self.assertEqual(e.memory.read('DriverA.Scratch'),[501,3,6,9,12,599]);self.assertEqual(e.memory.read('DriverB.Scratch'),[502,503,5,10,15,598]);self.assertTrue(e.memory.read('DriverA.Ready'))

    def test_matrix_column_and_cube_line_selection(self):
        e=self.checked();self.write(e,Sort=True);e.step();self.assertEqual(e.memory.read('GridA'),[[6,4,2],[12,10,8]]);self.assertEqual(e.memory.read('GridB'),[[16,14,10],[18,20,30]])
        self.assertEqual(e.memory.read('CubeA')[1][1],[7,8,9]);self.assertEqual(e.memory.read('CubeB')[1][0],[30,31,32]);self.assertEqual(e.memory.read('CubeA')[0][0],[6,5,4])

    def test_held_enable_skips_bad_indices_and_retains_changed_order(self):
        e=self.checked();self.write(e,Sort=True);e.step();self.write(e,IndexA=999,ColumnA=999,RowA=999);e.memory.write('SamplesA[1]',7);e.step();self.assertEqual(e.memory.read('SamplesA')[1:4],[7,4,6])

    def test_false_instruction_rearms_without_source_consumption(self):
        e=self.checked();self.write(e,Sort=True);e.step();self.write(e,Sort=False,IndexA=999);e.step();self.assertFalse(e.memory.read('OrderA.EN'))
        self.write(e,Sort=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_authored_false_aoi_rearms_only_its_instance(self):
        e=self.checked();self.write(e,Sort=True);e.step();self.write(e,EnabledA=False,IndexA=999);e.step();self.assertFalse(e.memory.read('OrderA.EN'));self.assertTrue(e.memory.read('OrderB.EN'))
        self.write(e,EnabledA=True,IndexA=2);e.memory.write('SamplesA[2]',10);e.step();self.assertEqual(e.memory.read('SamplesA'),[101,2,6,8,10,999])

    def test_skipped_body_retains_enable_and_needs_no_source_read(self):
        def skip(root):root.find('.//AddOnInstructionDefinition').set('ExecuteEnableInFalse','false')
        e=self.checked(skip);self.write(e,Sort=True);e.step();self.write(e,EnabledA=False,IndexA=999);e.step();self.assertTrue(e.memory.read('OrderA.EN'))
        self.write(e,EnabledA=True);e.step();self.assertEqual(e.memory.read('SamplesA')[1:4],[2,4,6])

    def test_run_prescan_keeps_enable_and_order(self):
        e=self.checked();self.write(e,Sort=True);e.step();e.enter_run();self.assertTrue(e.memory.read('OrderA.EN'));self.assertEqual(e.memory.read('OrderA.POS'),0)
        e.memory.write('SamplesA[1]',7);e.step();self.assertEqual(e.memory.read('SamplesA')[1:4],[7,4,6])

    def test_late_failure_restores_external_local_data_controls_and_frames(self):
        e=self.checked();self.write(e,Sort=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('DriverB.Scratch')[2:5],[5,10,15])

    def test_second_instance_short_window_rolls_back_first(self):
        e=self.checked();self.write(e,Sort=True,OrderB__LEN=5);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'boundary'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_missing_saved_local_value_remains_unknown(self):
        def missing(root):
            arr=root.find('./Controller/Tags/Tag[@Name="DriverA"]/Data/Structure/ArrayMember');arr.remove(arr.find('Element[@Index="[2]"]'))
        e=self.checked(missing);e.step();self.write(e,Sort=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_saved_partial_pos_remains_unqualified(self):
        def active(root):root.find('./Controller/Tags/Tag[@Name="DriverA"]/Data/Structure/StructureMember/DataValueMember[@Name="POS"]').set('Value','1')
        e=self.checked(active);self.write(e,Sort=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'POS zero'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_exact_array_type_shape_and_writable_actual_required(self):
        for field,value in (('DataType','REAL'),('Dimensions','5'),('Constant','true')):
            def wrong(root):root.find('./Controller/Tags/Tag[@Name="SamplesB"]').set(field,value)
            self.assertTrue(self.engine(wrong).blockers)

    def test_numeric_inout_source_kinds(self):
        for dtype in ('SINT','INT','DINT','REAL'):
            def typed(root):
                root.find('.//AddOnInstructionDefinition/Parameters/Parameter[@Name="Samples"]').set('DataType',dtype);root.find('./Controller/Tags/Tag[@Name="SampleView"]').set('DataType',dtype)
                for suffix in ('A','B'):
                    tag=root.find(f'./Controller/Tags/Tag[@Name="Samples{suffix}"]');tag.set('DataType',dtype);arr=tag.find('Data/Array');arr.set('DataType',dtype);arr.find('Element[@Index="[5]"]').set('Value','99')
            e=self.checked(typed);self.write(e,Sort=True);e.step();self.assertEqual(e.memory.read('SamplesA')[1:4],[2,4,6])

    def test_false_aoi_still_copies_required_inputs(self):
        e=self.checked();self.write(e,EnabledA=False);e.memory.values['indexa']=None;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_st_aoi_body_repeats_executed_calls(self):
        def st(root):
            routine=root.find('.//AddOnInstructionDefinition/Routines/Routine[@Name="Logic"]');routine.set('Type','ST');routine.remove(routine.find('RLLContent'))
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='IF Sort THEN SRT(Samples[Index],0,State); SRT(Scratch[Index],0,LocalState); END_IF;'
        e=self.checked(st);self.write(e,Sort=True);e.step();e.memory.write('SamplesA[1]',7);e.step();self.assertEqual(e.memory.read('SamplesA')[1:4],[4,6,7])

    def test_selected_routine_and_periodic_task(self):
        e=self.checked(harness=True);self.write(e,Sort=True);e.step();self.assertEqual(e.memory.read('SamplesB')[2:5],[10,20,30])
        def periodic(root):root.find('.//Task').attrib.update(Type='PERIODIC',Rate='20')
        e=self.checked(periodic);self.write(e,Sort=True);e.step(20);self.assertEqual(e.memory.read('SamplesA')[1:4],[2,4,6])

    def test_multi_dimensional_saved_local_arrays(self):
        import itertools
        for shape,source,axis,length,values in (((2,3),'Scratch[0,Column]',0,2,(6,10,9,12,4,3)),((2,2,3),'Scratch[1,Row,0]',2,3,(6,5,4,3,2,1,12,11,10,9,8,7))):
            def multi(root):
                dims=','.join(map(str,shape));root.find('.//AddOnInstructionDefinition/LocalTags/LocalTag[@Name="Scratch"]').set('Dimensions',dims)
                for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('Scratch[Index],0',source+','+str(axis))
                for suffix in ('A','B'):
                    obj=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure');arr=obj.find('ArrayMember');arr.clear();arr.attrib.update(Name='Scratch',DataType='DINT',Dimensions=dims)
                    for index,value in zip(itertools.product(*(range(n) for n in shape)),values,strict=True):E.SubElement(arr,'Element',Index='['+','.join(map(str,index))+']',Value=str(value))
                    obj.find('StructureMember/DataValueMember[@Name="LEN"]').set('Value',str(length))
            e=self.checked(multi);self.write(e,Sort=True);e.step()
            if len(shape)==2:self.assertEqual(e.memory.read('DriverA.Scratch'),[[6,4,9],[12,10,3]]);self.assertEqual(e.memory.read('DriverB.Scratch'),[[6,10,3],[12,4,9]])
            else:self.assertEqual(e.memory.read('DriverA.Scratch')[1][1],[7,8,9]);self.assertEqual(e.memory.read('DriverB.Scratch')[1][0],[10,11,12])

    def test_nested_instances_keep_local_arrays_and_control_identity(self):
        def nested(root):
            defs=root.find('./Controller/AddOnInstructionDefinitions');wrapper=copy.deepcopy(defs[0]);wrapper.set('Name','SortWrapper');defs.append(wrapper)
            locals=wrapper.find('LocalTags');locals.clear();E.SubElement(locals,'LocalTag',Name='Inner',DataType='LabSortDriver')
            for routine in wrapper.findall('Routines/Routine'):
                content=routine.find('RLLContent');content.clear();prefix='AFI()' if routine.get('Name')=='EnableInFalse' else ''
                E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text=prefix+'LabSortDriver(Inner,Sort,Index,Column,Row,Samples,Grid,Cube,State,GridState,CubeState);'
            for suffix in ('A','B'):
                tag=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]');tag.set('DataType','SortWrapper');obj=tag.find('Data/Structure');inner=copy.deepcopy(obj);inner.tag='StructureMember';inner.set('Name','Inner')
                for local in list(obj):
                    if local.tag in ('ArrayMember','StructureMember'):obj.remove(local)
                obj.set('DataType','SortWrapper');obj.append(inner)
            for text in root.findall('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('LabSortDriver(','SortWrapper(')
        e=self.checked(nested);self.write(e,Sort=True);e.step();self.assertEqual(e.memory.read('DriverA.Inner.Scratch')[1:4],[3,6,9]);self.assertEqual(e.memory.read('DriverB.Inner.Scratch')[2:5],[5,10,15]);self.assertEqual(len(e.addons.instances),4)

    def test_indirect_inout_rebinding_and_failed_frame_restore(self):
        def bank(root):
            dt=E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='SortBank',Family='NoFamily',Class='User');E.SubElement(E.SubElement(dt,'Members'),'Member',Name='Rows',DataType='DINT',Dimension='6')
            tags=root.find('./Controller/Tags');tag=E.SubElement(tags,'Tag',Name='BankIndex',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
            tag=E.SubElement(tags,'Tag',Name='Banks',DataType='SortBank',TagType='Base',Dimensions='2');arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='SortBank',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='SortBank');rows=copy.deepcopy(tags.find('Tag[@Name="SamplesA"]/Data/Array'));rows.tag='ArrayMember';rows.set('Name','Rows')
                if i:
                    for j,value in enumerate((9,3,6),1):rows.find(f'Element[@Index="[{j}]"]').set('Value',str(value))
                obj.append(rows)
            text=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text');text.text=text.text.replace('SampleView','Banks[BankIndex].Rows')
        e=self.checked(bank);self.write(e,Sort=True);e.step();self.write(e,Sort=False);e.step();self.write(e,Sort=True,BankIndex=1,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('Banks[1].Rows')[1:4],[3,6,9]);self.assertEqual(e.memory.read('Banks[0].Rows')[1:4],[2,4,6])

    def test_event_dispatch_later_failure_rolls_back_sorting(self):
        def event(root):
            content=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent');calls=[copy.deepcopy(row) for row in list(content)[:2]]
            for row in list(content)[:2]:content.remove(row)
            rung=E.Element('Rung',Number='0',Type='N');E.SubElement(rung,'Text').text='EVENT(SortEvent);';content.insert(0,rung)
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='EventRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags');body=E.SubElement(E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='EventRoutine',Type='RLL'),'RLLContent')
            for row in calls:body.append(row)
            task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='SortEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(event);self.write(e,Sort=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('DriverB.Scratch')[2:5],[5,10,15])


if __name__=='__main__':unittest.main()
