import unittest
from pathlib import Path
from xml.etree import ElementTree as E
import test_runtime as fixtures
from logixlab.model import ModelError


class ConditionTests(unittest.TestCase):
    engine=fixtures.RuntimeTests.engine

    def setUp(self):
        fixtures.RuntimeTests.setUp(self)
        self.root=E.parse(Path(__file__).resolve().parents[1]/'samples/CallLab.L5X').getroot()

    def check(self,expression,result):
        e=self.engine([f'CMP({expression})OTE(CompareOK);']);self.assertEqual(e.blockers,[])
        e.step();self.assertEqual(e.memory.read('CompareOK'),result,expression)

    def test_relations_and_arithmetic_precedence(self):
        for expr,result in [('InputValue=7',True),('InputValue<>7',False),('InputValue<8',True),('InputValue<=7',True),
                            ('InputValue>6',True),('InputValue>=8',False),('(2+3*4)=14',True),('16#F AND 3=3',True)]:
            with self.subTest(expr=expr):self.check(expr,result)

    def test_logical_precedence_and_negation(self):
        for expr,result in [('1=1||1=2&&1=2',True),('1=1^^1=1&&1=2',True),('!EarlyReturn&&Enabled',True),
                            ('Enabled AND EarlyReturn',False),('NOT Enabled',False),('Enabled=EarlyReturn',False)]:
            with self.subTest(expr=expr):self.check(expr,result)

    def test_float32_promotion_applies_to_entire_expression(self):
        self.check('(16777217=16777216)&&(RealInput>0.0)',True)
        self.check('ABS(-5)=5&&TRN(2.9)=2.0',True)

    def test_power_left_to_right_and_negation_precedence(self):
        self.check('2.0**3.0**2.0=64.0',True);self.check('-2.0**2.0=-4.0',True)

    def test_false_rung_does_not_evaluate_cmp_arithmetic(self):
        e=self.engine(['AFI()CMP(1.0/0.0>2.0)OTE(CompareOK);']);self.assertEqual(e.blockers,[]);e.step()
        self.assertFalse(e.memory.read('CompareOK'))

    def test_cmp_fault_rolls_back_earlier_writes(self):
        e=self.engine(['MOV(99,Result);','CMP(1.0/0.0>2.0)OTE(CompareOK);'])
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.read('Result'),0);self.assertEqual(e.time_ms,0)

    def test_logical_evaluation_does_not_hide_faults(self):
        e=self.engine(['CMP((1=1)||(1.0/0.0>0.0))OTE(CompareOK);'])
        with self.assertRaisesRegex(ModelError,'zero'):e.step()

    def test_unsupported_or_wrongly_typed_conditions_block_even_false(self):
        for expr in ('InputValue','InputValue&&Enabled','Enabled+1=2','InputValue<8<9','RealInput AND 1=1',
                     'InputValue**2=3','UNKNOWN=1','__import__(os)=1','InputValue==7','Enabled>EarlyReturn'):
            with self.subTest(expr=expr):self.assertTrue(self.engine([f'AFI()CMP({expr})OTE(CompareOK);']).blockers)

    def test_relational_syntax_remains_unavailable_to_cpt(self):
        self.assertTrue(self.engine(['CPT(Result,InputValue=7);']).blockers)

    def test_meq_pass_and_fail_and_zero_mask(self):
        for source,mask,compare,result in [('16#1234','16#00F0','16#0030',True),('16#1234','16#00F0','16#0040',False),
                                         ('-1','0','0',True),('-1','16#FFFFFFFF','16#FFFFFFFF',True)]:
            e=self.engine([f'MEQ({source},{mask},{compare})OTE(MaskOK);']);self.assertEqual(e.blockers,[]);e.step()
            self.assertEqual(e.memory.read('MaskOK'),result)

    def test_meq_zero_extends_signed_sint_and_int(self):
        tag=self.root.find('./Controller/Tags/Tag[@Name="PackedWord"]');data=tag.find('Data/DataValue')
        for dtype,bits in [('SINT',8),('INT',16)]:
            tag.set('DataType',dtype);data.set('DataType',dtype);data.set('Value','-1')
            e=self.engine([f'MEQ(PackedWord,16#FFFFFFFF,{(1<<bits)-1})OTE(MaskOK);']);self.assertEqual(e.blockers,[]);e.step()
            self.assertTrue(e.memory.read('MaskOK'))

    def test_meq_rejects_float_bool_wide_and_oversized_masks(self):
        for operand in ('RealInput','Enabled','16#100000000'):
            with self.subTest(operand=operand):self.assertTrue(self.engine([f'MEQ({operand},1,1)OTE(MaskOK);']).blockers)

    def test_cmp_string_comparisons_use_active_bytes(self):
        self.root=E.parse(Path(__file__).resolve().parents[1]/'samples/DataLab.L5X').getroot()
        for expression,result in [('Prefix>Message',True),('Prefix=Prefix',True),('Prefix<>Message',True)]:
            e=self.engine([f'CMP({expression})OTE(HighBit);']);self.assertEqual(e.blockers,[]);e.step()
            self.assertEqual(e.memory.read('HighBit'),result)
        self.assertTrue(self.engine(['CMP(Prefix=1)OTE(HighBit);']).blockers)
        self.assertTrue(self.engine(["CMP(Prefix='VALUE ')OTE(HighBit);"]).blockers)

    def test_indirect_bit_conditions_re_evaluate_indices_and_fault_atomically(self):
        e=self.engine(['MOV(99,Result);','CMP(PackedWord.[InputValue])OTE(CompareOK);'])
        self.assertEqual(e.blockers,[])
        e.memory.write('PackedWord',5)
        for index,expected in ((0,True),(1,False),(2,True)):
            e.memory.write('InputValue',index);e.step()
            self.assertEqual(e.memory.read('CompareOK'),expected)
        e.memory.write('InputValue',32);e.memory.write('Result',12);scan=e.scan_count
        with self.assertRaisesRegex(ModelError,'bit selection'):e.step()
        self.assertEqual(e.memory.read('Result'),12);self.assertEqual(e.scan_count,scan)
        for index in ('RealInput','Enabled'):
            self.assertTrue(self.engine(['CMP(PackedWord.['+index+'])OTE(CompareOK);']).blockers)


if __name__=='__main__':unittest.main()
