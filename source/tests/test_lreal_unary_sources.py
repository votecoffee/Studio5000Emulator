"""Numeric tag and bounded integer sources for unary ladder LREAL results."""
import decimal
import itertools
import math
import struct
import unittest
from xml.etree import ElementTree as E

import test_lreal_advanced as advanced
import test_lreal_math as basic
import test_mixed_lreal_math as mixed
from logixlab.model import Project
from logixlab.runtime import Engine

CASES={'SQR':(4,2.0),'LN':(1,0.0),'LOG':(100,2.0),'DEG':(1,57.29577951308232),
       'RAD':(90,math.pi/2),'SIN':(1,0.8414709848078965),'COS':(0,1.0),
       'TAN':(0,0.0),'ASN':(1,math.pi/2),'ACS':(0,math.pi/2),'ATN':(1,math.pi/4)}


class LrealUnarySourceTests(unittest.TestCase):
    setUp=mixed.MixedLrealMathTests.setUp
    checked=mixed.MixedLrealMathTests.checked
    snapshot=staticmethod(mixed.MixedLrealMathTests.snapshot)
    fault=mixed.MixedLrealMathTests.fault

    def engine(self,rungs=None,**options):
        defaults=dict(source='DINT',value=4,dest='LREAL');defaults.update(options)
        return basic.LrealMathTests.engine(self,rungs or ['SQR(Source,Results[1]);'],dtype=defaults.pop('other','DINT'),**defaults)

    def test_all_eleven_functions_and_ten_tag_types_establish_unknown_results(self):
        for name,dtype in itertools.product(CASES,mixed.TYPES):
            value,want=CASES[name]
            with self.subTest(name=name,dtype=dtype):
                e=self.checked([f'{name}(Source,Results[1])OTE(RunLatch);'],source=dtype,value=value);e.step()
                self.assertAlmostEqual(e.memory.read('Results[1]'),want,places=14)
                self.assertEqual(e.memory.read('Results')[::2],[None,None]);self.assertTrue(e.memory.read('RunLatch'))
                self.assertEqual(e.memory.read('Source'),value)

    def test_all_eleven_functions_accept_bounded_integer_constants(self):
        for name,(value,want) in CASES.items():
            e=self.checked([f'{name}({value},Results[1]);']);e.step()
            self.assertAlmostEqual(e.memory.read('Results[1]'),want,places=14)
        for token,value in [('2147483647',2147483647),('-2147483648',2147483648),
                            ('16#7FFF_FFFF',2147483647),('-16#8000_0000',2147483648)]:
            with decimal.localcontext() as ctx:
                ctx.prec=80;want=float(decimal.Decimal(value).sqrt())
            e=self.checked([f'SQR({token},Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),want)

    def test_dint_precision_avoids_real_intermediate_but_real_keeps_stored_precision(self):
        with decimal.localcontext() as ctx:
            ctx.prec=80;want=float(decimal.Decimal(16777217).sqrt())
        e=self.checked(value=16777217);e.step();self.assertEqual(e.memory.read('Results[1]'),want)
        e=self.checked(source='REAL',value=16777217);e.step();self.assertEqual((e.memory.read('Source'),e.memory.read('Results[1]')),(16777216.0,4096.0))
        e=self.checked(['SQR(16777217,Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),want)

    def test_large_unsigned_and_signed_sources_convert_numerically(self):
        e=self.checked(source='ULINT',value=2**64-1);e.step()
        self.assertEqual(e.memory.read('Results[1]'),float(2**32));self.assertEqual(e.memory.read('Source'),2**64-1)
        e=self.checked(source='LINT',value=-16);e.step();self.assertEqual(e.memory.read('Results[1]'),4.0)
        e=self.checked(['SIN(Source,Results[1]);'],source='LINT',value=-1);e.step();self.assertEqual(e.memory.read('Results[1]'),-0.8414709848078965)

    def test_lreal_precision_signed_zero_and_subnormals_remain_unchanged(self):
        e=self.checked(['LN(Source,Results[1]);'],source='LREAL',value=1.0000000000000002);e.step()
        self.assertEqual(e.memory.read('Results[1]'),2.2204460492503128e-16)
        for name in ('SIN','TAN','ASN','ATN','DEG','RAD'):
            e=self.checked([f'{name}(Source,Results[1]);'],source='REAL',value=-0.0);e.step()
            self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),struct.pack('<d',-0.0))
        e=self.checked(['SIN(Source,Results[1]);'],source='LREAL',value=5e-324);e.step();self.assertEqual(e.memory.read('Results[1]'),5e-324)

    def test_all_functions_false_prescan_and_reached_unknown_sources(self):
        for name in CASES:
            e=self.checked([f'XIC(StartPB){name}(Inputs[Index],Results[Index]);'])
            e.memory.write('Index',99);e.enter_run();e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
            e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown')
            e.memory.write('Inputs[1]',CASES[name][0]);e.step();self.assertAlmostEqual(e.memory.read('Results[1]'),CASES[name][1],places=14)

    def test_literal_domains_are_lazy_but_required_true_calls_fault(self):
        for name,value in [('LN',0),('LOG',-1),('ASN',2),('ACS',-2)]:
            e=self.checked([f'XIC(StartPB){name}({value},Results[1]);']);e.enter_run();e.step()
            e.memory.write('StartPB',True);self.fault(e,'finite LREAL')

    def test_tag_domains_overflow_and_later_fault_restore_advance_and_timing(self):
        for name,dtype,value in [('LN','USINT',0),('LOG','DINT',-1),('ASN','UINT',2),('ACS','REAL',-2),('DEG','LREAL',1e308)]:
            e=self.checked(['MOV(99,SpeedCommand);',f'{name}(Source,Results[1]);'],source=dtype,value=value);self.fault(e,'finite LREAL')
        e=self.checked(['SQR(Source,Results[1]);','DIV(1,Index,SpeedCommand);'],value=9)
        self.fault(e,'zero');e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Results[1]'),3.0)

    def test_alias_udt_unknown_member_and_overlapping_results_preserve_guards(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='UnaryPacket',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='LREAL',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='UnaryPacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='UnaryPacket')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='LREAL',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['SQR(Source,Selected);','SQR(Selected,Selected);'],value=16,mutate=fields);e.step()
        self.assertEqual((e.memory.read('Packet.Value'),e.memory.read('Packet.Guard')),(2.0,777))
        e=self.checked(['SQR(Source,Source);'],source='LREAL',value=16);e.step();self.assertEqual(e.memory.read('Source'),4.0)

    def aoi(self):
        helper=advanced.LrealAdvancedTests();helper.setUp();self.addCleanup(helper.doCleanups)
        original=helper.aoi();root=E.parse(original.project.path).getroot()
        advanced.queues.logic(root,['SQR(Value,Buffer[Index]);','RAD(Value,Stack[1]);'])
        E.ElementTree(root).write(original.project.path,encoding='utf8',xml_declaration=True)
        return Engine(Project(original.project.path))

    def test_warm_aoi_copied_dint_sources_and_lreal_bindings_rollback(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.memory.write('ValueA',9);e.memory.write('ValueB',16);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(3.0,4.0))
        locals_before=(e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[1]'))
        e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(3.0,4.0))
        self.assertEqual((e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[1]')),locals_before)

    def test_excluded_types_literals_destinations_and_profiles_remain_structural(self):
        for name in CASES:
            for token in ('TRUE','1e309L','1e39','2147483648','-2147483649','1LU','Inputs','RunLatch'):
                self.assertTrue(self.engine([f'AFI(){name}({token},Dest);']).blockers,(name,token))
        self.assertTrue(self.engine(['SQR(Source,Dest);'],source='LREAL',dest='REAL').blockers)
        self.assertEqual(self.checked(['XPY(Source,Mask,Dest);'],source='DINT',other='REAL').blockers,[])
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['SQR(9,Results[1]);'],mutate=constant).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(mutate=old).blockers)

    def test_report_separates_unary_destination_selection_from_power_rules(self):
        data=self.checked().report()['real_math'];unary=data['lreal']['unary']
        self.assertEqual(set(unary['instructions']),set(CASES));self.assertEqual(len(unary['source_types']),10)
        self.assertIn('L/U/UL',unary['constants']);self.assertFalse(unary['native_runtime_parity'])
        self.assertIn('no LREAL source',data['lreal']['power']['operands'])
