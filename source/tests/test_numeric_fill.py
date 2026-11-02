"""Numeric FLL conversions, lazy reads, snapshots and logical region guards."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_bit_transfer as fixtures
from logixlab.model import ModelError


class NumericFillTests(unittest.TestCase):
    setUp=fixtures.BitTransferTests.setUp
    checked=fixtures.BitTransferTests.checked

    def engine(self,rungs=None,*,source_type='DINT',dest_type='SINT',value=0,count=3,mutate=None):
        def fields(root):
            tags=root.find('./Controller/Tags')
            for name,kind,values in (('Fills',dest_type,(11,22,33,44,55)),('Inputs','DINT',(4660,99)),('Lengths','DINT',(3,99))):
                tag=E.SubElement(tags,'Tag',Name=name,DataType=kind,Dimensions=str(len(values)),TagType='Base');arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=kind,Dimensions=str(len(values)))
                for i,item in enumerate(values):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(item))
            if mutate:mutate(root)
        return fixtures.BitTransferTests.engine(self,rungs or ['FLL(Source,Fills[1],Mask);'],types=(source_type,'DINT','DINT'),values=(value,count,0),mutate=fields)

    @staticmethod
    def snapshot(e):
        bindings=(e.memory.frames,e.memory._resolved,e.addons.instances) if e.project.aois else None
        return copy.deepcopy((e.memory.values,bindings,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def test_all_sixteen_numeric_type_combinations(self):
        for source in ('SINT','INT','DINT','REAL'):
            for dest in ('SINT','INT','DINT','REAL'):
                value=3.5 if source=='REAL' else 3;expected=3.5 if source=='REAL' and dest=='REAL' else 4 if source=='REAL' else 3.0 if dest=='REAL' else 3
                e=self.checked(source_type=source,dest_type=dest,value=value);e.step()
                self.assertEqual(e.memory.read('Fills'),[11,expected,expected,expected,55]);self.assertEqual(e.memory.read('Source'),value)

    def test_integer_narrowing_preserves_low_bits_and_signed_top_bit(self):
        for source,dest,value,expected in (('DINT','SINT',0x12345678,120),('DINT','INT',0x12345678,22136),('INT','SINT',0x12ff,-1),('DINT','SINT',-129,127),('DINT','INT',-32769,32767),('DINT','SINT',128,-128)):
            e=self.checked(source_type=source,dest_type=dest,value=value);e.step();self.assertEqual(e.memory.read('Fills')[1:4],[expected]*3)

    def test_widening_sign_extends_without_bit_move_zero_fill(self):
        for source,dest,value in (('SINT','INT',-128),('SINT','DINT',-1),('INT','DINT',-32768)):
            e=self.checked(source_type=source,dest_type=dest,value=value);e.step();self.assertEqual(e.memory.read('Fills')[1:4],[value]*3)

    def test_real_rounding_and_float32_integer_conversion(self):
        for value,expected in ((2.5,2),(3.5,4),(-2.5,-2),(-3.5,-4)):
            e=self.checked(source_type='REAL',dest_type='INT',value=value);e.step();self.assertEqual(e.memory.read('Fills')[1:4],[expected]*3)
        e=self.checked(dest_type='REAL',value=16777217);e.step();self.assertEqual(e.memory.read('Fills')[1:4],[16777216.0]*3)

    def test_real_overflow_stays_excluded_and_rolls_back_prior_work(self):
        e=self.checked(['MOV(99,Dest);','FLL(Source,Fills[1],Mask);'],source_type='REAL',value=127.5);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'SINT overflow'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Source',126.5);e.step();self.assertEqual(e.memory.read('Fills')[1:4],[126]*3)

    def test_omitted_source_value_is_not_consumed_by_preflight_or_false_rung(self):
        def missing(root):
            arr=root.find('./Controller/Tags/Tag[@Name="Inputs"]/Data/Array');arr.remove(arr[0])
        e=self.checked(['XIC(StartPB)FLL(Inputs[0],Fills[1],Mask);'],mutate=missing);e.step();self.assertEqual(e.memory.read('Fills'),[11,22,33,44,55])
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Inputs[0]',4660);e.step();self.assertEqual(e.memory.read('Fills')[1:4],[52]*3)

    def test_omitted_length_and_bad_destination_index_are_lazy(self):
        def missing(root):
            arr=root.find('./Controller/Tags/Tag[@Name="Lengths"]/Data/Array');arr.remove(arr[0])
        e=self.checked(['XIC(StartPB)FLL(Source,Fills[Dest],Lengths[0]);'],mutate=missing);e.memory.write('Dest',999);e.step()
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Lengths[0]',2)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        e.memory.write('Dest',1);e.step();self.assertEqual(e.memory.read('Fills'),[11,0,0,44,55])

    def test_zero_length_validates_destination_but_skips_unknown_source(self):
        e=self.checked(['FLL(Source,Fills[Dest],Mask);'],count=0);e.memory.values['source']=None;e.step();self.assertEqual(e.memory.read('Fills'),[11,22,33,44,55])
        e.memory.write('Dest',999);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_full_fill_establishes_unknown_elements(self):
        def missing(root):root.find('./Controller/Tags/Tag[@Name="Fills"]/Data/Array').clear();root.find('./Controller/Tags/Tag[@Name="Fills"]/Data/Array').attrib.update(DataType='SINT',Dimensions='5')
        e=self.checked(value=4660,mutate=missing);e.step();self.assertEqual(e.memory.read('Fills'),[None,52,52,52,None])

    def test_source_and_length_are_captured_before_overlapping_stores(self):
        e=self.checked(['FLL(Fills[2],Fills[1],Fills[0]);'],count=3);e.memory.write('Fills[0]',3);e.step();self.assertEqual(e.memory.read('Fills'),[3,33,33,33,55])

    def test_lengths_and_member_bounds_retain_whole_advance_rollback(self):
        for count in (-1,100001,5):
            e=self.checked(count=count);before=self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before)
        e=self.checked(['FLL(Source,Fills[1],Mask);','DIV(1,Dest,SpeedCommand);'],value=4660);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('Dest',1);e.step();self.assertEqual(e.memory.read('Fills')[1:4],[52]*3)

    def test_alias_member_and_multidimensional_row_major_windows(self):
        def alias(root):
            tags=root.find('./Controller/Tags');E.SubElement(tags,'Tag',Name='FillView',DataType='SINT',Dimensions='5',TagType='Alias',AliasFor='Fills')
        e=self.checked(['FLL(Source,FillView[1],Mask);'],value=0x1234,mutate=alias);e.step();self.assertEqual(e.memory.read('Fills'),[11,52,52,52,55])
        def matrix(root):
            t=root.find('./Controller/Tags/Tag[@Name="Fills"]');t.set('Dimensions','2,3');arr=t.find('Data/Array');arr.clear();arr.attrib.update(DataType='SINT',Dimensions='2,3')
            for i in range(6):E.SubElement(arr,'Element',Index=f'[{i//3},{i%3}]',Value=str(i))
        e=self.checked(['FLL(Source,Fills[0,2],3);'],value=128,mutate=matrix);e.step();self.assertEqual(e.memory.read('Fills'),[[0,1,-128],[-128,-128,5]])

    def test_wrong_source_length_destination_and_constants_stay_blocked(self):
        for source in ('BOOL','LINT','USINT','UINT','UDINT','ULINT'):
            self.assertTrue(self.engine(source_type=source).blockers)
        for text in ('FLL(Source,Fills[1],TRUE);','FLL(Source,Fills[1],1.0);','FLL(TRUE,Fills[1],1);','FLL(2147483648,Fills[1],1);'):
            self.assertTrue(self.engine([text]).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Fills"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)

    def test_other_controller_profiles_keep_legacy_valid_range_behavior(self):
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        e=self.checked(value=3,mutate=old);e.step();self.assertEqual(e.memory.read('Fills')[1:4],[3]*3)
        self.assertTrue(self.engine(value=128,mutate=old).blockers)

    def aoi(self,*,prescan=False,typed=False):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        def fill(root):
            definition=root.find('.//AddOnInstructionDefinition');content=definition.find('Routines/Routine[@Name="Logic"]/RLLContent');content.clear();E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text='FLL(Value,Buffer[Index],2)FLL(Value,Stack[0],2);'
            if prescan:
                for obj in root.findall('./Controller/Tags/Tag[@DataType="LabQueueDriver"]/Data/Structure'):obj.remove(obj.find('ArrayMember[@Name="Stack"]'))
                definition.set('ExecutePrescan','true');body=E.SubElement(E.SubElement(definition.find('Routines'),'Routine',Name='Prescan',Type='RLL'),'RLLContent');E.SubElement(E.SubElement(body,'Rung',Number='0',Type='N'),'Text').text='FLL(0,Stack[0],4);'
            if typed:
                definition.find('Parameters/Parameter[@Name="Buffer"]').set('DataType','INT')
                for node in definition.find('LocalTags/LocalTag[@Name="Stack"]').iter():
                    if node.get('DataType')=='DINT':node.set('DataType','SINT')
                false=definition.find('Routines/Routine[@Name="EnableInFalse"]/RLLContent');false.clear();E.SubElement(E.SubElement(false,'Rung',Number='0',Type='N'),'Text').text='AFI()FLL(Value,Buffer[Index],2)FLL(Value,Stack[0],2);'
                for suffix,value in (('A',0x12345678),('B',-129)):
                    root.find(f'./Controller/Tags/Tag[@Name="Value{suffix}"]/Data/DataValue').set('Value',str(value))
                    tag=root.find(f'./Controller/Tags/Tag[@Name="Buffer{suffix}"]');tag.set('DataType','INT');tag.find('Data/Array').set('DataType','INT')
                    node=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]/Data/Structure/ArrayMember[@Name="Stack"]')
                    if node is not None:
                        node.set('DataType','SINT')
                        for element in node.findall('Element'):
                            if abs(int(element.get('Value','0')))>127:element.set('Value','77')
        e=f.engine(fill);self.assertEqual(e.blockers,[]);return e

    def test_aoi_inout_and_local_fills_and_prescan_initialization(self):
        e=self.aoi(prescan=True);self.assertEqual(e.memory.read('DriverA.Stack'),[0]*4);e.step()
        self.assertEqual(e.memory.read('DriverA.Stack')[:2],[11,11]);self.assertEqual(e.memory.read('DriverB.Stack')[:2],[22,22])

    def test_aoi_late_failure_restores_external_local_and_binding_state(self):
        e=self.aoi();e.memory.write('FaultDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('DriverB.Stack')[:2],[22,22])

    def test_typed_aoi_inout_and_local_arrays_use_distinct_widths(self):
        e=self.aoi(typed=True);guards={tag:e.memory.read(tag) for tag in ('BufferA[0]','BufferA[5]','BufferB[0]','BufferB[5]')};e.step()
        self.assertEqual(e.memory.read('BufferA')[1:3],[22136]*2);self.assertEqual(e.memory.read('BufferB')[2:4],[-129]*2)
        self.assertEqual(e.memory.read('DriverA.Stack')[:2],[120]*2);self.assertEqual(e.memory.read('DriverB.Stack')[:2],[127]*2)
        for tag,value in guards.items():self.assertEqual(e.memory.read(tag),value)

    def test_report_exposes_partial_native_boundaries(self):
        e=self.checked();report=e.report()['numeric_fill'];self.assertIn('low destination bits',report['integer_conversion']);self.assertFalse(report['clipping']);self.assertEqual(report['max_elements'],100000);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
