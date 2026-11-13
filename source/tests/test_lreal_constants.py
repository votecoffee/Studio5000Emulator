"""Bounded integer literals in ladder binary64 math and direct comparisons."""
import itertools
import struct
import unittest

import test_lreal_math as basic
import test_lreal_advanced as advanced
import test_mixed_lreal_comparisons as comparisons
from logixlab.model import Project
from logixlab.runtime import Engine


class LrealConstantTests(unittest.TestCase):
    setUp=basic.LrealMathTests.setUp
    checked=basic.LrealMathTests.checked
    engine=basic.LrealMathTests.engine
    snapshot=staticmethod(basic.LrealMathTests.snapshot)
    fault=basic.LrealMathTests.fault

    def test_binary_arithmetic_both_constant_positions_and_unknown_outputs(self):
        expected={'ADD':(10.5,10.5),'SUB':(4.5,-4.5),'MUL':(22.5,22.5),
                  'DIV':(2.5,0.4),'MOD':(1.5,3.0)}
        for name,results in expected.items():
            for index,args in enumerate(('Source,3','3,Source')):
                with self.subTest(name=name,args=args):
                    e=self.checked([f'{name}({args},Results[1])OTE(RunLatch);']);e.step()
                    self.assertEqual(e.memory.read('Results'),[None,results[index],None])
                    self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Source'),7.5)

    def test_six_relations_both_positions_equal_less_greater_and_boundaries(self):
        for value,expected in [(2.0,(False,True,True,True,False,False)),
                               (3.0,(True,False,False,True,False,True)),
                               (4.0,(False,True,False,False,True,True))]:
            for name,result in zip(('EQU','NEQ','LES','LEQ','GRT','GEQ'),expected):
                for args,source in [('Source,3',value),('3,Source',6-value)]:
                    with self.subTest(value=value,name=name,args=args):
                        e=self.checked([f'{name}({args})OTE(RunLatch);'],value=source);e.step()
                        self.assertIs(e.memory.read('RunLatch'),result)

    def test_limits_constants_in_every_position_and_both_bounds(self):
        cases=[('LIM(1,Source,3)',1,True),('LIM(1,Source,3)',3,True),
               ('LIM(1,Source,3)',2,True),('LIM(1,Source,3)',4,False),
               ('LIM(3,Source,1)',2,False),('LIM(3,Source,1)',1,True),
               ('LIM(3,Source,1)',3,True),('LIM(3,Source,1)',4,True),
               ('LIM(Source,2,3)',1,True),('LIM(1,2,Source)',3,True),
               ('LIM(Source,3,Source)',3,True),('LIM(Source,2,Source)',3,False)]
        for call,value,want in cases:
            with self.subTest(call=call,value=value):
                e=self.checked([call+'OTE(RunLatch);'],value=value);e.step();self.assertIs(e.memory.read('RunLatch'),want)
        for dtype in comparisons.TYPES:
            for args in itertools.permutations(('Source','Mask','3')):
                # One actual LREAL tag still chooses binary64 alongside a numeric tag.
                e=self.checked(['LIM('+','.join(args)+')OTE(RunLatch);'],dtype=dtype,value=2)
                before=(e.memory.read('Source'),e.memory.read('Mask'));e.step()
                self.assertIs(e.memory.read('RunLatch'),args[1]!='Source')
                self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),before)

    def test_integer_boundaries_radix_and_precision_do_not_pass_through_real(self):
        for token,value in [('2147483647',2147483647),('-2147483648',-2147483648),
                            ('16#7FFF_FFFF',2147483647),('-16#8000_0000',-2147483648),
                            ('2#11',3),('8#10',8),('+1',1)]:
            e=self.checked([f'ADD(Source,{token},Results[1]);'],value=0.0);e.step()
            self.assertEqual(e.memory.read('Results[1]'),float(value))
        e=self.checked(['SUB(Source,16777217,Results[1]);','EQU(Source,16777217)OTE(RunLatch);'],value=16777217.0)
        e.step();self.assertEqual(e.memory.read('Results[1]'),0.0);self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['SUB(Source,1,Results[1]);','GRT(Source,1)OTE(RunLatch);'],value=1.0000000000000002)
        e.step();self.assertEqual(e.memory.read('Results[1]'),2**-52);self.assertTrue(e.memory.read('RunLatch'))

    def test_false_prescan_skip_invalid_indices_unknowns_and_zero_divisors(self):
        e=self.checked(['XIC(StartPB)DIV(Inputs[Index],0,Results[Index]);',
                        'XIC(StartPB)LIM(0,Inputs[Index],10)OTE(RunLatch);'])
        e.memory.write('Index',99);e.enter_run();e.step();self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);self.fault(e,'Unknown');e.memory.write('Inputs[1]',2);self.fault(e,'zero')

    def test_true_zero_products_and_limits_still_consume_unknown_tags(self):
        for text in ('MUL(0,Inputs[0],Results[1]);','MUL(Inputs[0],0,Results[1]);',
                     'LIM(0,Inputs[0],0);','LIM(Inputs[0],0,Source);',
                     'LIM(Source,0,Inputs[0]);','EQU(Inputs[0],0);'):
            e=self.checked([text]);self.fault(e,'Unknown')

    def test_zero_divisor_overflow_and_late_fault_restore_values_and_timing(self):
        for call,value,error in [('DIV(Source,0,Results[1]);',1.0,'zero'),
                                  ('MOD(Source,0,Results[1]);',1.0,'zero'),
                                  ('MUL(Source,2147483647,Results[1]);',1e308,'Nonfinite LREAL')]:
            e=self.checked(['MOV(99,SpeedCommand);',call],value=value);self.fault(e,error)
        e=self.checked(['ADD(Source,1,Results[1]);','GRT(Source,0)OTE(RunLatch);','DIV(1,Index,SpeedCommand);'])
        self.fault(e,'zero');e.memory.write('Index',1);e.step()
        self.assertEqual(e.memory.read('Results[1]'),8.5);self.assertTrue(e.memory.read('RunLatch'))

    def test_signed_zero_subnormal_remainders_and_overlapping_sources(self):
        e=self.checked(['MUL(Source,0,Results[1]);'],value=-1.0);e.step()
        self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),struct.pack('<d',-0.0))
        e=self.checked(['MOD(Source,3,Results[1]);'],value=-7.5);e.step();self.assertEqual(e.memory.read('Results[1]'),-1.5)
        e=self.checked(['GRT(Source,0)OTE(RunLatch);'],value=5e-324);e.step();self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['ADD(Source,1,Source);','SUB(Source,1,Results[1]);']);e.step()
        self.assertEqual((e.memory.read('Source'),e.memory.read('Results[1]')),(8.5,7.5))

    def test_warm_aoi_bindings_preserve_rollback(self):
        helper=comparisons.MixedLrealComparisonTests();helper.setUp();self.addCleanup(helper.doCleanups)
        base=helper.aoi();root=advanced.E.parse(base.project.path).getroot()
        advanced.queues.logic(root,['ADD(Stack[0],1,Buffer[Index]);','GRT(Buffer[Index],0)OTE(Latched);'])
        advanced.E.ElementTree(root).write(base.project.path,encoding='utf8',xml_declaration=True)
        e=Engine(Project(base.project.path));self.assertEqual(e.blockers,[]);e.step()
        before=(e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]'))
        e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),before)
        self.assertTrue(e.memory.read('DriverA.Latched'));self.assertTrue(e.memory.read('DriverB.Latched'))

    def test_alias_and_udt_member_keep_guards_and_full_unknown_writes(self):
        def fields(root):
            E=advanced.E;c=root.find('Controller')
            members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='ConstantPacket',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='LREAL',Dimension='0')
            E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='ConstantPacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='ConstantPacket')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='LREAL',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['ADD(Source,1,Selected);','GRT(Selected,8)OTE(RunLatch);'],mutate=fields)
        e.step();self.assertEqual((e.memory.read('Packet.Value'),e.memory.read('Packet.Guard')),(8.5,777))
        self.assertTrue(e.memory.read('RunLatch'))

    def test_literal_and_destination_guards_remain_structural_even_when_false(self):
        for token in ('TRUE','1e999','2147483648','-2147483649','16#1_0000_0000','18446744073709551616UL','1.0UL'):
            for call in (f'ADD(Source,{token},Dest)',f'EQU(Source,{token})',f'LIM(0,Source,{token})'):
                self.assertTrue(self.engine(['XIC(StartPB)'+call+';']).blockers,(token,call))
        for call in ('ADD(Source,1,StartPB);','ADD(Source,1,Results);','NEG(TRUE,Dest);',
                     'MEQ(Source,1,Mask);','CPT(Dest,Source+1e999);','XPY(Source,1e999,Dest);'):
            self.assertTrue(self.engine([call]).blockers,call)
        def readonly(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['ADD(Source,1,Results[1]);'],mutate=readonly).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['ADD(Source,1,Dest);'],mutate=old).blockers)

    def test_report_describes_exact_constant_promotion_and_native_boundary(self):
        report=self.checked(['ADD(Source,1,Dest);']).report()
        for item in (report['scalar_math']['lreal_arithmetic'],report['numeric_comparisons']['lreal_ordering']):
            self.assertIn('DINT',item['constants'])
            self.assertIn('finite REAL',item['constants'])
            self.assertIn('L/U/UL',item['constants'])
            self.assertFalse(item['native_runtime_parity'])
