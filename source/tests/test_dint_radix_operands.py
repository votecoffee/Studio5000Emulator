"""Full unsuffixed DINT radix words are signed only in selected scalar consumers."""
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_numeric_storage as fixtures
import test_typed_integer_operands as typed
from logixlab import integer_math
from logixlab.model import Project,literal
from logixlab.runtime import Engine

WORDS=['16#FFFF_FFFF','8#37777777777','2#'+'1'*32]


class DintRadixTests(unittest.TestCase):
    setUp=fixtures.NumericStorageTests.setUp
    checked=fixtures.NumericStorageTests.checked
    snapshot=staticmethod(typed.TypedIntegerOperandTests.snapshot)
    fault=typed.TypedIntegerOperandTests.fault

    def engine(self,rungs=None,**kwargs):
        kwargs.setdefault('source','DINT');kwargs.setdefault('dest','DINT')
        return fixtures.NumericStorageTests.engine(self,rungs,**kwargs)

    def test_all_seven_arithmetic_forms_and_three_radices_keep_signed_dint_values(self):
        for word in WORDS:
            for name,args,want in [('ADD',f'{word},1',0),('SUB',f'{word},2',-3),('MUL',f'{word},3',-3),
                                   ('DIV',f'{word},2',0),('MOD',f'{word},2',-1),('NEG',word,1),('ABS',word,1)]:
                e=self.checked([f'{name}({args},Results[1]);']);e.step()
                self.assertEqual(e.memory.read('Results'),[None,want,None],(name,word))
        for name,want in [('DIV',-3),('MOD',-1)]:
            e=self.checked([f'{name}(16#FFFFFFF9,2,Results[1]);']);e.step();self.assertEqual(e.memory.read('Results[1]'),want)

    def test_relations_both_positions_and_constant_only_normal_or_reversed_limits(self):
        for name,left,right in [('EQU',False,False),('NEQ',True,True),('LES',True,False),
                                ('LEQ',True,False),('GRT',False,True),('GEQ',False,True)]:
            for args,want in [('16#FFFFFFFF,0',left),('0,16#FFFFFFFF',right)]:
                e=self.checked([f'{name}({args})OTE(RunLatch);']);e.step();self.assertEqual(e.memory.read('RunLatch'),want)
        for args,want in [('16#80000000,-1,16#7FFFFFFF',True),('16#FFFFFFFF,16#80000000,16#FFFFFFF0',True),
                          ('16#80000000,16#7FFFFFFF,16#FFFFFFFF',False)]:
            e=self.checked([f'LIM({args})OTE(RunLatch);']);e.step();self.assertEqual(e.memory.read('RunLatch'),want)

    def test_compatible_typed_radix_and_lint_values_remain_exact_above_binary64(self):
        e=self.checked(['ADD(Source,16#FFFFFFFF,Results[1]);','GRT(Results[1],16#80000000)OTE(RunLatch);'],source='LINT',dest='LINT',value=9007199254740993)
        e.step();self.assertEqual(e.memory.read('Results[1]'),9007199254740992);self.assertTrue(e.memory.read('RunLatch'))
        e=self.checked(['ADD(16#FFFFFFFFFFFFFFFFL,16#FFFFFFFF,Results[1]);'],source='LINT',dest='LINT')
        e.step();self.assertEqual(e.memory.read('Results[1]'),-2)
        self.assertTrue(self.engine(['AFI()ADD(Source,16#FFFFFFFF,Results[1]);'],source='ULINT',dest='ULINT').blockers)

    def test_positive_word_compatibility_and_narrow_constant_fit_remain_bounded(self):
        for source,dest in [('SINT','SINT'),('INT','INT'),('DINT','INT')]:
            e=self.checked(['ADD(Source,16#1,Results[1]);'],source=source,dest=dest);e.step()
            self.assertEqual(e.memory.read('Results[1]'),4)
        for dtype in ('SINT','INT','DINT'):
            e=self.checked(['ADD(Source,16#FFFFFFFF,Results[1]);'],source=dtype,dest=dtype);e.step()
            self.assertEqual(e.memory.read('Results[1]'),2)
        self.assertTrue(self.engine(['AFI()ADD(Source,16#FFFFFFFF,Results[1]);'],source='DINT',dest='INT').blockers)
        self.assertTrue(self.engine(['AFI()ADD(Source,16#FFFFFFFF,Results[1]);'],source='USINT',dest='USINT').blockers)

    def test_false_prescan_skips_live_indices_and_unknowns_then_establishes_a_selected_result(self):
        e=self.checked(['XIC(StartPB)ADD(Inputs[Index],16#FFFFFFFF,Results[Index]);'])
        e.memory.write('Index',99);e.step();self.assertEqual(e.memory.read('Results'),[None]*3)
        e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('Index',1);self.fault(e,'Unknown')
        e.memory.write('Inputs[1]',3);e.step();self.assertEqual(e.memory.read('Results'),[None,2,None])

    def test_invalid_words_permissions_floating_mixtures_and_profiles_block_false_calls(self):
        for token in ('16#100000000','2#2','8#8','16#GG','16#FFLU'):
            self.assertTrue(self.engine([f'AFI()ADD(Source,{token},Results[1]);']).blockers,token)
        for dtype in ('REAL','LREAL'):
            engine=self.engine(['AFI()ADD(Source,16#FFFFFFFF,Results[1]);'],source=dtype,dest=dtype)
            self.assertEqual(engine.blockers,[])
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Results"]').set('Constant','true')
        self.assertTrue(self.engine(['AFI()ADD(Source,16#FFFFFFFF,Results[1]);'],mutate=constant).blockers)
        for field,value in [('MajorRev','34'),('ProcessorType','1756-L75')]:
            def older(root):root.find('Controller').set(field,value)
            e=self.engine(['EQU(Source,16#FFFFFFFF)OTE(RunLatch);'],mutate=older,value=-1)
            if field=='MajorRev':self.assertTrue(any('Revision 34' in item for item in e.blockers))
            else:
                self.assertEqual(e.blockers,[]);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_zero_division_overflow_and_later_faults_restore_warm_values_and_progress(self):
        e=self.checked(['ADD(Source,16#FFFFFFFF,Results[0]);','DIV(16#FFFFFFF9,Mask,Results[1]);'])
        e.step();e.memory.write('Source',11);e.memory.write('Mask',0);self.fault(e,'zero')
        e.memory.write('Mask',2);e.step();self.assertEqual(e.memory.read('Results'),[10,-3,None])
        for call in ('ADD(16#80000000,-1,Results[1]);','DIV(16#80000000,16#FFFFFFFF,Results[1]);',
                     'ABS(16#80000000,Results[1]);','NEG(16#80000000,Results[1]);'):
            self.fault(self.checked(['MOV(99,SpeedCommand);',call]),'overflow')

    def test_aoi_inout_and_local_arithmetic_share_warm_rollback_and_exact_signed_constants(self):
        h=typed.TypedIntegerOperandTests();h.setUp();self.addCleanup(h.doCleanups);initial=h.aoi()
        root=E.parse(initial.project.path).getroot();changed=0
        for node in root.findall('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition/Routines/Routine[@Name="Logic"]/RLLContent/Rung/Text'):
            if '9007199254740993L,1L' in (node.text or ''):
                node.text=node.text.replace('9007199254740993L,1L','9007199254740993L,16#FFFFFFFF');changed+=1
        self.assertEqual(changed,1)
        E.ElementTree(root).write(initial.project.path,encoding='utf-8',xml_declaration=True)
        e=Engine(Project(initial.project.path));self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('BufferA[1]'),9007199254740992)
        e.memory.write('IndexA',2);e.memory.write('FaultDivisor',0);self.fault(e,'zero')
        e.memory.write('FaultDivisor',1);e.step();self.assertEqual(e.memory.read('BufferA[2]'),9007199254740992)

    def test_default_parser_bcd_sources_and_bit_masks_keep_their_existing_meanings(self):
        self.assertEqual(literal('16#FFFFFFFF'),4294967295)
        self.assertEqual(literal('-16#FFFFFFFF'),-4294967295)
        e=self.checked(['AND(Source,16#FFFFFFFF,Results[1]);'],source='LINT',dest='LINT',value=1<<32)
        e.step();self.assertEqual(e.memory.read('Results[1]'),0)
        self.assertEqual(integer_math.read_source(e.memory,'16#FFFFFFFF','MainProgram',radix=True),4294967295)
        self.assertEqual(integer_math.read_source(e.memory,'16#FFFFFFFF','MainProgram',radix=True,signed_dint=True),-1)

    def test_public_example_is_dormant_then_runs_all_signed_word_operations(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[])
        e.step();self.assertEqual(e.memory.read('DintRadixSelected'),[101,None,999])
        e.memory.write('DintRadixIndex',1);e.memory.write('DintRadixEnabled',True);e.step()
        for name,want in [('Sum',6),('Difference',-8),('Product',-14),('Quotient',-3),('Remainder',-1),('Negative',1),('Absolute',2),('Wide',9007199254740992)]:
            self.assertEqual(e.memory.read('DintRadix'+name),want)
        self.assertEqual(e.memory.read('DintRadixSelected'),[101,-1,999])
        for name in ('Equal','Less','Limit','Wrapped'):self.assertTrue(e.memory.read('DintRadix'+name))
        report=e.report()['scalar_math']['signed_dint_radix'];self.assertEqual(report['bits'],32);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
