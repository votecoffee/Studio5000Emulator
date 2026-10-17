import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
import test_runtime as fixtures
from logixlab.model import Project,ModelError
from logixlab.runtime import Engine
from logixlab.structured import Parser
from logixlab.server import Application


class StructuredTests(unittest.TestCase):
    def setUp(self):
        fixtures.RuntimeTests.setUp(self)
        self.root=E.parse(Path(__file__).resolve().parents[1]/'samples/TextLab.L5X').getroot()

    def text(self,source,name='MainRoutine'):
        content=self.root.find(f'./Controller/Programs/Program/Routines/Routine[@Name="{name}"]/STContent');content.clear()
        for i,line in enumerate(source.split('\n')):E.SubElement(content,'Line',Number=str(i)).text=line

    def engine(self,source=None):
        if source is not None:self.text(source)
        path=Path(self.tmp.name)/'fixture.L5X';E.ElementTree(self.root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path))

    def test_text_lab_full_scan_and_prescan(self):
        e=self.engine();self.assertEqual(e.blockers,[])
        self.assertEqual(e.memory.read('ClearedOnRun'),0);self.assertEqual(e.memory.read('ScanTotal'),0)
        self.assertEqual(e.memory.read('Accumulator.Count'),0)
        for _ in range(3):e.step()
        expected={'ScanTotal':3,'ClearedOnRun':17,'Sum':30,'Values':[0,3,6,9,12],'Scaled':61,'CaseResult':20,
                  'WhileCount':3,'RepeatCount':2,'SearchResult':3,'AOITotal':6,'Packed':15,'Done':True,'Truth':True}
        for ref,value in expected.items():self.assertEqual(e.memory.read(ref),value,ref)
        self.assertEqual(e.memory.string('Message'),'SCAN 3');self.assertEqual(e.memory.string('Shadow'),'SCAN 3')

    def test_if_elsif_else_select_first_true_branch(self):
        source='IF Selector=1 THEN State:=1; ELSIF Selector>0 THEN State:=2; ELSIF Selector=3 THEN State:=3; ELSE State:=-1; END_IF;'
        e=self.engine(source);self.assertEqual(e.blockers,[])
        for selector,result in ((1,1),(3,2),(-1,-1)):
            e.memory.write('Selector',selector);e.step();self.assertEqual(e.memory.read('State'),result)

    def test_false_st_branch_is_not_false_scanned(self):
        e=self.engine('IF Enable THEN State:=7; END_IF;');e.step();e.memory.write('Enable',False);e.step()
        self.assertEqual(e.memory.read('State'),7)

    def test_unreached_faulting_branch_does_not_evaluate(self):
        e=self.engine('IF Enable THEN State:=4; ELSE State:=1.0/0.0; END_IF;');self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('State'),4)

    def test_unknown_instruction_in_false_branch_still_blocks(self):
        self.assertTrue(self.engine('IF FALSE THEN SECRET(State); END_IF;').blockers)

    def test_st_rejects_ladder_only_instruction_forms(self):
        for text in ('OTE(Done);','TON(Accumulator,?,?);','MOV(1,State);','CMP(State=1);'):
            with self.subTest(text=text):self.assertTrue(self.engine(text).blockers)

    def test_nonretentive_assignment_resets_even_in_false_branch(self):
        e=self.engine('IF FALSE THEN ClearedOnRun [:=] 7; END_IF;');self.assertEqual(e.blockers,[])
        self.assertEqual(e.memory.read('ClearedOnRun'),0);e.memory.write('ClearedOnRun',9);e.step()
        self.assertEqual(e.memory.read('ClearedOnRun'),9)

    def test_ordinary_assignment_retains_imported_value_until_executed(self):
        e=self.engine('IF FALSE THEN ClearedOnRun:=7; END_IF;');self.assertEqual(e.memory.read('ClearedOnRun'),99)

    def test_for_positive_negative_zero_iterations_and_terminal_counter(self):
        for start,end,step,total,index in ((0,4,1,10,5),(4,0,-2,6,-2),(4,0,1,0,4),(0,4,-1,0,0)):
            with self.subTest(start=start,end=end,step=step):
                e=self.engine(f'Sum:=0; FOR Index:={start} TO {end} BY {step} DO Sum:=Sum+Index; END_FOR;')
                self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('Sum'),total);self.assertEqual(e.memory.read('Index'),index)

    def test_for_exit_leaves_counter_at_exit_value(self):
        e=self.engine('Sum:=0; FOR Index:=0 TO 9 DO IF Index=3 THEN EXIT; END_IF; Sum:=Sum+Index; END_FOR;')
        e.step();self.assertEqual(e.memory.read('Sum'),3);self.assertEqual(e.memory.read('Index'),3)

    def test_exit_affects_nearest_nested_loop(self):
        e=self.engine('Sum:=0; FOR Index:=0 TO 1 DO FOR BitIndex:=0 TO 5 DO Sum:=Sum+1; EXIT; END_FOR; Sum:=Sum+10; END_FOR;')
        e.step();self.assertEqual(e.memory.read('Sum'),22)

    def test_for_zero_step_rolls_back(self):
        e=self.engine('State:=9; FOR Index:=0 TO 4 BY Step DO Sum:=Sum+1; END_FOR;');e.memory.write('Step',0)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.time_ms,0)

    def test_for_rejects_real_bounds_or_counter(self):
        self.assertTrue(self.engine('FOR Index:=0 TO 2.0 DO Sum:=1; END_FOR;').blockers)
        self.assertTrue(self.engine('FOR Done:=0 TO 2 DO Sum:=1; END_FOR;').blockers)

    def test_for_mutating_bounds_and_dynamic_counter_are_blocked(self):
        for source in ('FOR Index:=0 TO Step DO Step:=Step+1; END_FOR;',
                       'FOR Index:=0 TO Index+3 DO Sum:=1; END_FOR;',
                       'FOR Values[Index]:=0 TO 2 DO Sum:=1; END_FOR;',
                       'FOR Index:=0 TO Step DO JSR(LadderScale,1,Sum,Scaled); END_FOR;'):
            with self.subTest(source=source):self.assertTrue(self.engine(source).blockers)

    def test_for_read_only_tag_bound_is_supported(self):
        e=self.engine('Sum:=0; FOR Index:=0 TO Step DO Sum:=Sum+Index; END_FOR;');self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('Sum'),3)

    def test_while_can_execute_zero_times_repeat_executes_once(self):
        e=self.engine('Sum:=0; WHILE FALSE DO Sum:=100; END_WHILE; REPEAT Sum:=Sum+1; UNTIL TRUE END_REPEAT;')
        e.step();self.assertEqual(e.memory.read('Sum'),1)

    def test_while_and_repeat_exit(self):
        for loop in ('WHILE TRUE DO Sum:=Sum+1; EXIT; END_WHILE;','REPEAT Sum:=Sum+1; EXIT; UNTIL FALSE END_REPEAT;'):
            e=self.engine('Sum:=0;'+loop);e.step();self.assertEqual(e.memory.read('Sum'),1)

    def test_empty_infinite_loops_hit_budget_and_rollback(self):
        for text in ('State:=7; WHILE TRUE DO END_WHILE;','State:=7; REPEAT UNTIL FALSE END_REPEAT;'):
            e=self.engine(text);e.instruction_limit=30
            with self.assertRaisesRegex(ModelError,'budget'):e.step()
            self.assertEqual(e.memory.read('State'),0);self.assertEqual(e.scan_count,0)

    def test_exit_outside_loop_is_blocked(self):self.assertTrue(self.engine('IF TRUE THEN EXIT; END_IF;').blockers)

    def test_case_single_list_range_else_and_no_fallthrough(self):
        e=self.engine('CASE Selector OF 1,2: State:=10; 3..5: State:=20; 4: State:=99; ELSE State:=-1; END_CASE;')
        self.assertEqual(e.blockers,[])
        for selector,state in ((1,10),(4,20),(9,-1)):
            e.memory.write('Selector',selector);e.step();self.assertEqual(e.memory.read('State'),state)

    def test_case_without_match_retains_value(self):
        e=self.engine('CASE Selector OF 9: State:=4; END_CASE;');e.memory.write('State',8);e.step();self.assertEqual(e.memory.read('State'),8)

    def test_case_rejects_real_dynamic_and_descending_selectors(self):
        for text in ('CASE 1.0 OF 1: State:=1; END_CASE;','CASE Selector OF Step: State:=1; END_CASE;','CASE Selector OF 5..1: State:=1; END_CASE;'):
            with self.subTest(text=text):self.assertTrue(self.engine(text).blockers)

    def test_st_precedence_relations_before_and_and_equality(self):
        e=self.engine('Done := 1<2 AND 3=3 OR FALSE; State:=2**3**2; Truth:=NOT FALSE AND TRUE;');e.step()
        self.assertTrue(e.memory.read('Done'));self.assertTrue(e.memory.read('Truth'));self.assertEqual(e.memory.read('State'),64)

    def test_st_function_names_and_real_rounding(self):
        e=self.engine('State:=TRUNC(-3.9); Sum:=SQRT(9.0)+ABS(-2); Done:=ACOS(1.0)=0.0;');e.step()
        self.assertEqual(e.memory.read('State'),-3);self.assertEqual(e.memory.read('Sum'),5);self.assertTrue(e.memory.read('Done'))

    def test_numeric_integer_limits_and_negative_modulo(self):
        e=self.engine('State := -2147483648; Sum := -7 MOD 3;');e.step()
        self.assertEqual(e.memory.read('State'),-2147483648);self.assertEqual(e.memory.read('Sum'),-1)

    def test_integer_division_and_wide_math_are_explicitly_blocked(self):
        self.assertTrue(self.engine('State:=7/2;').blockers)
        t=self.root.find('./Controller/Tags/Tag[@Name="State"]');t.set('DataType','LINT');t.find('Data/DataValue').set('DataType','LINT')
        self.assertTrue(self.engine('State:=1;').blockers)

    def test_bool_assignment_accepts_bool_or_0_1_only(self):
        for text in ('Done:=TRUE;','Done:=1;','Done:=FALSE;','Done:=0;'):
            self.assertEqual(self.engine(text).blockers,[])
        for text in ('Done:=2;','Done:=1.0;','Done:=Step;','State:=Enable;','IF 1 THEN State:=1; END_IF;'):
            with self.subTest(text=text):self.assertTrue(self.engine(text).blockers)

    def test_three_comment_forms_and_case_insensitivity(self):
        e=self.engine("// hello\nsTaTe:=4; (* ignored State:=99; *)\n/*ignored*/ sUm:=state+2;")
        e.step();self.assertEqual(e.memory.read('Sum'),6)

    def test_strings_literal_escapes_comparison_and_copy(self):
        e=self.engine("Message:='A$27B$$C$0A'; Shadow:=Message; Done:=Shadow='A$27B$$C$0A';")
        self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.string('Message'),"A'B$C\n");self.assertTrue(e.memory.read('Done'))
        e.memory.write('Message.DATA[1]',90);self.assertEqual(e.memory.string('Shadow'),"A'B$C\n")

    def test_comment_markers_inside_strings_are_data(self):
        e=self.engine("Message:='// (* /* '; ");e.step();self.assertEqual(e.memory.string('Message'),'// (* /* ')

    def test_empty_string_and_nonretentive_string(self):
        e=self.engine("Prefix [:=] ''; Message:='';");self.assertEqual(e.memory.string('Prefix'),'');e.step();self.assertEqual(e.memory.string('Message'),'')

    def test_string_bounds_and_wrongly_typed_assignments_are_blocked(self):
        for text in ("Message:='"+'a'*83+"';",'Message:=1;','State:=Message;','Values:=1;'):
            with self.subTest(text=text):self.assertTrue(self.engine(text).blockers)

    def test_malformed_source_is_blocked(self):
        for text in ('IF Enable THEN State:=1;','WHILE Enable DO State:=1;','State:=;', 'State:=2#2;',
                     '(* unclosed','/* unclosed',"Message:='unclosed;", "Message:='line\nbreak';",'State:=__import__(os);'):
            with self.subTest(text=text):self.assertTrue(self.engine(text).blockers)

    def test_indirect_array_bounds_checked_at_runtime_after_loop_initialization(self):
        e=self.engine('FOR Index:=0 TO 4 DO Values[Index]:=Index; END_FOR;');self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('Values'),[0,1,2,3,4])
        e=self.engine('State:=8; Values[Index]:=1;');self.assertEqual(e.blockers,[])
        with self.assertRaisesRegex(ModelError,'bounds'):e.step()
        self.assertEqual(e.memory.read('State'),0)

    def test_indirect_bits_validate_width_and_preserve_other_bits(self):
        e=self.engine('Packed:=16#80; FOR BitIndex:=0 TO 3 DO Packed.[BitIndex]:=1; END_FOR;');e.step();self.assertEqual(e.memory.read('Packed'),143)
        e=self.engine('Packed.[BitIndex]:=1;');self.assertEqual(e.blockers,[])
        with self.assertRaisesRegex(ModelError,'bit selection'):e.step()

    def test_unknown_initial_data_is_read_only_when_reached(self):
        array=self.root.find('./Controller/Tags/Tag[@Name="Values"]/Data/Array');array.remove(array[-1])
        e=self.engine('IF FALSE THEN State:=Values[4]; END_IF;');self.assertEqual(e.blockers,[]);e.step()
        e=self.engine('Sum:=99; State:=Values[4];');self.assertEqual(e.blockers,[])
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.read('Sum'),0)

    def test_constant_assignment_is_blocked_even_unreached(self):
        self.root.find('./Controller/Tags/Tag[@Name="State"]').set('Constant','true')
        self.assertTrue(self.engine('IF FALSE THEN State:=1; END_IF;').blockers)

    def test_st_aoi_not_invoked_in_false_branch_retains_state_and_input(self):
        e=self.engine();e.step();e.memory.write('Enable',False);e.memory.write('Step',9);e.step()
        self.assertEqual(e.memory.read('AOITotal'),2);self.assertEqual(e.memory.read('Accumulator.Step'),2)
        self.assertEqual(e.memory.read('Accumulator.Count'),2)

    def test_rll_false_call_executes_st_aoi_false_routine(self):
        r=self.root.find('./Controller/Programs/Program/Routines/Routine[@Name="MainRoutine"]');r.clear();r.set('Name','MainRoutine');r.set('Type','RLL')
        rung=E.SubElement(E.SubElement(r,'RLLContent'),'Rung',Number='0',Type='N');E.SubElement(rung,'Text').text='AFI()LabSTAccumulator(Accumulator,Step,AOITotal);'
        e=self.engine();self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('AOITotal'),-1)

    def test_st_aoi_hidden_defaults_remain_unknown_without_prescan(self):
        self.root.find('./Controller/AddOnInstructionDefinitions/AddOnInstructionDefinition').set('ExecutePrescan','false')
        e=self.engine();self.assertEqual(e.blockers,[])
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(e.memory.read('ScanTotal'),0)

    def test_trace_preserves_st_line_and_instance_context(self):
        e=self.engine();e.step();st=[t for t in e.trace if t.get('language')=='ST']
        self.assertTrue(any(t['routine']=='MainProgram/MainRoutine' and t['statement']=='for' for t in st))
        self.assertTrue(any(t['routine']=='AOI:LabSTAccumulator/Logic' and t['context']=='Accumulator' for t in st))

    def test_native_xml_line_wrappers_preserve_trace_and_call_numbers(self):
        for line in self.root.findall('.//STContent/Line'):line.text='\n'+(line.text or '')+'\n'
        e=self.engine();self.assertEqual(e.blockers,[]);e.step()
        main=e.project.routines['mainprogram/mainroutine']
        self.assertEqual(main.lines[5]['text'],'    Values[Index] := Index * 3;')
        self.assertTrue(any(r['number']=='37' and r['nodes'][0].name=='JSR' for r in main.rungs))
        self.assertTrue(any(t['routine']==main.key and t['number']=='1' and t.get('detail')=='ScanTotal = 1' for t in e.trace))
        self.assertTrue(any(t['routine']=='AOI:LabSTAccumulator/Logic' and t['number']=='0' and t['context']=='Accumulator' for t in e.trace))

    def test_embedded_multiline_content_in_numbered_line_blocks(self):
        self.text('State:=1;')
        self.root.find('.//Programs/Program/Routines/Routine/STContent/Line').text='State:=1;\nState:=2;'
        self.assertTrue(self.engine().blockers)

    def test_application_exports_st_source_and_traces(self):
        app=Application(self.tmp.name);state=app.command('demo',{'sample':'TextLab'});self.assertEqual(state['blockers'],[])
        routine=next(r for r in state['routines'] if r['key']=='MainProgram/MainRoutine')
        self.assertEqual(routine['kind'],'ST');self.assertEqual(routine['lines'][0]['number'],'0')
        self.assertIn('Text Lab',routine['lines'][0]['text'])
        state=app.command('step',{'count':3});self.assertEqual(state['scan'],3)
        self.assertTrue(any(t.get('language')=='ST' for t in state['trace']))
        self.assertTrue(app.command('report',{})['structured_text']['constructs']['for'])

    def test_nonsequential_st_lines_and_missing_source_block(self):
        r=self.root.find('./Controller/Programs/Program/Routines/Routine[@Name="MainRoutine"]')
        r.find('STContent/Line').set('Number','9');self.assertTrue(self.engine().blockers)
        r.remove(r.find('STContent'));self.assertTrue(self.engine().blockers)

    def test_st_sbr_must_be_first_statement_and_main_ret_blocks(self):
        self.text('State:=1; SBR(AdjustInput); RET(AdjustOutput);','TextAdjust')
        self.assertTrue(self.engine().blockers)
        self.assertTrue(self.engine('RET();').blockers)

    def test_arithmetic_fault_restores_prior_st_aoi_and_call_writes(self):
        e=self.engine('LabSTAccumulator(Accumulator,Step,AOITotal); JSR(LadderScale,1,Step,Scaled); State:=1.0/0.0;')
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.calls.stack,[]);self.assertEqual(e.time_ms,0)


if __name__=='__main__':unittest.main()
