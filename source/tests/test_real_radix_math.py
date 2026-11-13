"""Declared radix words round to float32 only in selected REAL ladder profiles."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_real_integer_literals as fixtures
from logixlab.model import ModelError, Project, literal
from logixlab.real_math import real
from logixlab.runtime import Engine


class RealRadixMathTests(unittest.TestCase):
    setUp = fixtures.RealIntegerLiteralTests.setUp
    engine = fixtures.RealIntegerLiteralTests.engine
    checked = fixtures.RealIntegerLiteralTests.checked
    comparison = fixtures.RealIntegerLiteralTests.comparison
    snapshot = staticmethod(fixtures.RealIntegerLiteralTests.snapshot)
    fault = fixtures.RealIntegerLiteralTests.fault

    def test_nineteen_math_forms_three_bases_and_four_declared_word_types(self):
        expected = {**fixtures.BINARY, **fixtures.UNARY}
        for name, base, suffix in itertools.product(expected, (2,8,16), ('','L','U','UL')):
            word = f'{base}#1{suffix}'; args = word+','+word if name in fixtures.BINARY else word
            e = self.checked([f'{name}({args},Results[1]);']); e.step()
            self.assertEqual(e.memory.read('Results'), [None, expected[name], None], (name,word))

    def test_six_relations_all_word_types_and_both_positions(self):
        for name, base, suffix, position, value in itertools.product(fixtures.RELATIONS, (2,8,16), ('','L','U','UL'), range(2), range(3)):
            word = f'{base}#1{suffix}'; args = 'Source,'+word if position == 0 else word+',Source'
            e = self.comparison([name+'('+args+')OTE(RunLatch);'], values=(value,1,1)); e.step()
            self.assertIs(e.memory.read('RunLatch'), fixtures.ORDER[value if position == 0 else 2-value][fixtures.RELATIONS.index(name)])

    def test_sign_width_grouping_and_float32_rounding_precede_calculation(self):
        for word, expected in [('16#FFFFFFFF',-1.0), ('8#37777777777',-1.0), ('2#'+'1'*32,-1.0),
                ('16#FFFFFFFFL',4294967296.0), ('16#FFFFFFFFFFFFFFFFL',-1.0),
                ('16#FFFFFFFFFFFFFFFFUL',float(1<<64)), ('16#8000000000000000L',-float(1<<63)),
                ('16#0000 FFFFl',65535.0), ('2#1_010uL',10.0)]:
            e = self.checked([f'ADD({word},0.0,Results[1]);']); e.step(); self.assertEqual(e.memory.read('Results[1]'),expected,word)
        for call, expected in [('SUB(16#1000001U,16777216.0,Results[1]);',0.0),
                ('SQR(16#1000001U,Results[1]);',4096.0), ('MOD(16#FFFFFFFFFFFFFFFFUL,3UL,Results[1]);',1.0)]:
            e = self.checked([call]); e.step(); self.assertEqual(e.memory.read('Results[1]'),expected)

    def test_lreal_priority_and_exact_integer_only_paths_are_preserved(self):
        e = self.checked(['SUB(16#1000001U,16777216.0L,Results[1]);']); e.step(); self.assertEqual(e.memory.read('Results[1]'),1.0)
        e = self.checked(['SQR(16#1000001U,Results[1]);'],dest='LREAL'); e.step(); self.assertGreater(e.memory.read('Results[1]'),4096.0)
        e = self.comparison(['EQU(Source,16#1000001U)OTE(RunLatch);'], values=(16777217,1,1)); e.step(); self.assertTrue(e.memory.read('RunLatch'))
        e = self.comparison(['EQU(Source,16777217.0L)OTE(RunLatch);'], values=(16777217,1,1)); e.step(); self.assertFalse(e.memory.read('RunLatch'))
        e = self.checked(['SUB(16#1000001U,16#1000000U,Results[1]);'],dest='UDINT'); e.step(); self.assertEqual(e.memory.read('Results[1]'),1)

    def test_wide_integer_destinations_convert_once_after_real_math(self):
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT'):
            for call in ('DIV(16#3U,2.0,Results[1]);','XPY(16#4U,0.5,Results[1]);'):
                e = self.checked([call],dest=dtype); e.step(); self.assertEqual(e.memory.read('Results[1]'),2)
        e = self.checked(['ADD(16#FFFFFF0000000000UL,0.0,Results[1]);'],dest='ULINT'); e.step()
        self.assertEqual(e.memory.read('Results[1]'),(1<<64)-(1<<40))
        e = self.checked(['ADD(16#FFFFFFFFFFFFFFFFUL,0.0,Results[1]);'],dest='ULINT'); self.fault(e,'overflow')

    def test_lim_all_positions_normal_reversed_and_collapsed_bounds(self):
        for base, suffix, position in itertools.product((2,8,16), ('','L','U','UL'), range(3)):
            args = ['Source','Mask','Dest']; args[position] = f'{base}#1{suffix}'
            e = self.comparison(['LIM('+','.join(args)+')OTE(RunLatch);'],source='REAL',other='REAL',high='REAL',values=(1,1,1)); e.step(); self.assertTrue(e.memory.read('RunLatch'))
        for value, expected in [(-2,True),(-1,True),(0,False),(1,True),(2,True)]:
            e = self.comparison(['LIM(16#1U,Source,8#37777777777)OTE(RunLatch);'],values=(value,1,1)); e.step(); self.assertIs(e.memory.read('RunLatch'),expected)
        e = self.comparison(['LIM(16#1000001U,Source,16#1000000UL)OTE(RunLatch);'],values=(16777216,1,1)); e.step(); self.assertTrue(e.memory.read('RunLatch'))

    def test_false_prescan_skip_indices_and_unknown_then_full_write_establishes_value(self):
        e = self.checked(['XIC(StartPB)ADD(16#1U,Inputs[Index],Results[Index]);'])
        e.memory.write('Index',99); e.step(); e.memory.write('StartPB',True); self.fault(e,'outside bounds')
        e.memory.write('Index',1); self.fault(e,'Unknown'); e.memory.write('Inputs[1]',2); e.step()
        self.assertEqual(e.memory.read('Results'),[None,3.0,None])

    def test_zero_product_and_decisive_limits_still_read_every_required_source(self):
        e = self.checked(['MUL(16#0UL,Inputs[1],Results[1]);']); self.fault(e,'Unknown')
        e = self.comparison(['LIM(16#1U,Source,16#0UL)OTE(RunLatch);']); e.memory.values['source']=None; self.fault(e,'Unknown')

    def test_domains_nonfinite_results_and_later_fault_restore_warm_state(self):
        for call, error in [('DIV(16#1L,16#0U,Results[1]);','zero'), ('LN(16#FFFFFFFFFFFFFFFFL,Results[1]);','finite'),
                ('XPY(16#FFFFFFFFFFFFFFFFUL,3UL,Results[1]);','finite')]:
            e = self.checked(['XIC(StartPB)'+call]); e.step(); e.memory.write('StartPB',True); self.fault(e,error)
        e = self.checked(['ADD(16#1U,Source,Results[1]);','DIV(1,Index,SpeedCommand);'],source='REAL')
        self.fault(e,'zero'); e.memory.write('Index',1); e.step(); self.assertEqual(e.memory.read('Results[1]'),4.0)

    def test_structural_guards_profiles_permissions_and_default_helpers_stay_scoped(self):
        for word in ('16#100000000','16#100000000U','16#10000000000000000UL','2#2UL','8#8L','16#FF_L','16#FF L','-16#1L','(16#1L)','16#1L+1L'):
            self.assertTrue(self.engine([f'AFI()ADD({word},Source,Results[1]);']).blockers,word)
            self.assertTrue(self.comparison([f'AFI()EQU(Source,{word})OTE(RunLatch);'],checked=False).blockers,word)
        for call in ('ADD(Inputs,16#1U,Results[1]);','LN(TRUE,Results[1]);'):
            self.assertTrue(self.engine(['AFI()'+call]).blockers,call)
        for dtype in ('SINT','INT','DINT'):
            self.assertTrue(self.engine(['AFI()SQR(16#1UL,Results[1]);'],dest=dtype).blockers)
        def readonly(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()ADD(16#1U,Source,Results[1]);'],mutate=readonly).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()ADD(16#1U,Source,Results[1]);'],mutate=lambda root:root.find('Controller').set(key,value)).blockers)
        e = self.checked(); from logixlab.numeric_storage import real_math_source
        with self.assertRaises(ModelError):real_math_source(e.memory,'16#FFFFFFFF','MainProgram')
        self.assertEqual(literal('16#FFFFFFFF'),4294967295)

    def test_alias_member_reads_and_overlapping_math_preserve_neighbors(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Value','Guard'):E.SubElement(members,'Member',Name=name,DataType='REAL',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='REAL',Value='777');E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='REAL',TagType='Alias',AliasFor='Packet1.Value')
        e = self.checked(['ADD(16#1U,2#1L,AliasValue);','MUL(AliasValue,8#3UL,AliasValue);','EQU(AliasValue,16#6U)OTE(RunLatch);'],mutate=fields)
        e.step(); self.assertEqual((e.memory.read('Packet1.Value'),e.memory.read('Packet1.Guard')),(6.0,777.0));self.assertTrue(e.memory.read('RunLatch'))

    def test_warm_aoi_copied_inputs_inout_locals_and_false_paths_are_atomic(self):
        h=fixtures.RealIntegerLiteralTests();h.setUp();self.addCleanup(h.doCleanups);old=h.aoi();root=E.parse(old.project.path).getroot()
        for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
            text.text=text.text.replace('1U,','16#1U,').replace('16777217UL,','16#1000001UL,').replace(',0L)',',16#0L)').replace(',4096UL)',',16#1000UL)').replace('1L,1U,','2#1L,16#1U,')
        E.ElementTree(root).write(old.project.path,encoding='utf8',xml_declaration=True);e=Engine(Project(old.project.path));self.assertEqual(e.blockers,[])
        e.memory.write('ValueA',16777217);e.step();self.assertEqual(e.memory.read('BufferA[1]'),16777216.0);self.assertEqual(e.memory.read('DriverA.Stack[1]'),4096.0)
        self.assertTrue(e.memory.read('DriverA.LiteralComparedInOut'));self.assertTrue(e.memory.read('DriverA.LiteralComparedLocal'))
        e.memory.write('IndexA',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),16777216.0)
        e.memory.write('EnabledA',False);e.memory.write('IndexA',99);e.step()

    def test_public_sample_values_report_and_late_recovery(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('RealRadixEnabled',True);e.memory.write('RealRadixIndex',1);e.step()
        expected={'Sum':4.0,'Unsigned':float(1<<64),'Signed':-1.0,'Loss':0.0,'Root':4096.0,'Power':2,'Quotient':1.5,'Selected':[101.0,2.0,999.0],'Match':True,'Rounded':True,'Range':True}
        for name,value in expected.items():self.assertEqual(e.memory.read('RealRadix'+name),value,name)
        e.memory.write('RealRadixSource',5);e.memory.write('RealRadixLateDivisor',0);self.fault(e,'zero');e.memory.write('RealRadixLateDivisor',1);e.step()
        self.assertEqual(e.memory.read('RealRadixSum'),6.0);self.assertEqual(e.memory.read('RealRadixSelected'),[101.0,4.0,999.0]);self.assertFalse(e.memory.read('RealRadixMatch'));self.assertFalse(e.memory.read('RealRadixRange'))
        for row in (e.report()['scalar_math']['real_arithmetic'],e.report()['real_math']['real_destination'],e.report()['numeric_comparisons']['real_ordering']):
            self.assertEqual(row['radix_sources']['bases'],[2,8,16]);self.assertFalse(row['radix_sources']['native_runtime_parity'])


if __name__ == '__main__':unittest.main()
