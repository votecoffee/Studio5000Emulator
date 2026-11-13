"""Integer-only radix operands preserve declared ranges, exact math and rollback."""
import copy
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_typed_integer_operands as fixtures
from logixlab.integer_math import typed_integer
from logixlab.model import ModelError,Project,literal
from logixlab.runtime import Engine


class RadixIntegerOperandTests(unittest.TestCase):
    setUp=fixtures.TypedIntegerOperandTests.setUp
    engine=fixtures.TypedIntegerOperandTests.engine
    checked=fixtures.TypedIntegerOperandTests.checked

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.time_ms,
                              e.scan_count,e.trace,e.scheduler_description(),e.last_timer))

    def fault(self,e,pattern):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,pattern):e.step()
        self.assertEqual(self.snapshot(e),before)

    @staticmethod
    def token(base,value,suffix):
        return f'{base}#{format(value,{2:"b",8:"o",16:"x"}[base])}{suffix}'

    def test_all_seven_arithmetic_forms_across_bases_and_declared_types(self):
        for base,(dtype,suffix) in itertools.product((2,8,16),fixtures.KINDS):
            for name,want in fixtures.BINARY.items():
                a,b=self.token(base,3,suffix),self.token(base,2,suffix)
                e=self.checked([f'{name}({a},{b},Results[1]);'],source=dtype,dest=dtype)
                e.step();self.assertEqual(e.memory.read('Results'),[None,want,None])
            for name,value,want in [('NEG',0,0),('ABS',1,1)]:
                e=self.checked([f'{name}({self.token(base,value,suffix)},Results[1]);'],source=dtype,dest=dtype)
                e.step();self.assertEqual(e.memory.read('Results[1]'),want)

    def test_all_relations_and_normal_reversed_limits_use_exact_integer_values(self):
        for base,(dtype,suffix) in itertools.product((2,8,16),fixtures.KINDS):
            one,three,five=(self.token(base,value,suffix) for value in (1,3,5))
            for name,want in [('EQU',False),('NEQ',True),('LES',False),('LEQ',False),('GRT',True),('GEQ',True)]:
                e=self.checked([f'{name}({three},{one})OTE(RunLatch);'],source=dtype,dest=dtype)
                e.step();self.assertIs(e.memory.read('RunLatch'),want)
            for low,value,high,want in [(one,three,five,True),(five,three,one,False),(five,five,one,True)]:
                e=self.checked([f'LIM({low},{value},{high})OTE(RunLatch);'],source=dtype,dest=dtype)
                e.step();self.assertIs(e.memory.read('RunLatch'),want)

    def test_full_width_signed_and_unsigned_numeric_values_are_not_mask_patterns(self):
        for call,dest,want in [('ADD(16#0020000000000001L,1L,Results[1]);','LINT',9007199254740994),
                               ('DIV(16#FFFFFFFFFFFFFFFFUL,3UL,Results[1]);','ULINT',6148914691236517205),
                               ('MOD(8#1777777777777777777777UL,3UL,Results[1]);','ULINT',0),
                               ('ADD(16#FFFFFFFFL,1L,Results[1]);','LINT',4294967296),
                               ('ABS(16#FFFFFFFFFFFFFFFEL,Results[1]);','LINT',2)]:
            e=self.checked([call],dest=dest);e.step();self.assertEqual(e.memory.read('Results[1]'),want)
        for call in ['LES(16#FFFFFFFFFFFFFFFFL,0L)','GRT(16#FFFFFFFFL,4294967294U)',
                     'GRT(16#FFFFFFFFFFFFFFFFUL,9223372036854775808UL)']:
            e=self.checked([call+'OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_complete_source_ranges_block_narrowing_and_lossy_signedness_even_while_false(self):
        for call,source,dest in [('ADD(Source,16#1UL,Results[1]);','DINT','ULINT'),
                                 ('ADD(Source,16#0L,Results[1]);','UDINT','UDINT'),
                                 ('EQU(Source,16#0UL)OTE(RunLatch);','LINT','LINT'),
                                 ('GRT(Source,16#0U)OTE(RunLatch);','SINT','LINT')]:
            self.assertTrue(self.engine(['AFI()'+call],source=source,dest=dest,value=1).blockers,call)
        e=self.checked(['ADD(Source,16#1L,Results[1]);'],source='UDINT',dest='LINT',value=4294967295)
        e.step();self.assertEqual(e.memory.read('Results[1]'),4294967296)

    def test_floating_time_and_boolean_mixes_do_not_enter_the_radix_integer_profile(self):
        for source,value in [('REAL',1.0),('LREAL',1.0),('TIME',1),('BOOL',True)]:
            for call in ('ADD(Source,16#1L,Results[1]);','EQU(Source,16#1L)OTE(RunLatch);'):
                self.assertTrue(self.engine(['AFI()'+call],source=source,value=value).blockers,(source,call))
        for dest in ('REAL','LREAL','TIME','SINT'):
            self.assertTrue(self.engine(['AFI()ADD(16#1L,1L,Results[1]);'],dest=dest).blockers,dest)

    def test_invalid_and_overwide_literals_block_both_math_and_ordering(self):
        for token in ('16#100000000U','16#10000000000000000L','2#2UL','8#8L','16#FF U','16#FFLU','-16#FFL'):
            for call in (f'ADD(Source,{token},Results[1]);',f'LIM(0L,Source,{token})OTE(RunLatch);'):
                self.assertTrue(self.engine(['AFI()'+call]).blockers,(token,call))

    def test_false_paths_defer_indices_and_zero_products_require_known_sources(self):
        e=self.checked(['XIC(StartPB)MUL(Inputs[Index],16#0L,Results[Index]);'])
        e.memory.write('Index',999);e.step();e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);self.fault(e,'Unknown');e.memory.write('Inputs[1]',37);e.step()
        self.assertEqual(e.memory.read('Results'),[None,0,None])
        e=self.checked(['LIM(16#0L,Inputs[1],16#0L)OTE(RunLatch);']);self.fault(e,'Unknown')

    def test_reached_overflow_and_zero_divisors_restore_previous_writes(self):
        for call,dest,pattern in [('ADD(16#FFFFFFFFFFFFFFFFUL,1UL,Results[1]);','ULINT','overflow'),
                                  ('SUB(16#0UL,1UL,Results[1]);','ULINT','overflow'),
                                  ('ABS(16#8000000000000000L,Results[1]);','LINT','overflow'),
                                  ('NEG(16#8000000000000000L,Results[1]);','LINT','overflow'),
                                  ('DIV(16#8000000000000000L,-1L,Results[1]);','LINT','overflow'),
                                  ('DIV(1L,16#0L,Results[1]);','LINT','zero'),
                                  ('MOD(1L,2#0L,Results[1]);','LINT','zero')]:
            e=self.checked(['MOV(77,SpeedCommand);',call],dest=dest);self.fault(e,pattern)

    def test_alias_members_and_overlapping_sources_preserve_exact_values_and_neighbors(self):
        def fields(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Value','Guard'):E.SubElement(members,'Member',Name=name,DataType='LINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='LINT',Value='777')
            E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='LINT',TagType='Alias',AliasFor='Packet1.Value')
        e=self.checked(['ADD(16#0020000000000001L,0L,AliasValue);','ADD(AliasValue,16#1L,AliasValue);',
                        'GRT(AliasValue,16#0020000000000001L)OTE(RunLatch);'],mutate=fields)
        e.step();self.assertEqual((e.memory.read('Packet1.Value'),e.memory.read('Packet1.Guard')),(9007199254740994,777))
        self.assertTrue(e.memory.read('RunLatch'))

    def test_warm_aoi_integer_outputs_locals_bindings_and_late_rollback(self):
        helper=fixtures.TypedIntegerOperandTests();helper.setUp();self.addCleanup(helper.doCleanups)
        old=helper.aoi();root=E.parse(old.project.path).getroot()
        import test_aoi_queues as queues
        queues.logic(root,['ADD(16#0020000000000001L,1L,Buffer[Index]);','DIV(16#0020000000000001L,3L,Item);',
                           'ADD(Buffer[Index],2#1L,Stack[Index]);','GRT(Stack[Index],16#0020000000000002L)OTE(ExactCompared);'])
        E.ElementTree(root).write(old.project.path,encoding='utf8',xml_declaration=True)
        e=Engine(Project(old.project.path));self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual((e.memory.read('BufferA[1]'),e.memory.read('ItemA'),e.memory.read('DriverA.Stack[1]')),
                         (9007199254740994,3002399751580331,9007199254740995))
        self.assertTrue(e.memory.read('DriverA.ExactCompared'))
        e.memory.write('IndexA',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero')
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),9007199254740994)

    def test_permissions_profiles_and_unrelated_literal_consumers_do_not_expand(self):
        self.assertIsNone(typed_integer('16#FFUL'))
        with self.assertRaises(ValueError):literal('16#FFUL')
        for call in ('SWPB(16#FFUL,REVERSE,Results[1]);','CMP(Source=16#FFUL)OTE(RunLatch);','XPY(Source,16#FFUL,Results[1]);',
                     'FLL(16#FFUL,Results[1],1);','CPT(Results[1],16#FFUL);','MOV(1,Results[16#FFUL]);'):
            self.assertTrue(self.engine([call]).blockers,call)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()ADD(16#1L,1L,Results[1]);'],mutate=constant).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()ADD(16#1L,1L,Results[1]);'],mutate=lambda root:root.find('Controller').set(key,value)).blockers)

    def test_public_sample_results_reports_and_late_fault_recovery(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'))
        self.assertEqual(e.blockers,[]);e.step();e.memory.write('TypedIntEnabled',True);e.step()
        for name,want in [('TypedIntSigned',9007199254740994),('TypedIntQuotient',6148914691236517205),('TypedIntRemainder',0),
                          ('TypedIntDword',4294967295),('TypedIntDifference',-4294967295),
                          ('TypedRadixProduct',-4),('TypedRadixNegative',-2),('TypedRadixAbsolute',2)]:self.assertEqual(e.memory.read(name),want)
        self.assertTrue(e.memory.read('TypedIntExact'));self.assertTrue(e.memory.read('TypedIntLimit'))
        e.memory.write('TypedIntOverflow',True);self.fault(e,'overflow');e.memory.write('TypedIntOverflow',False)
        e.memory.write('TypedIntIndex',1);e.memory.write('TypedIntLateDivisor',0);self.fault(e,'zero')
        e.memory.write('TypedIntLateDivisor',1);e.step();self.assertEqual(e.memory.read('TypedIntSelected'),[(1<<64)-1]*2+[903])
        report=e.report()
        for profile in (report['scalar_math']['typed_integer_arithmetic'],report['numeric_comparisons']['typed_integer_ordering']):
            self.assertEqual(profile['radix_bases'],[2,8,16]);self.assertFalse(profile['native_runtime_parity'])


if __name__=='__main__':unittest.main()
