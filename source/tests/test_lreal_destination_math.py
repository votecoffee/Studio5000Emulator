"""LREAL result selection across numeric sources and bounded integer constants."""
import itertools
import math
import struct
import unittest
from xml.etree import ElementTree as E

import test_lreal_unary_sources as unary
import test_lreal_advanced as advanced
import test_mixed_lreal_math as mixed
from logixlab.model import Project
from logixlab.runtime import Engine

EXPECTED={'ADD':5.0,'SUB':1.0,'MUL':6.0,'DIV':1.5,'MOD':1.0,'XPY':9.0}


class LrealDestinationMathTests(unittest.TestCase):
    setUp=unary.LrealUnarySourceTests.setUp
    checked=unary.LrealUnarySourceTests.checked
    snapshot=staticmethod(unary.LrealUnarySourceTests.snapshot)
    fault=unary.LrealUnarySourceTests.fault

    def engine(self,rungs=None,**options):
        defaults=dict(source='DINT',other='DINT',value=3);defaults.update(options)
        return unary.LrealUnarySourceTests.engine(self,rungs or ['ADD(Source,Mask,Results[1]);'],**defaults)

    def test_all_hundred_numeric_pairs_and_six_binary_instructions(self):
        for source,other,name in itertools.product(mixed.TYPES,mixed.TYPES,EXPECTED):
            with self.subTest(source=source,other=other,name=name):
                e=self.checked([f'{name}(Source,Mask,Results[1]);'],source=source,other=other)
                e.memory.write('Mask',2);before=(e.memory.read('Source'),e.memory.read('Mask'));e.step()
                self.assertEqual(e.memory.read('Results'),[None,EXPECTED[name],None])
                self.assertEqual((e.memory.read('Source'),e.memory.read('Mask')),before)

    def test_neg_abs_all_numeric_types_and_bounded_constant_only_calls(self):
        for source,name in itertools.product(mixed.TYPES,('NEG','ABS')):
            e=self.checked([f'{name}(Source,Results[1]);'],source=source);e.step()
            self.assertEqual(e.memory.read('Results[1]'),-3.0 if name=='NEG' else 3.0)
        for name,args,want in [('ADD','3,2',5.0),('SUB','3,2',1.0),('MUL','3,2',6.0),
                               ('DIV','3,2',1.5),('MOD','-7,3',-1.0),('XPY','3,2',9.0),
                               ('NEG','3',-3.0),('ABS','-3',3.0)]:
            e=self.checked([f'{name}({args},Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),want)

    def test_numeric_tags_and_constants_in_both_binary_positions(self):
        want={'ADD':(5.0,5.0),'SUB':(1.0,-1.0),'MUL':(6.0,6.0),
              'DIV':(1.5,2/3),'MOD':(1.0,2.0),'XPY':(9.0,8.0)}
        for dtype,name,position in itertools.product(mixed.TYPES,want,range(2)):
            args='Source,2' if position==0 else '2,Source'
            e=self.checked([f'{name}({args},Results[1]);'],source=dtype);e.step()
            self.assertEqual(e.memory.read('Results[1]'),want[name][position])

    def test_destination_selects_fractional_division_and_avoids_integer_overflow(self):
        e=self.checked(['DIV(Source,Mask,Results[1]);']);e.memory.write('Mask',2);e.step();self.assertEqual(e.memory.read('Results[1]'),1.5)
        e=self.checked(['ADD(Source,1,Results[1]);'],value=2147483647);e.step();self.assertEqual(e.memory.read('Results[1]'),2147483648.0)
        for call,want in [('ADD(2147483647,1,Results[1]);',2147483648.0),
                          ('NEG(-2147483648,Results[1]);',2147483648.0),
                          ('ABS(-2147483648,Results[1]);',2147483648.0),
                          ('XPY(2,-3,Results[1]);',0.125)]:
            e=self.checked([call]);e.step();self.assertEqual(e.memory.read('Results[1]'),want)
        e=self.checked(['NEG(0,Results[1]);']);e.step()
        self.assertEqual(struct.pack('<d',e.memory.read('Results[1]')),struct.pack('<d',-0.0))

    def test_real_storage_precision_and_wide_rounding_precede_calculation(self):
        e=self.checked(['ADD(Source,1,Results[1]);'],value=16777217);e.step();self.assertEqual(e.memory.read('Results[1]'),16777218.0)
        e=self.checked(['ADD(Source,1,Results[1]);'],source='REAL',value=16777217);e.step();self.assertEqual(e.memory.read('Results[1]'),16777217.0)
        e=self.checked(['MOD(Source,Mask,Results[1]);'],source='ULINT',other='LINT',value=2**64-1);e.step()
        self.assertEqual(e.memory.read('Results[1]'),1.0);self.assertEqual(e.memory.read('Source'),2**64-1)
        e=self.checked(['NEG(Source,Results[1]);'],source='ULINT',value=2**64-1);e.step();self.assertEqual(e.memory.read('Results[1]'),-float(2**64))
        e=self.checked(['MUL(Source,Mask,Results[1]);'],source='REAL',other='REAL',value=3.4e38);e.memory.write('Mask',3.4e38);e.step()
        self.assertTrue(math.isfinite(e.memory.read('Results[1]')));self.assertGreater(e.memory.read('Results[1]'),1e76)

    def test_integer_only_comparison_remains_exact_above_binary64_precision(self):
        e=self.checked(['GRT(Source,Mask)OTE(RunLatch);'],source='LINT',other='LINT',value=9007199254740993)
        e.memory.write('Mask',9007199254740992);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertIn('at least one LREAL',e.report()['numeric_comparisons']['lreal_ordering']['operands'])
        self.assertIn('no LREAL source',e.report()['scalar_math']['lreal_arithmetic']['operands'])

    def test_false_prescan_skip_indices_and_all_true_sources_remain_required(self):
        for name in EXPECTED:
            e=self.checked([f'XIC(StartPB){name}(Inputs[Index],2,Results[Index]);'])
            e.memory.write('Index',99);e.enter_run();e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
            e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown')
        for call in ('MUL(0,Inputs[0],Results[1]);','XPY(1,Inputs[0],Results[1]);','XPY(Inputs[0],0,Results[1]);','NEG(Inputs[0],Results[1]);'):
            e=self.checked([call]);self.fault(e,'Unknown')

    def test_zero_divisors_power_domains_and_late_fault_restore_advance(self):
        for call,options in [('DIV(3,0,Results[1]);',{}),('MOD(3,0,Results[1]);',{}),
                              ('XPY(0,-1,Results[1]);',{}),('XPY(Source,Mask,Results[1]);',{'value':-2,'other':'REAL'}),
                              ('XPY(2147483647,2147483647,Results[1]);',{})]:
            e=self.checked(['MOV(99,SpeedCommand);',call],**options)
            if options:e.memory.write('Mask',0.5)
            self.fault(e,'zero|finite LREAL')
        e=self.checked(['ADD(Source,2,Results[1]);','XPY(Source,2,Results[2]);','DIV(1,Index,SpeedCommand);'])
        self.fault(e,'zero');e.memory.write('Index',1);e.step();self.assertEqual(e.memory.read('Results'),[None,5.0,9.0])

    def test_alias_udt_unknown_writes_and_overlapping_results_preserve_guards(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='DoublePacket',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Value',DataType='LREAL',Dimension='0');E.SubElement(members,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet',DataType='DoublePacket',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='DoublePacket')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777');E.SubElement(c.find('Tags'),'Tag',Name='Selected',DataType='LREAL',TagType='Alias',AliasFor='Packet.Value')
        e=self.checked(['ADD(Source,2,Selected);','XPY(Selected,2,Selected);'],mutate=fields);e.step()
        self.assertEqual((e.memory.read('Packet.Value'),e.memory.read('Packet.Guard')),(25.0,777))

    def aoi(self):
        helper=advanced.LrealAdvancedTests();helper.setUp();self.addCleanup(helper.doCleanups)
        original=helper.aoi();root=E.parse(original.project.path).getroot()
        advanced.queues.logic(root,['ADD(Value,1,Buffer[Index]);','XPY(Value,2,Stack[1]);'])
        E.ElementTree(root).write(original.project.path,encoding='utf8',xml_declaration=True)
        return Engine(Project(original.project.path))

    def test_warm_aoi_dint_only_sources_and_lreal_outputs_rollback(self):
        e=self.aoi();self.assertEqual(e.blockers,[]);e.memory.write('ValueA',2);e.memory.write('ValueB',3);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('BufferB[2]')),(3.0,4.0))
        e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step()
        self.assertEqual((e.memory.read('DriverA.Stack[1]'),e.memory.read('DriverB.Stack[1]')),(4.0,9.0))

    def test_excluded_constants_types_destinations_and_profiles_remain_guarded(self):
        for name in EXPECTED:
            for token in ('TRUE','1e309L','1e39','2147483648','1LU','Inputs','RunLatch'):
                self.assertTrue(self.engine([f'AFI(){name}(Source,{token},Dest);']).blockers,(name,token))
        for call in ('ADD(Source,1,RunLatch);','XPY(Source,2,RunLatch);'):
            self.assertTrue(self.engine([call],source='LREAL').blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['ADD(1,2,Results[1]);'],mutate=constant).blockers)
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(mutate=old).blockers)

    def test_reports_distinguish_result_selected_math_from_ordering_and_unary(self):
        report=self.checked().report();a=report['scalar_math']['lreal_arithmetic'];p=report['real_math']['lreal']['power']
        self.assertIn('constant-only',a['selection_by_destination']);self.assertIn('no LREAL source',p['operands'])
        self.assertFalse(a['native_runtime_parity']);self.assertFalse(p['native_runtime_parity'])
