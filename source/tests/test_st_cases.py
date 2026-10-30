"""Numeric CASE selection follows DINT or finite float32 REAL evaluation."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_structured as fixtures
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine


class NumericCaseTests(unittest.TestCase):
    setUp=fixtures.StructuredTests.setUp
    text=fixtures.StructuredTests.text

    def engine(self,source,value=0.0,dtype='REAL',mutate=None):
        tag=self.root.find('./Controller/Tags/Tag[@Name="Selector"]');tag.set('DataType',dtype)
        data=tag.find('Data/DataValue');data.set('DataType',dtype);data.set('Value',str(value))
        if mutate:mutate(self.root)
        return fixtures.StructuredTests.engine(self,source)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_real_single_value_and_else(self):
        e=self.checked('CASE Selector OF 2.5: State:=10; ELSE State:=-1; END_CASE;',2.5);e.step();self.assertEqual(e.memory.read('State'),10)
        e.memory.write('Selector',2.75);e.step();self.assertEqual(e.memory.read('State'),-1)

    def test_real_range_includes_both_endpoints(self):
        e=self.checked('CASE Selector OF -1.25..2.5: State:=10; ELSE State:=-1; END_CASE;')
        for value,expected in ((-1.25,10),(2.5,10),(0,10),(-1.2501,-1),(2.5001,-1)):
            e.memory.write('Selector',value);e.step();self.assertEqual(e.memory.read('State'),expected,value)

    def test_lists_ranges_exponents_and_leading_decimal_points(self):
        e=self.checked('CASE Selector OF -.5, + 2.5E-1, 1e1..2E+1: State:=7; ELSE State:=-1; END_CASE;')
        for value,expected in ((-.5,7),(.25,7),(10,7),(15,7),(20,7),(9.99,-1)):
            e.memory.write('Selector',value);e.step();self.assertEqual(e.memory.read('State'),expected)

    def test_later_real_labels_are_detected_after_branch_bodies(self):
        e=self.checked('CASE Selector OF 0: State:=0; 1.5: State:=1; .25.. .5: State:=2; -2e0: State:=3; ELSE State:=-1; END_CASE;',-2)
        for value,expected in ((1.5,1),(.3,2),(-2,3)):
            e.memory.write('Selector',value);e.step();self.assertEqual(e.memory.read('State'),expected)

    def test_overlap_and_duplicates_use_first_branch_without_fallthrough(self):
        e=self.checked('CASE Selector OF 0.0..2.0: State:=State+1; 1.0,1.0..3.0: State:=99; ELSE State:=-1; END_CASE;',1)
        e.step();self.assertEqual(e.memory.read('State'),1)

    def test_empty_first_match_does_not_fall_through(self):
        e=self.checked('State:=7; CASE Selector OF 1.0: 1.0: State:=99; ELSE State:=-1; END_CASE;',1)
        e.step();self.assertEqual(e.memory.read('State'),7)

    def test_no_match_without_else_retains_prior_value(self):
        e=self.checked('CASE Selector OF 0.1..0.2: State:=7; END_CASE;',2.5)
        e.memory.write('State',88);e.step();self.assertEqual(e.memory.read('State'),88)

    def test_selector_is_evaluated_once_before_selected_body_changes_it(self):
        e=self.checked('CASE Selector OF 1.0: Selector:=2.0; State:=10; 2.0: State:=20; END_CASE;',1)
        e.step();self.assertEqual(e.memory.read('State'),10);self.assertEqual(e.memory.read('Selector'),2.0)
        e.step();self.assertEqual(e.memory.read('State'),20)

    def test_real_expression_and_integer_expression_keep_separate_profiles(self):
        for selector,label,expected in (('5/2','2',7),('5/2','2.5',-1),('5.0/2','2.5',7)):
            source=f'CASE {selector} OF {label}: State:=7; ELSE State:=-1; END_CASE;'
            if selector=='5/2' and label=='2.5':self.assertTrue(self.engine(source).blockers)
            else:
                e=self.checked(source);e.step();self.assertEqual(e.memory.read('State'),expected)

    def test_real_labels_round_to_float32_like_selector(self):
        e=self.checked('CASE Selector OF 0.1: State:=1; 0.2..0.3: State:=2; ELSE State:=-1; END_CASE;',.1)
        self.assertNotEqual(e.memory.read('Selector'),.1);e.step();self.assertEqual(e.memory.read('State'),1)
        e.memory.write('Selector',.3);e.step();self.assertEqual(e.memory.read('State'),2)

    def test_rounded_equal_labels_choose_first_and_no_epsilon_is_added(self):
        e=self.checked('CASE Selector OF 16777217.0: State:=1; 16777216.0: State:=2; ELSE State:=-1; END_CASE;',16777216)
        e.step();self.assertEqual(e.memory.read('State'),1)
        e=self.checked('CASE Selector OF 0.1: State:=1; ELSE State:=-1; END_CASE;',.10000001)
        e.step();self.assertEqual(e.memory.read('State'),-1)

    def test_finite_large_small_and_signed_zero_real_labels(self):
        for value,label in ((3e38,'3e38'),(-3e38,'-3e38'),(1e-40,'1e-40'),(-0.0,'0.0')):
            e=self.checked('CASE Selector OF '+label+': State:=7; ELSE State:=-1; END_CASE;',value)
            e.step();self.assertEqual(e.memory.read('State'),7)

    def test_integer_immediates_in_real_context_use_float32_not_dint_bounds(self):
        e=self.checked('CASE Selector OF 3000000000: State:=7; ELSE State:=-1; END_CASE;',3000000000)
        e.step();self.assertEqual(e.memory.read('State'),7)
        e=self.checked('CASE Selector OF +16#FF: State:=9; ELSE State:=-1; END_CASE;',255)
        e.step();self.assertEqual(e.memory.read('State'),9)

    def test_narrow_integer_case_remains_exact_with_signed_radix_ranges(self):
        for dtype,value in (('SINT',-128),('INT',-32768),('DINT',-2147483648)):
            e=self.checked('CASE Selector OF -2147483648..-1: State:=7; 0,+16#FF: State:=8; ELSE State:=-1; END_CASE;',value,dtype)
            e.step();self.assertEqual(e.memory.read('State'),7)
        e=self.checked('CASE Selector OF 2147483647: State:=9; END_CASE;',2147483647,'DINT')
        e.step();self.assertEqual(e.memory.read('State'),9)

    def test_real_labels_do_not_promote_integer_selector(self):
        for label in ('1.0','1e0','1..2.0'):
            self.assertTrue(self.engine('CASE Selector OF '+label+': State:=1; END_CASE;',1,'DINT').blockers)

    def test_invalid_out_of_range_and_descending_labels_block_unreached_branches(self):
        for dtype,label in (('REAL','3.5e38'),('REAL','1e999'),('REAL','2.00000001..2.0'),('DINT','2147483648'),('DINT','-2147483649')):
            source='IF FALSE THEN CASE Selector OF '+label+': State:=1; END_CASE; END_IF;'
            self.assertTrue(self.engine(source,0,dtype).blockers,(dtype,label))

    def test_malformed_dynamic_and_non_numeric_labels_block(self):
        for label in ('Step','TRUE',"'1'",'1+2','1 2','1 .2','1e 2','1e','1.2.3','1,,2','1..','..1','1..2..3','1UL','nan','inf'):
            self.assertTrue(self.engine('CASE Selector OF '+label+': State:=1; END_CASE;').blockers,label)

    def test_non_numeric_or_wide_selector_and_typed_labels_remain_blocked(self):
        for source in ('CASE TRUE OF 1: State:=1; END_CASE;',"CASE 'a' OF 1: State:=1; END_CASE;",
                       'CASE 1L OF 1: State:=1; END_CASE;','CASE Selector OF 1L: State:=1; END_CASE;'):
            self.assertTrue(self.engine(source).blockers,source)

    def test_nested_case_and_nearest_loop_exit(self):
        e=self.checked('State:=0; FOR Index:=0 TO 3 DO CASE Selector OF 1.0: CASE Index OF 1: EXIT; ELSE State:=State+1; END_CASE; ELSE State:=99; END_CASE; END_FOR;',1)
        e.step();self.assertEqual(e.memory.read('State'),1);self.assertEqual(e.memory.read('Index'),1)

    def test_skipped_faulting_bodies_do_not_evaluate(self):
        e=self.checked('CASE Selector OF 1.0: State:=1/0; ELSE State:=7; END_CASE;',2)
        e.step();self.assertEqual(e.memory.read('State'),7)

    def test_faulting_selector_or_selected_body_rolls_back_scan(self):
        for source in ('State:=7; CASE Selector/0.0 OF 1.0: Sum:=1; END_CASE;',
                       'State:=7; CASE Selector OF 1.0: Sum:=1/0; END_CASE;'):
            e=self.checked(source,1);before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
            with self.assertRaisesRegex(ModelError,'zero'):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule);self.assertEqual((e.scan_count,e.time_ms),(0,0))

    def test_unknown_selector_faults_instead_of_taking_else(self):
        e=self.checked('State:=7; CASE Selector OF 1.0: Sum:=1; ELSE Sum:=2; END_CASE;')
        e.memory.values['selector']=None;before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before)

    def test_nonretentive_case_assignment_prescan_remains_lexical(self):
        e=self.checked('CASE Selector OF 1.0: ClearedOnRun [:=] 7; END_CASE;',2)
        self.assertEqual(e.memory.read('ClearedOnRun'),0);e.step();self.assertEqual(e.memory.read('ClearedOnRun'),0)

    def test_real_aoi_parameter_binding_selects_branch(self):
        def mutate(root):
            parameter=root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition/Parameters/Parameter[@Name="Step"]')
            parameter.set('DataType','REAL');parameter.find('DefaultData/DataValue').set('DataType','REAL')
            root.find('./Controller/Tags/Tag[@Name="Accumulator"]/Data/Structure/DataValueMember[@Name="Step"]').set('DataType','REAL')
            content=root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition/Routines/Routine[@Name="Logic"]/STContent');content.clear()
            E.SubElement(content,'Line',Number='0').text='CASE Step OF 1.0..2.0: Total:=42; ELSE Total:=-42; END_CASE;'
        e=self.checked('LabSTAccumulator(Accumulator,Selector,AOITotal);',1.5,mutate=mutate)
        e.step();self.assertEqual(e.memory.read('AOITotal'),42);e.memory.write('Selector',3.0);e.step();self.assertEqual(e.memory.read('AOITotal'),-42)

    def test_case_report_exposes_profile_without_claiming_native_parity(self):
        report=self.checked('CASE Selector OF 1.0: State:=1; END_CASE;').report()['structured_text']
        self.assertIn('CASE (integer/REAL)',report['supported']);self.assertIn('REAL',report['case']['numeric_types'])
        self.assertFalse(report['case']['native_runtime_parity'])

    def test_bundled_text_lab_case_fault_rolls_back_prior_work_and_recovers(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/TextLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('RealCaseResult'),20);self.assertEqual(e.memory.read('RealCaseVisits'),1)
        e.memory.write('RealCaseInput',1.0);e.step();self.assertEqual(e.memory.read('RealCaseResult'),10)
        e.memory.write('RealCaseDivisor',0);before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        self.assertEqual((e.scan_count,e.time_ms),(2,20))
        e.memory.write('RealCaseDivisor',1);e.step();self.assertEqual(e.memory.read('RealCaseVisits'),3)
        self.assertEqual(e.memory.read('ScanTotal'),3);self.assertEqual(e.memory.read('AOITotal'),6)


if __name__=='__main__':unittest.main()
