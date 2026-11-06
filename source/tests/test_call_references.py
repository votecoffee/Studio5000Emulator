"""Bounded indirect JSR caller elements, captured copies and rollback."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_calls as fixtures
from logixlab.model import ModelError


class CallReferenceTests(unittest.TestCase):
    setUp = fixtures.CallTests.setUp
    routine = fixtures.CallTests.routine
    body = fixtures.CallTests.body

    def engine(self, rungs, mutate=None):
        self.root = E.parse(Path(__file__).resolve().parents[1] / 'samples/CallLab.L5X').getroot()
        tags = self.root.find('./Controller/Tags')
        for name, kind, value in [('IndirectEnabled', 'BOOL', 0), ('InputIndex', 'DINT', 99), ('OutputIndex', 'DINT', 99)]:
            tag = E.SubElement(tags, 'Tag', Name=name, DataType=kind, TagType='Base')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType=kind, Value=str(value))
        for name, kind in [('Inputs', 'DINT'), ('Outputs', 'DINT'), ('OtherOutputs', 'DINT'), ('RealInputs', 'REAL'), ('RealOutputs', 'REAL'), ('FlagInputs', 'BOOL'), ('FlagOutputs', 'BOOL'), ('Pairs', 'LabPair'), ('PairResults', 'LabPair')]:
            tag = E.SubElement(tags, 'Tag', Name=name, DataType=kind, TagType='Base', Dimensions='3')
            E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType=kind, Dimensions='3')
        if mutate:mutate(self.root)
        return fixtures.CallTests.engine(self, rungs)

    def checked(self, *args, **kwargs):
        e = self.engine(*args, **kwargs); self.assertEqual(e.blockers, []); self.assertFalse(e.memory.structural); return e

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values, e.memory.frames, e.addons.instances, e.calls.stack,
                              e.scan_count, e.time_ms, e.scheduler_description(), e.trace, e.last_timer))

    def test_false_prescan_and_required_live_addresses_values_then_retry(self):
        e = self.checked(['XIC(IndirectEnabled)JSR(DoubleValue,1,Inputs[InputIndex],Outputs[OutputIndex]);'])
        before = copy.deepcopy(e.memory.values); e.step(); self.assertEqual(e.memory.values, before)
        e.memory.write('IndirectEnabled', True)
        for expected, writes in [('outside bounds', []), ('outside bounds', [('InputIndex', 1)]), ('Unknown', [('OutputIndex', 1)])]:
            for ref, value in writes:e.memory.write(ref, value)
            before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, expected):e.step()
            self.assertEqual(self.snapshot(e), before); self.assertEqual(e.calls.stack, [])
        e.memory.write('Inputs[1]', 7); e.step(); self.assertEqual(e.memory.read('Outputs')[1], 14)
        self.assertEqual(e.memory.read('Inputs')[1], 7); self.assertIsNone(e.memory.read('Outputs')[0])

    def test_indices_are_reselected_for_each_executed_call_and_false_retains_results(self):
        e = self.checked(['XIC(IndirectEnabled)JSR(DoubleValue,1,Inputs[InputIndex],Outputs[OutputIndex]);'])
        for ref, value in [('InputIndex', 1), ('OutputIndex', 1), ('Inputs[1]', 7), ('IndirectEnabled', True)]:e.memory.write(ref, value)
        e.step(); e.memory.write('InputIndex', 2); e.memory.write('OutputIndex', 2); e.memory.write('Inputs[2]', 11); e.step()
        self.assertEqual(e.memory.read('Outputs')[1:], [14, 22]); e.memory.write('IndirectEnabled', False)
        e.memory.values['inputindex'] = None; e.memory.values['outputindex'] = None; e.step(); self.assertEqual(e.memory.read('Outputs')[1:], [14, 22])

    def test_return_address_is_captured_before_sbr_changes_its_index(self):
        def capture(root):self.routine('Capture', ['SBR(OutputIndex);', 'RET(OutputIndex);'])
        e = self.checked(['JSR(Capture,1,2,Outputs[OutputIndex]);'], capture)
        e.memory.write('OutputIndex', 1); e.step(); self.assertEqual(e.memory.read('OutputIndex'), 2)
        self.assertEqual(e.memory.read('Outputs')[1], 2); self.assertIsNone(e.memory.read('Outputs')[2])

    def test_all_input_addresses_and_values_are_captured_before_any_sbr_copy(self):
        def capture(root):self.routine('Capture', ['SBR(InputIndex,NestedInput);', 'RET(NestedInput);'])
        e = self.checked(['JSR(Capture,2,2,Inputs[InputIndex],Outputs[OutputIndex]);'], capture)
        e.memory.write('InputIndex', 1); e.memory.write('OutputIndex', 1); e.memory.write('Inputs[1]', 17); e.memory.write('Inputs[2]', 29); e.step()
        self.assertEqual((e.memory.read('InputIndex'), e.memory.read('NestedInput')), (2, 17)); self.assertEqual(e.memory.read('Outputs')[1], 17)

    def test_alias_indirection_and_multiple_disjoint_return_arrays(self):
        def setup(root):
            tags = root.find('./Controller/Tags')
            E.SubElement(tags, 'Tag', Name='InputView', TagType='Alias', AliasFor='Inputs[InputIndex]')
            E.SubElement(root.find('./Controller/Programs/Program/Tags'), 'Tag', Name='OutputView', TagType='Alias', AliasFor='Outputs[OutputIndex]')
            self.routine('Two', ['SBR(NestedInput);', 'MUL(NestedInput,2,WorkValue);', 'RET(NestedInput,WorkValue);'])
        e = self.checked(['XIC(IndirectEnabled)JSR(Two,1,InputView,OutputView,OtherOutputs[OutputIndex]);'], setup)
        e.step()
        for ref, value in [('InputIndex', 1), ('OutputIndex', 1), ('Inputs[1]', 19), ('IndirectEnabled', True)]:e.memory.write(ref, value)
        e.step(); self.assertEqual((e.memory.read('Outputs')[1], e.memory.read('OtherOutputs')[1]), (19, 38))

    def test_selected_logical_records_preserve_unknown_fields_and_independent_storage(self):
        def pair(root):self.routine('PairEcho', ['SBR(PairFormal);', 'RET(PairFormal);'])
        e = self.checked(['XIC(IndirectEnabled)JSR(PairEcho,1,Pairs[InputIndex],PairResults[OutputIndex]);'], pair)
        e.step(); e.memory.write('InputIndex', 1); e.memory.write('OutputIndex', 1); e.memory.write('Pairs[1].A', 23); e.memory.write('IndirectEnabled', True); e.step()
        self.assertEqual(e.memory.read('PairResults')[1], {'A':23, 'B':None}); e.memory.write('Pairs[1].A', 31)
        call = next(event for visit in e.trace for event in visit['events'] if event['instruction']=='JSR')
        self.assertEqual(call['operand_samples'][2:],[
            {'address':'Pairs[1]','type':'LABPAIR','aggregate':True},
            {'address':'PairResults[1]','type':'LABPAIR','aggregate':True},
        ])
        self.assertEqual(e.memory.read('PairResults')[1]['A'], 23); self.assertIsNone(e.memory.read('PairResults')[0]['A'])

    def test_bool_real_and_wide_integer_elements_transfer_exact_matching_types(self):
        for kind, value in [('BOOL', True), ('REAL', 1.25), ('LINT', 9007199254740993), ('ULINT', 18446744073709551615)]:
            def typed(root):
                tags = root.find('./Controller/Tags')
                for name in ('TypedInputs', 'TypedOutputs'):
                    tag = E.SubElement(tags, 'Tag', Name=name, DataType=kind, TagType='Base', Dimensions='3')
                    E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType=kind, Dimensions='3')
                tag = E.SubElement(tags, 'Tag', Name='TypedFormal', DataType=kind, TagType='Base')
                E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'DataValue', DataType=kind, Value='0')
                self.routine('TypedEcho', ['SBR(TypedFormal);', 'RET(TypedFormal);'])
            e = self.checked(['JSR(TypedEcho,1,TypedInputs[InputIndex],TypedOutputs[OutputIndex]);'], typed)
            e.memory.write('InputIndex', 1); e.memory.write('OutputIndex', 2); e.memory.write('TypedInputs[1]', value); e.step()
            self.assertEqual(e.memory.read('TypedOutputs')[2], value); self.assertIs(type(e.memory.read('TypedOutputs')[2]), type(value))
            call = next(event for visit in e.trace for event in visit['events'] if event['instruction']=='JSR')
            captured = str(value) if kind in ('LINT','ULINT') else value
            self.assertEqual(call['operand_samples'][3],{'address':'TypedOutputs[2]','type':kind,'value':captured})

    def test_multidimensional_element_member_and_program_local_references(self):
        def local(root):
            tags = root.find('./Controller/Tags'); inputs = tags.find('Tag[@Name="Inputs"]'); tags.remove(inputs)
            root.find('./Controller/Programs/Program/Tags').append(inputs)
        e = self.checked(['JSR(DoubleValue,1,Inputs[InputIndex],Outputs[OutputIndex]);'], local)
        e.memory.write('Program:MainProgram.Inputs[1]', 13); e.memory.write('InputIndex', 1); e.memory.write('OutputIndex', 1); e.step()
        self.assertEqual(e.memory.read('Outputs')[1], 26)
        def grid(root):
            tag = E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='Grid', DataType='DINT', TagType='Base', Dimensions='2,2')
            a = E.SubElement(E.SubElement(tag, 'Data', Format='Decorated'), 'Array', DataType='DINT', Dimensions='2,2')
            E.SubElement(a, 'Element', Index='[1,1]', Value='8')
        e = self.checked(['JSR(DoubleValue,1,Grid[InputIndex,1],Outputs[OutputIndex]);'], grid)
        e.memory.write('InputIndex', 1); e.memory.write('OutputIndex', 1); e.step(); self.assertEqual(e.memory.read('Outputs')[1], 16)
        e = self.checked(['JSR(DoubleValue,1,Pairs[InputIndex].A,Outputs[OutputIndex]);'])
        e.memory.write('InputIndex', 1); e.memory.write('OutputIndex', 1); e.memory.write('Pairs[1].A', 9); e.step(); self.assertEqual(e.memory.read('Outputs')[1], 18)

    def test_actual_return_overlap_is_checked_before_any_call_copy(self):
        def setup(root):
            E.SubElement(root.find('./Controller/Tags'), 'Tag', Name='FixedOutput', TagType='Alias', AliasFor='Outputs[1]')
            self.routine('Two', ['RET(WorkValue,NestedOutput);'])
        e = self.checked(['XIC(IndirectEnabled)JSR(Two,0,FixedOutput,Outputs[OutputIndex]);'], setup)
        e.step(); e.memory.write('OutputIndex', 1); e.memory.write('IndirectEnabled', True); before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Overlapping'):e.step()
        self.assertEqual(self.snapshot(e), before); e.memory.write('OutputIndex', 2); e.step()
        self.assertEqual(e.memory.read('Outputs')[1:], [0, 0])

    def test_caller_accepts_distinct_live_return_elements_of_the_same_array(self):
        def setup(root):
            self.routine('Two',['SBR(NestedInput);','ADD(CallCount,1,CallCount);',
                                'MOV(2,OutputIndex);','RET(NestedInput,29);'])
        e = self.checked(['XIC(IndirectEnabled)JSR(Two,1,InputValue,Outputs[InputIndex],Outputs[OutputIndex]);'],setup)
        e.step()
        self.assertEqual(e.memory.read('Outputs'),[None,None,None])
        for ref,value in [('InputIndex',0),('OutputIndex',1),('IndirectEnabled',True)]:
            e.memory.write(ref,value)
        e.step()
        self.assertEqual(e.memory.read('OutputIndex'),2)
        self.assertEqual(e.memory.read('Outputs'),[7,29,None])
        self.assertEqual(e.memory.read('CallCount'),1)

        e.memory.write('InputIndex',2)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Overlapping parameter destinations'):
            e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('OutputIndex',0)
        e.step()
        self.assertEqual(e.memory.read('Outputs'),[29,29,7])
        self.assertEqual(e.memory.read('CallCount'),2)
        self.assertEqual(e.calls.stack,[])

    def test_caller_defers_cross_parameter_overlap_until_input_selection(self):
        def setup(root):
            self.routine('Two',['SBR(Inputs[0],WorkValue);'])
        e = self.checked(['JSR(Two,2,17,Inputs[InputIndex]);'],setup)
        e.memory.write('InputIndex',1)
        e.memory.write('Inputs[1]',29)
        e.step()
        self.assertEqual(e.memory.read('Inputs'),[17,29,None])
        self.assertEqual(e.memory.read('WorkValue'),29)

        e.memory.write('InputIndex',0)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Cross-parameter'):
            e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_nested_and_later_faults_restore_transfers_call_stack_and_scheduler(self):
        for inner in (False, True):
            def fault(root):
                if inner:self.routine('DoubleValue', ['SBR(NestedInput);', 'MOV(77,NestedOutput)DIV(1,WorkValue,NestedOutput);', 'RET(NestedOutput);'])
            rungs = ['XIC(IndirectEnabled)JSR(DoubleValue,1,Inputs[InputIndex],Outputs[OutputIndex]);']
            if not inner:rungs += ['XIC(IndirectEnabled)DIV(1,WorkValue,Result);']
            e = self.checked(rungs, fault); e.step()
            for ref, value in [('InputIndex', 1), ('OutputIndex', 1), ('Inputs[1]', 7), ('IndirectEnabled', True), ('WorkValue', 0)]:e.memory.write(ref, value)
            before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError, 'zero'):e.step()
            self.assertEqual(self.snapshot(e), before); self.assertEqual(e.calls.stack, [])
            e.memory.write('WorkValue', 1); e.step(); self.assertIsNotNone(e.memory.read('Outputs')[1])

    def test_existing_st_jsr_calls_share_caller_selection(self):
        def st(root):
            routine = root.find('./Controller/Programs/Program/Routines/Routine[@Name="MainRoutine"]'); routine.remove(routine.find('RLLContent')); routine.set('Type', 'ST')
            E.SubElement(E.SubElement(routine, 'STContent'), 'Line', Number='0').text = 'IF IndirectEnabled THEN JSR(DoubleValue,1,Inputs[InputIndex],Outputs[OutputIndex]); END_IF;'
        e = self.checked([], st); e.step(); e.memory.write('InputIndex', 1); e.memory.write('OutputIndex', 1); e.memory.write('Inputs[1]', 11); e.memory.write('IndirectEnabled', True); e.step()
        self.assertEqual(e.memory.read('Outputs')[1], 22)

    def test_callee_samples_formals_and_returns_at_the_reached_instruction(self):
        def setup(root):
            self.routine('Selected',['SBR(InputIndex,Inputs[InputIndex]);',
                                     'MOV(2,OutputIndex);',
                                     'RET(Inputs[InputIndex-1]);'])
        e = self.checked(['XIC(IndirectEnabled)JSR(Selected,2,2,InputValue,Outputs[OutputIndex]);'],setup)
        e.step()
        self.assertEqual(e.memory.read('InputIndex'),99)
        self.assertEqual(e.memory.read('Inputs'),[None,None,None])
        for ref,value in [('InputIndex',1),('OutputIndex',0),('IndirectEnabled',True)]:
            e.memory.write(ref,value)
        e.step()
        self.assertEqual(e.memory.read('Inputs'),[None,7,None])
        self.assertEqual(e.memory.read('OutputIndex'),2)
        self.assertEqual(e.memory.read('Outputs'),[7,None,None])
        self.assertEqual(e.calls.stack,[])
        transfers = {}
        for visit in e.trace:
            for event in visit['events']:
                if 'operand_samples' in event:
                    self.assertIn(event['instruction']+'(',visit['operand_source'])
                    transfers[event['instruction']] = event['operand_samples']
        self.assertEqual(transfers,{
            'JSR':[None,None,{'address':None,'type':'DINT','value':2},
                   {'address':'InputValue','type':'DINT','value':7},
                   {'address':'Outputs[0]','type':'DINT','value':7}],
            'SBR':[{'address':'InputIndex','type':'DINT','value':2},
                   {'address':'Inputs[1]','type':'DINT','value':7}],
            'RET':[{'address':'Inputs[1]','type':'DINT','value':7}],
        })
        e.memory.write('Inputs[1]',99)
        self.assertEqual(transfers['RET'][0]['value'],7)
        e.memory.write('IndirectEnabled',False)
        e.step()
        self.assertFalse(any('operand_samples' in event for visit in e.trace for event in visit['events']))

    def test_callee_skips_live_index_of_an_unreached_return(self):
        def setup(root):
            self.routine('Choose',['XIC(EarlyReturn)RET(Inputs[InputIndex]);',
                                   'MOV(1,InputIndex);','RET(Inputs[InputIndex]);'])
        e = self.checked(['JSR(Choose,0,Outputs[0]);'],setup)
        e.memory.write('Inputs[1]',19)
        e.step()
        self.assertEqual(e.memory.read('Outputs'),[19,None,None])
        e.memory.write('InputIndex',99)
        e.memory.write('EarlyReturn',True)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Array index outside bounds'):
            e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_callee_defers_indirect_overlap_and_rejects_actual_collision_before_copy(self):
        def setup(root):
            self.routine('Selected',['SBR(Inputs[InputIndex],Inputs[OutputIndex]);',
                                     'RET(Inputs[InputIndex],Inputs[OutputIndex]);'])
        e = self.checked(['JSR(Selected,2,17,23,Outputs[0],Outputs[1]);'],setup)
        for index,message in [(99,'outside bounds'),(0,'Overlapping')]:
            e.memory.write('InputIndex',0)
            e.memory.write('OutputIndex',index)
            before = self.snapshot(e)
            with self.assertRaisesRegex(ModelError,message):
                e.step()
            self.assertEqual(self.snapshot(e),before)
        e.memory.write('OutputIndex',1)
        e.step()
        self.assertEqual(e.memory.read('Inputs'),[17,23,None])
        self.assertEqual(e.memory.read('Outputs'),[17,23,None])
        self.assertEqual(e.calls.stack,[])

    def test_callee_reads_all_return_values_before_copying_any(self):
        def setup(root):
            self.routine('Selected',['MOV(77,WorkValue);','RET(Inputs[0],Inputs[InputIndex]);'])
        e = self.checked(['JSR(Selected,0,Outputs[0],Outputs[1]);'],setup)
        e.memory.write('Inputs[0]',10)
        e.memory.write('InputIndex',1)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):
            e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[1]',20)
        e.step()
        self.assertEqual(e.memory.read('Outputs'),[10,20,None])

    def test_return_checks_cross_parameter_overlap_at_the_selected_source(self):
        def setup(root):
            self.routine('Selected',['MOV(77,WorkValue);','RET(WorkValue,Inputs[InputIndex]);'])
        e = self.checked(['JSR(Selected,0,Inputs[0],Outputs[1]);'],setup)
        e.memory.write('Inputs[0]',10)
        e.memory.write('InputIndex',0)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Cross-parameter'):
            e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('Inputs[1]',20)
        e.memory.write('InputIndex',1)
        e.step()
        self.assertEqual(e.memory.read('Inputs'),[77,20,None])
        self.assertEqual(e.memory.read('Outputs'),[None,20,None])

    def test_types_literal_bounds_and_older_profiles_remain_guarded(self):
        for text in ('JSR(DoubleValue,1,Inputs[99],Result);', 'JSR(DoubleValue,1,PackedWord.0,Result);', 'JSR(DoubleValue,1,RealInputs[InputIndex],Outputs[OutputIndex]);'):
            self.assertTrue(self.engine(['AFI()' + text]).blockers, text)
        def formal(root):self.routine('Bad', ['SBR(Inputs[99]);', 'RET(NestedOutput);'])
        self.assertTrue(self.engine(['AFI()JSR(Bad,1,InputValue,Result);'], formal).blockers)
        def returned(root):self.routine('Bad', ['RET(RealInputs[InputIndex]);'])
        self.assertTrue(self.engine(['AFI()JSR(Bad,0,Result);'], returned).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Outputs"]').set('Constant', 'true')
        self.assertTrue(self.engine(['AFI()JSR(DoubleValue,1,Inputs[InputIndex],Outputs[OutputIndex]);'], constant).blockers)
        def older(root):root.find('Controller').set('ProcessorType', '1756-L75')
        self.assertTrue(self.engine(['AFI()JSR(DoubleValue,1,Inputs[InputIndex],Outputs[OutputIndex]);'], older).blockers)
        def older_callee(root):
            older(root)
            self.routine('Bad',['SBR(Inputs[InputIndex]);'])
        self.assertTrue(self.engine(['AFI()JSR(Bad,1,InputValue);'],older_callee).blockers)
        def st_callee(root):
            self.routine('Bad',[])
            target = root.find('./Controller/Programs/Program/Routines/Routine[@Name="Bad"]')
            target.remove(target.find('RLLContent'))
            target.set('Type','ST')
            E.SubElement(E.SubElement(target,'STContent'),'Line',Number='0').text='RET(Inputs[InputIndex]);'
        self.assertTrue(self.engine(['AFI()JSR(Bad,0,Result);'],st_callee).blockers)
        def fixed_overlap(root):
            E.SubElement(root.find('./Controller/Tags'),'Tag',Name='FixedOutput',TagType='Alias',AliasFor='Outputs[0]')
            self.routine('Two',['RET(WorkValue,NestedOutput);'])
        e = self.engine(['AFI()JSR(Two,0,FixedOutput,Outputs[0]);'],fixed_overlap)
        self.assertTrue(any('Overlapping parameter destinations' in problem for problem in e.blockers))

        def whole_overlap(root):
            self.routine('Two',['RET(ArrayFormal,WorkValue);'])
        e = self.engine(['AFI()JSR(Two,0,ArrayOutput,ArrayOutput[OutputIndex]);'],whole_overlap)
        self.assertTrue(any('Overlapping parameter destinations' in problem for problem in e.blockers))


if __name__ == '__main__':unittest.main()
