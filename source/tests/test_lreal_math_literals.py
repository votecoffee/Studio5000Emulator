"""Declared immediate precision in nineteen LREAL-result ladder math forms."""
import itertools
import math
import struct
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_lreal_destination_math as fixtures
import test_file_bcd as snapshots
from logixlab.model import Project, literal
from logixlab.runtime import Engine

BINARY={'ADD':2.0,'SUB':0.0,'MUL':1.0,'DIV':1.0,'MOD':0.0,'XPY':1.0}
UNARY={'NEG':-1.0,'ABS':1.0,'SQR':1.0,'LN':0.0,'LOG':0.0,
       'DEG':math.degrees(1),'RAD':math.radians(1),'SIN':math.sin(1),
       'COS':math.cos(1),'TAN':math.tan(1),'ASN':math.pi/2,'ACS':0.0,'ATN':math.pi/4}
TOKENS=('1','1L','1u','1Ul','1.0','1.0l')
RESULT_CASES = (
    ('ADD', '2.5L,2.0L', 4.5), ('SUB', '5.5L,2.0L', 3.5),
    ('MUL', '1.5L,2.0L', 3.0), ('DIV', '7.0L,2U', 3.5),
    ('MOD', '7.5L,2U', 1.5), ('NEG', '-2.5L', 2.5), ('ABS', '-3.5L', 3.5),
    ('XPY', '4.0L,0.5L', 2.0), ('SQR', '-9.0L', 3.0),
    ('LN', '1.0L', 0.0), ('LOG', '100.0L', 2.0),
    ('DEG', '0.0L', 0.0), ('RAD', '0.0L', 0.0),
    ('SIN', '0.0L', 0.0), ('COS', '0.0L', 1.0), ('TAN', '0.0L', 0.0),
    ('ASN', '0.0L', 0.0), ('ACS', '1.0L', 0.0), ('ATN', '0.0L', 0.0),
)


