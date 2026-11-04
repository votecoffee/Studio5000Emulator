"""Logical basic-record payload queues without hidden instruction-state transfer."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_control_operations as base
import test_numeric_queues as numeric
import test_aoi_queues as aoi
from logixlab.model import ModelError

KINDS=('TIMER','COUNTER','CONTROL')


def fields(kind,value):
    if kind=='TIMER':return dict(PRE=500,ACC=value,EN=True,TT=True,DN=False)
    if kind=='COUNTER':return dict(PRE=10,ACC=value,CU=True,CD=False,DN=False,OV=False,UN=False)
    return dict(LEN=value,POS=2,EN=True,EU=False,DN=False,EM=False,ER=False,UL=True,IN=False,FD=True)


def record(kind,value,*,member=None):
    node=E.Element('StructureMember' if member else 'Structure',DataType=kind)
    if member:node.set('Name',member)
    if kind=='QueuedCell':
        E.SubElement(node,'DataValueMember',Name='Id',DataType='DINT',Value=str(value))
        for name,dtype in [('Timer','TIMER'),('Counter','COUNTER'),('State','CONTROL')]:node.append(record(dtype,value,member=name))
        array=E.SubElement(node,'ArrayMember',Name='Timers',DataType='TIMER',Dimensions='2')
        for i in range(2):E.SubElement(array,'Element',Index=f'[{i}]').append(record('TIMER',value+i))
    else:
        for name,item in fields(kind,value).items():E.SubElement(node,'DataValueMember',Name=name,DataType='BOOL' if type(item) is bool else 'DINT',Value=str(int(item)))
    return node


class BasicRecordQueueTests(unittest.TestCase):
    setUp=base.ControlOperationTests.setUp
    checked=base.ControlOperationTests.checked
    snapshot=staticmethod(numeric.NumericQueueTests.snapshot)

    def engine(self,logic=None,*,kind='TIMER',mutate=None,length=2,position=0,**kwargs):
        def payloads(root):
            tags=root.find('./Controller/Tags')
            if kind=='QueuedCell':
                members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name=kind,Class='User'),'Members')
                for name,dtype,size in [('Id','DINT',0),('Timer','TIMER',0),('Counter','COUNTER',0),('State','CONTROL',0),('Timers','TIMER',2)]:E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension=str(size))
            for name,value in [('Incoming',11),('Outgoing',99)]:
                tag=tags.find(f'Tag[@Name="{name}"]');data=tag.find('Data');data.clear();data.set('Format','Decorated');data.append(record(kind,value))
            array=tags.find('Tag[@Name="Queue"]/Data/Array')
            for item,value in zip(array,(11,22,33,999)):
                item.attrib.pop('Value',None);item.append(record(kind,value))
            if mutate:mutate(root)
        logic=logic if logic is not None else ['XIC(StartPB)FFL(Incoming,Queue[0],Ctl,?,?);','XIC(PartSensor)FFU(Queue[0],Outgoing,Ctl,?,?);']
        return base.ControlOperationTests.engine(self,logic,dtype=kind,mutate=payloads,length=length,position=position,**kwargs)

    def pulse(self,e,gate):
        e.memory.write(gate,False);e.step();e.memory.write(gate,True);e.step()

    def fault(self,e,match):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,match):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_all_three_basic_record_fifos_keep_order_flags_and_guards(self):
        for kind in KINDS:
            e=self.checked(kind=kind);e.step();expected=[]
            key='LEN' if kind=='CONTROL' else 'ACC'
            for value in (41,52):
                e.memory.write('Incoming.'+key,value);expected.append(copy.deepcopy(e.memory.read('Incoming')));self.pulse(e,'StartPB')
            self.assertEqual(e.memory.read('Ctl.POS'),2);self.assertTrue(e.memory.read('Ctl.DN'))
            e.memory.write('StartPB',False)
            for item in expected:self.pulse(e,'PartSensor');self.assertEqual(e.memory.read('Outgoing'),item)
            self.assertTrue(e.memory.read('Ctl.EM'));self.assertEqual(e.memory.read('Queue')[3][key],999)

    def test_all_three_basic_record_lifos_pop_in_reverse_and_clear_only_one_slot(self):
        for kind in KINDS:
            e=self.checked(['XIC(StartPB)LFL(Incoming,Queue[0],Ctl,?,?);','XIC(PartSensor)LFU(Queue[0],Outgoing,Ctl,?,?);'],kind=kind);key='LEN' if kind=='CONTROL' else 'ACC';expected=[]
            for value in (41,52):
                e.memory.write('Incoming.'+key,value);expected.append(copy.deepcopy(e.memory.read('Incoming')));self.pulse(e,'StartPB')
            first=copy.deepcopy(e.memory.read('Queue[0]'));e.memory.write('StartPB',False);self.pulse(e,'PartSensor')
            self.assertEqual(e.memory.read('Outgoing'),expected[1]);self.assertEqual(e.memory.read('Queue[0]'),first);self.assertEqual(e.memory.read('Queue[1]'),e.project.default(kind))
            self.pulse(e,'PartSensor');self.assertEqual(e.memory.read('Outgoing'),expected[0]);self.assertEqual(e.memory.read('Queue')[3][key],999)

    def test_sources_queue_cells_and_unloaded_records_own_independent_storage(self):
        e=self.checked(kind='QueuedCell');source=copy.deepcopy(e.memory.read('Incoming'));self.pulse(e,'StartPB');e.memory.write('Incoming.Timers[0].ACC',777)
        self.assertEqual(e.memory.read('Queue[0]'),source);e.memory.write('StartPB',False);self.pulse(e,'PartSensor');e.memory.write('Queue[0].Id',555)
        self.assertEqual(e.memory.read('Outgoing'),source);e.memory.write('Outgoing.Timers[0].ACC',888);self.assertNotEqual(e.memory.read('Incoming.Timers[0].ACC'),888)

    def test_empty_unloads_establish_unknown_outputs_with_declared_defaults(self):
        for kind in (*KINDS,'QueuedCell'):
            for op in ('FFU','LFU'):
                e=self.checked([f'XIC(PartSensor){op}(Queue[0],Outgoing,Ctl,?,?);'],kind=kind);e.memory.values['outgoing']=None
                self.pulse(e,'PartSensor');self.assertEqual(e.memory.read('Outgoing'),e.project.default(kind));self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_unknown_fields_are_copied_as_data_without_interpreting_flags(self):
        for kind in KINDS:
            e=self.checked(kind=kind);key='LEN' if kind=='CONTROL' else 'ACC';e.memory.values['incoming'][key]=None;e.memory.values['incoming']['EN' if kind!='COUNTER' else 'CU']=None
            expected=copy.deepcopy(e.memory.read('Incoming'));self.pulse(e,'StartPB');e.memory.write('StartPB',False);self.pulse(e,'PartSensor');self.assertEqual(e.memory.read('Outgoing'),expected)
            with self.assertRaises(ModelError):e.memory.read('Outgoing.'+key)

    def test_fifo_retains_whole_region_read_and_lifo_only_consumes_selected_record(self):
        for op in ('FFU','LFU'):
            e=self.checked([f'XIC(PartSensor){op}(Queue[0],Outgoing,Ctl,?,?);'],position=1);e.step();e.memory.values['queue'][1]=None;e.memory.write('PartSensor',True)
            if op=='FFU':self.fault(e,'Unknown')
            else:e.step();self.assertEqual(e.memory.read('Outgoing.ACC'),11);self.assertIsNone(e.memory.read('Queue')[1])

    def test_nested_basic_record_arrays_copy_and_clear_with_typed_members(self):
        e=self.checked(kind='QueuedCell');expected=copy.deepcopy(e.memory.read('Incoming'));self.pulse(e,'StartPB');e.memory.write('StartPB',False);self.pulse(e,'PartSensor')
        self.assertEqual(e.memory.read('Outgoing'),expected);self.assertEqual(e.memory.read('Queue[1]'),e.project.default('QueuedCell'))
        self.assertIs(e.memory.read('Queue[1].Timer.EN'),False);self.assertIs(e.memory.read('Queue[1].Counter.CU'),False);self.assertIs(e.memory.read('Queue[1].State.EN'),False)

    def test_alias_indirect_windows_retain_neighbors_and_check_live_bounds(self):
        def aliases(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='View',DataType='TIMER',TagType='Alias',AliasFor='Queue')
        e=self.checked(['XIC(StartPB)FFL(Incoming,View[SpeedCommand],Ctl,?,?);','XIC(PartSensor)FFU(View[SpeedCommand],Outgoing,Ctl,?,?);'],mutate=aliases);e.memory.write('SpeedCommand',1);before=copy.deepcopy(e.memory.read('Queue'));self.pulse(e,'StartPB')
        self.assertEqual(e.memory.read('Queue[0]'),before[0]);self.assertEqual(e.memory.read('Queue[3]'),before[3]);e.memory.write('StartPB',False);e.step();e.memory.write('SpeedCommand',3);e.memory.write('StartPB',True);self.fault(e,'boundary')

    def test_prescan_held_and_full_load_paths_skip_unused_invalid_payload_indices(self):
        def arrays(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Inputs',DataType='TIMER',TagType='Base',Dimensions='2');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='TIMER',Dimensions='2')
        e=self.checked(['XIC(StartPB)FFL(Inputs[SpeedCommand],Queue[0],Ctl,?,?);'],mutate=arrays);e.memory.write('SpeedCommand',99);e.step();e.memory.write('Ctl.POS',2);e.memory.write('StartPB',True);before=copy.deepcopy(e.memory.read('Queue'));e.step();e.step();self.assertEqual(e.memory.read('Queue'),before)
        e.memory.write('StartPB',False);e.step();e.memory.write('Ctl.POS',0);e.memory.write('StartPB',True);self.fault(e,'outside bounds')

    def test_control_payload_cannot_overlap_queue_control_or_unload_into_same_array(self):
        for logic in (['FFL(Ctl,Queue[0],Ctl,?,?);'],['FFU(Queue[0],Ctl,Ctl,?,?);'],['FFU(Queue[0],Queue[3],Ctl,?,?);']):self.assertTrue(self.engine(logic,kind='CONTROL').blockers)
        self.assertTrue(self.engine(['FFL(Incoming,Queue[0],Queue[3],?,?);'],kind='CONTROL').blockers)

    def test_exact_type_constant_and_profile_guards_remain(self):
        self.assertTrue(self.engine(['FFL(Incoming,Queue[0],Ctl,?,?);'],mutate=lambda root:root.find('./Controller/Tags/Tag[@Name="Incoming"]').set('DataType','COUNTER')).blockers)
        for tag in ('Queue','Outgoing'):
            self.assertTrue(self.engine(mutate=lambda root:root.find(f'./Controller/Tags/Tag[@Name="{tag}"]').set('Constant','true')).blockers)
        for key,value in [('MajorRev','34'),('ProcessorType','1756-L75')]:self.assertTrue(self.engine(mutate=lambda root:root.find('Controller').set(key,value)).blockers)

    @staticmethod
    def aoi(root):
        definition=root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition')
        for name in ('Value','Item','Buffer'):
            p=definition.find(f'Parameters/Parameter[@Name="{name}"]');p.set('DataType','TIMER');p.set('Usage','InOut')
        definition.find('LocalTags/LocalTag[@Name="Stack"]').set('DataType','TIMER');E.SubElement(definition.find('LocalTags'),'LocalTag',Name='RecordOut',DataType='TIMER',Dimensions='0')
        tags=root.find('./Controller/Tags')
        for name,value in [('ValueA',11),('ValueB',22),('ItemA',0),('ItemB',0)]:
            tag=tags.find(f'Tag[@Name="{name}"]');tag.set('DataType','TIMER');data=tag.find('Data');data.clear();data.set('Format','Decorated');data.append(record('TIMER',value))
        for name in ('BufferA','BufferB'):
            tag=tags.find(f'Tag[@Name="{name}"]');tag.set('DataType','TIMER');array=tag.find('Data/Array');array.set('DataType','TIMER')
            for item in array:value=int(item.attrib.pop('Value'));item.append(record('TIMER',value))
        for obj in root.findall('./Controller/Tags/Tag[@DataType="LabQueueDriver"]/Data/Structure'):
            for name in ('Value','Item'):obj.remove(obj.find(f'DataValueMember[@Name="{name}"]'))
            array=obj.find('ArrayMember[@Name="Stack"]');array.set('DataType','TIMER')
            for item in array:value=int(item.attrib.pop('Value'));item.append(record('TIMER',value))
        texts=['XIC(Load)FFL(Value,Buffer[Index],State,?,?);','XIC(Unload)FFU(Buffer[Index],Item,State,?,?);','XIC(Push)LFL(Value,Stack[0],StackState,?,?);','XIC(Pop)LFU(Stack[0],RecordOut,StackState,?,?);']
        aoi.logic(root,texts);aoi.logic(root,['AFI()'+text.split(')',1)[1] for text in texts],name='EnableInFalse')

    def test_aoi_exact_inout_and_local_record_storage_roll_back_and_remain_independent(self):
        q=aoi.AOIQueueTests();q.setUp();self.addCleanup(q.doCleanups);e=q.checked(self.aoi);e.step()
        for name,value in [('Load',True),('Push',True),('FaultDivisor',0)]:e.memory.write(name,value)
        self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[1].ACC'),11);self.assertEqual(e.memory.read('BufferB[2].ACC'),22)
        e.memory.write('ValueA.ACC',99);self.assertEqual(e.memory.read('DriverA.Stack[0].ACC'),11)
        for name,value in [('Load',False),('Push',False),('Unload',True),('Pop',True)]:e.memory.write(name,value)
        e.step();self.assertEqual((e.memory.read('ItemA.ACC'),e.memory.read('ItemB.ACC'),e.memory.read('DriverA.RecordOut.ACC'),e.memory.read('DriverB.RecordOut.ACC')),(11,22,11,22))

    def test_later_fault_restores_records_controls_bindings_and_scheduler(self):
        e=self.checked(['XIC(StartPB)FFL(Incoming,Queue[0],Ctl,?,?);','XIC(StartPB)DIV(1,SpeedCommand,SpeedSetpoint);']);e.step();e.memory.write('StartPB',True);e.memory.write('SpeedCommand',0);self.fault(e,'zero')
        e.memory.write('SpeedCommand',1);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertEqual(e.memory.read('Queue[0]'),e.memory.read('Incoming'))

    def test_payload_moves_do_not_copy_or_reset_private_timer_or_file_history(self):
        e=self.checked();e.step();e.last_timer[('incoming',())]=123;e._file_incremental.add(('unrelated',()));history=copy.deepcopy((e.last_timer,e._file_incremental));self.pulse(e,'StartPB');e.memory.write('StartPB',False);self.pulse(e,'PartSensor')
        self.assertEqual((e.last_timer,e._file_incremental),history)

    def test_report_identifies_basic_record_data_and_retains_native_boundaries(self):
        report=self.checked().report()['control_operations'];self.assertEqual(report['basic_record_payloads'],list(KINDS));self.assertIn('private instruction histories',report['aggregate_values']);self.assertFalse(report['native_control_layout']);self.assertFalse(report['native_fault_classification'])
