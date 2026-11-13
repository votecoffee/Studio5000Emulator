"""Typed integer sources across REAL-result math and REAL-tag comparisons."""
import itertools
import math
import struct
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_real_destination_math as arithmetic
import test_mixed_real_comparisons as comparisons
import test_file_bcd as snapshots
from logixlab.model import Project, literal
from logixlab.real_math import real
from logixlab.runtime import Engine

KINDS=(('LINT','1L'),('UDINT','1u'),('ULINT','1Ul'))
BINARY={'ADD':2.0,'SUB':0.0,'MUL':1.0,'DIV':1.0,'MOD':0.0,'XPY':1.0}
UNARY={'NEG':-1.0,'ABS':1.0,'SQR':1.0,'LN':0.0,'LOG':0.0,'DEG':57.295780181884766,
       'RAD':0.01745329238474369,'SIN':0.8414709568023682,'COS':0.5403022766113281,
       'TAN':1.5574077367782593,'ASN':1.5707963705062866,'ACS':0.0,'ATN':0.7853981852531433}
RELATIONS=('EQU','NEQ','LES','LEQ','GRT','GEQ')
ORDER={0:(False,True,True,True,False,False),1:(True,False,False,True,False,True),2:(False,True,False,False,True,True)}
BAD=['9223372036854775808L','-9223372036854775809L','4294967296U','-1U','18446744073709551616UL','-1UL','1LU','1_000L','16#100000000U','1.0UL','1e3U','(1L)','1L+1L','TRUE']


