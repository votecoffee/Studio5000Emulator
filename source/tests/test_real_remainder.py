"""Finite ladder REAL remainder with lazy references and atomic recovery."""
import math
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_scalar_math as fixtures
from logixlab.model import ModelError


class RealRemainderTests(unittest.TestCase):
    setUp = fixtures.ScalarMathTests.setUp
    checked = fixtures.ScalarMathTests.checked
    snapshot = staticmethod(fixtures.ScalarMathTests.snapshot)

    def engine(self, rungs=None, *, source='REAL', other='REAL', dest='REAL', value=-7.5, divisor=2, mutate=None):
        def fields(root):
            tag = root.find('./Controller/Tags/Tag[@Name="Mask"]');tag.set('DataType', other)
            node = tag.find('Data/DataValue');node.set('DataType', other);node.set('Value', str(divisor))
            if mutate:mutate(root)
        return fixtures.ScalarMathTests.engine(self, rungs or ['MOD(Source,Mask,Results[1]);'],
                                              source=source, dest=dest, value=value, mutate=fields)

    def test_fractional_remainders_keep_dividend_sign_for_both_divisor_signs(self):
        for a, b, expected in ((7.5,2,1.5),(-7.5,2,-1.5),(7.5,-2,1.5),(-7.5,-2,-1.5),
                               (1.5,3,1.5),(-1.5,3,-1.5),(0.0,3,0.0),(-0.0,3,-0.0)):
            with self.subTest(a=a,b=b):
                e=self.checked(value=a,divisor=b);e.step();result=e.memory.read('Results[1]')
                self.assertEqual(result,expected);self.assertEqual(math.copysign(1,result),math.copysign(1,expected))
                self.assertEqual(e.memory.read('Results')[::2],[None,None])

    def test_real_and_each_narrow_integer_source_pair_with_four_result_types(self):
        for source, other in (('REAL','REAL'),('REAL','SINT'),('REAL','INT'),('REAL','DINT'),
                              ('SINT','REAL'),('INT','REAL'),('DINT','REAL')):
            for dest in ('SINT','INT','DINT','REAL'):
                with self.subTest(source=source,other=other,dest=dest):
                    e=self.checked(source=source,other=other,dest=dest,value=-7,divisor=3);e.step()
                    self.assertEqual(e.memory.read('Results[1]'),-1)

    def test_integer_to_real_promotion_happens_before_remainder(self):
        e=self.checked(source='DINT',value=16777217,divisor=3);e.step()
        self.assertEqual(e.memory.read('Results[1]'),1.0)
        e=self.checked(other='DINT',value=33554432,divisor=16777217);e.step()
        self.assertEqual(e.memory.read('Results[1]'),0.0)

    def test_fractional_immediates_are_rounded_to_float32_before_execution(self):
        e=self.checked(['MOD(0.3,0.1,Results[1]);']);e.step()
        self.assertEqual(e.memory.read('Results[1]'),7.450580596923828e-09)
        e=self.checked(['MOD(-7.5,2,Results[0]);','MOD(7,2.5,Results[1]);']);e.step()
        self.assertEqual(e.memory.read('Results')[:2],[-1.5,2.0])

    def test_integer_results_round_nearest_even_for_positive_and_negative_ties(self):
        for value, divisor, expected in ((5.5,3,2),(7.5,4,4),(-5.5,3,-2),(-7.5,4,-4)):
            e=self.checked(value=value,divisor=divisor,dest='DINT');e.step()
            self.assertEqual(e.memory.read('Results[1]'),expected)

    def test_small_divisors_large_finite_values_and_signed_zero_do_not_form_a_quotient(self):
        for value, divisor, expected in ((3.4028234663852886e38,1.401298464324817e-45,0.0),
                                        (-8,2,-0.0),(1.401298464324817e-45,2,1.401298464324817e-45)):
            e=self.checked(value=value,divisor=divisor);e.step();result=e.memory.read('Results[1]')
            self.assertEqual(result,expected);self.assertEqual(math.copysign(1,result),math.copysign(1,expected))

    def test_false_and_prescan_skip_unknown_values_and_bad_indices(self):
        e=self.checked(['XIC(StartPB)MOD(Inputs[Index],Mask,Results[Index]);']);e.memory.write('Index',999)
        self.assertEqual(e.memory.read('Results'),[None]*3);reads=[];read=e.memory.read
        def tracked(ref,scope=''):
            if not e.memory.structural:reads.append(ref)
            return read(ref,scope)
        with patch.object(e.memory,'read',side_effect=tracked):e.step()
        self.assertNotIn('Index',reads);self.assertNotIn('Inputs[Index]',reads)
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Index',1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[1]',-7.5);e.step();self.assertEqual(e.memory.read('Results'),[None,-1.5,None])

    def test_either_unknown_source_is_required_only_when_reached_and_recovers(self):
        for instruction in ('MOD(Inputs[0],Mask,Results[1]);','MOD(Source,Inputs[0],Results[1]);'):
            e=self.checked(['MOV(99,SpeedCommand);',instruction]);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)
            e.memory.write('Inputs[0]',2);e.step();self.assertIsNotNone(e.memory.read('Results[1]'))

    def test_zero_and_underflowed_immediate_divisors_roll_back_then_retry(self):
        for divisor in (0.0,-0.0,1e-50):
            e=self.checked(['MOV(99,SpeedCommand);',f'MOD(Source,{divisor},Results[1]);']);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'zero'):e.step()
            self.assertEqual(self.snapshot(e),before)
        e=self.checked(['MOV(99,SpeedCommand);','MOD(Source,Mask,Results[1]);'],divisor=0)
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Mask',2);e.step();self.assertEqual(e.memory.read('Results[1]'),-1.5)

    def test_unrepresentable_integer_result_rolls_back_all_writes_and_retries(self):
        e=self.checked(['MOV(99,SpeedCommand);','MOD(Source,Mask,Results[1]);'],dest='SINT',value=127.5,divisor=1000)
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'overflow'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Source',126.5);e.step();self.assertEqual(e.memory.read('Results[1]'),126)

    def test_later_failure_restores_remainder_unknowns_overlap_aliases_and_scheduler(self):
        def aliases(root):
            E.SubElement(root.find('./Controller/Tags'),'Tag',Name='ResultAlias',TagType='Alias',DataType='REAL',AliasFor='Results[0]')
        e=self.checked(['MOD(Source,Mask,ResultAlias);','MOD(Results[0],1,Results[0]);','DIV(1,Inputs[0],SpeedCommand);'],mutate=aliases)
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[0]',1);e.step();self.assertEqual(e.memory.read('Results'),[-0.5,None,None])

    def test_invalid_shapes_permissions_and_bool_results_stay_blocked(self):
        for rung in ('MOD(StartPB,Mask,Results[0]);','MOD(Source,Mask,Results);','MOD(Inputs,Mask,Results[0]);','MOD(Missing,Mask,Results[0]);'):
            self.assertTrue(self.engine(['AFI()'+rung]).blockers,rung)
        self.assertTrue(self.engine(dest='BOOL').blockers)
        for kwargs in ({'source':'LINT','value':7},{'other':'ULINT','value':7},
                       {'source':'LREAL','value':7},{'other':'LREAL','value':7},
                       {'dest':'UDINT','value':7}):
            e=self.checked(**kwargs);e.step();self.assertEqual(e.memory.read('Results[1]'),1)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()MOD(Source,Mask,Results[0]);'],mutate=constant).blockers)

    def test_nonfinite_and_out_of_range_real_immediates_stop_without_partial_writes(self):
        for text in ('MOD(1e309,2,Results[0]);','MOD(Source,1e309,Results[0]);','MOD(1e40,2,Results[0]);'):
            e=self.engine(['MOV(99,SpeedCommand);',text]);self.assertTrue(e.blockers)
            self.assertEqual(e.scan_count,0);self.assertEqual(e.memory.read('SpeedCommand'),0)

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        queues.logic(root,['MOD(Value,2.5,Buffer[Index])MOD(Value,3.0,Stack[0]);'])
        queues.logic(root,['AFI()MOD(Value,2.5,Buffer[Index])MOD(Value,3.0,Stack[0]);'],name='EnableInFalse')
        for name in ('DriverA','DriverB'):
            arr=root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure/ArrayMember[@Name="Stack"]')
            arr.remove(arr.find('Element[@Index="[0]"]'))

    def test_aoi_immediate_real_math_establishes_unknown_locals_and_restores_bindings(self):
        import test_aoi_queues as queues
        fixture=queues.AOIQueueTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
        e=fixture.checked(self.aoi_logic);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(1,2))
        self.assertEqual((e.memory.read('DriverA.Stack[0]'),e.memory.read('DriverB.Stack[0]')),(2,1))
        e.memory.write('EnabledB',False);e.memory.write('IndexB',999);e.step()
        e.memory.write('EnabledB',True);e.memory.write('ValueA',-7);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('IndexB',2);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('DriverA.Stack[0]')),(-2,-1))
        self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)

    def test_exact_integer_remainders_and_other_controller_boundary_remain(self):
        for dest,expected in (('DINT',2),('REAL',1)):
            e=self.checked(source='DINT',other='DINT',dest=dest,value=16777217,divisor=3);e.step()
            self.assertEqual(e.memory.read('Results[1]'),expected)
        e=self.checked(source='LINT',other='LINT',dest='LINT',value=9007199254740993,divisor=7);e.step()
        self.assertEqual(e.memory.read('Results[1]'),5)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        e=self.checked(['MOD(Source,Mask,Dest);'],mutate=old)
        with self.assertRaisesRegex(ModelError,'integers only'):e.step()
        report=self.checked().report()['scalar_math'];self.assertFalse(report['real_remainder']['native_precision'])


if __name__=='__main__':unittest.main()
