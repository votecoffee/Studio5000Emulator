import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
import test_runtime as fixtures
from logixlab.model import ModelError, Project, ascii_bytes
from logixlab.runtime import Engine

ROOT=Path(__file__).resolve().parents[1]


class ExpansionTests(unittest.TestCase):
    engine=fixtures.RuntimeTests.engine

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=E.parse(ROOT/'samples/DataLab.L5X').getroot()

    def test_data_lab_end_to_end(self):
        e=self.engine();self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('Grid[1,1]'),50)
        self.assertEqual(e.memory.read('Scaled'),110.0)
        self.assertEqual(e.memory.string('Message'),'VALUE 50')
        self.assertEqual(e.memory.string('Snippet'),'VAL')
        self.assertEqual(e.memory.read('ParsedNumber'),50)
        self.assertEqual(e.memory.read('LoopCount'),3)
        self.assertEqual(e.memory.read('WideDest'),9223372036854775806)
        self.assertTrue(e.memory.read('HighBit'))
        self.assertEqual(e.memory.read('SkippedValue'),0)

    def test_copy_spans_rows_in_row_major_order(self):
        e=self.engine(['COP(Source[1],Grid[0,2],4);']);e.step()
        self.assertEqual(e.memory.read('Grid'),[[0,0,20],[30,40,50]])

    def test_overlapping_copy_propagates_forward(self):
        for instruction in ('COP','CPS'):
            with self.subTest(instruction=instruction):
                e=self.engine([f'{instruction}(Source[0],Source[1],5);']);e.step()
                self.assertEqual(e.memory.read('Source'),[10]*6)

    def test_copy_bounds_and_type_mismatch_are_blocked(self):
        for rung in ('COP(Source[0],Grid[0,0],7);','COP(WideSource,Columns,1);'):
            with self.subTest(rung=rung):self.assertTrue(self.engine([rung]).blockers)

    def test_dynamic_block_length_fault_rolls_back_prior_writes(self):
        e=self.engine(['MOV(99,ParsedNumber);','COP(Source[0],Buffer[0],Columns);'])
        self.assertEqual(e.blockers,[]);e.memory.write('Columns',7)
        with self.assertRaisesRegex(ModelError,'boundary'):e.step()
        self.assertEqual(e.memory.read('ParsedNumber'),0)
        self.assertEqual(e.memory.read('Buffer'),[0]*6)

    def test_zero_length_copy_changes_nothing(self):
        e=self.engine(['COP(Source[0],Buffer[0],0);']);e.step()
        self.assertEqual(e.memory.read('Buffer'),[0]*6)

    def test_fll_converts_numeric_and_preserves_other_elements(self):
        e=self.engine(['FLL(2.5,Buffer[1],3);']);e.step()
        self.assertEqual(e.memory.read('Buffer'),[0,2,2,2,0,0])

    def test_fll_zeroes_string_storage(self):
        e=self.engine(['FLL(0,Prefix,1);']);e.step()
        self.assertEqual(e.memory.string('Prefix'),'')
        self.assertEqual(e.memory.read('Prefix.DATA'),[0]*82)

    def test_nonzero_structure_fill_is_blocked(self):
        self.assertTrue(self.engine(['FLL(1,Prefix,1);']).blockers)

    def test_size_second_dimension(self):
        e=self.engine(['SIZE(Grid,1,Columns);']);e.step()
        self.assertEqual(e.memory.read('Columns'),3)
        self.assertTrue(self.engine(['SIZE(Grid,2,Columns);']).blockers)

    def test_size_rechecks_a_changed_dimension_operand(self):
        e=self.engine(['SIZE(Grid,Index,Columns);']);e.memory.write('Index',-1)
        with self.assertRaisesRegex(ModelError,'dimension'):e.step()
        self.assertEqual(e.memory.read('Columns'),0)

    def test_omitted_decorated_array_element_remains_unknown(self):
        def mutate(root):
            array=root.find("./Controller/Tags/Tag[@Name='Source']/Data/Array")
            array.remove(array[-1])
        e=self.engine(['NOP();'],mutate)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.memory.read('Source[5]')
        self.assertIsNone(e.memory.values['source'][5])

    def test_three_dimensional_initialization_and_index_expression(self):
        def mutate(root):
            t=root.find("./Controller/Tags/Tag[@Name='Grid']");t.set('Dimensions','2 2 2')
            d=t.find('Data');d.clear();d.set('Format','Decorated');a=E.SubElement(d,'Array',DataType='DINT',Dimensions='2,2,2')
            import itertools
            for value,idx in enumerate(itertools.product(range(2),repeat=3)):
                E.SubElement(a,'Element',Index='['+','.join(map(str,idx))+']',Value=str(value))
        e=self.engine(['MOV(Grid[Index,0,Index],ParsedNumber);'],mutate);e.step()
        self.assertEqual(e.memory.read('ParsedNumber'),5)
        names=[t['name'] for t in e.memory.leaves()]
        self.assertIn('Grid[1,0,1]',names);self.assertNotIn('Grid[1][0][1]',names)

    def test_indirect_integer_arithmetic_and_nested_subscript(self):
        e=self.engine(['MOV(Source[(Index+1)*2],ParsedNumber);']);e.step()
        self.assertEqual(e.memory.read('ParsedNumber'),50)
        e.memory.write('Source[0]',2)
        self.assertEqual(e.memory.read('Source[Source[0]]'),30)
        with self.assertRaisesRegex(ModelError,'integer'):e.memory.read('Source[Index/2]')

    def test_cpt_precedence_and_bitwise_operations(self):
        cases=[('2+3*4',14),('(2+3)*4',20),('15 AND 6 XOR 1 OR 16',23),('NOT 0',-1),('-7 MOD 3',-1)]
        for expression,expected in cases:
            with self.subTest(expression=expression):
                e=self.engine([f'CPT(ParsedNumber,{expression});']);e.step()
                self.assertEqual(e.memory.read('ParsedNumber'),expected)

    def test_cpt_power_associativity_and_negation(self):
        for expression,expected in [('2.0**3.0**2.0',64.0),('-2.0**2.0',-4.0),('(-2.0)**2.0',4.0),('7/2',3.5)]:
            with self.subTest(expression=expression):
                e=self.engine([f'CPT(Scaled,{expression});']);e.step()
                self.assertEqual(e.memory.read('Scaled'),expected)

    def test_cpt_float32_intermediates(self):
        e=self.engine(['CPT(Scaled,16777216.0+1.0);']);e.step()
        self.assertEqual(e.memory.read('Scaled'),16777216.0)

    def test_cpt_functions_and_integer_division_boundary(self):
        e=self.engine(['CPT(Scaled,SQR(16.0)+ABS(-3.0));']);e.step()
        self.assertEqual(e.memory.read('Scaled'),7.0)
        self.assertTrue(self.engine(['CPT(ParsedNumber,7/2);']).blockers)

    def test_expression_unknowns_and_code_syntax_are_blocked(self):
        for expression in ['Missing+1','__import__(os)','Source.__class__','2;3','open(1)']:
            with self.subTest(expression=expression):self.assertTrue(self.engine([f'AFI()CPT(Scaled,{expression});']).blockers)

    def test_false_cpt_does_not_evaluate_divide_by_zero(self):
        e=self.engine(['AFI()CPT(Scaled,1.0/0.0);']);self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('Scaled'),0)

    def test_true_expression_fault_rolls_back(self):
        e=self.engine(['MOV(12,ParsedNumber);','CPT(Scaled,1.0/0.0);'])
        with self.assertRaisesRegex(ModelError,'rolled back'):e.step()
        self.assertEqual(e.memory.read('ParsedNumber'),0)

    def test_forward_jump_skips_without_false_scanning_outputs(self):
        e=self.engine(['JMP(Done);','AFI()OTE(HighBit);','LBL(Done)NOP();'])
        e.memory.write('HighBit',True);e.step()
        self.assertTrue(e.memory.read('HighBit'))
        self.assertNotIn('1',[x['number'] for x in e.trace])

    def test_backward_jump_loop_and_transfer_trace(self):
        e=self.engine(['LBL(Again)ADD(LoopCount,1,LoopCount)LES(LoopCount,3)JMP(Again);']);e.step()
        self.assertEqual(e.memory.read('LoopCount'),3)
        self.assertEqual(len(e.trace),3)
        self.assertEqual(e.trace[0]['control'],'jump again')

    def test_jump_missing_duplicate_or_nested_label_blocks(self):
        for rungs in [['JMP(Missing);'],['LBL(A)NOP();','LBL(A)NOP();'],['[LBL(A),NOP()];'],['NOP()LBL(A);']]:
            with self.subTest(rungs=rungs):self.assertTrue(self.engine(rungs).blockers)

    def test_unbounded_loop_stops_and_rolls_back(self):
        e=self.engine(['MOV(99,ParsedNumber);','LBL(Again)JMP(Again);']);e.instruction_limit=100
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(e.memory.read('ParsedNumber'),0)
        self.assertEqual(e.scan_count,0)

    def test_tnd_returns_only_from_called_routine(self):
        self.root=E.parse(ROOT/'samples/ConveyorDemo.L5X').getroot()
        def mutate(root):
            content=root.find(".//Routine[@Name='Reporting']/RLLContent")
            content[0].find('Text').text='TND();'
        e=self.engine(['JSR(Reporting,0);','MOV(9,SpeedCommand);'],mutate);e.step()
        self.assertEqual(e.memory.read('SpeedCommand'),9)
        self.assertEqual(e.memory.read('DisplayedPartCount'),0)

    def test_concat_mid_and_alias_destination(self):
        e=self.engine(['DTOS(Index,NumberText)CONCAT(Prefix,NumberText,Message)MID(Message,3,1,Message);']);e.step()
        self.assertEqual(e.memory.string('Message'),'VAL')
        self.assertEqual(e.memory.read('Message.LEN'),3)

    def test_string_write_preserves_unused_backing_bytes(self):
        e=self.engine(['NOP();']);e.memory.write('Message','ABCDE');e.memory.write('Message','Z')
        self.assertEqual(e.memory.string('Message'),'Z')
        self.assertEqual(e.memory.read('Message.DATA[1]'),ord('B'))

    def test_string_overflow_rolls_back_previous_changes(self):
        e=self.engine(['MOV(99,ParsedNumber);','CONCAT(Prefix,Prefix,Message);'])
        e.memory.write('Prefix','X'*50)
        with self.assertRaisesRegex(ModelError,'capacity'):e.step()
        self.assertEqual(e.memory.read('ParsedNumber'),0)
        self.assertEqual(e.memory.string('Message'),'')

    def test_stod_first_contiguous_signed_group(self):
        for text,expected in [('weight=-123.45kg',-123),('part12/34',12),('NO NUMBER',0)]:
            with self.subTest(text=text):
                e=self.engine(['STOD(Message,ParsedNumber);']);e.memory.write('Message',text);e.step()
                self.assertEqual(e.memory.read('ParsedNumber'),expected)

    def test_string_compare_ignores_unused_tail(self):
        e=self.engine(['EQU(Prefix,Message)OTE(HighBit);'])
        e.memory.write('Message','VALUE XXXXX');e.memory.write('Message','VALUE ');e.step()
        self.assertTrue(e.memory.read('HighBit'))

    def test_invalid_mid_range_stops(self):
        e=self.engine(['MID(Prefix,20,1,Message);'])
        with self.assertRaisesRegex(ModelError,'bounds'):e.step()
        self.assertTrue(self.engine(['MID(Prefix,1,0,Message);']).blockers)

    def test_omitted_nested_string_tail_is_unknown_not_zero(self):
        def mutate(root):
            t=root.find("./Controller/Tags/Tag[@Name='Message']");t.remove(t.find('Data'))
            d=E.SubElement(t,'Data',Format='Decorated');s=E.SubElement(d,'Structure',DataType='STRING')
            E.SubElement(s,'DataValueMember',Name='LEN',DataType='DINT',Value='2')
            E.SubElement(s,'DataValueMember',Name='DATA',DataType='STRING',Radix='ASCII').text='AB'
        e=self.engine(['CONCAT(Message,Prefix,NumberText);'],mutate)
        self.assertEqual(e.blockers,[]);self.assertEqual(e.memory.string('Message'),'AB')
        with self.assertRaisesRegex(ModelError,'Unknown'):e.memory.read('Message.DATA[2]')
        self.assertIsNone(e.memory.values['message']['DATA'][2])
        e.step();self.assertEqual(e.memory.string('NumberText'),'ABVALUE ')

    def test_full_l5k_string_backing_and_escape_bytes(self):
        e=self.engine(['NOP();'])
        self.assertEqual(e.memory.read('Prefix.DATA[6]'),0)
        self.assertEqual(ascii_bytes("'A$00$$$'$ff'"),[65,0,36,39,-1])

    def test_wide_integer_rows_preserve_exact_decimal_digits(self):
        e=self.engine(['MOV(WideSource,WideDest);']);e.step()
        row=next(t for t in e.memory.leaves() if t['name']=='WideDest')
        self.assertEqual(row['value'],'9223372036854775806')
        self.assertEqual(row['kind'],'integer_text')
        e.memory.write('WideDest','9007199254740993')
        self.assertEqual(e.memory.read('WideDest'),9007199254740993)
        e=self.engine(['ADD(WideSource,WideSource,WideDest);'])
        self.assertEqual(e.blockers,[])
        with self.assertRaisesRegex(ModelError,'overflow'):e.step()

    def test_unsigned_bit_access_does_not_sign_extend(self):
        e=self.engine(['OTL(PackedStatus.15);']);e.memory.write('PackedStatus',0);e.step()
        self.assertEqual(e.memory.read('PackedStatus'),32768)

    def test_native_udt_bit_metadata(self):
        def mutate(root):
            dt=E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Flags');m=E.SubElement(dt,'Members')
            E.SubElement(m,'Member',Name='Backing',DataType='SINT',Dimension='0',Hidden='true')
            E.SubElement(m,'Member',Name='Ready',DataType='BIT',Dimension='0',Hidden='false',Target='Backing',BitNumber='2')
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Flags',DataType='Flags',TagType='Base')
            d=E.SubElement(t,'Data',Format='Decorated');s=E.SubElement(d,'Structure',DataType='Flags')
            E.SubElement(s,'DataValueMember',Name='Ready',DataType='BOOL',Value='1')
        e=self.engine(['XIC(Flags.Ready)OTE(HighBit);'],mutate);self.assertEqual(e.blockers,[]);e.step()
        self.assertTrue(e.memory.read('HighBit'))

    def test_data_only_type_does_not_enable_instruction_execution(self):
        def mutate(root):
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='CustomAOI',TagType='Base')
            d=E.SubElement(t,'Data',Format='Decorated');s=E.SubElement(d,'Structure',DataType='CustomAOI')
            E.SubElement(s,'DataValueMember',Name='EnableIn',DataType='BOOL',Value='1')
        e=self.engine(['XIC(Instance.EnableIn)OTE(HighBit);'],mutate);e.step();self.assertTrue(e.memory.read('HighBit'))
        blocked=self.engine(['CustomAOI(Instance);'])
        self.assertTrue(any('unsupported CUSTOMAOI' in b for b in blocked.blockers))
        self.assertIn('CustomAOI',e.report()['data_only_types'])


if __name__=='__main__':unittest.main(verbosity=2)
