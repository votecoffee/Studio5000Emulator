"""LREAL tag/literal selection, typed thresholds, precision and atomic recovery."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_mixed_lreal_comparisons as fixtures
import test_file_bcd as snapshots
from logixlab.model import INT_BITS, Project, literal
from logixlab.runtime import Engine

RELATIONS=('EQU','NEQ','LES','LEQ','GRT','GEQ')
TOKENS=('1','1L','1u','1Ul','1.0','1.0l')
EXPECTED={0:(False,True,True,True,False,False),1:(True,False,False,True,False,True),2:(False,True,False,False,True,True)}


class LrealComparisonLiteralTests(unittest.TestCase):
    setUp=fixtures.MixedLrealComparisonTests.setUp
    engine=fixtures.MixedLrealComparisonTests.engine
    checked=fixtures.MixedLrealComparisonTests.checked
    snapshot=staticmethod(snapshots.FileBcdTests.snapshot)
    fault=snapshots.FileBcdTests.fault

    def test_six_relations_all_constant_kinds_both_operand_positions(self):
        for name,token,position,value in itertools.product(RELATIONS,TOKENS,range(2),range(3)):
            args='Source,'+token if position==0 else token+',Source'
            e=self.checked([name+'('+args+')OTE(RunLatch);'],value=value);before=e.memory.read('Source');e.step()
            expected=EXPECTED[value if position==0 else 2-value][RELATIONS.index(name)]
            self.assertIs(e.memory.read('RunLatch'),expected,(name,token,position,value));self.assertEqual(e.memory.read('Source'),before)

    def test_floating_l_literal_selects_all_ten_tag_types(self):
        for source,name,value in itertools.product((*INT_BITS,'REAL','LREAL'),RELATIONS,range(3)):
            e=self.checked([name+'(Source,1.0L)OTE(RunLatch);'],source=source,value=value);e.step()
            self.assertIs(e.memory.read('RunLatch'),EXPECTED[value][RELATIONS.index(name)])

    def test_constant_only_relations_and_limits_select_binary64(self):
        for call,expected in [('EQU(1L,1.0L)',True),('NEQ(0.1,0.1L)',True),
                              ('LES(0.1L,0.1)',True),('LEQ(1.0L,1U)',True),
                              ('GRT(2UL,1.0L)',True),('GEQ(1.0L,1.0L)',True),
                              ('LIM(0U,0.5L,1L)',True),('LIM(1U,0.5L,0L)',False)]:
            e=self.checked([call+'OTE(RunLatch);']);e.step();self.assertIs(e.memory.read('RunLatch'),expected)

    def test_lim_accepts_typed_constants_in_all_three_positions(self):
        for token,position in itertools.product(TOKENS,range(3)):
            # Tagged LREAL operands select binary64 independently of the constant.
            args=['Source','Mask','High'];args[position]=token
            e=self.checked(['LIM('+','.join(args)+')OTE(RunLatch);'],source='LREAL',other='LREAL',high='LREAL',value=1,high_value=1)
            e.memory.write('Mask',1);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_lim_literal_selection_works_in_every_position_and_reversed_ranges(self):
        for args in ('1.0L,Mask,High','Source,1.0L,High','Source,Mask,1.0L'):
            e=self.checked(['LIM('+args+')OTE(RunLatch);'],source='DINT',other='DINT',high='DINT',value=1,high_value=1)
            e.memory.write('Mask',1);e.step();self.assertTrue(e.memory.read('RunLatch'))
        for value,expected in [(-1,True),(0,True),(1,False),(2,True),(3,True)]:
            e=self.checked(['LIM(2U,Source,0.0L)OTE(RunLatch);'],value=value);e.step();self.assertIs(e.memory.read('RunLatch'),expected)

    def test_real_default_and_explicit_lreal_have_no_tolerance(self):
        for call,source,value,want in [('EQU(Source,0.1L)','LREAL',.1,True),
                                       ('EQU(Source,0.1)','LREAL',.1,False),
                                       ('GRT(Source,0.1L)','REAL',.1,True),
                                       ('EQU(Source,0.1)','REAL',.1,True),
                                       ('GRT(Source,1.0L)','LREAL',1.0000000000000002,True)]:
            e=self.checked([call+'OTE(RunLatch);'],source=source,value=value);e.step();self.assertIs(e.memory.read('RunLatch'),want)

    def test_integer_rounding_during_lreal_promotion_keeps_integer_only_ordering_exact(self):
        for call,value,want in [('EQU(Source,9007199254740992.0L)',9007199254740993,True),
                                ('GRT(Source,9007199254740992.0L)',9007199254740993,False),
                                ('EQU(Source,9223372036854775807L)',9223372036854775807,True)]:
            e=self.checked([call+'OTE(RunLatch);'],source='LREAL' if call.endswith('5807L)') else 'LINT',value=value);e.step();self.assertIs(e.memory.read('RunLatch'),want)
        e=self.checked(['EQU(Source,Mask)OTE(RunLatch);'],source='LINT',other='LINT',value=9007199254740993);e.memory.write('Mask',9007199254740992);e.step();self.assertFalse(e.memory.read('RunLatch'))
        e=self.checked(['EQU(Source,18446744073709551615UL)OTE(RunLatch);'],value=float(1<<64));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_large_subnormal_underflow_and_signed_zero_thresholds(self):
        for call,want in [('EQU(1e308L,1e308L)',True),('GRT(5e-324L,0.0L)',True),
                          ('EQU(-0.0L,0.0L)',True),('EQU(1e-50,0.0L)',True),
                          ('GRT(1e-50L,0.0L)',True),('LIM(-0.0L,0.0L,5e-324L)',True)]:
            e=self.checked([call+'OTE(RunLatch);']);e.step();self.assertIs(e.memory.read('RunLatch'),want)

    def test_false_and_prescan_skip_unknown_values_and_bad_indirect_indices(self):
        e=self.checked(['XIC(StartPB)EQU(Inputs[Index],0.1L)OTE(RunLatch);']);e.memory.write('Index',999);e.memory.write('RunLatch',True);e.step();self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown');e.memory.write('Inputs[1]',.1);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_known_relation_and_limits_do_not_skip_other_required_unknown_inputs(self):
        for call in ('EQU(0.0L,Inputs[1])','NEQ(0.0L,Inputs[1])','LIM(1.0L,Inputs[1],1.0L)'):
            e=self.checked([call+'OTE(RunLatch);']);self.fault(e,'Unknown')

    def test_late_failure_restores_prior_coils_values_timing_and_traces(self):
        e=self.checked(['EQU(0.1L,0.1L)OTE(RunLatch);','DIV(1,Index,SpeedCommand);']);self.fault(e,'zero');e.memory.write('Index',1);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_alias_and_member_sources_remain_read_only(self):
        def fields(root):
            c=root.find('Controller');m=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            for name in ('Value','Guard'):E.SubElement(m,'Member',Name=name,DataType='LREAL',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Value',DataType='LREAL',Value='0.1');E.SubElement(obj,'DataValueMember',Name='Guard',DataType='LREAL',Value='777.25')
            E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='LREAL',TagType='Alias',AliasFor='Packet1.Value')
        e=self.checked(['EQU(AliasValue,0.1L)OTE(RunLatch);'],mutate=fields);before=e.memory.read('Packet1');e.step();self.assertTrue(e.memory.read('RunLatch'));self.assertEqual(e.memory.read('Packet1'),before)

    def aoi(self):
        f=fixtures.MixedLrealComparisonTests();f.setUp();self.addCleanup(f.doCleanups);old=f.aoi();root=E.parse(old.project.path).getroot()
        import test_aoi_queues as queues
        definition=root.find('.//AddOnInstructionDefinition');E.SubElement(definition.find('LocalTags'),'LocalTag',Name='LiteralLocalResult',DataType='BOOL',Radix='Decimal',ExternalAccess='Read/Write')
        for suffix in ('A','B'):
            root.find('./Controller/Tags/Tag[@Name="Driver'+suffix+'"]/Data/Structure/ArrayMember[@Name="Stack"]/Element[@Index="[0]"]').set('Value','0.1')
        queues.logic(root,['GRT(Value,0.5L)OTE(Latched);','LIM(-1.0L,Buffer[Index],1.0L)OTE(CompareEqual);','EQU(Stack[0],0.1L)OTE(LiteralLocalResult);'])
        queues.logic(root,['AFI()EQU(Buffer[Index],0.0L)OTE(LiteralLocalResult);'],name='EnableInFalse')
        E.ElementTree(root).write(old.project.path,encoding='utf8',xml_declaration=True);e=Engine(Project(old.project.path));self.assertEqual(e.blockers,[]);return e

    def test_warm_aoi_copied_input_inout_and_local_readers_keep_atomic_recovery(self):
        e=self.aoi();e.step();self.assertTrue(e.memory.read('DriverA.Latched'));self.assertTrue(e.memory.read('DriverA.CompareEqual'));self.assertTrue(e.memory.read('DriverA.LiteralLocalResult'))
        e.memory.write('BufferA[1]',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertFalse(e.memory.read('DriverA.CompareEqual'))
        e.memory.write('EnabledA',False);e.memory.write('IndexA',999);e.step()

    def test_malformed_out_of_range_and_unsupported_typed_forms_are_structural(self):
        bad=['9223372036854775808L','-9223372036854775809L','4294967296U','-1U','18446744073709551616UL','-1UL','1e309L','1e39','2147483648','16#FFFFFFFF','16#FFU','1LU','1_000L','LREAL#1.0','1.0UL','1e3U','(1L)','1L+1L','TRUE','Inputs']
        for token in bad:
            self.assertTrue(self.engine(['AFI()EQU(Source,'+token+')OTE(RunLatch);']).blockers,token)
            self.assertTrue(self.engine(['AFI()LIM(0.0L,'+token+',1.0L)OTE(RunLatch);']).blockers,token)

    def test_integer_only_typed_constants_meq_st_and_old_profiles_do_not_widen(self):
        for call in ('EQU(1L,1UL)','LIM(0L,1UL,2L)','MEQ(Source,1.0L,Source)'):
            self.assertTrue(self.engine([call+'OTE(RunLatch);'],source='DINT',value=1).blockers,call)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.engine(['AFI()EQU(Source,0.1L)OTE(RunLatch);'],mutate=lambda root:root.find('Controller').set(key,value)).blockers)
        self.assertEqual(literal('16#FFFFFFFF'),4294967295)

    def test_report_exposes_literal_selection_and_native_limits(self):
        row=self.checked().report()['numeric_comparisons']['lreal_ordering'];self.assertIn('floating L/l',row['selection_by_literal']);self.assertIn('finite REAL',row['constants']);self.assertFalse(row['native_runtime_parity'])

    def test_sample_thresholds_unknowns_and_rollback_retry(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step();e.memory.write('CompareLitEnabled',True);e.step()
        for name,want in [('CompareLitEqual',True),('CompareLitDefault',False),('CompareLitPromotedReal',True),('CompareLitRoundedWide',True),('CompareLitNormal',True),('CompareLitReversed',False),('CompareLitConstantOnly',True),('CompareLitSelected',True)]:self.assertIs(e.memory.read(name),want)
        e.memory.write('CompareLitIndex',1);self.fault(e,'Unknown');e.memory.write('CompareLitInputs[1]',.1);e.step();self.assertTrue(e.memory.read('CompareLitSelected'))
        e.memory.write('CompareLitValue',.2);e.memory.write('CompareLitLateDivisor',0);self.fault(e,'zero');e.memory.write('CompareLitLateDivisor',1);e.step();self.assertFalse(e.memory.read('CompareLitEqual'))
        e.memory.write('CompareLitEnabled',False);e.memory.write('CompareLitIndex',999);e.step();self.assertFalse(e.memory.read('CompareLitSelected'))


if __name__=='__main__':unittest.main()
