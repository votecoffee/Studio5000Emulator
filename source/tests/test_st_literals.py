"""Typed decimal ST constants retain width, range and language boundaries."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_wide_st as fixtures
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine
from logixlab.st_expression import STExpression


class StructuredLiteralTests(unittest.TestCase):
    setUp=fixtures.WideStructuredTests.setUp
    engine=fixtures.WideStructuredTests.engine
    checked=fixtures.WideStructuredTests.checked

    def test_decimal_suffixes_cover_full_declared_ranges(self):
        for dtype,text,expected in (('LINT','9223372036854775807L',9223372036854775807),
                                    ('LINT','-9223372036854775808L',-9223372036854775808),
                                    ('UDINT','4294967295U',4294967295),('UDINT','0U',0),
                                    ('ULINT','18446744073709551615UL',18446744073709551615),('ULINT','0UL',0)):
            with self.subTest(dtype=dtype,text=text):
                e=self.checked('WideDest:='+text+';',dtype=dtype);e.step();self.assertEqual(e.memory.read('WideDest'),expected)
                self.assertIs(type(e.memory.read('WideDest')),int)

    def test_suffixes_are_case_insensitive_and_keep_decimal_magnitude(self):
        for dtype,suffix in (('LINT','l'),('LINT','L'),('UDINT','u'),('ULINT','uL'),('ULINT','Ul'),('ULINT','ul')):
            e=self.checked('WideDest:=00042'+suffix+';',dtype=dtype);e.step();self.assertEqual(e.memory.read('WideDest'),42)

    def test_typed_literal_metadata_is_not_misread_as_tag_references(self):
        expression=STExpression('9007199254740993L+2L')
        self.assertEqual(expression.refs,[]);self.assertEqual(expression.typed_types,{'LINT'})
        e=self.checked('WideDest:=0;');self.assertEqual(expression.evaluate(e.memory),9007199254740995)

    def test_exact_arithmetic_and_quotients_above_float_precision(self):
        for dtype,text,expected in (('LINT','9007199254740993L+2L',9007199254740995),
                                    ('LINT','-9223372036854775808L/3L',-3074457345618258602),
                                    ('LINT','-9223372036854775808L MOD 3L',-2),
                                    ('UDINT','4294967295U/3U',1431655765),
                                    ('ULINT','18446744073709551615UL/3UL',6148914691236517205)):
            e=self.checked('WideDest:='+text+';',dtype=dtype);e.step();self.assertEqual(e.memory.read('WideDest'),expected)

    def test_bitwise_operations_use_literal_width(self):
        for dtype,text,expected in (('LINT','NOT 0L',-1),('UDINT','NOT 0U',4294967295),
                                    ('ULINT','NOT 0UL',18446744073709551615),
                                    ('ULINT','18446744073709551615UL AND 1UL',1),
                                    ('ULINT','9223372036854775808UL OR 1UL',9223372036854775809)):
            e=self.checked('WideDest:='+text+';',dtype=dtype);e.step();self.assertEqual(e.memory.read('WideDest'),expected)

    def test_literal_only_comparisons_infer_wide_type_without_numeric_destination(self):
        for text,expected in (('9007199254740992L<9007199254740993L',True),
                              ('18446744073709551615UL=NOT 0UL',True),('4294967295U<0U',False)):
            e=self.checked('Result:='+text+';');e.step();self.assertEqual(e.memory.read('Result'),expected)

    def test_matching_typed_operands_and_bounded_untyped_literals_combine(self):
        e=self.checked('WideDest:=WideA+2L;',a=9007199254740993);e.step();self.assertEqual(e.memory.read('WideDest'),9007199254740995)
        e=self.checked('WideDest:=1UL+2;',dtype='ULINT');e.step();self.assertEqual(e.memory.read('WideDest'),3)

    def test_signed_minimum_accepts_parentheses_and_unsigned_negative_zero(self):
        for text,expected in (('-(9223372036854775808L)',-9223372036854775808),('+9223372036854775807L',9223372036854775807)):
            e=self.checked('WideDest:='+text+';');e.step();self.assertEqual(e.memory.read('WideDest'),expected)
        e=self.checked('WideDest:=-0UL;',dtype='ULINT');e.step();self.assertEqual(e.memory.read('WideDest'),0)

    def test_invalid_literal_ranges_block_even_in_unreached_branches(self):
        for dtype,text in (('LINT','9223372036854775808L'),('LINT','-9223372036854775809L'),
                           ('UDINT','4294967296U'),('UDINT','-1U'),
                           ('ULINT','18446744073709551616UL'),('ULINT','-1UL')):
            e=self.engine('IF FALSE THEN WideDest:='+text+'; END_IF;',dtype=dtype)
            self.assertTrue(e.blockers,(dtype,text));self.assertIn('overflow',str(e.blockers))

    def test_malformed_suffixes_and_boundaries_remain_rejected(self):
        for text in ('1LU','1ULU','1ULL','1UU','1L2','1ULgarbage','1 L','1 UL'):
            self.assertTrue(self.engine('WideDest:='+text+';').blockers,text)

    def test_real_exponent_radix_and_grouped_typed_forms_remain_unqualified(self):
        for text in ('1.0L','1e3L','.5UL','16#FFU','2#11UL','8#77L','1_000L'):
            self.assertTrue(self.engine('WideDest:='+text+';').blockers,text)

    def test_mixed_literal_types_and_numeric_destinations_are_rejected(self):
        for dtype,text in (('LINT','1U'),('ULINT','1L'),('UINT','1U'),('USINT','1U'),('LINT','1L+1U'),('LINT','WideA+1UL')):
            self.assertTrue(self.engine('WideDest:='+text+';',dtype=dtype).blockers,(dtype,text))
        for source in ('SpeedCommand:=1L;','Result:=1UL;','WideDest:=1L+0.0;'):
            self.assertTrue(self.engine(source).blockers,source)

    def test_profile_gate_applies_to_typed_constants_without_tag_operands(self):
        for kwargs in (dict(processor='1756-L75'),dict(revision='34'),dict(processor='5069-L340ERM')):
            self.assertTrue(self.engine('Result:=1L=1L;',**kwargs).blockers)

    def test_typed_for_case_and_index_forms_do_not_bypass_existing_guards(self):
        for source in ('FOR SpeedCommand:=0 TO 3L DO WideDest:=1L; END_FOR;',
                       'CASE 1L OF 1:WideDest:=1L; END_CASE;',
                       'CASE SpeedCommand OF 1L:WideDest:=1L; END_CASE;',
                       'WideDest:=WideA[0U];'):
            self.assertTrue(self.engine(source).blockers,source)

    def test_cpt_and_cmp_lexers_do_not_accept_st_suffixes(self):
        from logixlab.expressions import Expression
        from logixlab.conditions import Condition
        for create,text in ((Expression,'1L+2L'),(Condition,'1U=1U')):
            with self.assertRaises(ModelError):create(text)

    def test_instruction_arguments_do_not_silently_gain_literal_conversions(self):
        e=self.engine('FLL(0L,WideDest,1);');self.assertTrue(e.blockers);self.assertIn('0L',str(e.blockers))

    def test_names_strings_and_comments_containing_suffix_text_are_preserved(self):
        def tags(root):
            from test_string_operations import string_data
            tags=root.find('./Controller/Tags')
            tag=E.SubElement(tags,'Tag',Name='Source1L',TagType='Base',DataType='LINT')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='LINT',Value='9007199254740993')
            tag=E.SubElement(tags,'Tag',Name='Note',TagType='Base',DataType='STRING');string_data(E.SubElement(tag,'Data',Format='Decorated'),'')
        e=self.checked("Note:='1UL 9223372036854775808L'; (* 999999999999999999999999999UL *)\nWideDest:=Source1L+2L; // 9999999999999999999999L",mutate=tags)
        e.step();self.assertEqual(e.memory.string('Note'),'1UL 9223372036854775808L');self.assertEqual(e.memory.read('WideDest'),9007199254740995)

    def test_unknown_destination_can_be_established_from_full_width_constant(self):
        e=self.checked('WideDest:=18446744073709551615UL;',dtype='ULINT');e.memory.values['widedest']=None;e.step()
        self.assertEqual(e.memory.read('WideDest'),18446744073709551615)
        self.assertEqual(next(row['value'] for row in e.memory.leaves() if row['name']=='WideDest'),'18446744073709551615')

    def test_valid_literal_arithmetic_faults_roll_back_earlier_writes(self):
        for dtype,text in (('LINT','9223372036854775807L+1L'),('ULINT','0UL-1UL'),
                           ('LINT','ABS(-9223372036854775808L)'),('ULINT','1UL/0UL')):
            e=self.checked('SpeedCommand:=99; WideDest:='+text+';',dtype=dtype);before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule);self.assertEqual((e.scan_count,e.time_ms),(0,0))

    def test_skipped_bodies_skip_arithmetic_but_boolean_operands_remain_eager(self):
        e=self.checked('IF StartPB THEN WideDest:=1UL/0UL; END_IF;',dtype='ULINT');e.step();self.assertEqual(e.memory.read('WideDest'),0)
        e=self.checked('IF FALSE AND (1UL/0UL>0UL) THEN WideDest:=1UL; END_IF;',dtype='ULINT');before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_typed_constants_work_in_if_while_and_repeat_conditions(self):
        e=self.checked('WideDest:=0L; IF 1L<2L THEN WHILE WideDest<3L DO WideDest:=WideDest+1L; END_WHILE; END_IF; REPEAT WideDest:=WideDest-1L; UNTIL WideDest=0L END_REPEAT;')
        e.step();self.assertEqual(e.memory.read('WideDest'),0)

    def test_nonretentive_assignment_prescan_clears_before_typed_write(self):
        e=self.checked('IF StartPB THEN WideDest [:=] 18446744073709551615UL; END_IF;',dtype='ULINT',dest=99)
        self.assertEqual(e.memory.read('WideDest'),0);e.memory.write('StartPB',True);e.step();self.assertEqual(e.memory.read('WideDest'),18446744073709551615)
        e.enter_run();self.assertEqual(e.memory.read('WideDest'),0)

    def test_typed_constants_work_in_aoi_output_and_inout_expressions(self):
        def aoi(root):
            sample=E.parse(Path(__file__).resolve().parents[1]/'samples/AOILab.L5X').getroot()
            definition=copy.deepcopy(sample.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition'))
            for node in definition.iter():
                if node.get('DataType')=='DINT':node.set('DataType','LINT')
            logic=definition.find('./Routines/Routine[@Name="Logic"]');logic.remove(logic.find('RLLContent'));logic.set('Type','ST')
            E.SubElement(E.SubElement(logic,'STContent'),'Line',Number='0').text='Total:=Shared+9007199254740993L; Shared:=Shared+1L;'
            root.find('./Controller/AddOnInstructionDefinitions').append(definition)
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',TagType='Base',DataType='LabAccumulator')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='LabAccumulator')
            for name,dtype,value in (('EnableIn','BOOL',0),('EnableOut','BOOL',0),('Step','LINT',0),('Total','LINT',0),('Limit','LINT',100)):
                E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value=str(value))
        e=self.checked('LabAccumulator(Instance,WideB,WideDest,WideA);',a=2,mutate=aoi);e.step()
        self.assertEqual(e.memory.read('WideDest'),9007199254740995);self.assertEqual(e.memory.read('WideA'),3)

    def test_report_describes_typed_literals_without_claiming_native_parity(self):
        row=self.checked('WideDest:=1L;').report()['wide_st_execution']
        self.assertIn('L/U/UL',row['literals']);self.assertFalse(row['native_runtime_parity'])

    def test_integer_lab_exposes_constants_and_recovers_after_late_literal_arithmetic_fault(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/IntegerLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        expected=dict(StLiteralSigned=-9223372036854775808,StLiteralUnsigned=18446744073709551615,
                      StLiteralDword=4294967295,StLiteralNot=18446744073709551615,StLiteralQuotient=6148914691236517205)
        for name,value in expected.items():self.assertEqual(e.memory.read(name),value)
        self.assertTrue(e.memory.read('StLiteralCheck'));self.assertTrue(e.memory.read('StAllMatches'))
        e.memory.write('StLiteralOffset',1);e.step();self.assertEqual(e.memory.read('StLiteralSigned'),-9223372036854775807)
        self.assertFalse(e.memory.read('StLiteralCheck'))
        e.memory.write('SignedInput',12345);e.memory.write('StLiteralOffset',-1);before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaisesRegex(ModelError,'overflow'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        e.memory.write('StLiteralOffset',0);e.step();self.assertEqual(e.memory.read('StSignedSum'),12347)
        self.assertTrue(e.memory.read('StLiteralCheck'));self.assertTrue(e.memory.read('StAllMatches'))


if __name__=='__main__':unittest.main()
