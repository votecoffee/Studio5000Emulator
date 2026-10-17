import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
import test_runtime as fixtures
from logixlab.model import ModelError
from logixlab.runtime import Engine
from logixlab.server import Application


class CallTests(unittest.TestCase):
    engine=fixtures.RuntimeTests.engine

    def setUp(self):
        fixtures.RuntimeTests.setUp(self)
        self.root=E.parse(Path(__file__).resolve().parents[1]/'samples/CallLab.L5X').getroot()

    def body(self,name='Calculate'):
        return self.root.find(f'./Controller/Programs/Program/Routines/Routine[@Name="{name}"]/RLLContent')

    def routine(self,name,texts):
        rr=self.root.find('./Controller/Programs/Program/Routines')
        old=rr.find(f'./Routine[@Name="{name}"]')
        if old is not None:rr.remove(old)
        content=E.SubElement(E.SubElement(rr,'Routine',Name=name,Type='RLL'),'RLLContent')
        for i,text in enumerate(texts):
            rung=E.SubElement(content,'Rung',Number=str(i),Type='N');E.SubElement(rung,'Text').text=text

    def test_lab_nested_calls_and_copied_arrays_structures(self):
        e=self.engine();self.assertEqual(e.blockers,[])
        self.assertEqual(e.memory.read('FormalInput'),0)  # No parameter transfer in prescan.
        for _ in range(2):e.step()
        for ref,value in {'Result':24,'RealOutput':7.5,'CompareOK':True,'MaskOK':True,'ArrayOutput':[10,25,30],
                          'PairOutput':{'A':13,'B':9},'ArrayInput':[10,20,30],'PairInput':{'A':4,'B':9},'CallCount':2}.items():
            self.assertEqual(e.memory.read(ref),value,ref)
        self.assertEqual(e.calls.stack,[])
        e.memory.write('ArrayFormal[0]',99);e.memory.write('PairFormal.A',88)
        self.assertEqual(e.memory.read('ArrayOutput[0]'),10);self.assertEqual(e.memory.read('PairOutput.A'),13)

    def test_false_jsr_does_not_transfer_or_execute(self):
        e=self.engine();e.memory.write('Enabled',False);e.memory.write('FormalInput',88);e.memory.write('Result',55);e.step()
        self.assertEqual(e.memory.read('FormalInput'),88);self.assertEqual(e.memory.read('Result'),55)
        self.assertEqual(e.memory.read('CallCount'),0)

    def test_input_parameter_is_value_copy(self):
        self.body()[1].find('Text').text='MOV(99,FormalInput)MOV(FormalInput,WorkValue);'
        e=self.engine();e.step();self.assertEqual(e.memory.read('Result'),198)
        self.assertEqual(e.memory.read('InputValue'),7)

    def test_conditional_ret_copies_and_exits_immediately(self):
        e=self.engine();e.memory.write('EarlyReturn',True);e.step()
        self.assertEqual(e.memory.read('Result'),12);self.assertEqual(e.memory.read('RealOutput'),2.5)
        self.assertEqual(e.memory.read('NestedOutput'),0)

    def test_immediate_input_and_return_operands(self):
        self.routine('Literal',['SBR(FormalInput);','RET(42);'])
        e=self.engine(['JSR(Literal,1,4,Result);']);self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('Result'),42);self.assertEqual(e.memory.read('FormalInput'),4)

    def test_real_immediate_copied_as_float32(self):
        self.routine('Literal',['SBR(FormalReal);','RET(FormalReal);'])
        e=self.engine(['JSR(Literal,1,16777217.0,RealOutput);']);e.step()
        self.assertEqual(e.memory.read('RealOutput'),16777216.0)

    def test_bool_parameters(self):
        self.routine('Flag',['SBR(CompareOK);','XIO(CompareOK)OTE(MaskOK);','RET(MaskOK);'])
        e=self.engine(['JSR(Flag,1,Enabled,EarlyReturn);']);self.assertEqual(e.blockers,[]);e.step()
        self.assertTrue(e.memory.read('CompareOK'));self.assertFalse(e.memory.read('EarlyReturn'))

    def test_main_ret_and_calling_main_are_blocked_even_false(self):
        for text in ('AFI()RET();','AFI()JSR(MainRoutine,0);'):
            with self.subTest(text=text):self.assertTrue(self.engine([text]).blockers)

    def test_header_must_be_first_unbranched_and_unique(self):
        for texts in (['NOP()SBR(FormalInput);'],['[SBR(FormalInput),NOP()];'],['SBR(FormalInput);','SBR(FormalInput);']):
            self.routine('Bad',texts)
            with self.subTest(texts=texts):self.assertTrue(self.engine(['JSR(Bad,1,InputValue);']).blockers)

    def test_missing_header_and_count_mismatches_are_blocked(self):
        for text in ('JSR(DoubleValue,0,Result);','JSR(DoubleValue,2,InputValue,InputValue,Result);','JSR(DoubleValue,1,InputValue);'):
            with self.subTest(text=text):self.assertTrue(self.engine([text]).blockers)

    def test_jsr_input_count_malformed_or_more_than_40_is_blocked(self):
        for text in ('JSR(Calculate);','JSR(Calculate,-1);','JSR(Calculate,InputValue);','JSR(Calculate,41);'):
            with self.subTest(text=text):self.assertTrue(self.engine([text]).blockers)

    def test_literal_return_destination_and_type_mismatch_are_blocked(self):
        for text in ('JSR(DoubleValue,1,InputValue,42);','JSR(DoubleValue,1,RealInput,Result);','JSR(DoubleValue,1,InputValue,RealOutput);'):
            with self.subTest(text=text):self.assertTrue(self.engine([text]).blockers)

    def test_dimensions_and_structure_type_must_match(self):
        for text in ('JSR(TransformData,2,ArrayInput[0],PairInput,ArrayOutput,PairOutput);',
                     'JSR(TransformData,2,ArrayInput,PairInput,ArrayOutput[0],PairOutput);',
                     'JSR(TransformData,2,ArrayInput,ArrayInput,ArrayOutput,PairOutput);'):
            with self.subTest(text=text):self.assertTrue(self.engine([text]).blockers)

    def test_read_only_formal_or_return_destination_blocks(self):
        for name in ('FormalInput','Result'):
            original=copy.deepcopy(self.root)
            self.root.find(f'./Controller/Tags/Tag[@Name="{name}"]').set('Constant','true')
            self.assertTrue(self.engine().blockers);self.root=original

    def test_constant_input_source_is_allowed(self):
        self.root.find('./Controller/Tags/Tag[@Name="InputValue"]').set('Constant','true')
        e=self.engine();self.assertEqual(e.blockers,[]);e.step();self.assertEqual(e.memory.read('Result'),24)

    def test_indirect_or_bit_parameter_references_block(self):
        for text in ('JSR(DoubleValue,1,ArrayInput[InputValue],Result);','JSR(DoubleValue,1,PackedWord.0,Result);'):
            with self.subTest(text=text):self.assertTrue(self.engine([text]).blockers)

    def test_cross_parameter_overlap_is_rejected(self):
        self.routine('Swap',['SBR(FormalInput,WorkValue);'])
        e=self.engine(['JSR(Swap,2,WorkValue,FormalInput);'])
        self.assertTrue(any('overlap' in b for b in e.blockers))

    def test_same_single_source_destination_is_safe(self):
        e=self.engine(['JSR(DoubleValue,1,NestedInput,Result);']);self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('Result'),0)

    def test_overlapping_return_destinations_are_rejected(self):
        self.routine('Two',['RET(WorkValue,FormalInput);'])
        e=self.engine(['JSR(Two,0,Result,Result);'])
        self.assertTrue(any('Overlapping' in b for b in e.blockers))

    def test_fallthrough_with_no_returns_is_allowed(self):
        self.routine('NoReturn',['SBR(FormalInput);','ADD(FormalInput,1,WorkValue);'])
        e=self.engine(['JSR(NoReturn,1,InputValue);']);self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('WorkValue'),8)

    def test_return_destinations_need_ret_and_unreached_ret_rolls_back(self):
        self.routine('Missing',['SBR(FormalInput);'])
        self.assertTrue(self.engine(['JSR(Missing,1,InputValue,Result);']).blockers)
        self.routine('Missing',['SBR(FormalInput);','MOV(88,WorkValue)AFI()RET(WorkValue);'])
        e=self.engine(['JSR(Missing,1,InputValue,Result);']);self.assertEqual(e.blockers,[])
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'without passing'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.calls.stack,[]);self.assertEqual(e.time_ms,0)

    def test_fault_in_nested_routine_rolls_back_all_copies(self):
        self.body('DoubleValue')[1].find('Text').text='MOV(77,NestedOutput)DIV(1,0,NestedOutput);'
        e=self.engine();before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'divide'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.calls.stack,[]);self.assertEqual(e.trace,[])

    def test_harness_requires_caller_for_parameterized_routine(self):
        e=self.engine();h=Engine(e.project,'routine','MainProgram/Calculate')
        self.assertTrue(any('requires a JSR caller' in b for b in h.blockers))

    def test_unknown_array_storage_is_preserved_by_value_transfer(self):
        a=self.root.find('./Controller/Tags/Tag[@Name="ArrayInput"]/Data/Array');a.remove(a[-1])
        e=self.engine();self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual(e.memory.read('ArrayOutput')[:2],[10,25])
        with self.assertRaisesRegex(ModelError,'Unknown'):e.memory.read('ArrayOutput[2]')

    def test_25_nested_calls_pass_and_26_fail_with_rollback(self):
        for count in (25,26):
            for i in range(count):self.routine('Depth'+str(i),[f'JSR(Depth{i+1},0);' if i<count-1 else 'MOV(99,Result);'])
            e=self.engine(['JSR(Depth0,0);']);self.assertEqual(e.blockers,[])
            if count==25:e.step();self.assertEqual(e.memory.read('Result'),99)
            else:
                with self.assertRaisesRegex(ModelError,'25'):e.step()
                self.assertEqual(e.memory.read('Result'),0)
            self.assertEqual(e.calls.stack,[])

    def test_40_inputs_and_returns_are_supported(self):
        tags=self.root.find('./Controller/Tags');template=tags.find('./Tag[@Name="FormalInput"]')
        formals=[];outputs=[]
        for i in range(40):
            for prefix,target in [('Formal',formals),('Output',outputs)]:
                name=prefix+str(i);t=copy.deepcopy(template);t.set('Name',name);tags.append(t);target.append(name)
        self.routine('Forty',['SBR('+','.join(formals)+');','RET('+','.join(formals)+');'])
        e=self.engine(['JSR(Forty,40,'+','.join(['InputValue']*40+outputs)+');']);self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual([e.memory.read(x) for x in outputs],[7]*40)

    def test_bundled_call_lab_and_coverage_contract(self):
        app=Application(self.tmp.name);state=app.command('demo',{'sample':'CallLab'});self.assertEqual(state['blockers'],[])
        self.assertEqual(state['entry_routines'],['mainprogram/mainroutine'])
        state=app.command('step',{'count':1});self.assertEqual(state['scan'],1)
        report=app.command('report',{});self.assertEqual(report['routine_parameters']['nesting_limit'],25)
        self.assertEqual(report['routine_parameters']['calls']['mainprogram/calculate'],{'inputs':2,'returns':2})


if __name__=='__main__':unittest.main()