class LrealMathLiteralTests(unittest.TestCase):
    setUp=fixtures.LrealDestinationMathTests.setUp
    engine=fixtures.LrealDestinationMathTests.engine
    checked=fixtures.LrealDestinationMathTests.checked
    snapshot=staticmethod(snapshots.FileBcdTests.snapshot)
    fault=snapshots.FileBcdTests.fault

    def test_all_nineteen_forms_accept_each_declared_constant_kind(self):
        for name,token in itertools.product({**BINARY,**UNARY},TOKENS):
            with self.subTest(name=name,token=token):
                args=token+','+token if name in BINARY else token
                e=self.checked([f'{name}({args},Results[1]);']);e.step()
                self.assertEqual(e.memory.read('Results'),[None,({**BINARY,**UNARY})[name],None])

    def test_typed_constants_work_in_both_binary_operand_positions(self):
        expected={'ADD':(4.0,4.0),'SUB':(2.0,-2.0),'MUL':(3.0,3.0),
                  'DIV':(3.0,1/3),'MOD':(0.0,1.0),'XPY':(3.0,1.0)}
        for name,token,position in itertools.product(expected,TOKENS[1:],range(2)):
            args='Source,'+token if position==0 else token+',Source'
            e=self.checked([f'{name}({args},Results[1]);'],value=3);e.step()
            self.assertEqual(e.memory.read('Results[1]'),expected[name][position])

    def test_real_default_and_lreal_suffix_preserve_source_precision(self):
        e=self.checked(['ADD(0.1,0.0L,Results[0]);','ADD(0.1L,0.0L,Results[1]);']);e.step()
        self.assertEqual(e.memory.read('Results'),[.10000000149011612,.1,None])
        e=self.checked(['SQR(16777217.0,Results[0]);','SQR(16777217.0L,Results[1]);']);e.step()
        self.assertEqual(e.memory.read('Results'),[4096.0,math.sqrt(16777217),None])

    def test_typed_integer_ranges_round_only_when_promoted_to_binary64(self):
        for text,expected in [('9007199254740993L',9007199254740992.0),
                              ('18446744073709551615UL',float(1<<64)),
                              ('4294967295U',4294967295.0),('-9223372036854775808L',float(-(1<<63)))]:
            e=self.checked(['ADD('+text+',0.0L,Results[1]);']);e.step()
            self.assertEqual(e.memory.read('Results[1]'),expected)
        e=self.checked(['MOD(18446744073709551615UL,3UL,Results[1]);']);e.step()
        self.assertEqual(e.memory.read('Results[1]'),1.0)

    def test_large_subnormal_and_signed_zero_constants_retain_binary64_bits(self):
        for call,expected in [('MUL(1e308L,1L,Results[1]);',1e308),
                              ('MUL(5e-324L,1L,Results[1]);',5e-324),
                              ('MUL(-0.0L,1L,Results[1]);',-0.0),
                              ('NEG(0.0L,Results[1]);',-0.0),
                              ('ABS(-0.0L,Results[1]);',0.0)]:
            e=self.checked([call]);e.step()
            self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),struct.pack('<d',expected))

    def test_unsuffixed_real_underflow_occurs_before_binary64_promotion(self):
        e=self.checked(['MUL(1e-50,1L,Results[0]);','MUL(1e-50L,1L,Results[1]);']);e.step()
        self.assertEqual(e.memory.read('Results'),[0.0,1e-50,None])

    def test_invalid_ranges_digits_and_expression_forms_remain_structural(self):
        bad=['9223372036854775808L','-9223372036854775809L','4294967296U','-1U',
             '18446744073709551616UL','-1UL','1e309L','1e39','2147483648',
             '16#FFFFFFFF','16#FFU','1LU','1_000L','LREAL#1.0','1.0UL','1e3U',
             '(1L)','1L+1L','ABS(1L)','TRUE','Inputs']
        for text in bad:
            for name in ('ADD','XPY','SQR'):
                args=text+',1L' if name in BINARY else text
                self.assertTrue(self.engine([f'AFI(){name}({args},Results[1]);']).blockers,(name,text))

    def test_domain_and_result_range_checks_are_lazy_and_atomic(self):
        for call,pattern in [('LN(-1.0L,Results[1]);','finite'),('XPY(-2L,0.5L,Results[1]);','finite'),
                             ('XPY(0L,-1L,Results[1]);','finite'),('ASN(1.0000000000000002L,Results[1]);','finite'),
                             ('DIV(1L,0.0L,Results[1]);','zero'),('MOD(1L,0.0L,Results[1]);','zero'),
                             ('MUL(1e308L,2UL,Results[1]);','Nonfinite')]:
            e=self.checked(['XIC(StartPB)'+call]);e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
            e.memory.write('StartPB',True);self.fault(e,pattern)

    def test_false_and_prescan_skip_live_source_and_destination_indices(self):
        e=self.checked(['XIC(StartPB)ADD(Inputs[Index],0.1L,Results[Index]);']);e.memory.write('Index',999);e.step()
        e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);self.fault(e,'Unknown');e.memory.write('Inputs[1]',2);e.step()
        self.assertEqual(e.memory.read('Results'),[None,2.1,None])

    def test_zero_products_and_unit_powers_still_consume_unknown_sources(self):
        for call in ('MUL(Inputs[1],0L,Results[1]);','XPY(1L,Inputs[1],Results[1]);'):
            e=self.checked([call]);self.fault(e,'Unknown')

    def test_overlapping_scalar_sources_are_captured_before_stores(self):
        e=self.checked(['ADD(Results[1],0.5L,Results[1]);']);e.memory.write('Results[1]',2);e.step()
        self.assertEqual(e.memory.read('Results'),[None,2.5,None])

    def test_late_failures_restore_values_timing_traces_and_scheduler(self):
        e=self.checked(['ADD(0.1L,0.0L,Results[1]);','DIV(1,Index,SpeedCommand);'])
        self.fault(e,'zero');e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Results[1]'),.1)

    def test_alias_members_and_indirect_destinations_preserve_guards(self):
        def fields(root):
            c=root.find('Controller');m=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Value','Guard'):E.SubElement(m,'Member',Name=name,DataType='LREAL',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='LREAL',Value='777.25')
            E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='LREAL',TagType='Alias',AliasFor='Packet1.Value')
        e=self.checked(['ADD(0.1L,0.0L,AliasValue);','SQR(4U,Results[FRD(TOD(1))]);'],mutate=fields);e.step()
        self.assertEqual((e.memory.read('Packet1.Value'),e.memory.read('Packet1.Guard')),(.1,777.25))
        self.assertEqual(e.memory.read('Results'),[None,2.0,None])

    @staticmethod
    def aoi_fields(root):
        import test_aoi_queues as queues
        import test_lreal_results as results
        results.LrealResultTests.aoi_fields(root,'LREAL')
        queues.logic(root,['ADD(Value,0.1L,Buffer[Index]);','SQR(4U,Item);','XPY(0.5L,1L,Stack[Index]);'])
        queues.logic(root,['AFI()LN(-1.0L,Stack[Index]);'],name='EnableInFalse')

    def test_warm_aoi_output_inout_and_local_state_rollback(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups)
        e=f.checked(self.aoi_fields);value=e.memory.read('ValueA');e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('ItemA'),e.memory.read('DriverA.Stack[1]')),(value+.1,2.0,.5))
        e.memory.write('IndexA',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero')
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),value+.1)
        e.memory.write('EnabledA',False);e.memory.write('IndexA',999);e.step()

    def test_invalid_operands_and_firmware_profiles_remain_guarded(self):
        for dest in ('SINT','INT','DINT','LINT','REAL'):
            for call in (('ADD(1.0L,TRUE,Results[1]);' if dest=='REAL' else 'ADD(1UL,1UL,Results[1]);' if dest=='LINT' else 'ADD(1L,1L,Results[1]);'),'XPY(1.0L,TRUE,Results[1]);','SQR(1e309L,Results[1]);'):
                self.assertTrue(self.engine([call],dest=dest).blockers,(call,dest))
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()ADD(1L,1L,Results[1]);'],mutate=lambda root:root.find('Controller').set(key,value)).blockers)
        self.assertTrue(self.engine(['EQU(Source,1e309L)OTE(RunLatch);'],source='LREAL').blockers)
        self.assertEqual(literal('16#FFFFFFFF'),4294967295)

    def test_lreal_sources_can_write_all_nine_other_numeric_destinations(self):
        destinations = ('SINT', 'INT', 'DINT', 'LINT', 'USINT', 'UINT', 'UDINT', 'ULINT', 'REAL')
        for dtype, (name, args, value) in itertools.product(destinations, RESULT_CASES):
            with self.subTest(dtype=dtype, name=name):
                engine = self.checked([f'{name}({args},Results[1]);'], dest=dtype)
                engine.step()
                expected = value if dtype == 'REAL' else round(value)
                self.assertEqual(engine.memory.read('Results'), [None, expected, None])

    def test_lreal_source_precision_survives_until_the_final_write(self):
        engine = self.checked([
            'SUB(Source,16777216,Results[0]);',
            'SUB(16777216,Source,Results[1]);',
            'DIV(1e39L,1e39L,Results[2]);',
        ], source='LREAL', value=16777217, dest='REAL')
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [1.0, -1.0, 1.0])
        self.assertEqual(engine.memory.read('Source'), 16777217.0)
        engine = self.checked([
            'SQR(1e60L,Results[0]);',
            'DIV(1e-50L,1e-50L,Results[1]);',
            'ADD(0.1L,0.1,Results[2]);',
        ], dest='REAL')
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [1.0000000150474662e30, 1.0, 0.20000000298023224])

    def test_integer_results_round_once_and_reject_out_of_range_values(self):
        for call, dtype, expected in (
            ('ADD(-2.5L,0,Results[1]);', 'DINT', -2),
            ('NEG(3.5L,Results[1]);', 'DINT', -4),
            ('ABS(-9223372036854774784.0L,Results[1]);', 'LINT', 9223372036854774784),
            ('ADD(-0.5L,0,Results[1]);', 'ULINT', 0),
        ):
            with self.subTest(call=call, dtype=dtype):
                engine = self.checked([call], dest=dtype)
                engine.step()
                self.assertEqual(engine.memory.read('Results[1]'), expected)
        for call, dtype, error in (
            ('ADD(127.5L,0,Results[1]);', 'SINT', 'overflow'),
            ('NEG(1.5L,Results[1]);', 'UINT', 'overflow'),
            ('XPY(2.0L,63,Results[1]);', 'LINT', 'overflow'),
            ('ADD(1e39L,0,Results[1]);', 'REAL', 'finite REAL'),
            ('XPY(1e20L,2,Results[1]);', 'REAL', 'finite REAL'),
            ('LN(-1.0L,Results[1]);', 'DINT', 'finite LREAL'),
        ):
            with self.subTest(call=call, dtype=dtype):
                engine = self.checked(['MOV(99,SpeedCommand);', call], dest=dtype)
                self.fault(engine, error)

    def test_indirect_sources_and_destinations_skip_false_and_rollback_late_faults(self):
        engine = self.checked([
            'XIC(StartPB)SUB(Inputs[Index],16777216,Results[Index]);',
            'XIC(StartPB)DIV(1,Mask,SpeedCommand);',
        ], source='LREAL', dest='LINT')
        engine.memory.write('Index', 99)
        engine.enter_run()
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [None, None, None])
        engine.memory.write('StartPB', True)
        self.fault(engine, 'outside bounds')
        engine.memory.write('Index', 1)
        self.fault(engine, 'Unknown')
        engine.memory.write('Inputs[1]', 16777217.0)
        engine.memory.write('Mask', 0)
        self.fault(engine, 'zero')
        engine.memory.write('Mask', 1)
        engine.step()
        self.assertEqual(engine.memory.read('Results'), [None, 1, None])

    def test_aoi_outputs_inout_and_locals_use_the_destination_conversion(self):
        import test_aoi_queues as queues

        fixture = queues.AOIQueueTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)

        def logic(root):
            queues.logic(root, [
                'SUB(16777217.0L,16777216,Buffer[Index]);',
                'XPY(4.0L,0.5L,Item);',
                'ADD(3.5L,0,Stack[Index]);',
            ])
            queues.logic(root, ['AFI()ADD(3.5L,0,Stack[Index]);'], name='EnableInFalse')

        engine = fixture.checked(logic)
        engine.step()
        self.assertEqual(engine.memory.read('BufferA[1]'), 1)
        self.assertEqual(engine.memory.read('ItemA'), 2)
        self.assertEqual(engine.memory.read('DriverA.Stack[1]'), 4)
        engine.memory.write('IndexA', 2)
        engine.memory.write('FaultDivisor', 0)
        self.fault(engine, 'zero')
        engine.memory.write('FaultDivisor', 1)
        engine.step()
        self.assertEqual(engine.memory.read('BufferA[2]'), 1)

    def test_permissions_shapes_and_reporting_remain_explicit(self):
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()ADD(1L,1L,Results[1]);'],mutate=constant).blockers)
        self.assertTrue(self.engine(['AFI()ADD(1L,1L,Results);']).blockers)
        e=self.checked();report=e.report()
        self.assertIn('L/U/UL',report['scalar_math']['lreal_arithmetic']['constants'])
        self.assertIn('finite REAL',report['real_math']['lreal']['unary']['constants'])
        self.assertFalse(report['scalar_math']['lreal_arithmetic']['native_runtime_parity'])

    def test_sample_precision_unknowns_faults_and_recovery(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('MathLitSelected'),[None,None,903.25])
        e.memory.write('MathLitEnabled',True);e.step()
        for name,value in [('MathLitDouble',.1),('MathLitDefault',.10000000149011612),('MathLitRounded',9007199254740992.0),('MathLitUnsigned',1.0),('MathLitDivide',1.5),('MathLitPower',math.pow(2,3.5)),('MathLitRoot',math.sqrt(16777217))]:self.assertEqual(e.memory.read(name),value)
        self.assertEqual(e.memory.read('MathLitSelected'),[1.0000000000000002,None,903.25])
        for flag in ('MathLitDomainFault','MathLitRangeFault'):
            e.memory.write(flag,True);self.fault(e,'finite');e.memory.write(flag,False);e.step()
        e.memory.write('MathLitIndex',1);e.memory.write('MathLitLateDivisor',0);self.fault(e,'zero')
        e.memory.write('MathLitLateDivisor',1);e.step();self.assertEqual(e.memory.read('MathLitSelected'),[1.0000000000000002]*2+[903.25])
        e.memory.write('MathLitEnabled',False);e.memory.write('MathLitIndex',999);e.step()


if __name__=='__main__':unittest.main()