class RealIntegerLiteralTests(unittest.TestCase):
    setUp=arithmetic.RealDestinationMathTests.setUp
    engine=arithmetic.RealDestinationMathTests.engine
    checked=arithmetic.RealDestinationMathTests.checked
    snapshot=staticmethod(snapshots.FileBcdTests.snapshot)
    fault=snapshots.FileBcdTests.fault

    def comparison(self,rungs=None,*,checked=True,**options):
        e=comparisons.MixedRealComparisonTests.engine(self,rungs,**options)
        if checked:self.assertEqual(e.blockers,[])
        return e

    def test_all_nineteen_math_forms_and_three_integer_suffixes(self):
        for name,(_,token) in itertools.product({**BINARY,**UNARY},KINDS):
            args=token+','+token if name in BINARY else token
            e=self.checked([name+'('+args+',Results[1]);']);e.step()
            self.assertEqual(e.memory.read('Results'),[None,({**BINARY,**UNARY})[name],None],(name,token))

    def test_typed_math_literals_match_their_declared_source_tags(self):
        for (source,token),name in itertools.product(KINDS,{**BINARY,**UNARY}):
            tags='Source,Source' if name in BINARY else 'Source';constants=token+','+token if name in BINARY else token
            e=self.checked([name+'('+tags+',Results[0]);',name+'('+constants+',Results[1]);'],source=source,value=1);e.step()
            self.assertEqual(e.memory.read('Results[0]'),e.memory.read('Results[1]'))
            self.assertEqual(e.memory.read('Source'),1)

    def test_both_binary_operand_positions_keep_real_calculation(self):
        expected={'ADD':(4.0,4.0),'SUB':(2.0,-2.0),'MUL':(3.0,3.0),'DIV':(3.0,0.3333333432674408),'MOD':(0.0,1.0),'XPY':(3.0,1.0)}
        for name,(_,token),position in itertools.product(expected,KINDS,range(2)):
            args='Source,'+token if position==0 else token+',Source'
            e=self.checked([name+'('+args+',Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),expected[name][position])

    def test_integer_source_precision_precedes_real_math_and_result_rounding(self):
        for call,want in [('ADD(16777217U,1L,Results[1]);',16777216.0),('SQR(16777217U,Results[1]);',4096.0),
                          ('MOD(18446744073709551615UL,3UL,Results[1]);',1.0),('DIV(3L,2U,Results[1]);',1.5),
                          ('ADD(4294967295U,0L,Results[1]);',4294967296.0),('NEG(-9223372036854775808L,Results[1]);',float(1<<63))]:
            e=self.checked([call]);e.step();self.assertEqual(e.memory.read('Results[1]'),want)
        e=self.checked(['SQR(16777217U,Results[1]);'],dest='LREAL');e.step();self.assertEqual(e.memory.read('Results[1]'),math.sqrt(16777217))

    def test_suffix_case_sign_leading_zeroes_and_negative_zero(self):
        for token in ('0001l','+1L','1UL','1ul','1uL'):
            e=self.checked(['ADD('+token+',1U,Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),2.0)
        e=self.checked(['NEG(0UL,Results[1]);']);e.step();self.assertEqual(struct.pack('<f',e.memory.read('Results[1]')),struct.pack('<f',-0.0))

    def test_six_relations_typed_thresholds_and_both_operand_orders(self):
        for name,(_,token),position,value in itertools.product(RELATIONS,KINDS,range(2),range(3)):
            args='Source,'+token if position==0 else token+',Source'
            e=self.comparison([name+'('+args+')OTE(RunLatch);'],values=(value,1,1));e.step()
            self.assertIs(e.memory.read('RunLatch'),ORDER[value if position==0 else 2-value][RELATIONS.index(name)])

    def test_limits_accept_all_constant_positions_and_reversed_endpoints(self):
        for (_,token),position in itertools.product(KINDS,range(3)):
            args=['Source','Mask','Dest'];args[position]=token
            e=self.comparison(['LIM('+','.join(args)+')OTE(RunLatch);'],source='REAL',other='REAL',high='REAL',values=(1,1,1));e.step();self.assertTrue(e.memory.read('RunLatch'))
        for value,want in [(-1,True),(0,True),(1,False),(2,True),(3,True)]:
            e=self.comparison(['LIM(2UL,Source,0L)OTE(RunLatch);'],values=(value,1,1));e.step();self.assertIs(e.memory.read('RunLatch'),want)

    def test_real_threshold_rounding_and_lreal_comparison_priority(self):
        for call,want in [('EQU(Source,16777217U)',True),('LIM(16777216L,Source,16777217UL)',True),
                          ('EQU(Source,16777217.0L)',False),('LES(Source,16777217.0L)',True)]:
            e=self.comparison([call+'OTE(RunLatch);'],values=(16777216,1,1));e.step();self.assertIs(e.memory.read('RunLatch'),want)
        e=self.comparison(['EQU(Source,18446744073709551615UL)OTE(RunLatch);'],values=(float(1<<64),1,1));e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_false_math_skips_live_indices_and_full_writes_establish_unknowns(self):
        e=self.checked(['XIC(StartPB)ADD(1L,Inputs[Index],Results[Index]);']);e.memory.write('Index',999);e.step()
        e.memory.write('StartPB',True);self.fault(e,'outside bounds');e.memory.write('Index',1);self.fault(e,'Unknown')
        e.memory.write('Inputs[1]',2);e.step();self.assertEqual(e.memory.read('Results'),[None,3.0,None])

    def test_false_comparisons_clear_coils_and_skip_unknown_values(self):
        e=self.comparison(['XIC(StartPB)EQU(Source,1UL)OTE(RunLatch);'],values=(1,1,1));e.memory.values['source']=None;e.memory.write('RunLatch',True);e.step();self.assertFalse(e.memory.read('RunLatch'))
        e.memory.write('StartPB',True);self.fault(e,'Unknown');e.memory.write('Source',1);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_zero_products_and_zero_width_limits_still_consume_sources(self):
        e=self.checked(['MUL(Inputs[1],0UL,Results[1]);']);self.fault(e,'Unknown')
        e=self.comparison(['LIM(1L,Source,1UL)OTE(RunLatch);'],values=(1,1,1));e.memory.values['source']=None;self.fault(e,'Unknown')

    def test_domains_ranges_and_later_faults_roll_back_the_advance(self):
        for call,pattern in [('DIV(1L,0UL,Results[1]);','zero'),('MOD(1U,0L,Results[1]);','zero'),
                             ('XPY(-1L,0.5,Results[1]);','finite'),('LN(0UL,Results[1]);','finite'),
                             ('XPY(18446744073709551615UL,3L,Results[1]);','finite')]:
            e=self.checked(['XIC(StartPB)'+call]);e.step();e.memory.write('StartPB',True);self.fault(e,pattern)
        e=self.checked(['ADD(1L,1U,Results[1]);','DIV(1,Index,SpeedCommand);']);self.fault(e,'zero')

    def test_alias_members_and_overlap_keep_canonical_storage(self):
        def fields(root):
            c=root.find('Controller');m=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Class='User'),'Members')
            E.SubElement(m,'Member',Name='Value',DataType='REAL',Dimension='0');E.SubElement(m,'Member',Name='Guard',DataType='DINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='DINT',Value='777');E.SubElement(c.find('Tags'),'Tag',Name='AliasValue',DataType='REAL',TagType='Alias',AliasFor='Packet1.Value')
        e=self.checked(['ADD(1L,1U,AliasValue);','MUL(AliasValue,3UL,AliasValue);','EQU(AliasValue,6U)OTE(RunLatch);'],mutate=fields);e.step()
        self.assertEqual((e.memory.read('Packet1.Value'),e.memory.read('Packet1.Guard')),(6.0,777));self.assertTrue(e.memory.read('RunLatch'))

    def aoi(self):
        helper=arithmetic.RealDestinationMathTests();helper.setUp();self.addCleanup(helper.doCleanups);old=helper.aoi();root=E.parse(old.project.path).getroot()
        import test_aoi_queues as queues
        definition=root.find('.//AddOnInstructionDefinition')
        for name in ('LiteralComparedInOut','LiteralComparedLocal'):E.SubElement(definition.find('LocalTags'),'LocalTag',Name=name,DataType='BOOL',Radix='Decimal',ExternalAccess='Read/Write')
        queues.logic(root,['ADD(Value,1U,Buffer[Index]);','SQR(16777217UL,Stack[1]);','GRT(Buffer[Index],0L)OTE(LiteralComparedInOut);','EQU(Stack[1],4096UL)OTE(LiteralComparedLocal);'])
        queues.logic(root,['AFI()ADD(1L,1U,Buffer[Index]);'],name='EnableInFalse')
        E.ElementTree(root).write(old.project.path,encoding='utf8',xml_declaration=True);e=Engine(Project(old.project.path));self.assertEqual(e.blockers,[]);return e

    def test_warm_aoi_copied_integer_real_inout_local_and_comparison_rollback(self):
        e=self.aoi();e.memory.write('ValueA',16777217);e.step();self.assertEqual(e.memory.read('BufferA[1]'),16777216.0);self.assertEqual(e.memory.read('DriverA.Stack[1]'),4096.0)
        self.assertTrue(e.memory.read('DriverA.LiteralComparedInOut'));self.assertTrue(e.memory.read('DriverA.LiteralComparedLocal'))
        e.memory.write('IndexA',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero');e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),16777216.0)
        e.memory.write('EnabledA',False);e.memory.write('IndexA',999);e.step()

    def test_typed_ranges_grammar_and_excluded_source_shapes_remain_structural(self):
        for token in BAD:
            self.assertTrue(self.engine(['AFI()ADD(Source,'+token+',Results[1]);']).blockers,token)
            self.assertTrue(self.comparison(['AFI()EQU(Source,'+token+')OTE(RunLatch);'],checked=False).blockers,token)
        for token in ('1.0UL','1e309L','Inputs','TRUE'):
            self.assertTrue(self.engine(['AFI()SQR('+token+',Results[1]);']).blockers,token)

    def test_other_results_integer_only_comparisons_and_profiles_do_not_widen(self):
        for dest in ('SINT','INT','DINT','LINT'):
            self.assertTrue(self.engine(['AFI()'+('ADD(1UL,1UL,Results[1]);' if dest=='LINT' else 'ADD(1L,1U,Results[1]);')],dest=dest).blockers,dest)
        for call in ('EQU(1L,1UL)','LIM(0L,1U,2UL)','MEQ(Source,1.0L,Source)'):
            self.assertTrue(self.comparison([call+'OTE(RunLatch);'],source='DINT',checked=False).blockers,call)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            change=lambda root:root.find('Controller').set(key,value)
            self.assertTrue(self.engine(['AFI()ADD(1L,1U,Results[1]);'],mutate=change).blockers)
            self.assertTrue(self.comparison(['AFI()EQU(Source,1UL)OTE(RunLatch);'],mutate=change,checked=False).blockers)
        self.assertEqual(literal('16#FFFFFFFF'),4294967295)

    def test_permissions_and_reports_expose_selected_scope(self):
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()ADD(1L,1U,Results[1]);'],mutate=constant).blockers)
        report=self.checked().report();self.assertIn('L/U/UL',report['scalar_math']['real_arithmetic']['constants']);self.assertIn('L/U/UL',report['real_math']['real_destination']['constants'])
        self.assertIn('L/U/UL',report['numeric_comparisons']['real_ordering']['constants']);self.assertFalse(report['numeric_comparisons']['real_ordering']['native_runtime_parity'])

    def test_sample_precision_unknowns_ranges_and_atomic_retry(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('RealIntSelected'),[None,None,903.25])
        e.memory.write('RealIntEnabled',True);e.step()
        for name,value in [('RealIntSum',16777216.0),('RealIntRoot',4096.0),('RealIntRemainder',1.0),('RealIntDivide',1.5),('RealIntPower',8.0)]:self.assertEqual(e.memory.read(name),value)
        self.assertTrue(e.memory.read('RealIntEqual'));self.assertTrue(e.memory.read('RealIntLimit'));self.assertEqual(e.memory.read('RealIntSelected'),[4294967296.0,None,903.25])
        e.memory.write('RealIntRangeFault',True);self.fault(e,'finite');e.memory.write('RealIntRangeFault',False);e.step()
        e.memory.write('RealIntIndex',1);e.memory.write('RealIntLateDivisor',0);self.fault(e,'zero');e.memory.write('RealIntLateDivisor',1);e.step();self.assertEqual(e.memory.read('RealIntSelected'),[4294967296.0]*2+[903.25])
        e.memory.write('RealIntEnabled',False);e.memory.write('RealIntIndex',999);e.step()


if __name__=='__main__':unittest.main()
