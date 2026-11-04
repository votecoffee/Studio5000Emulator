"""Mixed numeric FIFO/LIFO payloads, live selection, AOIs and rollback."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_control_operations as fixtures
import test_aoi_queues as aoi
from logixlab.model import ModelError


class NumericQueueTests(unittest.TestCase):
    setUp = fixtures.ControlOperationTests.setUp
    types = ('SINT', 'INT', 'DINT', 'REAL')
    cases = ((-7, (-7, -7, -7, -7.0)),
             (4660, (52, 4660, 4660, 4660.0)),
             (1193046, (86, 13398, 1193046, 1193046.0)),
             (-3.5, (-4, -4, -4, -3.5)))

    def engine(self, rungs, *, source_type='DINT', dest_type='DINT', source=11, mutate=None, **kwargs):
        def fields(root):
            for name, dtype, value in [('Incoming', source_type, source), ('Outgoing', dest_type, 99)]:
                tag=root.find(f'./Controller/Tags/Tag[@Name="{name}"]');tag.set('DataType',dtype)
                data=tag.find('Data/DataValue');data.set('DataType',dtype);data.set('Value',str(value))
            if mutate:mutate(root)
        return fixtures.ControlOperationTests.engine(self,rungs,mutate=fields,**kwargs)

    def checked(self, *args, **kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);self.assertFalse(e.memory.structural);return e

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.scan_count,e.time_ms,
                              e.scheduler_description(),e.trace,e.last_timer,e._file_incremental))

    def fault(self,e,match):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,match):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_all_sixteen_load_type_pairs_for_fifo_and_lifo(self):
        for op in ('FFL','LFL'):
            for source_type,(value,expected) in zip(self.types,self.cases):
                for dtype,result in zip(self.types,expected):
                    with self.subTest(op=op,source=source_type,array=dtype):
                        e=self.checked([f'XIC(StartPB){op}(Incoming,Queue[0],Ctl,?,?);'],source_type=source_type,source=value,dtype=dtype,length=3,queue=(0,0,0,99))
                        e.step();e.memory.write('StartPB',True);e.step()
                        self.assertEqual(e.memory.read('Queue'),[result,0,0,99]);self.assertEqual(e.memory.read('Incoming'),value)
                        self.assertEqual(e.memory.read('Ctl.POS'),1);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_all_sixteen_unload_type_pairs_for_fifo_and_lifo(self):
        for op in ('FFU','LFU'):
            for dtype,(value,expected) in zip(self.types,self.cases):
                for dest_type,result in zip(self.types,expected):
                    with self.subTest(op=op,array=dtype,dest=dest_type):
                        e=self.checked([f'XIC(StartPB){op}(Queue[0],Outgoing,Ctl,?,?);'],dest_type=dest_type,dtype=dtype,length=3,position=1,queue=(value,0,0,99))
                        e.step();e.memory.values['outgoing']=None;e.memory.write('StartPB',True);e.step()
                        self.assertEqual(e.memory.read('Outgoing'),result);self.assertEqual(e.memory.read('Queue'),[0,0,0,99]);self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_float32_integer_precision_and_nearest_even_rounding(self):
        for value,expected in ((16777217,16777216.0),(-16777217,-16777216.0)):
            e=self.checked(['XIC(StartPB)FFL(Incoming,Queue[0],Ctl,?,?);'],dtype='REAL',source=value,length=2)
            e.step();e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue[0]'),expected)
        for value,expected in ((2.5,2),(3.5,4),(-2.5,-2),(-3.5,-4)):
            e=self.checked(['XIC(StartPB)LFL(Incoming,Queue[0],Ctl,?,?);'],dtype='INT',source_type='REAL',source=value,length=2)
            e.step();e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue[0]'),expected)

    def test_bounded_real_and_dint_immediates_convert_only_on_reached_load(self):
        for literal,dtype,expected in [('3.5','SINT',4),('4660','SINT',52),('-1','INT',-1),('16777217','REAL',16777216.0)]:
            for op in ('FFL','LFL'):
                e=self.checked([f'XIC(StartPB){op}({literal},Queue[0],Ctl,?,?);'],dtype=dtype,length=1,queue=(0,0,0,99))
                e.step();e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Queue[0]'),expected)
        e=self.checked(['XIC(StartPB)FFL(128.0,Queue[0],Ctl,?,?);'],dtype='SINT',length=1,queue=(0,0,0,99))
        e.step();e.memory.write('StartPB',True);self.fault(e,'overflow')

    def test_fifo_shift_and_lifo_pop_keep_array_type_and_other_slots(self):
        for op,expected,remaining in [('FFU',2,[2.5,7.25,0.0,99]),('LFU',2,[1.5,0.0,7.25,99])]:
            e=self.checked([f'XIC(StartPB){op}(Queue[0],Outgoing,Ctl,?,?);'],dtype='REAL',dest_type='DINT',length=3,position=2,queue=(1.5,2.5,7.25,99))
            e.step();e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Outgoing'),expected);self.assertEqual(e.memory.read('Queue'),remaining)

    def test_empty_unload_establishes_typed_zero_without_consuming_array_values(self):
        for op in ('FFU','LFU'):
            for dtype,dest_type in [('REAL','SINT'),('SINT','REAL')]:
                e=self.checked([f'XIC(StartPB){op}(Queue[0],Outgoing,Ctl,?,?);'],dtype=dtype,dest_type=dest_type,length=2,queue=(0,0,0,99))
                e.step();e.memory.values['queue']=[None]*4;e.memory.values['outgoing']=None
                e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Outgoing'),0)
                self.assertIs(type(e.memory.read('Outgoing')),float if dest_type=='REAL' else int);self.assertEqual(e.memory.values['queue'],[None]*4)

    @staticmethod
    def indirect(root):
        tags=root.find('./Controller/Tags')
        for name,dtype,values in [('Inputs','REAL',[-3.5,2.5]),('Outputs','INT',[77,88])]:
            tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base',Dimensions='2')
            array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions='2')
            for i,value in enumerate(values):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value))
        tag=E.SubElement(tags,'Tag',Name='Index',DataType='DINT',TagType='Base')
        E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='99')
        E.SubElement(tags,'Tag',Name='SourceAlias',TagType='Alias',AliasFor='Inputs[Index]')
        E.SubElement(tags,'Tag',Name='DestAlias',TagType='Alias',AliasFor='Outputs[Index]')

    def test_alias_indirect_payloads_are_lazy_and_convert_when_an_edge_moves_data(self):
        for op in ('FFL','LFL'):
            e=self.checked([f'XIC(StartPB){op}(SourceAlias,Queue[0],Ctl,?,?);'],mutate=self.indirect,length=1,dtype='SINT',queue=(0,0,0,99))
            e.step();e.memory.write('StartPB',True);self.fault(e,'outside bounds')
            e.memory.write('Index',0);e.step();self.assertEqual(e.memory.read('Queue[0]'),-4)
            e.memory.write('Index',99);e.step();e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
            self.assertEqual(e.memory.read('Ctl.POS'),1)
        for op in ('FFU','LFU'):
            e=self.checked([f'XIC(StartPB){op}(Queue[0],DestAlias,Ctl,?,?);'],mutate=self.indirect,length=2,position=1,dtype='REAL',queue=(3.5,0,0,99))
            e.step();e.memory.write('StartPB',True);self.fault(e,'outside bounds')
            e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Outputs'),[77,4])
            e.memory.write('Index',99);e.step();self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_required_unknown_load_faults_and_can_recover(self):
        for op in ('FFL','LFL'):
            e=self.checked([f'XIC(StartPB){op}(Incoming,Queue[0],Ctl,?,?);'],dtype='INT',source_type='REAL',length=2)
            e.memory.values['incoming']=None;e.step();e.memory.write('StartPB',True);self.fault(e,'Unknown')
            e.memory.write('Incoming',3.5);e.step();self.assertEqual(e.memory.read('Queue[0]'),4)

    def test_real_overflow_restores_data_control_time_trace_and_scheduler(self):
        for op in ('FFL','LFL','FFU','LFU'):
            load=op in ('FFL','LFL')
            rung=f'{op}(Incoming,Queue[0],Ctl,?,?);' if load else f'{op}(Queue[0],Outgoing,Ctl,?,?);'
            e=self.checked(['XIC(StartPB)'+rung],dtype='SINT' if load else 'REAL',source_type='REAL',dest_type='SINT',source=128.0,length=2,position=0 if load else 1,queue=(0 if load else 128.0,17,0,99))
            e.step();e.memory.write('StartPB',True);self.fault(e,'overflow')
            e.memory.write('Incoming' if load else 'Queue[0]',3.5);e.step()
            self.assertEqual(e.memory.read('Queue[0]' if load else 'Outgoing'),4)

    @staticmethod
    def mixed_aoi(root):
        # AOI call parameters keep exact declared binding types. Only the
        # queue instructions convert between those independently typed values.
        def change(node,dtype):
            node.set('DataType',dtype)
            for child in node.iter():
                if child.get('DataType')=='DINT':child.set('DataType',dtype)
        change(root.find('.//Parameter[@Name="Value"]'),'REAL')
        change(root.find('.//Parameter[@Name="Buffer"]'),'INT')
        change(root.find('.//LocalTag[@Name="Stack"]'),'SINT')
        for name in ('ValueA','ValueB'):change(root.find(f'./Controller/Tags/Tag[@Name="{name}"]'),'REAL')
        for name in ('BufferA','BufferB'):change(root.find(f'./Controller/Tags/Tag[@Name="{name}"]'),'INT')
        for tag in root.findall('./Controller/Tags/Tag[@DataType="LabQueueDriver"]'):
            record=tag.find('Data/Structure');change(record.find('DataValueMember[@Name="Value"]'),'REAL');stack=record.find('ArrayMember[@Name="Stack"]');change(stack,'SINT')
            for item in stack.findall('Element'):item.set('Value','77')
        aoi.logic(root,['XIC(Load)FFL(Value,Buffer[Index],State,?,?);','XIC(Unload)FFU(Buffer[Index],Item,State,?,?);',
                        'XIC(Push)LFL(Value,Stack[0],StackState,?,?);','XIC(Pop)LFU(Stack[0],Popped,StackState,?,?);'])

    def test_aoi_inout_arrays_local_stacks_and_later_fault_rollback(self):
        e=aoi.AOIQueueTests.engine(self,self.mixed_aoi);self.assertEqual(e.blockers,[]);e.step()
        for name,value in [('Load',True),('Push',True),('ValueA',3.5),('ValueB',-2.5),('FaultDivisor',0)]:e.memory.write(name,value)
        self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual(e.memory.read('BufferA[1]'),4);self.assertEqual(e.memory.read('BufferB[2]'),-2)
        self.assertEqual(e.memory.read('DriverA.Stack[0]'),4);self.assertEqual(e.memory.read('DriverB.Stack[0]'),-2)
        for name,value in [('Load',False),('Push',False),('Unload',True),('Pop',True)]:e.memory.write(name,value)
        e.step();self.assertEqual(e.memory.read('ItemA'),4);self.assertEqual(e.memory.read('DriverB.Popped'),-2)

    def test_unqualified_types_constants_shapes_and_profiles_stay_blocked(self):
        for dtype in ('BOOL','LINT','USINT','UINT','UDINT','ULINT'):
            for load in (True,False):
                rung='FFL(Incoming,Queue[0],Ctl,?,?);' if load else 'FFU(Queue[0],Outgoing,Ctl,?,?);'
                e=self.engine([rung],source_type=dtype if load else 'DINT',dest_type='DINT' if load else dtype,source=1)
                self.assertTrue(e.blockers,(dtype,load))
        for text in ('FFL(2147483648,Queue[0],Ctl,?,?);','FFL(3.4e99,Queue[0],Ctl,?,?);','FFU(Queue[0],1,Ctl,?,?);'):
            self.assertTrue(self.engine([text],length=2).blockers,text)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Outgoing"]').set('Constant','true')
        self.assertTrue(self.engine(['FFU(Queue[0],Outgoing,Ctl,?,?);'],mutate=constant).blockers)
        for major,processor in [('34','1756-L85E'),('35','1756-L75')]:
            def profile(root):root.find('Controller').set('MajorRev',major);root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(['FFL(Incoming,Queue[0],Ctl,?,?);'],source_type='REAL',dtype='INT',mutate=profile).blockers)

    def test_report_identifies_bounded_conversion_and_retained_native_limits(self):
        from logixlab.control_operations import description
        report=description();self.assertIn('FFL/FFU/LFL/LFU',report['numeric_conversions'])
        self.assertIn('nearest-even',report['numeric_conversions']);self.assertIn('rollback',report['numeric_selection'])
        self.assertFalse(report['native_fault_classification'])
