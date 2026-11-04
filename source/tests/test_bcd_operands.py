"""Qualified decimal inputs and decoded results around the DINT BCD boundary."""
import copy
import unittest
from xml.etree import ElementTree as E

import test_numeric_conversions as fixtures
from logixlab.model import ModelError


class BCDOperandTests(unittest.TestCase):
    setUp=fixtures.NumericConversionTests.setUp
    engine=fixtures.NumericConversionTests.engine
    checked=fixtures.NumericConversionTests.checked

    @staticmethod
    def snapshot(e):
        bindings=(e.memory.frames,e.memory._resolved,e.addons.instances) if e.project.aois else None
        return copy.deepcopy((e.memory.values,bindings,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def test_tod_accepts_all_three_signed_source_types(self):
        for dtype in ('SINT','INT','DINT'):
            for source,packed in ((0,0),(9,9),(19,0x19),(99,0x99),(127,0x127)):
                e=self.checked(['TOD(Source,Dest);'],types=(dtype,'DINT','DINT'),values=(source,0,7));e.step()
                self.assertEqual(e.memory.read('Dest'),packed);self.assertEqual(e.memory.read('Source'),source)

    def test_frd_accepts_all_three_signed_result_types(self):
        for dtype in ('SINT','INT','DINT'):
            for packed,expected in ((0,0),(0x19,19),(0x99,99),(0x127,127),(0x7f,85)):
                e=self.checked(['FRD(Source,Dest);'],types=('DINT','DINT',dtype),values=(packed,0,7));e.step()
                self.assertEqual(e.memory.read('Dest'),expected);self.assertIs(type(e.memory.read('Dest')),int)

    def test_byte_and_word_round_trip_preserves_exact_decimal_values(self):
        for dtype,values in (('SINT',(0,9,99,127)),('INT',(0,99,9999,32767))):
            e=self.checked(['TOD(Source,Mask);','FRD(Mask,Dest);'],types=(dtype,'DINT',dtype))
            for value in values:e.memory.write('Source',value);e.step();self.assertEqual(e.memory.read('Dest'),value)
        e=self.checked(['TOD(Source,Mask);','FRD(Mask,Dest);'],values=(16777217,0,7));e.step();self.assertEqual(e.memory.read('Dest'),16777217)

    def test_word_source_maximum_and_decoded_word_boundary(self):
        e=self.checked(['TOD(Source,Dest);'],types=('INT','DINT','DINT'),values=(32767,0,7));e.step();self.assertEqual(e.memory.read('Dest'),0x32767)
        for packed,wanted in ((0x32767,32767),(0xffff,16665)):
            e=self.checked(['FRD(Source,Dest);'],types=('DINT','DINT','INT'),values=(packed,0,7));e.step();self.assertEqual(e.memory.read('Dest'),wanted)

    def test_decoded_range_failure_rolls_back_prior_writes_and_scan_state(self):
        for dtype,packed in (('SINT',0x128),('SINT',0xff),('INT',0x32768),('INT',-1)):
            e=self.checked(['MOV(23,Mask);','FRD(Source,Dest);'],types=('DINT','DINT',dtype),values=(packed,0,7));before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,dtype+' overflow'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_tod_negative_narrow_sources_keep_existing_range_fault_policy(self):
        for dtype,value in (('SINT',-1),('SINT',-128),('INT',-1),('INT',-32768)):
            e=self.checked(['MOV(23,Mask);','TOD(Source,Dest);'],types=(dtype,'DINT','DINT'),values=(value,0,7));before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'TOD source outside'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_false_and_run_prescan_retain_unknown_destination_without_reading_source(self):
        for text,types in (('AFI()TOD(Source,Dest);',('INT','DINT','DINT')),('AFI()FRD(Source,Dest);',('DINT','DINT','SINT'))):
            e=self.checked([text],types=types);e.memory.values['source']=e.memory.values['dest']=None;e.enter_run();e.step();self.assertIsNone(e.memory.values['dest'])

    def test_full_narrow_results_establish_unknown_and_continue_rung(self):
        for dtype in ('SINT','INT'):
            e=self.checked(['FRD(Source,Dest)OTE(RunLatch);'],types=('DINT','DINT',dtype),values=(0x99,0,7));e.memory.values['dest']=None;e.step()
            self.assertEqual(e.memory.read('Dest'),99);self.assertTrue(e.memory.read('RunLatch'))

    def test_frd_narrow_sources_and_tod_narrow_results_are_available(self):
        for dtype in ('SINT','INT'):
            self.assertEqual(self.engine(['FRD(Source,Dest);'],types=(dtype,'DINT','DINT')).blockers,[])
            self.assertEqual(self.engine(['TOD(Source,Dest);'],types=('DINT','DINT',dtype)).blockers,[])
        for dtype in ('REAL','BOOL'):
            self.assertTrue(self.engine(['TOD(Source,Dest);'],types=(dtype,'DINT','DINT')).blockers)
            self.assertTrue(self.engine(['FRD(Source,Dest);'],types=('DINT','DINT',dtype)).blockers)

    def test_bounded_immediates_decode_to_narrow_results(self):
        for value in ('127','16#7F','8#177','2#0111_1111'):
            e=self.checked([f'FRD({value},Dest);'],types=('DINT','DINT','SINT'));e.step();self.assertEqual(e.memory.read('Dest'),85)
        for value in ('-1','16#FFFF_FFFF'):
            e=self.checked([f'FRD({value},Dest);'],types=('DINT','DINT','INT'));before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'INT overflow'):e.step()
            self.assertEqual(self.snapshot(e),before)

    @staticmethod
    def packet(root):
        c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='BCDDevice',Family='NoFamily',Class='User'),'Members')
        fields=(('Raw','DINT',0x127),('Decimal','INT',12345),('Encoded','DINT',0),('Decoded','SINT',7),('Guard','DINT',999))
        for name,dtype,_ in fields:E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension='0')
        tags=c.find('Tags');obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet1',DataType='BCDDevice',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='BCDDevice')
        for name,dtype,value in fields:E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value=str(value))
        E.SubElement(tags,'Tag',Name='ByteView',DataType='SINT',TagType='Alias',AliasFor='Packet1.Decoded')
        arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Results',DataType='INT',Dimensions='2',TagType='Base'),'Data',Format='Decorated'),'Array',DataType='INT',Dimensions='2')
        for i,value in enumerate((7,999)):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(value))

    def test_alias_member_and_indirect_result_preserve_adjacent_data(self):
        e=self.checked(['FRD(Packet1.Raw,ByteView);','TOD(Packet1.Decimal,Packet1.Encoded);','FRD(16#32767,Results[Mask]);'],mutate=self.packet,values=(0,0,7));e.step()
        self.assertEqual((e.memory.read('Packet1.Decoded'),e.memory.read('Packet1.Encoded'),e.memory.read('Packet1.Guard')),(127,0x12345,999));self.assertEqual(e.memory.read('Results'),[32767,999])

    def test_bad_indirect_result_rolls_back_prior_narrow_conversion(self):
        e=self.checked(['FRD(Packet1.Raw,ByteView);','FRD(16#32767,Results[Mask]);'],mutate=self.packet,values=(0,0,7));e.memory.write('Mask',999);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_constants_and_bit_or_aggregate_results(self):
        def source(root):root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant','true')
        e=self.checked(['TOD(Source,Dest);'],types=('INT','DINT','DINT'),values=(99,0,7),mutate=source);e.step();self.assertEqual(e.memory.read('Dest'),0x99)
        def dest(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        self.assertTrue(self.engine(['FRD(Source,Dest);'],types=('DINT','DINT','INT'),mutate=dest).blockers)
        for target in ('Dest.0','Results','Packet1'):
            self.assertTrue(self.engine([f'FRD(Source,{target});'],mutate=self.packet).blockers)

    def aoi(self,*,late=False):
        import test_addons as addons
        f=addons.AddOnTests();f.setUp();self.addCleanup(f.doCleanups)
        for param_name,kind in (('Step','INT'),('Total','SINT')):
            for node in f.definition().find(f'Parameters/Parameter[@Name="{param_name}"]').iter():
                if node.get('DataType')=='DINT':node.set('DataType',kind)
        for node in f.definition().find('LocalTags/LocalTag[@Name="Count"]').iter():
            if node.get('DataType')=='DINT':node.set('DataType','INT')
        tags=f.root.find('./Controller/Tags')
        for suffix in ('A','B'):
            for tag_name,kind in (('Step'+suffix,'INT'),('Total'+suffix,'SINT')):
                tag=tags.find(f'Tag[@Name="{tag_name}"]');tag.set('DataType',kind);tag.find('Data/DataValue').set('DataType',kind)
            for member,kind in (('Step','INT'),('Total','SINT'),('Count','INT')):
                node=tags.find(f'Tag[@Name="Accumulator{suffix}"]/Data/Structure/DataValueMember[@Name="{member}"]')
                if node is not None:node.set('DataType',kind)
        f.body()[0].find('Text').text='TOD(Step,Shared)FRD(Shared,Count)FRD(Shared,Total);'
        rungs=['XIC(EnableA)LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);','XIC(EnableB)LabAccumulator(AccumulatorB,StepB,TotalB,SharedB);']
        if late:rungs+=['DIV(1,StepA,Truncated);']
        e=f.engine(rungs);self.assertEqual(e.blockers,[]);return e

    def test_aoi_narrow_input_local_output_and_dint_inout(self):
        e=self.aoi();e.memory.write('StepA',99);e.memory.write('StepB',127);e.step()
        self.assertEqual(tuple(e.memory.read(t) for t in ('SharedA','SharedB','AccumulatorA.Count','AccumulatorB.Count','TotalA','TotalB')),(0x99,0x127,99,127,99,127))

    def test_late_aoi_result_range_failure_restores_local_output_inout_and_bindings(self):
        e=self.aoi();e.memory.write('StepA',128);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'SINT overflow'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('StepA',127);e.step();self.assertEqual(e.memory.read('TotalA'),127)

    def test_later_fault_restores_successful_aoi_conversions(self):
        e=self.aoi(late=True);e.memory.write('StepA',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('StepA',2);e.step();self.assertEqual(e.memory.read('SharedB'),3)

    def test_report_keeps_packed_boundary_and_remaining_forms_explicit(self):
        e=self.checked(['FRD(Source,Dest);']);report=e.report()['numeric_conversions']
        self.assertEqual(report['rll_operands']['FRD']['destinations'],['SINT','INT','DINT','LINT','USINT','UINT','UDINT','ULINT']);self.assertEqual(report['rll_operands']['TOD']['sources'],report['rll_operands']['FRD']['destinations'])
        self.assertIn('range errors',report['frd_range']);self.assertFalse(report['native_math_status'])


if __name__=='__main__':unittest.main()
