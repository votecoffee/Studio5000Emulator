"""AVE narrow results, retained controls and canonical storage boundaries."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_array_statistics as fixtures
from logixlab.model import ModelError


class IntegerAverageTests(unittest.TestCase):
    setUp=fixtures.ArrayStatisticsTests.setUp
    checked=fixtures.ArrayStatisticsTests.checked

    def engine(self,rungs=None,*,result_type='DINT',mutate=None,**kwargs):
        def typed(root):
            tag=root.find('./Controller/Tags/Tag[@Name="Result"]');tag.set('DataType',result_type);tag.find('Data/DataValue').set('DataType',result_type)
            if mutate:mutate(root)
        return fixtures.ArrayStatisticsTests.engine(self,rungs or ['AVE(Queue[0],0,Result,Ctl,?,?);'],mutate=typed,**kwargs)

    @staticmethod
    def snapshot(e):
        # AOI frame/binding caches are transactional. Standalone static lookup
        # memoization is deliberately retained by Engine.step and is not PLC state.
        bindings=(e.memory.frames,e.memory._resolved,e.addons.instances) if e.project.aois else None
        return copy.deepcopy((e.memory.values,bindings,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def test_source_and_result_type_matrix_and_guards(self):
        for source in ('SINT','INT','DINT','REAL'):
            for result in ('SINT','INT','DINT'):
                e=self.checked(dtype=source,result_type=result,queue=(1,2,3,4,99));e.step()
                self.assertEqual(e.memory.read('Result'),2);self.assertIs(type(e.memory.read('Result')),int)
                self.assertEqual(e.memory.read('Queue'),[1,2,3,4,99]);self.assertEqual((e.memory.read('Ctl.POS'),e.memory.read('Ctl.DN')),(4,True))

    def test_signed_halves_and_nonhalf_means_round_to_nearest_even(self):
        for dtype in ('SINT','INT','DINT'):
            for values,expected in (((1,2),2),((2,3),2),((3,4),4),((-1,-2),-2),((-2,-3),-2),((-3,-4),-4),((1,2,2),2),((-1,-2,-2),-2)):
                e=self.checked(dtype='REAL',result_type=dtype,length=len(values),queue=values);e.step();self.assertEqual(e.memory.read('Result'),expected)

    def test_float32_source_and_accumulation_precision_remains_explicit(self):
        e=self.checked(length=1,queue=(16777217,99));e.step();self.assertEqual(e.memory.read('Result'),16777216)
        e=self.checked(queue=(16777216,1,-16777216,2,99));e.step();self.assertEqual(e.memory.read('Result'),0)
        e=self.checked(result_type='REAL',queue=(16777216,1,-16777216,2,99));e.step();self.assertEqual(e.memory.read('Result'),0.5)
        e=self.checked(length=1,queue=(2147483647,99));before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'DINT overflow'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_integer_range_is_checked_after_mean_rounding(self):
        for dtype,value,expected in (('SINT',127.49,127),('SINT',-128.5,-128),('INT',32767.49,32767),('INT',-32768.5,-32768),('DINT',2147483520,2147483520),('DINT',-2147483648,-2147483648)):
            e=self.checked(result_type=dtype,dtype='REAL',length=1,queue=(value,99));e.step();self.assertEqual(e.memory.read('Result'),expected)

    def test_range_errors_restore_result_controls_and_prior_changes(self):
        for dtype,value in (('SINT',127.5),('SINT',-128.51),('INT',32767.5),('INT',-32768.51),('DINT',2147483648.0)):
            e=self.checked(['MOV(23,SpeedCommand);','AVE(Queue[0],0,Result,Ctl,?,?);'],result_type=dtype,dtype='REAL',length=1,queue=(value,99));before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,dtype+' overflow'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_held_result_then_false_rearm_uses_new_samples(self):
        e=self.checked(['XIC(StartPB)AVE(Queue[0],0,Result,Ctl,?,?);'],queue=(1,2,3,4,99))
        e.memory.write('StartPB',True);e.step();e.memory.write('Queue[0]',5);e.step();self.assertEqual(e.memory.read('Result'),2)
        e.memory.write('StartPB',False);e.step();self.assertEqual((e.memory.read('Ctl.POS'),e.memory.read('Result')),(0,2))
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Result'),4)

    def test_false_and_inhibited_calls_skip_live_source_indices(self):
        for mode in ('false','EN','DN','ER'):
            e=self.checked(['XIC(StartPB)AVE(Queue[Incoming],0,Result,Ctl,?,?);'])
            e.memory.write('Incoming',999)
            if mode!='false':e.memory.write('StartPB',True);e.memory.write('Ctl.'+mode,True)
            e.step();self.assertEqual(e.memory.read('Result'),7)

    def test_full_write_establishes_unknown_and_prescan_retains_result(self):
        e=self.checked();e.memory.values['result']=None;e.step();self.assertEqual(e.memory.read('Result'),5)
        e.enter_run();self.assertEqual(e.memory.read('Result'),5);self.assertFalse(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Ctl.POS'),4)

    def test_two_and_three_dimensional_integer_results_keep_axis_boundaries(self):
        for shape,values,source,dim,length,expected in (((2,3),(1,2,3,4,5,6),'Queue[0,1]',0,2,4),((2,2,3),range(12),'Queue[1,0,2]',1,2,10)):
            e=self.checked([f'AVE({source},{dim},Result,Ctl,?,?);'],result_type='INT',length=length,mutate=fixtures.ArrayStatisticsTests.multidimensional(shape,values));e.step();self.assertEqual(e.memory.read('Result'),expected)

    @staticmethod
    def packet(root):
        import test_control_operations as controls
        c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='AveragePacket',Family='NoFamily',Class='User'),'Members')
        for name,dtype,dim in (('Samples','REAL','2'),('Mean','INT','0'),('Guard','INT','0'),('State','CONTROL','0')):E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension=dim)
        tags=c.find('Tags');obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet1',DataType='AveragePacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='AveragePacket')
        arr=E.SubElement(obj,'ArrayMember',Name='Samples',DataType='REAL',Dimensions='2')
        for i,value in enumerate((2,3)):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(value))
        for name,value in (('Mean',7),('Guard',99)):E.SubElement(obj,'DataValueMember',Name=name,DataType='INT',Value=str(value))
        state=controls.control_data(obj,2);state.tag='StructureMember';state.set('Name','State')
        E.SubElement(tags,'Tag',Name='MeanView',DataType='INT',TagType='Alias',AliasFor='Packet1.Mean')
        E.SubElement(tags,'Tag',Name='StateView',DataType='CONTROL',TagType='Alias',AliasFor='Packet1.State')

    def test_disjoint_sibling_integer_result_and_control_share_a_base(self):
        e=self.checked(['AVE(Packet1.Samples[0],0,MeanView,StateView,?,?);'],mutate=self.packet);e.step()
        self.assertEqual((e.memory.read('Packet1.Mean'),e.memory.read('Packet1.Guard')),(2,99));self.assertEqual(e.memory.read('Packet1.Samples'),[2.0,3.0])

    def test_own_control_and_source_array_results_are_rejected_canonically(self):
        for dest in ('Ctl.LEN','Ctl.POS','Queue[4]'):
            self.assertTrue(self.engine([f'AVE(Queue[0],0,{dest},Ctl,?,?);']).blockers)
        for dest in ('StateView.LEN','Packet1.State.POS'):
            self.assertTrue(any('CONTROL record' in b for b in self.engine([f'AVE(Packet1.Samples[0],0,{dest},StateView,?,?);'],mutate=self.packet).blockers))

    def test_std_still_requires_real_and_ave_rejects_other_result_types(self):
        for dtype in ('SINT','INT','DINT'):self.assertTrue(self.engine(['STD(Queue[0],0,Result,Ctl,?,?);'],result_type=dtype).blockers)
        for dtype in ('BOOL','LINT','USINT','UINT','UDINT','ULINT'):self.assertTrue(self.engine(result_type=dtype).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Result"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)

    def test_unknown_samples_and_later_fault_restore_integer_and_control_state(self):
        e=self.checked();e.memory.values['queue'][1]=None;before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)
        e=self.checked(['AVE(Queue[0],0,Result,Ctl,?,?);','DIV(1,Incoming,SpeedCommand);']);e.memory.write('Incoming',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Incoming',1);e.step();self.assertEqual(e.memory.read('Result'),5)

    def aoi(self,kind='INT',mutate=None,inout=False):
        import test_aoi_statistics as aoi
        f=aoi.AOIStatisticsTests();f.setUp();self.addCleanup(f.doCleanups)
        def typed(root):
            definition=root.find('.//AddOnInstructionDefinition')
            for name in ('Mean','ColumnMean','RowMean','PlaneMean','LocalMean'):
                param=definition.find(f'Parameters/Parameter[@Name="{name}"]')
                for node in param.iter():
                    if node.get('DataType')=='REAL':node.set('DataType',kind)
                for suffix in ('A','B'):root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure/DataValueMember[@Name="{name}"]').set('DataType',kind)
            for suffix in ('A',):
                for arr in (root.find(f'./Controller/Tags/Tag[@Name="Samples{suffix}"]/Data/Array'),root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure/ArrayMember[@Name="Scratch"]')):
                    for i,value in enumerate((1.5,2.5,3.5),1):arr.find(f'Element[@Index="[{i}]"]').set('Value',str(value))
            if inout:
                param=definition.find('Parameters/Parameter[@Name="Mean"]');param.set('Usage','InOut');param.set('Required','true')
                for child in list(param):
                    if child.tag=='DefaultData':param.remove(child)
                for suffix,rung in zip(('A','B'),root.findall('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung')[:2],strict=True):
                    obj=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="Mean"]'))
                    tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='MeanOut'+suffix,DataType=kind,TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=kind,Value='7')
                    text=rung.find('Text');text.text=text.text.replace(');',',MeanOut'+suffix+');')
            if mutate:mutate(root)
        e=f.engine(typed);self.assertEqual(e.blockers,[]);return e

    def test_aoi_integer_outputs_local_learning_and_axis_means(self):
        for dtype in ('SINT','INT','DINT'):
            e=self.aoi(dtype);e.memory.write('Calculate',True);e.step()
            self.assertEqual(tuple(e.memory.read(t) for t in ('DriverA.Mean','DriverA.LocalMean','DriverA.ColumnMean','DriverA.RowMean','DriverA.PlaneMean','DriverB.Mean','DriverB.LocalMean')),(2,2,7,10,7,20,6))
            self.assertEqual(e.memory.read('DriverA.Deviation'),1.0)

    def test_aoi_scalar_inout_results_and_late_rollback(self):
        e=self.aoi('DINT',inout=True);e.memory.write('Calculate',True);e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('FaultDivisor',1);e.step();self.assertEqual((e.memory.read('MeanOutA'),e.memory.read('MeanOutB')),(2,20))

    def test_second_aoi_integer_overflow_rolls_back_first_instance(self):
        e=self.aoi('SINT');e.memory.write('Calculate',True)
        for i in (2,3,4):e.memory.write(f'SamplesB[{i}]',127.5)
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'SINT overflow'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('SamplesB[2]',126);e.step();self.assertEqual((e.memory.read('DriverA.Mean'),e.memory.read('DriverB.Mean')),(2,127))

    def test_report_distinguishes_integer_ave_from_real_only_std(self):
        e=self.checked();report=e.report()['array_statistics']
        self.assertEqual(report['destinations'],{'AVE':['DINT','INT','REAL','SINT'],'STD':['REAL']});self.assertIn('ties to even',report['integer_ave']);self.assertFalse(report['native_math_status'])


if __name__=='__main__':unittest.main()
