"""Bounded DINT constants in widening ladder arithmetic; no constant folding."""
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

import test_widening_arithmetic as fixtures
from logixlab.model import ModelError

BOUNDS = {'SINT':(-128,127), 'USINT':(0,255), 'INT':(-32768,32767), 'UINT':(0,65535),
          'DINT':(-2147483648,2147483647), 'UDINT':(0,4294967295),
          'LINT':(-9223372036854775808,9223372036854775807), 'ULINT':(0,18446744073709551615)}


class ArithmeticConstantTests(unittest.TestCase):
    setUp = fixtures.WideningArithmeticTests.setUp
    checked = fixtures.WideningArithmeticTests.checked
    engine = fixtures.WideningArithmeticTests.engine
    snapshot = staticmethod(fixtures.WideningArithmeticTests.snapshot)

    def test_400_mixed_source_destination_constant_position_cases(self):
        for source in BOUNDS:
            for dest in BOUNDS:
                if source == dest or not {source,dest} & fixtures.WIDE:continue
                for value in (-1,0,127,2147483647):
                    for args in (f'Source,{value}',f'{value},Source'):
                        with self.subTest(source=source,dest=dest,args=args):
                            e=self.engine([f'ADD({args},Results[1]);'],source=source,dest=dest,value=3)
                            allowed=source in fixtures.DESTINATIONS[dest] and BOUNDS[dest][0] <= value <= BOUNDS[dest][1]
                            self.assertEqual(not e.blockers,allowed)
                            if allowed:
                                if dest=='DINT' and value==2147483647:
                                    with self.assertRaisesRegex(ModelError,'overflow'):e.step()
                                else:e.step();self.assertEqual(e.memory.read('Results'),[None,3+value,None])

    def test_five_binary_operations_keep_operand_order_and_signed_results(self):
        cases=[('ADD',-4,-4),('SUB',-10,10),('MUL',-21,-21),('DIV',-2,0),('MOD',-1,3)]
        for op,right,left in cases:
            for args,result in [('Source,3',right),('3,Source',left)]:
                e=self.checked([f'{op}({args},Results[1]);'],source='DINT',value=-7)
                with patch('logixlab.scalar_math.real',side_effect=AssertionError('Integer constant used REAL')):e.step()
                self.assertEqual(e.memory.read('Results'),[None,result,None])

    def test_exact_radix_boundaries_unsigned_and_unary_legacy_forms(self):
        cases=[('ADD(Source,-2147483648,Results[1]);','UDINT','LINT',4294967295,2147483647),
               ('ADD(Source,16#7FFF_FFFF,Results[1]);','DINT','LINT',3,2147483650),
               ('MUL(Source,2147483647,Results[1]);','UDINT','LINT',4294967295,9223372030412324865),
               ('ADD(Source,1,Results[1]);','USINT','UINT',255,256),
               ('DIV(-2147483648,Source,Results[1]);','USINT','LINT',3,-715827882),
               ('MOD(-2147483648,Source,Results[1]);','USINT','LINT',3,-2),
               ('MUL(Source,65537,Results[1]);','UINT','UDINT',65535,4294967295),
               ('NEG(-2147483648,Results[1]);','DINT','LINT',3,2147483648),
               ('ABS(-2147483648,Results[1]);','DINT','LINT',3,2147483648),
               ('ADD(Source,1,Results[1]);','LINT','LINT',9007199254740993,9007199254740994)]
        for text,source,dest,value,result in cases:
            e=self.checked([text],source=source,dest=dest,value=value);e.step();self.assertEqual(e.memory.read('Results')[1],result)

    def test_false_prescan_and_actual_index_are_lazy(self):
        e=self.checked(['XIC(StartPB)ADD(Inputs[Index],1,Results[Index]);'],source='DINT')
        e.memory.write('Index',999);e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('StartPB',True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Index',1);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[1]',7);e.step();self.assertEqual(e.memory.read('Results'),[None,8,None])

    def test_zero_constant_does_not_skip_unknown_tags(self):
        for text in ('MUL(0,Inputs[0],Results[1]);','MUL(Inputs[0],0,Results[1]);','DIV(0,Inputs[0],Results[1]);','MOD(0,Inputs[0],Results[1]);'):
            e=self.checked([text],source='DINT');before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
            self.assertEqual(self.snapshot(e),before)

    def test_zero_divisors_overflow_underflow_and_late_faults_roll_back(self):
        cases=[('DIV(Source,0,Results[1]);','DINT','LINT',7,'zero'),
               ('MOD(Source,0,Results[1]);','DINT','LINT',7,'zero'),
               ('MUL(Source,65538,Results[1]);','UINT','UDINT',65535,'overflow'),
               ('SUB(0,Source,Results[1]);','UINT','UDINT',7,'overflow')]
        for text,source,dest,value,error in cases:
            e=self.checked(['MOV(99,SpeedCommand);',text],source=source,dest=dest,value=value);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,error):e.step()
            self.assertEqual(self.snapshot(e),before)
        e=self.checked(['ADD(Source,1,Results[0]);','MUL(Source,2,Results[1]);','DIV(Source,0,Results[2]);'],source='DINT');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_udt_alias_full_write_and_sibling_guards(self):
        def fields(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            for name,dtype in [('Value','LINT'),('Guard','DINT')]:E.SubElement(members,'Member',Name=name,DataType=dtype,Dimension='0')
            tags=root.find('./Controller/Tags');tag=E.SubElement(tags,'Tag',Name='Packet1',DataType='Packet',TagType='Base')
            record=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(record,'DataValueMember',Name='Guard',DataType='DINT',Value='987')
            E.SubElement(tags,'Tag',Name='AliasValue',DataType='LINT',TagType='Alias',AliasFor='Packet1.Value')
        e=self.checked(['ADD(Source,1,AliasValue);','SUB(100,AliasValue,AliasValue);'],source='DINT',mutate=fields)
        e.step();self.assertEqual(e.memory.read('Packet1'),{'Value':92,'Guard':987})

    @staticmethod
    def aoi_logic(root):
        import test_aoi_queues as queues
        fixtures.WideningArithmeticTests.aoi_logic(root)
        queues.logic(root,['ADD(Value,1,Buffer[Index])SUB(100,Value,Stack[0])MUL(Value,2,Stack[1]);'])
        queues.logic(root,['AFI()ADD(Value,1,Buffer[Index])MUL(Value,2,Stack[Index]);'],name='EnableInFalse')

    def test_aoi_inputs_inout_unknowns_false_indices_and_binding_recovery(self):
        import test_aoi_queues as queues
        f=queues.AOIQueueTests();f.setUp();self.addCleanup(f.doCleanups);e=f.checked(self.aoi_logic);e.step()
        self.assertEqual(e.memory.read('BufferA[1]'),12);self.assertEqual(e.memory.read('BufferB[2]'),23)
        self.assertEqual(e.memory.read('DriverA.Stack')[:2],[89,22]);self.assertEqual(e.memory.read('DriverB.Stack')[:2],[78,44])
        e.memory.write('EnabledB',False);e.memory.write('IndexB',999);e.step()
        e.memory.write('EnabledB',True);e.memory.write('ValueA',100);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'outside bounds'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('IndexB',2);e.step();self.assertEqual(e.memory.read('BufferA[1]'),101)
        self.assertEqual(e.memory.read('DriverA.Stack')[:2],[0,200]);self.assertEqual(e.memory.read('DriverA.Stack[3]'),777)

    def test_unsupported_literals_types_permissions_and_old_targets_stay_blocked(self):
        for source,dest,constant in [('DINT','LINT','2147483648'),('DINT','LINT','16#FFFF_FFFF'),
                                     ('DINT','LINT','TRUE'),('USINT','UINT','-1'),
                                     ('DINT','ULINT','1'),('LINT','DINT','1')]:
            with self.subTest(source=source,dest=dest,constant=constant):
                self.assertTrue(self.engine([f'AFI()ADD(Source,{constant},Results[0]);'],source=source,dest=dest).blockers)
        for constant in ('1.0','1L','1U'):
            with self.subTest(constant=constant):
                e = self.checked([f'ADD(Source,{constant},Results[0]);'],source='DINT',dest='LINT',value=3)
                e.step()
                self.assertEqual(e.memory.read('Results[0]'),4)
        for text in ('ADD(Inputs,1,Results[0]);','ADD(Source,1,Results);','ADD(StartPB,1,Results[0]);','ADD(Missing,1,Results[0]);'):
            self.assertTrue(self.engine(['AFI()'+text],source='DINT').blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()ADD(Source,1,Results[0]);'],source='DINT',mutate=constant).blockers)
        for processor,revision in [('1756-L75','35'),('1756-L85E','34')]:
            def old(root):root.find('Controller').set('ProcessorType',processor);root.find('Controller').set('MajorRev',revision)
            self.assertTrue(self.engine(['ADD(Source,1,Results[0]);'],source='DINT',mutate=old).blockers)
        report=self.checked().report()['scalar_math']['widening_arithmetic'];self.assertIn('signed DINT',report['constants']);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
