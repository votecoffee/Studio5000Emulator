"""Logical FIFO/LIFO UDT payloads with binary64 and exact time/date fields."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_fifo_records as fixtures
from logixlab.model import ModelError

STAMP=1794483000000000123
POSITION=1.0000000000000002
EXTRA={'Wait':'TIME32','Elapsed':'TIME','Ticks':'LTIME','Date':'DT'}


def precise_fields(root):
    types=root.find('./Controller/DataTypes')
    point=E.SubElement(E.SubElement(types,'DataType',Name='QueuePoint',Family='NoFamily',Class='User'),'Members')
    for name,dtype in (('Axis','LREAL'),('Age','TIME')):
        E.SubElement(point,'Member',Name=name,DataType=dtype,Dimension='0')
    members=types.find('DataType[@Name="PartRecord"]/Members')
    for name,dtype in EXTRA.items():E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension='0')
    for name,dtype in (('Positions','LREAL'),('Points','QueuePoint')):
        E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension='2')
    for obj in root.findall('.//Structure[@DataType="PartRecord"]'):
        for name,dtype in EXTRA.items():E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value='0')
        array=E.SubElement(obj,'ArrayMember',Name='Positions',DataType='LREAL',Dimensions='2')
        for i in range(2):E.SubElement(array,'Element',Index=f'[{i}]',Value='0.0')
        array=E.SubElement(obj,'ArrayMember',Name='Points',DataType='QueuePoint',Dimensions='2')
        for i in range(2):
            point=E.SubElement(E.SubElement(array,'Element',Index=f'[{i}]'),'Structure',DataType='QueuePoint')
            E.SubElement(point,'DataValueMember',Name='Axis',DataType='LREAL',Value='0.0')
            E.SubElement(point,'DataValueMember',Name='Age',DataType='TIME',Value='0')


class PreciseRecordQueueTests(unittest.TestCase):
    setUp=fixtures.RecordQueueTests.setUp
    engine=fixtures.RecordQueueTests.engine
    checked=fixtures.RecordQueueTests.checked
    pulse=fixtures.RecordQueueTests.pulse
    part=fixtures.RecordQueueTests.part

    def precise(self,logic=None,mutate=None):
        def change(root):
            precise_fields(root)
            if mutate:mutate(root)
        return self.checked(logic,mutate=change)

    def sample(self,e,number=1):
        self.part(e,number)
        for path,value in {'Position':POSITION*number,'Timestamp':STAMP+number,
                'Wait':-12345,'Elapsed':-123456789,'Ticks':-987654321,'Date':1794483000000001,
                'Positions[0]':POSITION,'Positions[1]':2.0000000000000004,
                'Points[0].Axis':POSITION,'Points[0].Age':-999,
                'Points[1].Axis':-POSITION,'Points[1].Age':999}.items():
            e.memory.write('IncomingPart.'+path,value)
        return copy.deepcopy(e.memory.read('IncomingPart'))

    def snapshot(self,e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved,e.addons.instances,
                              e.last_timer,e.scan_count,e.time_ms,e.trace,e.scheduler_description()))

    def test_fifo_preserves_binary64_and_all_time_families_in_order(self):
        e=self.precise();saved=[]
        for number in (1,2,3):saved.append(self.sample(e,number));self.pulse(e,'LoadPart')
        for value in saved:
            self.pulse(e,'UnloadPart');self.assertEqual(e.memory.read('OutgoingPart'),value)
        self.assertNotEqual(saved[0]['Position'],1.0)
        self.assertEqual(saved[0]['Timestamp'],STAMP+1)
        self.assertIs(type(saved[0]['Position']),float);self.assertIs(type(saved[0]['Timestamp']),int)

    def test_lifo_preserves_nested_arrays_and_returns_reverse_order(self):
        e=self.precise();saved=[]
        for number in (1,2):saved.append(self.sample(e,number));self.pulse(e,'PushPart')
        for value in reversed(saved):
            self.pulse(e,'PopPart');self.assertEqual(e.memory.read('PoppedPart'),value)
        self.assertEqual(e.memory.read('StackControl.POS'),0)

    def test_source_and_unloaded_records_are_detached_from_queue_storage(self):
        e=self.precise();saved=self.sample(e);self.pulse(e,'LoadPart')
        self.sample(e,2);self.assertEqual(e.memory.read('PartQueue[0]'),saved)
        self.pulse(e,'LoadPart');self.pulse(e,'UnloadPart')
        e.memory.write('PartQueue[0].Points[0].Axis',99)
        e.memory.write('PartQueue[0].Timestamp',STAMP+99)
        self.assertEqual(e.memory.read('OutgoingPart'),saved)

    def test_fifo_tail_and_empty_unload_establish_typed_zeros(self):
        e=self.precise();self.sample(e);self.pulse(e,'LoadPart');self.pulse(e,'UnloadPart')
        zero=e.project.default('PartRecord');self.assertEqual(e.memory.read('PartQueue[2]'),zero)
        self.pulse(e,'UnloadPart');self.assertEqual(e.memory.read('OutgoingPart'),zero)
        self.assertIs(type(zero['Position']),float)
        for name in ('Timestamp',*EXTRA):self.assertIs(type(zero[name]),int)

    def test_lifo_clears_only_popped_slot_and_preserves_guards(self):
        e=self.precise();guard=copy.deepcopy(e.memory.read('PartStack[3]'))
        first=self.sample(e);self.pulse(e,'PushPart');self.sample(e,2);self.pulse(e,'PushPart')
        self.pulse(e,'PopPart');self.assertEqual(e.memory.read('PartStack[0]'),first)
        self.assertEqual(e.memory.read('PartStack[1]'),e.project.default('PartRecord'))
        self.assertEqual(e.memory.read('PartStack[3]'),guard)

    def test_unknown_leaves_remain_unknown_through_full_logical_copies(self):
        e=self.precise();self.sample(e)
        e.memory.values['incomingpart']['Position']=None;e.memory.values['incomingpart']['Timestamp']=None
        e.memory.values['incomingpart']['Points'][1]['Age']=None
        expected=copy.deepcopy(e.memory.values['incomingpart'])
        self.pulse(e,'LoadPart');self.assertEqual(e.memory.read('PartQueue[0]'),expected)
        self.pulse(e,'UnloadPart');self.assertEqual(e.memory.read('OutgoingPart'),expected)
        self.assertIsNone(e.memory.values['outgoingpart']['Timestamp'])

    def test_alias_payloads_and_indirect_starts_keep_declared_record_type(self):
        def aliases(root):
            tags=root.find('./Controller/Tags')
            for name,target in (('SourceView','IncomingPart'),('DestView','OutgoingPart')):
                E.SubElement(tags,'Tag',Name=name,DataType='PartRecord',TagType='Alias',AliasFor=target)
        logic=['XIC(LoadPart)FFL(SourceView,PartQueue[FaultDivisor],PartControl,?,?);',
               'XIC(UnloadPart)FFU(PartQueue[FaultDivisor],DestView,PartControl,?,?);']
        e=self.precise(logic,aliases);expected=self.sample(e);self.pulse(e,'LoadPart')
        self.assertEqual(e.memory.read('PartQueue[1]'),expected)
        self.pulse(e,'UnloadPart');self.assertEqual(e.memory.read('OutgoingPart'),expected)

    def test_false_and_held_calls_defer_unknown_source_records(self):
        e=self.precise();expected=self.sample(e);self.pulse(e,'LoadPart')
        e.memory.values['incomingpart']=None;e.step()
        self.assertEqual(e.memory.read('PartQueue[0]'),expected)
        e.memory.write('LoadPart',False);e.step();self.assertEqual(e.memory.read('PartControl.POS'),1)
        e.memory.write('LoadPart',True);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_later_fault_restores_records_edges_and_schedule_then_retries(self):
        e=self.precise();e.step();expected=self.sample(e)
        e.memory.write('LoadPart',True);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('PartQueue[0]'),expected)

    def test_run_entry_preserves_exact_payloads_and_does_not_replay_load(self):
        e=self.precise();expected=self.sample(e);self.pulse(e,'LoadPart')
        e.enter_run();e.step();self.assertEqual(e.memory.read('PartControl.POS'),1)
        self.assertEqual(e.memory.read('PartQueue[0]'),expected)

    def test_aoi_inout_payloads_preserve_nested_values_and_clear_tail(self):
        def worker(root):
            c=root.find('Controller')
            definition=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='PreciseQueue',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
            params=E.SubElement(definition,'Parameters')
            items=[('EnableIn','BOOL','Input',0),('EnableOut','BOOL','Output',0),
                   ('Value','PartRecord','InOut',0),('Buffer','PartRecord','InOut',4),
                   ('State','CONTROL','InOut',0),('Item','PartRecord','InOut',0),
                   ('Load','BOOL','Input',0),('Unload','BOOL','Input',0)]
            for name,dtype,usage,size in items:
                required='false' if name.startswith('Enable') else 'true'
                p=E.SubElement(params,'Parameter',Name=name,DataType=dtype,Usage=usage,TagType='Base',Required=required,Visible=required)
                if size:p.set('Dimensions',str(size))
            E.SubElement(definition,'LocalTags')
            content=E.SubElement(E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
            for i,text in enumerate(('XIC(Load)FFL(Value,Buffer[0],State,?,?);','XIC(Unload)FFU(Buffer[0],Item,State,?,?);')):
                E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Worker',DataType='PreciseQueue',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='PreciseQueue')
            for name in ('EnableIn','EnableOut','Load','Unload'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.precise(['PreciseQueue(Worker,IncomingPart,PartQueue,PartControl,OutgoingPart,LoadPart,UnloadPart);'],worker)
        expected=self.sample(e);self.pulse(e,'LoadPart');self.pulse(e,'UnloadPart')
        self.assertEqual(e.memory.read('OutgoingPart'),expected)
        self.assertEqual(e.memory.read('PartQueue[2]'),e.project.default('PartRecord'))

    def test_scalar_wide_and_time_queues_remain_outside_record_profile(self):
        import test_control_operations
        case=test_control_operations.ControlOperationTests();case.setUp();self.addCleanup(case.doCleanups)
        for dtype in ('LREAL','TIME32','TIME','LTIME','DT','LDT'):
            e=case.engine(['FFL(Incoming,Queue[0],Ctl,?,?);'],dtype=dtype)
            self.assertTrue(e.blockers,dtype)

    def test_report_lists_udt_leaf_types_without_claiming_native_layout(self):
        report=self.precise().report()['control_operations']
        self.assertTrue({'LREAL','TIME32','TIME','LTIME','DT','LDT'}<=set(report['udt_scalar_fields']))
        self.assertFalse(report['native_control_layout'])


if __name__=='__main__':unittest.main()
