"""AOI array scope, local queue storage, lifecycle and transactional binding."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine

SAMPLE=Path(__file__).resolve().parents[1]/'samples/AOIQueueLab.L5X'


def logic(root,texts,name='Logic'):
    routine=root.find(f'.//AddOnInstructionDefinition/Routines/Routine[@Name="{name}"]');routine.remove(routine.find('RLLContent'))
    content=E.SubElement(routine,'RLLContent')
    for i,text in enumerate(texts):E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text


class AOIQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'queue.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),mode=mode,routine='MainProgram/MainRoutine' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def write(self,e,**values):
        for name,value in values.items():e.memory.write(name,value)

    def snapshot(self,e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.scan_count,e.time_ms,e.scheduler_description(),e.trace,e.last_timer))

    def pulse(self,e,tag,**values):
        e.memory.write(tag,False);e.step();self.write(e,**values);e.memory.write(tag,True);e.step()

    def test_independent_inout_queues_use_each_instances_index(self):
        e=self.checked();e.step()
        for a,b in ((11,21),(12,22)):self.pulse(e,'Load',ValueA=a,ValueB=b)
        self.assertEqual(e.memory.read('BufferA'),[101,11,12,0,0,901]);self.assertEqual(e.memory.read('BufferB'),[102,0,21,22,0,902])
        self.write(e,Load=False)
        for a,b in ((11,21),(12,22)):
            self.pulse(e,'Unload');self.assertEqual((e.memory.read('ItemA'),e.memory.read('ItemB')),(a,b))
        self.assertEqual(e.memory.read('BufferA'),[101,0,0,0,0,901]);self.assertEqual(e.memory.read('StateA.POS'),0)

    def test_local_stacks_unload_to_disjoint_members_of_same_instance(self):
        e=self.checked();e.step()
        for a,b in ((11,21),(12,22)):self.pulse(e,'Push',ValueA=a,ValueB=b)
        self.write(e,Push=False)
        for a,b in ((12,22),(11,21)):
            self.pulse(e,'Pop');self.assertEqual((e.memory.read('DriverA.Popped'),e.memory.read('DriverB.Popped')),(a,b))
        self.assertEqual(e.memory.read('DriverA.Stack'),[0,0,0,777]);self.assertEqual(e.memory.read('DriverB.Stack'),[0,0,0,777])

    def test_local_left_and_right_shifts_retain_guard_and_independent_edges(self):
        for op in ('BSL','BSR'):
            def change(root):
                routine=root.find('.//AddOnInstructionDefinition/Routines/Routine[@Name="Logic"]/RLLContent/Rung[@Number="4"]/Text')
                routine.text=routine.text.replace('BSL(',op+'(')
                if op=='BSR':
                    for a in root.findall('./Controller/Tags/Tag[@DataType="LabQueueDriver"]/Data/Structure/ArrayMember[@Name="Bits"]'):
                        a.find('Element[@Index="[0]"]').set('Value','1')
            e=self.checked(change);e.step();self.pulse(e,'Shift')
            self.assertEqual(e.memory.read('DriverA.Bits'),[1,0,888] if op=='BSL' else [0,1,888])
            self.assertEqual(e.memory.read('DriverB.Bits'),e.memory.read('DriverA.Bits'))
            before=e.memory.read('DriverA.Bits').copy();e.step();self.assertEqual(e.memory.read('DriverA.Bits'),before)

    def test_frame_indices_do_not_fall_back_to_same_named_controller_tags(self):
        def shadow(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Index',DataType='DINT',TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
        e=self.checked(shadow);e.step();self.pulse(e,'Load')
        self.assertEqual(e.memory.read('Buffer[Index]','@AOI:drivera'),11)
        e.memory.write('Bits[Index]',2,'@AOI:drivera');e.memory.write('BufferA[2]',66)
        self.assertEqual(e.memory.read('Buffer[Bits[Index]]','@AOI:drivera'),66)
        e.memory.write('Buffer[Index].[Index]',False,'@AOI:drivera');self.assertEqual(e.memory.read('BufferA[1]'),9);self.assertEqual(e.memory.read('BufferA[0]'),101)

    def test_missing_index_parameter_is_not_replaced_by_controller_data(self):
        def unknown(root):logic(root,['FFL(Value,Buffer[ControllerIndex],State,?,?);'])
        self.assertTrue(any('Unknown AOI' in b for b in self.engine(unknown).blockers))

    def test_shared_st_array_reference_regression_uses_the_same_frame_scope(self):
        def st(root):
            r=root.find('.//AddOnInstructionDefinition/Routines/Routine[@Name="Logic"]');r.remove(r.find('RLLContent'));r.set('Type','ST')
            E.SubElement(E.SubElement(r,'STContent'),'Line',Number='0').text='Item:=Buffer[Index]; Buffer[Index]:=Value; Bits[Index]:=Value; Word:=Bits[Index];'
        e=self.checked(st);e.step();self.assertEqual(e.memory.read('BufferA[1]'),11);self.assertEqual(e.memory.read('BufferB[2]'),22)
        self.assertEqual((e.memory.read('DriverA.Word'),e.memory.read('DriverB.Word')),(11,22))

    def test_enable_in_false_routine_rearms_external_and_local_controls(self):
        e=self.checked();e.step();self.write(e,Load=True,Push=True,Shift=True);e.step()
        self.write(e,EnabledA=False,IndexA=999);e.step()
        self.assertFalse(e.memory.read('StateA.EN'));self.assertFalse(e.memory.read('DriverA.StackState.EN'));self.assertFalse(e.memory.read('DriverA.ShiftState.EN'))
        self.assertTrue(e.memory.read('StateB.EN'));self.assertFalse(e.memory.read('DriverA.EnableOut'))
        self.write(e,EnabledA=True,IndexA=1,ValueA=33);e.step()
        self.assertEqual(e.memory.read('BufferA[2]'),33);self.assertEqual(e.memory.read('DriverA.Stack[1]'),33);self.assertEqual(e.memory.read('DriverA.Word'),3)
        self.assertEqual(e.memory.read('StateB.POS'),1)

    def test_skipped_aoi_without_false_routine_retains_its_edge_latches(self):
        def no_false(root):root.find('.//AddOnInstructionDefinition').set('ExecuteEnableInFalse','false')
        e=self.checked(no_false);e.step();self.write(e,Load=True);e.step();self.write(e,EnabledA=False);e.step();self.write(e,EnabledA=True,ValueA=33);e.step()
        self.assertEqual(e.memory.read('StateA.POS'),1);self.assertEqual(e.memory.read('BufferA[1]'),11)

    def test_prescan_prevents_first_load_and_run_reentry_retains_data(self):
        def held(root):root.find('./Controller/Tags/Tag[@Name="Load"]/Data/DataValue').set('Value','1')
        e=self.checked(held);e.step();self.assertEqual(e.memory.read('StateA.POS'),0)
        self.pulse(e,'Load');self.assertEqual(e.memory.read('StateA.POS'),1);e.enter_run();e.step()
        self.assertEqual(e.memory.read('StateA.POS'),1);self.assertEqual(e.memory.read('BufferA[1]'),11)

    def test_omitted_local_array_values_stay_unknown_until_explicitly_initialized(self):
        def hidden(root):
            for obj in root.findall('./Controller/Tags/Tag[@DataType="LabQueueDriver"]/Data/Structure'):
                obj.remove(obj.find('ArrayMember[@Name="Stack"]'))
            p=root.find('.//AddOnInstructionDefinition/LocalTags/LocalTag[@Name="Stack"]')
            a=E.SubElement(E.SubElement(p,'DefaultData',Format='Decorated'),'Array',DataType='DINT',Dimensions='4')
            for i in range(4):E.SubElement(a,'Element',Index=f'[{i}]',Value='999')
        e=self.checked(hidden);e.step()
        self.assertEqual(e.memory.values['drivera']['Stack'],[None]*4);self.pulse(e,'Push')
        self.assertEqual(e.memory.values['drivera']['Stack'],[11,None,None,None])
        self.write(e,Push=False);self.pulse(e,'Pop');self.assertEqual(e.memory.read('DriverA.Popped'),11)
        self.assertEqual(e.memory.values['drivera']['Stack'],[0,None,None,None])

    def test_prescan_can_explicitly_establish_omitted_local_buffer_values(self):
        def init(root):
            for obj in root.findall('./Controller/Tags/Tag[@DataType="LabQueueDriver"]/Data/Structure'):obj.remove(obj.find('ArrayMember[@Name="Stack"]'))
            d=root.find('.//AddOnInstructionDefinition');d.set('ExecutePrescan','true');content=E.SubElement(E.SubElement(d.find('Routines'),'Routine',Name='Prescan',Type='RLL'),'RLLContent')
            E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='FLL(0,Stack[0],4);'
        e=self.checked(init);self.assertEqual(e.memory.read('DriverA.Stack'),[0]*4);self.assertEqual(e.memory.read('DriverB.Stack'),[0]*4)

    def test_unknown_required_local_control_is_not_inferred_from_definition_defaults(self):
        def unknown(root):
            obj=root.find('./Controller/Tags/Tag[@Name="DriverA"]/Data/Structure/StructureMember[@Name="StackState"]');obj.remove(obj.find('DataValueMember[@Name="LEN"]'))
        e=self.engine(unknown);self.assertTrue(any('Prescan' in b for b in e.blockers));self.assertEqual(e.memory.values,e.project.initial)

    def test_invalid_second_instance_index_restores_first_instance_and_inputs(self):
        e=self.checked();e.step();self.write(e,Load=True,Push=True,Shift=True,IndexB=999);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'bounds'):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,IndexB=2);e.step()
        self.assertEqual(e.memory.read('BufferA[1]'),11);self.assertEqual(e.memory.read('BufferB[2]'),22)

    def test_late_fault_restores_external_queues_local_stacks_and_shift_outputs(self):
        e=self.checked();e.step();self.write(e,Load=True,Push=True,Shift=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step()
        self.assertEqual(e.memory.read('DriverA.Stack[0]'),11);self.assertEqual(e.memory.read('DriverB.Stack[0]'),22)
        self.assertEqual(e.memory.read('DriverA.Word'),1)

    def test_inout_type_dimensions_and_constant_bindings_remain_exact(self):
        for change in ('dimensions','type','constant'):
            def mutate(root):
                tag=root.find('./Controller/Tags/Tag[@Name="BufferA"]')
                if change=='dimensions':root.find('.//Parameter[@Name="Buffer"]').set('Dimensions','5')
                elif change=='constant':tag.set('Constant','true')
                else:root.find('.//Parameter[@Name="Buffer"]').set('DataType','REAL')
            self.assertTrue(self.engine(mutate).blockers)

    def test_aoi_array_starts_require_a_fully_selected_one_dimensional_element(self):
        for text in ('FFL(Value,Buffer,State,?,?);','FFL(Value,Value,State,?,?);','FFU(Stack[0],Stack[3],StackState,?,?);'):
            self.assertTrue(self.engine(lambda root:logic(root,[text])).blockers,text)
        def matrix(root):
            d=root.find('.//Parameter[@Name="Buffer"]');d.set('Dimensions','2,3')
            for tag in root.findall('./Controller/Tags/Tag[@DataType="DINT"][@Dimensions="6"]'):
                tag.set('Dimensions','2,3');a=tag.find('Data/Array');a.set('Dimensions','2,3')
                for i,item in enumerate(a):item.set('Index',f'[{i//3},{i%3}]')
            logic(root,['FFL(Value,Buffer[0,Index],State,?,?);'])
        self.assertTrue(self.engine(matrix).blockers)

    def test_other_controller_profiles_remain_blocked_for_aoi_array_execution(self):
        for field,value in (('MajorRev','34'),('ProcessorType','1756-L75'),('ProcessorType','5069-L340ERM')):
            self.assertTrue(self.engine(lambda root:root.find('Controller').set(field,value)).blockers)

    def test_instruction_budget_failure_restores_all_instances(self):
        e=self.checked();e.step();self.write(e,Load=True,Push=True,Shift=True);e.instruction_limit=10;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_failed_scan_restores_inout_bindings_after_a_dynamic_bank_change(self):
        def banks(root):
            c=root.find('Controller');tags=c.find('Tags');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Bank',Family='NoFamily',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Data',DataType='DINT',Dimension='6');E.SubElement(members,'Member',Name='State',DataType='CONTROL',Dimension='0')
            tag=E.SubElement(tags,'Tag',Name='Banks',DataType='Bank',TagType='Base',Dimensions='2');array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='Bank',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(array,'Element',Index=f'[{i}]'),'Structure',DataType='Bank')
                a=copy.deepcopy(tags.find('Tag[@Name="BufferA"]/Data/Array'));a.tag='ArrayMember';a.set('Name','Data');obj.append(a)
                state=copy.deepcopy(tags.find('Tag[@Name="StateA"]/Data/Structure'));state.tag='StructureMember';state.set('Name','State');obj.append(state)
            t=E.SubElement(tags,'Tag',Name='Which',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
            text=root.find('.//Program/Routines/Routine/RLLContent/Rung[@Number="1"]/Text');text.text=text.text.replace('BufferA,StateA','Banks[Which].Data,Banks[Which].State')
        e=self.checked(banks);e.step();self.assertEqual(e.memory.frames['@AOI:drivera']['buffer'],('Banks[0].Data',''))
        self.write(e,Which=1,Load=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step()
        self.assertEqual(e.memory.read('Banks[0].Data[1]'),0);self.assertEqual(e.memory.read('Banks[1].Data[1]'),11)
        self.assertEqual(e.memory.frames['@AOI:drivera']['buffer'],('Banks[1].Data',''))

    def test_nested_aoi_array_and_control_bindings_remain_instance_specific(self):
        def nested(root):
            definitions=root.find('./Controller/AddOnInstructionDefinitions');driver=definitions[0];wrapper=copy.deepcopy(driver);wrapper.set('Name','LabQueueWrapper');wrapper.set('ExecuteEnableInFalse','false')
            wrapper.remove(wrapper.find('LocalTags'));locals=E.SubElement(wrapper,'LocalTags');E.SubElement(locals,'LocalTag',Name='Core',DataType='LabQueueDriver',ExternalAccess='None')
            wrapper.remove(wrapper.find('Routines'));routines=E.SubElement(wrapper,'Routines');body=E.SubElement(E.SubElement(routines,'Routine',Name='Logic',Type='RLL'),'RLLContent')
            for i,text in enumerate(('LabQueueDriver(Core,Load,Unload,Push,Pop,Shift,Index,Value,Item,Buffer,State);','MOV(Core.Popped,Popped)MOV(Core.Word,Word);')):
                E.SubElement(E.SubElement(body,'Rung',Number=str(i),Type='N'),'Text').text=text
            definitions.append(wrapper)
            for tag in root.findall('./Controller/Tags/Tag[@DataType="LabQueueDriver"]'):
                tag.set('DataType','LabQueueWrapper');obj=tag.find('Data/Structure');core=copy.deepcopy(obj);core.tag='StructureMember';core.set('Name','Core')
                for item in list(obj):
                    if item.tag!='DataValueMember':obj.remove(item)
                obj.set('DataType','LabQueueWrapper');obj.append(core)
            for text in root.findall('.//Program/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('LabQueueDriver(','LabQueueWrapper(')
        e=self.checked(nested);e.step();self.write(e,Load=True,Push=True,Shift=True);e.step()
        self.assertEqual(e.memory.read('BufferA[1]'),11);self.assertEqual(e.memory.read('BufferB[2]'),22)
        self.assertEqual(e.memory.read('DriverA.Core.Stack[0]'),11);self.assertEqual(e.memory.read('DriverB.Core.Stack[0]'),22)
        self.assertEqual(e.memory.frames['@AOI:driverb.core']['buffer'],('BufferB',''))

    def record_engine(self,dtype,*,overlap=False):
        root=E.parse(SAMPLE.parent/'RecordLab.L5X').getroot();tags=root.find('./Controller/Tags')
        source,queue=('IncomingPart','PartQueue') if dtype=='PartRecord' else ('IncomingText','TextQueue')
        definition=E.SubElement(root.find('./Controller/AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='LocalRecordQueue',Class='Standard',Revision='1.0',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
        pars=E.SubElement(definition,'Parameters')
        for name,kind,usage,required in [('EnableIn','BOOL','Input',False),('EnableOut','BOOL','Output',False),('Load','BOOL','Input',True),('Unload','BOOL','Input',True),('Source',dtype,'InOut',True),('Dest',dtype,'InOut',True)]:
            E.SubElement(pars,'Parameter',Name=name,DataType=kind,Usage=usage,Required=str(required).lower(),Visible=str(required).lower())
        locals=E.SubElement(definition,'LocalTags')
        for name,kind,dim in [('Queue',dtype,'4'),('State','CONTROL','0'),('Result',dtype,'0')]:E.SubElement(locals,'LocalTag',Name=name,DataType=kind,Dimensions=dim,ExternalAccess='None')
        body=E.SubElement(E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
        for i,text in enumerate(('XIC(Load)FFL(Source,Queue[0],State,?,?);','XIC(Unload)FFU(Queue[0],Dest,State,?,?);')):E.SubElement(E.SubElement(body,'Rung',Number=str(i),Type='N'),'Text').text=text
        obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='RecordDriver',DataType='LocalRecordQueue',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='LocalRecordQueue')
        for name in ('EnableIn','EnableOut','Load','Unload'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        a=copy.deepcopy(tags.find(f'Tag[@Name="{queue}"]/Data/Array'));a.tag='ArrayMember';a.set('Name','Queue');obj.append(a)
        state=copy.deepcopy(tags.find('Tag[@Name="PartControl"]/Data/Structure'));state.tag='StructureMember';state.set('Name','State');obj.append(state)
        result=copy.deepcopy(tags.find(f'Tag[@Name="{source}"]/Data/Structure'));result.tag='StructureMember';result.set('Name','Result');obj.append(result)
        main=root.find('.//Program/Routines/Routine/RLLContent');main.clear();dest='RecordDriver.Queue[3]' if overlap else 'RecordDriver.Result'
        E.SubElement(E.SubElement(main,'Rung',Number='0',Type='N'),'Text').text=f'LocalRecordQueue(RecordDriver,LoadPart,UnloadPart,{source},{dest});'
        path=Path(self.tmp.name)/'records.L5X';E.ElementTree(root).write(path,encoding='utf-8');return Engine(Project(path))

    def test_record_local_queue_and_disjoint_result_preserve_exact_unknown_fields(self):
        e=self.record_engine('PartRecord');self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('IncomingPart.Lot',9007199254740993);e.memory.values['incomingpart']['Name']['DATA'][15]=None
        expected=copy.deepcopy(e.memory.read('IncomingPart'));self.pulse(e,'LoadPart');self.write(e,LoadPart=False);self.pulse(e,'UnloadPart')
        self.assertEqual(e.memory.read('RecordDriver.Result'),expected);self.assertEqual(e.memory.read('RecordDriver.Queue[3].Id'),999)
        self.assertTrue(self.record_engine('PartRecord',overlap=True).blockers)

    def test_custom_string_local_queue_and_result_preserve_all_backing_bytes(self):
        e=self.record_engine('LabelText');self.assertEqual(e.blockers,[]);e.step();e.memory.write_string('IncomingText','A$');e.memory.write('IncomingText.DATA[15]',-1)
        expected=copy.deepcopy(e.memory.read('IncomingText'));self.pulse(e,'LoadPart');self.write(e,LoadPart=False);self.pulse(e,'UnloadPart')
        self.assertEqual(e.memory.read('RecordDriver.Result'),expected);self.assertEqual(e.memory.string('RecordDriver.Queue[3]'),'KEEP')

    def test_event_task_calls_restore_both_instances_on_invalid_array_index(self):
        def event(root):
            content=root.find('.//Program/Routines/Routine/RLLContent');calls=[copy.deepcopy(r) for r in content if r.get('Number') in ('1','2')]
            for r in list(content):
                if r.get('Number') in ('1','2'):content.remove(r)
            E.SubElement(E.SubElement(content,'Rung',Number='1',Type='N'),'Text').text='EVENT(QueueEvent);'
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='EventQueues',Class='Standard',Disabled='false');E.SubElement(p,'Tags');body=E.SubElement(E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='EventQueues',Type='RLL'),'RLLContent')
            for r in calls:body.append(r)
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='QueueEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(event);e.step();self.write(e,Load=True,Push=True);e.step();self.assertEqual(e.memory.read('DriverB.Stack[0]'),22)
        self.write(e,Load=False);e.step();self.write(e,Load=True,IndexB=999);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_periodic_and_routine_harness_use_the_same_aoi_bindings(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','Periodic');t.set('Rate','10')
        for e in (self.checked(periodic),self.checked(mode='routine',defer=True)):
            e.step(10);self.write(e,Load=True,Push=True);e.step(10);self.assertEqual(e.memory.read('BufferA[1]'),11);self.assertEqual(e.memory.read('DriverB.Stack[0]'),22)

    def test_report_and_bundled_aoi_queue_lab(self):
        from logixlab.model import ARITIES, ST_ONLY_ARITIES
        from logixlab.server import SAMPLES
        self.assertIn('AOIQueueLab',SAMPLES);e=self.checked();p=e.report()
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(102,29));self.assertIn('InOut',p['control_operations']['aoi_arrays']);self.assertFalse(p['control_operations']['native_control_layout'])
        self.assertEqual(len(e.addons.instances),2);self.assertEqual({r.kind for a in e.project.aois.values() for r in a.routines.values()},{'RLL'})


if __name__=='__main__':unittest.main()
