"""BCD bit patterns, byte ordering and ST call write effects."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_bit_transfer as fixtures
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


class NumericConversionTests(unittest.TestCase):
    setUp = fixtures.BitTransferTests.setUp
    engine = fixtures.BitTransferTests.engine
    checked = fixtures.BitTransferTests.checked

    def st(self, text, **kwargs):
        def change(root):
            routine = root.find('./Controller/Programs/Program/Routines/Routine')
            routine.set('Type', 'ST');routine.remove(routine.find('RLLContent'))
            content = E.SubElement(routine, 'STContent')
            E.SubElement(content, 'Line', Number='0').text = text
        return self.engine([], mutate=change, **kwargs)

    def test_frd_weighted_nibbles_include_a_through_f_as_documented(self):
        for source, expected in ((0,0),(0x12345678,12345678),(0x1234567e,12345684),
                                 (-1,166666665),(-1717986919,99999999),(-2147483648,80000000)):
            with self.subTest(source=source):
                e = self.checked(['FRD(Source,Dest);'], values=(source,0,7))
                e.step();self.assertEqual(e.memory.read('Dest'), expected)
                self.assertEqual(e.memory.read('Source'), source)

    def test_tod_zero_small_digits_and_signed_packed_boundary(self):
        for source, expected in ((0,0),(9,9),(10,16),(12345678,0x12345678),
                                 (80000000,-2147483648),(99999999,-1717986919)):
            e = self.checked(['TOD(Source,Dest);'], values=(source,0,7))
            e.step();self.assertEqual(e.memory.read('Dest'), expected)

    def test_bcd_round_trip_retains_decimal_inputs(self):
        e = self.checked(['TOD(Source,Dest);','FRD(Dest,Mask);'])
        for source in (0,1,19,99,100,1001,12345678,87654321,99999999):
            e.memory.write('Source', source);e.step()
            self.assertEqual(e.memory.read('Mask'), source)

    def test_bounded_immediate_formats_and_signed_patterns(self):
        for source, expected in (('16#FFFF_FFFF',166666665),('-1',166666665),
                                 ('8#37777777777',166666665),('2#'+'1'*32,166666665)):
            e = self.checked([f'FRD({source},Dest);']);e.step()
            self.assertEqual(e.memory.read('Dest'), expected)
        e = self.checked(['TOD(99999999,Dest);']);e.step()
        self.assertEqual(e.memory.read('Dest'), -1717986919)

    def test_tod_range_failure_rolls_back_prior_writes_and_scheduler(self):
        for source in (-1,100000000,2147483647):
            e = self.checked(['MOV(23,Mask);','TOD(Source,Dest);'], values=(source,7,9))
            before = copy.deepcopy(e.memory.values)
            with self.assertRaisesRegex(ModelError, 'qualified'):e.step()
            self.assertEqual(e.memory.values, before)
            self.assertEqual((e.scan_count,e.time_ms), (0,0))
            self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],0)

    def test_swpb_dint_orders_and_signed_results(self):
        for source, order, expected in ((0x12345678,'REVERSE',0x78563412),
                 (0x12345678,'WORD',0x56781234),(0x12345678,'HIGHLOW',0x34127856),
                 (0x123456ff,'REVERSE',-11127790),(0x1234ffff,'WORD',-60876),
                 (-1,'HIGHLOW',-1)):
            e = self.checked([f'SWPB(Source,{order},Dest);'], values=(source,0,0))
            e.step();self.assertEqual(e.memory.read('Dest'),expected)

    def test_swpb_int_all_orders_and_sign_extension_to_dint(self):
        for order in ('REVERSE','WORD','HIGHLOW'):
            for dtype in ('INT','DINT'):
                e = self.checked([f'SWPB(Source,{order},Dest);'], types=('INT','DINT',dtype),values=(0x12ab,0,0))
                e.step();self.assertEqual(e.memory.read('Dest'),-21742)
                e.memory.write('Source',-256);e.step();self.assertEqual(e.memory.read('Dest'),255)

    def test_swpb_in_place_captures_original_word(self):
        e = self.checked(['SWPB(Source,REVERSE,Source);'],values=(0x12345678,0,0))
        e.step();self.assertEqual(e.memory.read('Source'),0x78563412)
        e.step();self.assertEqual(e.memory.read('Source'),0x12345678)

    def test_prescan_false_rungs_and_unknown_values(self):
        for text in ('FRD(Source,Dest);','TOD(Source,Dest);','SWPB(Source,WORD,Dest);'):
            e = self.checked(['AFI()'+text],values=(5,0,9))
            self.assertEqual(e.memory.read('Dest'),9)
            e.memory.values['source']=None;e.step();self.assertEqual(e.memory.read('Dest'),9)
            e = self.checked([text]);e.memory.values['source']=None
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual((e.scan_count,e.time_ms),(0,0))

    def test_full_writes_establish_unknown_destination_and_rung_out(self):
        for text, expected in (('FRD(16#1234,Dest)',1234),('TOD(1234,Dest)',0x1234),
                               ('SWPB(Source,WORD,Dest)',0x56781234)):
            e = self.checked([text+'OTE(RunLatch);'],values=(0x12345678,0,0))
            e.memory.values['dest']=None;e.step()
            self.assertEqual(e.memory.read('Dest'),expected);self.assertTrue(e.memory.read('RunLatch'))

    def test_swpb_st_execution_and_false_branch_preserve_output(self):
        e=self.st('IF StartPB THEN SWPB(Source,reverse,Dest); END_IF;',values=(0x12345678,0,7))
        self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('Dest'),7)
        e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('Dest'),0x78563412)
        self.assertTrue(any(t.get('language')=='ST' for t in e.trace))

    def test_st_for_write_effects_protect_tag_bounds_and_step(self):
        for text in ('FOR Source:=0 TO Mask DO SWPB(Dest,REVERSE,Mask); END_FOR;',
                     'FOR Source:=0 TO 2 BY Mask DO SWPB(Dest,WORD,Mask); END_FOR;'):
            e=self.st(text,values=(0,2,0))
            self.assertTrue(any('bounds/step' in b for b in e.blockers),e.blockers)
        e=self.st('FOR Mask:=0 TO 1 DO SWPB(Source,HIGHLOW,Dest); END_FOR;',values=(0x12345678,0,0))
        self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('Dest'),0x34127856)

    def test_bcd_calls_and_expressions_remain_unavailable_in_st(self):
        for text in ('FRD(Source,Dest);','TOD(Source,Dest);','Dest:=FRD(Source);','Dest:=TOD(Source);'):
            self.assertTrue(self.st(text).blockers)
        self.assertTrue(self.engine(['CPT(Dest,FRD(Source));']).blockers)

    def test_unqualified_types_immediates_modes_and_arities_block(self):
        for dtype in ('SINT','INT','LINT','USINT','UINT','UDINT','ULINT','REAL','BOOL'):
            for text in ('FRD(Source,Dest);','TOD(Source,Dest);'):
                for types in ((dtype,'DINT','DINT'),('DINT','DINT',dtype)):
                    self.assertTrue(self.engine([text],types=types).blockers,(text,types))
        for text in ('SWPB(1234,REVERSE,Dest);','SWPB(Source,Mask,Dest);','SWPB(Source,0,Dest);',
                     'SWPB(Source,HIGH/LOW,Dest);','SWPB(Source,REVERSE);', 'FRD(Source);','TOD(Source,Mask,Dest);'):
            self.assertTrue(self.engine([text]).blockers,text)
        for types in (('SINT','DINT','DINT'),('DINT','DINT','INT'),('REAL','DINT','DINT')):
            self.assertTrue(self.engine(['SWPB(Source,WORD,Dest);'],types=types).blockers)
        for value in ('TRUE','1.0','2147483648','16#100000000'):
            self.assertTrue(self.engine([f'FRD({value},Dest);']).blockers)

    def test_constant_destination_rejected_but_constant_source_accepted(self):
        for text in ('FRD(Source,Dest);','TOD(Source,Dest);','SWPB(Source,WORD,Dest);'):
            def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
            self.assertTrue(self.engine([text],mutate=constant).blockers)
            def source(root):root.find('./Controller/Tags/Tag[@Name="Source"]').set('Constant','true')
            e=self.checked([text],mutate=source);e.step()

    def test_array_alias_udt_member_and_indirect_scalar_access(self):
        def tags(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Word',DataType='DINT',Dimension='0')
            tags=c.find('Tags');array=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Words',DataType='INT',Dimensions='2',TagType='Base'),'Data',Format='Decorated'),'Array',DataType='INT',Dimensions='2')
            for i,value in enumerate((0x12ab,999)):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value))
            struct=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(struct,'DataValueMember',Name='Word',DataType='DINT',Value='0')
            E.SubElement(tags,'Tag',Name='AliasWord',TagType='Alias',DataType='DINT',AliasFor='Packet1.Word')
        e=self.checked(['SWPB(Words[Source],WORD,AliasWord);'],mutate=tags)
        e.step();self.assertEqual(e.memory.read('Packet1.Word'),-21742);self.assertEqual(e.memory.read('Words[1]'),999)
        self.assertTrue(self.engine(['SWPB(Words,WORD,Dest);'],mutate=tags).blockers)

    def test_aoi_input_output_and_inout_bindings(self):
        import test_addons as aoi
        fixture=aoi.AddOnTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        fixture.body()[0].find('Text').text='TOD(Step,Total)SWPB(Step,REVERSE,Shared);'
        e=fixture.engine();self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('TotalA'),2);self.assertEqual(e.memory.read('TotalB'),3)
        self.assertEqual(e.memory.read('SharedA'),0x02000000);self.assertEqual(e.memory.read('SharedB'),0x03000000)

    def test_late_fault_rolls_back_conversion_and_st_output(self):
        e=self.st('SWPB(Source,WORD,Dest); Mask:=1.0/0.0;',values=(1234,0,9))
        self.assertEqual(e.blockers,[]);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)

    def test_profile_and_report_boundaries(self):
        for processor in ('1756-L75','unknown'):
            def old(root):root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(['FRD(Source,Dest);'],mutate=old).blockers)
        e=self.checked(['FRD(Source,Dest);']);report=e.report()['numeric_conversions']
        self.assertEqual(report['instructions'],['FRD','SWPB','TOD']);self.assertFalse(report['native_math_status'])


    def test_bundled_conversion_lab_numeric_and_array_results(self):
        from logixlab.server import SAMPLES
        self.assertIn('ConversionLab',SAMPLES)
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/ConversionLab.L5X'))
        self.assertEqual(e.blockers,[]);e.step()
        for tag,value in dict(Packed=0x12345678,Decoded=12345678,Weighted=12345684,
                              Reverse=0x78563412,Words=0x56781234,HighLow=0x34127856,
                              SignExtended=-21742,STValue=0x34127856,Index=2,AllOK=True).items():
            self.assertEqual(e.memory.read(tag),value,tag)
        self.assertEqual(e.memory.read('SwappedWords'),[-21742,255,999])


if __name__=='__main__':unittest.main()
