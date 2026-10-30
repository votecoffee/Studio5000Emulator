"""Wide ST exact values, declared types and transactional execution boundaries."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_integer_math as fixtures
from logixlab.model import ModelError,Project
from logixlab.runtime import Engine


class WideStructuredTests(unittest.TestCase):
    setUp=fixtures.IntegerMathTests.setUp

    def engine(self,source, dtype='LINT', a=7,b=3,dest=0,*,types=None,processor='1756-L85E',revision='35',mutate=None):
        root=E.parse(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').getroot();c=root.find('Controller')
        c.set('ProcessorType',processor);c.set('MajorRev',revision)
        for name,value,kind in zip(('WideA','WideB','WideDest','Result'),(a,b,dest,0),(*(types or (dtype,)*3),'BOOL')):
            tag=E.SubElement(c.find('Tags'),'Tag',Name=name,TagType='Base',DataType=kind)
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=kind,Value=str(value))
        routine=c.find('./Programs/Program/Routines/Routine');routine.remove(routine.find('RLLContent'));routine.set('Type','ST')
        content=E.SubElement(routine,'STContent')
        for i,line in enumerate(source.split('\n')):E.SubElement(content,'Line',Number=str(i)).text=line
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'wide-st.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path))

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_basic_arithmetic_all_declared_wide_types(self):
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT'):
            for operator,a,b,expected in (('+',200,3,203),('-',200,3,197),('*',40,6,240),('/',7,2,3),('MOD',7,3,1)):
                with self.subTest(dtype=dtype,operator=operator):
                    e=self.checked(f'WideDest:=WideA {operator} WideB;',dtype,a,b);e.step();self.assertEqual(e.memory.read('WideDest'),expected)

    def test_large_values_are_exact_above_float_and_browser_integer_ranges(self):
        for dtype in ('LINT','ULINT'):
            e=self.checked('WideDest:=WideA+WideB;',dtype,9007199254740993,2);e.step()
            self.assertEqual(e.memory.read('WideDest'),9007199254740995)
            self.assertEqual(next(row['value'] for row in e.memory.leaves() if row['name']=='WideDest'),'9007199254740995')
        e=self.checked('WideDest:=WideA+WideB;','ULINT',18446744073709551614,1);e.step()
        self.assertEqual(e.memory.read('WideDest'),18446744073709551615)

    def test_signed_quotients_and_remainders_do_not_use_float_rounding(self):
        for a,b,quotient,remainder in ((-7,3,-2,-1),(7,-3,-2,1),(-7,-3,2,-1),(-9223372036854775808,3,-3074457345618258602,-2)):
            for operator,expected in (('/',quotient),('MOD',remainder)):
                e=self.checked(f'WideDest:=WideA {operator} WideB;',a=a,b=b);e.step();self.assertEqual(e.memory.read('WideDest'),expected)
        e=self.checked('WideDest:=WideA/WideB;','ULINT',18446744073709551615,3);e.step()
        self.assertEqual(e.memory.read('WideDest'),6148914691236517205)

    def test_exact_relations_do_not_collapse_adjacent_large_values(self):
        for dtype in ('LINT','ULINT'):
            for operator,expected in (('=',False),('<>',True),('<',True),('<=',True),('>',False),('>=',False)):
                e=self.checked(f'Result:=WideA {operator} WideB;',dtype,9007199254740992,9007199254740993);e.step()
                self.assertEqual(e.memory.read('Result'),expected)

    def test_literal_assignment_uses_the_declared_destination_context(self):
        for dtype in ('LINT','USINT','UINT','UDINT','ULINT'):
            e=self.checked('WideDest:=1+2*3;',dtype);e.step();self.assertEqual(e.memory.read('WideDest'),7)
        e=self.checked('WideDest:=-2147483648;');e.step();self.assertEqual(e.memory.read('WideDest'),-2147483648)

    def test_signed_negate_absolute_and_unary_plus(self):
        for expr,expected in (('-WideA',9),('ABS(WideA)',9),('+WideA',-9)):
            e=self.checked('WideDest:='+expr+';',a=-9);e.step();self.assertEqual(e.memory.read('WideDest'),expected)

    def test_bitwise_not_and_binary_operators_use_declared_width(self):
        for dtype,bits in (('LINT',64),('USINT',8),('UINT',16),('UDINT',32),('ULINT',64)):
            e=self.checked('WideDest:=NOT WideA;',dtype,0);e.step()
            self.assertEqual(e.memory.read('WideDest'),-1 if dtype=='LINT' else (1<<bits)-1)
            for operator,expected in (('AND',0),('OR',15),('XOR',15)):
                e=self.checked(f'WideDest:=WideA {operator} WideB;',dtype,10,5);e.step();self.assertEqual(e.memory.read('WideDest'),expected)
        e=self.checked('WideDest:=WideA XOR 1;',a=-9223372036854775808);e.step()
        self.assertEqual(e.memory.read('WideDest'),-9223372036854775807)

    def test_bool_logic_and_wide_relations_can_control_if_and_assign_bool(self):
        e=self.checked('Result:=(WideA+1=WideB) AND StartPB; IF NOT Result OR (WideA<WideB) THEN WideDest:=WideA+WideB; END_IF;',a=8,b=9)
        e.step();self.assertFalse(e.memory.read('Result'));self.assertEqual(e.memory.read('WideDest'),17)
        e.memory.write('StartPB',True);e.step();self.assertTrue(e.memory.read('Result'))

    def test_precedence_and_parentheses_follow_existing_st_grammar(self):
        for expr,expected in (('WideA+WideB*2',13),('(WideA+WideB)*2',20),('NOT WideA AND WideB',0)):
            e=self.checked('WideDest:='+expr+';',a=7,b=3);e.step();self.assertEqual(e.memory.read('WideDest'),expected)

    def test_while_and_repeat_use_wide_conditions_and_share_the_budget(self):
        e=self.checked('WideDest:=0; WHILE WideDest<WideB DO WideDest:=WideDest+1; END_WHILE; REPEAT WideDest:=WideDest-1; UNTIL WideDest=0 END_REPEAT;',b=3)
        e.step();self.assertEqual(e.memory.read('WideDest'),0)
        e=self.checked('WHILE WideA>0 DO WideDest:=WideDest+1; END_WHILE;');e.instruction_limit=20
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_skipped_branch_does_not_evaluate_division_by_zero(self):
        e=self.checked('IF StartPB THEN WideDest:=WideA/WideB; END_IF;',b=0,dest=13);e.step()
        self.assertEqual(e.memory.read('WideDest'),13)
        e.memory.write('StartPB',True);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'divide by zero'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_overflow_underflow_and_intermediate_overflow_roll_back_the_whole_advance(self):
        cases=(('LINT','WideA+WideB',9223372036854775807,1),('ULINT','WideA+WideB',18446744073709551615,1),
               ('USINT','WideA-WideB',0,1),('LINT','WideA/WideB',-9223372036854775808,-1),
               ('LINT','ABS(WideA)',-9223372036854775808,1),('LINT','(WideA+WideB)-WideB',9223372036854775807,1))
        for dtype,expr,a,b in cases:
            e=self.checked('SpeedCommand:=99; WideDest:='+expr+';',dtype,a,b,13);before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
            with self.assertRaisesRegex(ModelError,'overflow'):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule);self.assertEqual((e.scan_count,e.time_ms),(0,0))

    def test_reached_unknown_sources_fault_but_unknown_destinations_can_be_established(self):
        e=self.checked('WideDest:=WideA+WideB;');e.memory.values['widedest']=None;e.step();self.assertEqual(e.memory.read('WideDest'),10)
        e.memory.values['widea']=None;before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_mixed_types_and_destinations_block_even_in_unreached_branches(self):
        for types in (('LINT','DINT','LINT'),('LINT','ULINT','LINT'),('LINT','LINT','DINT'),('ULINT','REAL','ULINT')):
            self.assertTrue(self.engine('IF FALSE THEN WideDest:=WideA+WideB; END_IF;',types=types).blockers,types)
        for source in ('WideDest:=SpeedCommand;','SpeedCommand:=WideA;','WideDest:=TRUE;','WideDest:=WideA+StartPB;'):
            self.assertTrue(self.engine(source).blockers,source)

    def test_wide_real_typed_and_out_of_dint_immediates_remain_unqualified(self):
        for expr in ('2147483648','9007199254740993','1.0','1L','WideA+2147483648','WideA+1.0'):
            self.assertTrue(self.engine('WideDest:='+expr+';').blockers,expr)
        for expr in ('-1','WideA+(-1)'):
            self.assertTrue(self.engine('WideDest:='+expr+';',dtype='ULINT').blockers,expr)

    def test_power_other_functions_and_numeric_bool_comparisons_are_rejected(self):
        for source in ('WideDest:=WideA**2;','WideDest:=TRUNC(WideA);','WideDest:=SQRT(WideA);','Result:=WideA=StartPB;'):
            self.assertTrue(self.engine(source).blockers,source)

    def test_wide_for_case_and_array_index_forms_remain_explicitly_blocked(self):
        for source in ('FOR SpeedCommand:=0 TO WideA DO WideDest:=1; END_FOR;',
                       'FOR WideDest:=0 TO 2 DO WideA:=WideA+1; END_FOR;',
                       'CASE WideA OF 1:WideDest:=1; END_CASE;', 'WideDest:=Samples[WideA];'):
            self.assertTrue(self.engine(source).blockers,source)

    def test_other_controller_and_firmware_profiles_are_rejected(self):
        for kwargs in (dict(processor='1756-L75'),dict(revision='34'),dict(processor='5069-L340ERM')):
            self.assertTrue(self.engine('WideDest:=WideA+1;',**kwargs).blockers)

    def test_aliases_and_program_local_wide_tags_preserve_exact_types(self):
        def tags(root):
            E.SubElement(root.find('./Controller/Tags'),'Tag',Name='AliasA',TagType='Alias',DataType='LINT',AliasFor='WideA')
            tag=E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='LocalWide',TagType='Base',DataType='LINT')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='LINT',Value='0')
        e=self.checked('LocalWide:=AliasA+WideB; WideDest:=LocalWide;',a=9007199254740993,b=2,mutate=tags);e.step()
        self.assertEqual(e.memory.read('WideDest'),9007199254740995)

    def test_aoi_st_input_output_and_inout_bindings_use_exact_wide_values(self):
        def aoi(root):
            sample=E.parse(Path(__file__).resolve().parents[1]/'samples/AOILab.L5X').getroot()
            definition=copy.deepcopy(sample.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition'))
            for node in definition.iter():
                if node.get('DataType')=='DINT':node.set('DataType','LINT')
            logic=definition.find('./Routines/Routine[@Name="Logic"]');logic.remove(logic.find('RLLContent'));logic.set('Type','ST')
            E.SubElement(E.SubElement(logic,'STContent'),'Line',Number='0').text='Count:=Count+Step; Total:=Count; Shared:=Shared+Step; EnableOut:=Count<Limit;'
            root.find('./Controller/AddOnInstructionDefinitions').append(definition)
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',TagType='Base',DataType='LabAccumulator')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='LabAccumulator')
            for name,dtype,value in (('EnableIn','BOOL',0),('EnableOut','BOOL',0),('Step','LINT',0),('Total','LINT',0),('Limit','LINT',100)):
                E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value=str(value))
        e=self.checked('LabAccumulator(Instance,WideB,WideDest,WideA);',a=9007199254740993,b=2,mutate=aoi);e.step();e.step()
        self.assertEqual(e.memory.read('WideDest'),4);self.assertEqual(e.memory.read('WideA'),9007199254740997)
        self.assertEqual(e.memory.frames['@AOI:instance']['shared'],('WideA',''))
        self.assertEqual(e.calls.stack,[]);self.assertIsNone(e._executing_task)

    def test_report_qualifies_profile_and_native_boundaries(self):
        row=self.checked('WideDest:=WideA+WideB;').report()['wide_st_execution']
        self.assertTrue(row['available']);self.assertFalse(row['mixed_numeric_types']);self.assertFalse(row['native_runtime_parity'])

    def test_eager_boolean_operands_do_not_hide_a_required_fault(self):
        e=self.checked('IF FALSE AND (WideA/WideB>0) THEN WideDest:=1; END_IF;',b=0)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'divide by zero'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_nonretentive_wide_assignment_prescan_resets_without_evaluating_source(self):
        e=self.checked('IF FALSE THEN WideDest [:=] WideA; END_IF;',dest=99)
        self.assertEqual(e.memory.read('WideDest'),0);e.memory.write('WideDest',42);e.step();self.assertEqual(e.memory.read('WideDest'),42)
        e.enter_run();self.assertEqual(e.memory.read('WideDest'),0)

    def test_typed_jsr_sbr_ret_carries_exact_values_through_st(self):
        def sub(root):
            program=root.find('./Controller/Programs/Program')
            tag=E.SubElement(program.find('Tags'),'Tag',Name='LocalWide',TagType='Base',DataType='LINT')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='LINT',Value='0')
            routine=E.SubElement(program.find('Routines'),'Routine',Name='Sub',Type='ST')
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text='SBR(LocalWide); LocalWide:=LocalWide+1; RET(LocalWide);'
        e=self.checked('JSR(Sub,1,WideA,WideDest);',a=9007199254740993,mutate=sub);e.step()
        self.assertEqual(e.memory.read('WideDest'),9007199254740994);self.assertEqual(e.memory.read('WideA'),9007199254740993)
        self.assertEqual(e.calls.stack,[])

    def test_udt_selected_array_destination_retains_neighboring_guard(self):
        def member(root):
            c=root.find('Controller');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='Packet',Family='NoFamily',Class='User'),'Members')
            E.SubElement(members,'Member',Name='Values',DataType='LINT',Dimension='2');E.SubElement(members,'Member',Name='Guard',DataType='LINT',Dimension='0')
            obj=E.SubElement(E.SubElement(E.SubElement(c.find('Tags'),'Tag',Name='Packet1',DataType='Packet',TagType='Base'),'Data',Format='Decorated'),'Structure',DataType='Packet')
            array=E.SubElement(obj,'ArrayMember',Name='Values',DataType='LINT',Dimensions='2')
            for i,value in enumerate((0,17)):E.SubElement(array,'Element',Index=f'[{i}]',Value=str(value))
            E.SubElement(obj,'DataValueMember',Name='Guard',DataType='LINT',Value='9223372036854775807')
        e=self.checked('Packet1.Values[SpeedCommand]:=WideA+WideB; WideDest:=Packet1.Values[0];',a=9007199254740993,b=2,mutate=member);e.step()
        self.assertEqual(e.memory.read('WideDest'),9007199254740995);self.assertEqual(e.memory.read('Packet1.Values'),[9007199254740995,17])
        self.assertEqual(e.memory.read('Packet1.Guard'),9223372036854775807)

    def test_bundled_integer_lab_compares_rll_st_and_recovers_after_late_st_fault(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/IntegerLab.L5X'));self.assertEqual(e.blockers,[])
        e.step();self.assertTrue(e.memory.read('StAllMatches'))
        for name in ('SignedSum','SignedQuotient','SignedRemainder','UnsignedSum','UnsignedComplement','ByteSum','WordSum','DwordSum'):
            self.assertEqual(e.memory.read('St'+name),e.memory.read(name),name)
        e.memory.write('StDelta',3);e.step();self.assertFalse(e.memory.read('StAllMatches'))
        e.memory.write('StDelta',2);e.memory.write('StDivisor',0);before=copy.deepcopy(e.memory.values);schedule=e.scheduler_description()
        with self.assertRaisesRegex(ModelError,'divide by zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.scheduler_description(),schedule)
        e.memory.write('StDivisor',3);e.step();self.assertTrue(e.memory.read('StAllMatches'))


if __name__=='__main__':unittest.main()
