"""Ladder math integer results: conversion boundaries, bindings and rollback."""
import copy
import itertools
import unittest
from xml.etree import ElementTree as E

import test_real_math as fixtures
import test_real_destination_math as wide
from logixlab.model import INT_BITS, ModelError


class MathIntegerResultTests(unittest.TestCase):
    setUp=fixtures.RealMathTests.setUp
    engine=fixtures.RealMathTests.engine
    checked=fixtures.RealMathTests.checked

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved,e.addons.instances,
                              e.scan_count,e.time_ms,e.trace,e.scheduler_description()))

    def test_every_math_family_accepts_narrow_integer_destinations(self):
        cases=(('SQR',3,2),('XPY',2,8),('LN',3,1),('LOG',20,1),('DEG',1,57),
               ('RAD',90,2),('SIN',1,1),('COS',1,1),('TAN',1,2),('ASN',1,2),
               ('ACS',-1,3),('ATN',1,1))
        for source_type in ('SINT','INT','DINT','REAL'):
            for dest_type in ('SINT','INT','DINT'):
                for name,value,expected in cases:
                    with self.subTest(source=source_type,dest=dest_type,name=name):
                        args='Source,Mask,Dest' if name=='XPY' else 'Source,Dest'
                        e=self.checked([f'{name}({args});'],types=(source_type,source_type,dest_type),values=(value,3,7))
                        e.step();self.assertEqual(e.memory.read('Dest'),expected)
                        self.assertIs(type(e.memory.read('Dest')),int)

    def test_5580_integer_square_root_rounds_instead_of_truncating(self):
        for source in ('3','3.0','16#3','Source'):
            e=self.checked([f'SQR({source},Dest);'],types=('DINT','REAL','DINT'),values=(3,2,7))
            e.step();self.assertEqual(e.memory.read('Dest'),2)
        for source,expected in ((-3,2),(-2147483648,46341)):
            e=self.checked(['SQR(Source,Dest);'],types=('DINT','REAL','DINT'),values=(source,2,7))
            e.step();self.assertEqual(e.memory.read('Dest'),expected)

    def test_positive_and_negative_exact_halves_round_to_even(self):
        for dtype in ('SINT','INT','DINT'):
            for value,expected in ((-3.5,-4),(-2.5,-2),(-1.5,-2),(-0.5,0),(0.5,0),(1.5,2),(2.5,2),(3.5,4)):
                e=self.checked(['XPY(Source,1.0,Dest);'],types=('REAL','REAL',dtype),values=(value,2,7))
                e.step();self.assertEqual(e.memory.read('Dest'),expected)
        for value,expected in ((2.25,2),(6.25,2),(12.25,4)):
            e=self.checked(['SQR(Source,Dest);'],types=('REAL','REAL','DINT'),values=(value,2,7))
            e.step();self.assertEqual(e.memory.read('Dest'),expected)

    def test_rounding_uses_finite_float32_intermediate(self):
        for value,expected in ((16777217,16777216),(-16777217,-16777216),(2147483520,2147483520)):
            e=self.checked(['XPY(Source,1,Dest);'],types=('DINT','REAL','DINT'),values=(value,2,7))
            e.step();self.assertEqual(e.memory.read('Dest'),expected)
        e=self.checked(['XPY(Source,1,Dest);'],types=('DINT','REAL','DINT'),values=(2147483647,2,7))
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'DINT overflow'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_bounds_are_checked_after_rounding(self):
        for dtype,value,expected in (('SINT',127.49,127),('SINT',-128.5,-128),
                                     ('INT',32767.49,32767),('INT',-32768.5,-32768),
                                     ('DINT',-2147483648.0,-2147483648)):
            e=self.checked(['XPY(Source,1,Dest);'],types=('REAL','REAL',dtype),values=(value,2,7))
            e.step();self.assertEqual(e.memory.read('Dest'),expected)

    def test_out_of_range_rounded_result_rolls_back_prior_work(self):
        for dtype,value in (('SINT',127.5),('SINT',-128.51),('INT',32767.5),
                            ('INT',-32768.51),('DINT',2147483648.0),('DINT',-2147483904.0)):
            e=self.checked(['MOV(23,Mask);','XPY(Source,1,Dest);'],types=('REAL','REAL',dtype),values=(value,2,7))
            before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,dtype+' overflow'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_false_and_run_prescan_preserve_unknown_results(self):
        e=self.checked(['AFI()SQR(Source,Dest);'],types=('REAL','REAL','DINT'))
        e.memory.values['source']=e.memory.values['dest']=None;e.enter_run();e.step()
        self.assertIsNone(e.memory.values['dest'])

    def test_full_integer_write_establishes_unknown_result_and_continues_power(self):
        for dtype in ('SINT','INT','DINT'):
            e=self.checked(['SQR(Source,Dest)OTE(RunLatch);'],types=('REAL','REAL',dtype),values=(6.25,2,7))
            e.memory.values['dest']=None;e.step();self.assertEqual(e.memory.read('Dest'),2);self.assertTrue(e.memory.read('RunLatch'))

    def test_in_place_integer_result_captures_original_inputs(self):
        e=self.checked(['SQR(Source,Source);','XPY(Source,Mask,Mask);'],types=('DINT','INT','DINT'),values=(-3,3,7))
        e.step();self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),(2,8))

    @staticmethod
    def aggregate(root):
        c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='MathPacket',Family='NoFamily',Class='User'),'Members')
        for name in ('Value','Guard'):E.SubElement(members,'Member',Name=name,DataType='INT',Dimension='0')
        tags=c.find('Tags');obj=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Packet1',DataType='MathPacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='MathPacket')
        for name,value in (('Value',7),('Guard',1234)):E.SubElement(obj,'DataValueMember',Name=name,DataType='INT',Value=str(value))
        E.SubElement(tags,'Tag',Name='AliasResult',DataType='INT',TagType='Alias',AliasFor='Packet1.Value')
        arr=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Results',DataType='SINT',Dimensions='2',TagType='Base'),'Data',Format='Decorated'),'Array',DataType='SINT',Dimensions='2')
        for i,value in enumerate((7,99)):E.SubElement(arr,'Element',Index=f'[{i}]',Value=str(value))

    def test_alias_member_and_indirect_array_destinations_preserve_guards(self):
        e=self.checked(['SQR(Source,AliasResult);','XPY(-2.5,1,Results[Mask]);'],types=('REAL','DINT','DINT'),values=(6.25,0,7),mutate=self.aggregate)
        e.step();self.assertEqual((e.memory.read('Packet1.Value'),e.memory.read('Packet1.Guard'),e.memory.read('Results')),(2,1234,[-2,99]))

    def test_late_bad_indirect_destination_rolls_back_earlier_result(self):
        e=self.checked(['SQR(Source,AliasResult);','XPY(-2.5,1,Results[Mask]);'],types=('REAL','DINT','DINT'),values=(6.25,0,7),mutate=self.aggregate)
        e.memory.write('Mask',999);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_domain_unknown_and_nonfinite_sources_roll_back_integer_results(self):
        for text in ('LN(0,Dest);','LOG(-1,Dest);','ASN(2,Dest);','ACS(-2,Dest);','XPY(-2,0.5,Dest);','XPY(2,128,Dest);'):
            e=self.checked(['SQR(6.25,Dest);',text],types=('REAL','REAL','DINT'));before=self.snapshot(e)
            with self.assertRaises(ModelError):e.step()
            self.assertEqual(self.snapshot(e),before)
        for value in (None,float('inf'),float('nan')):
            e=self.checked(['SQR(Source,Dest);'],types=('REAL','REAL','DINT'));e.memory.values['source']=value
            with self.assertRaises(ModelError):e.step()
            self.assertEqual((e.memory.read('Dest'),e.scan_count,e.time_ms),(7,0,0))

    def aoi(self,*,late=False):
        import test_addons as addons
        f=addons.AddOnTests();f.setUp();self.addCleanup(f.doCleanups)
        f.body()[0].find('Text').text='SQR(Step,Count)MOV(Count,Total)SQR(Shared,Shared);'
        e=f.engine(['LabAccumulator(AccumulatorA,StepA,TotalA,SharedA);','LabAccumulator(AccumulatorB,StepB,TotalB,SharedB);']+(['DIV(1,StepA,TotalA);'] if late else []))
        self.assertEqual(e.blockers,[]);return e

    def test_aoi_independent_local_output_and_inout_integer_results(self):
        e=self.aoi();e.step()
        self.assertEqual(tuple(e.memory.read(t) for t in ('AccumulatorA.Count','AccumulatorB.Count','TotalA','TotalB','SharedA','SharedB')),(1,2,1,2,3,4))

    def test_late_fault_rolls_back_all_aoi_integer_result_paths(self):
        e=self.aoi(late=True);e.memory.write('StepA',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('StepA',2);e.step();self.assertEqual(e.memory.read('SharedB'),4)

    def test_bool_bits_aggregate_and_constant_destinations_stay_blocked(self):
        self.assertTrue(self.engine(['SQR(Source,Dest);'],types=('REAL','REAL','BOOL'),values=(3,2,0)).blockers)
        for ref in ('Results','Packet1','Dest.0','3'):
            self.assertTrue(self.engine([f'SQR(Source,{ref});'],mutate=self.aggregate).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Dest"]').set('Constant','true')
        self.assertTrue(self.engine(['SQR(Source,Dest);'],types=('REAL','REAL','INT'),mutate=constant).blockers)

    def test_report_exposes_rounding_and_overflow_boundary(self):
        e=self.checked(['SQR(Source,Dest);'],types=('REAL','REAL','DINT'));report=e.report()['real_math']
        self.assertEqual(report['destinations'],['DINT','INT','REAL','SINT']);self.assertIn('ties to even',report['integer_conversion']);self.assertIn('out-of-range',report['integer_conversion'])
        self.assertFalse(report['native_math_status']);self.assertFalse(report['native_fault_classification'])


class WideRootPowerTests(unittest.TestCase):
    setUp = wide.RealDestinationMathTests.setUp
    engine = wide.RealDestinationMathTests.engine
    checked = wide.RealDestinationMathTests.checked
    fault = wide.RealDestinationMathTests.fault
    snapshot = staticmethod(wide.RealDestinationMathTests.snapshot)

    def test_integer_tag_inputs_and_all_result_types(self):
        for source, dest in itertools.product(INT_BITS, repeat=2):
            with self.subTest(source=source, dest=dest):
                engine = self.checked(
                    ['SQR(Source,Results[0]);', 'XPY(Source,Mask,Results[1]);'],
                    source=source, other='UINT', dest=dest, value=4,
                )
                engine.memory.write('Mask', 3)
                engine.step()
                self.assertEqual(engine.memory.read('Results'), [2, 64, None])
                self.assertEqual((engine.memory.read('Source'), engine.memory.read('Mask')), (4, 3))

    def test_exact_rounding_distinguishes_adjacent_large_integer_radicands(self):
        engine = self.checked([
            'SQR(16000000004000000000UL,Results[0]);',
            'SQR(16000000004000000001UL,Results[1]);',
            'SQR(18446744073709551615UL,Results[2]);',
        ], dest='ULINT')
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [4000000000, 4000000001, 4294967296])
        engine = self.checked(['SQR(Source,Results[1]);'], source='LINT', value=-(1 << 63), dest='LINT')
        engine.step()
        self.assertEqual(engine.memory.read('Results[1]'), 3037000500)

    def test_powers_preserve_exact_values_signed_limits_and_exponent_parity(self):
        engine = self.checked([
            'XPY(9007199254740993L,1,Results[0]);',
            'XPY(-2L,63U,Results[1]);',
            'XPY(-1,18446744073709551615UL,Results[2]);',
        ], dest='LINT')
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [9007199254740993, -9223372036854775808, -1])
        engine = self.checked(['XPY(3,34U,Results[1]);'], dest='ULINT')
        engine.step()
        self.assertEqual(engine.memory.read('Results[1]'), 16677181699666569)

    def test_negative_and_zero_exponents_with_integer_destinations(self):
        for base, exponent, expected in (
            ('0L', '0', 1), ('0L', '18446744073709551615UL', 0),
            ('-1L', '-9223372036854775807L', -1), ('-1L', '-9223372036854775808L', 1),
            ('2L', '-1', 0), ('-2L', '-1', 0), ('3L', '-9223372036854775808L', 0),
        ):
            with self.subTest(base=base, exponent=exponent):
                engine = self.checked([f'XPY({base},{exponent},Results[1]);'], dest='LINT')
                engine.step()
                self.assertEqual(engine.memory.read('Results[1]'), expected)

    def test_overflows_and_zero_to_negative_power_restore_prior_work(self):
        for call, dtype, error in (
            ('XPY(0L,-1,Results[1]);', 'LINT', 'zero'),
            ('XPY(2L,18446744073709551615UL,Results[1]);', 'ULINT', 'overflow'),
            ('XPY(2L,63U,Results[1]);', 'LINT', 'overflow'),
            ('XPY(-2L,3,Results[1]);', 'UINT', 'overflow'),
            ('SQR(18446744073709551615UL,Results[1]);', 'UDINT', 'overflow'),
        ):
            with self.subTest(call=call, dtype=dtype):
                engine = self.checked(['MOV(99,SpeedCommand);', call], dest=dtype)
                self.fault(engine, error)

    def test_false_prescan_and_failed_steps_leave_indirect_results_unknown(self):
        engine = self.checked([
            'XIC(StartPB)XPY(Inputs[Index],1,Results[Index]);',
            'XIC(StartPB)DIV(1,Mask,SpeedCommand);',
        ], source='ULINT', dest='ULINT')
        engine.memory.write('Index', 99)
        engine.enter_run()
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [None, None, None])
        engine.memory.write('StartPB', True)
        self.fault(engine, 'outside bounds')
        engine.memory.write('Index', 1)
        self.fault(engine, 'Unknown')
        engine.memory.write('Inputs[1]', 9007199254740993)
        engine.memory.write('Mask', 0)
        self.fault(engine, 'zero')
        engine.memory.write('Mask', 1)
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [None, 9007199254740993, None])
        for call in ('XPY(Inputs[1],0,Results[1]);', 'XPY(1,Inputs[1],Results[1]);'):
            self.fault(self.checked([call], source='ULINT', dest='ULINT'), 'Unknown')

    def test_exact_selection_leaves_floating_and_legacy_paths_available(self):
        engine = self.checked([
            'XPY(16777217,1,SpeedCommand);',
            'XPY(16777217U,1,Results[0]);',
            'XPY(16777217U,1.0,Results[1]);',
            'XPY(16777217U,1.0L,Results[2]);',
        ], dest='LINT')
        engine.step()
        self.assertEqual(engine.memory.read('SpeedCommand'), 16777216)
        self.assertEqual(engine.memory.read('Results'), [16777217, 16777216, 16777217])

    def test_preflight_rejects_invalid_literals_types_and_permissions(self):
        for call in (
            'SQR(16#FFFFFFFF,Results[1]);', 'SQR(18446744073709551616UL,Results[1]);',
            'SQR(Inputs,Results[1]);', 'XPY(2L,TRUE,Results[1]);',
            'XPY(2L,3,Results);', 'SQR(1L,RunLatch);',
        ):
            self.assertTrue(self.engine(['AFI()' + call], dest='ULINT').blockers, call)
        def readonly(root):
            root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant', 'true')
        self.assertTrue(self.engine(['SQR(3L,Results[1]);'], dest='LINT', mutate=readonly).blockers)
        report = self.checked(['SQR(3L,Results[1]);'], dest='LINT').report()['real_math']['integer_root_power']
        self.assertEqual(set(report['destination_types']), set(INT_BITS))
        self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
