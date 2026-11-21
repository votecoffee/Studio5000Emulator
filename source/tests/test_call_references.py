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

    def structured_routine(self, name, *lines):
        routines = self.root.find('./Controller/Programs/Program/Routines')
        routine = E.SubElement(routines, 'Routine', Name=name, Type='ST')
        content = E.SubElement(routine, 'STContent')
        for number, line in enumerate(lines):
            E.SubElement(content, 'Line', Number=str(number)).text = line

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
                if inner:self.routine('DoubleValue', ['SBR(NestedInput);', 'MOV(77,NestedOutput)CPT(NestedOutput,1/WorkValue);', 'RET(NestedOutput);'])
            rungs = ['XIC(IndirectEnabled)JSR(DoubleValue,1,Inputs[InputIndex],Outputs[OutputIndex]);']
            if not inner:rungs += ['XIC(IndirectEnabled)CPT(Result,1/WorkValue);']
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

    def test_structured_callee_uses_transfer_time_indices_and_captured_caller_destination(self):
        def setup(root):
            self.structured_routine('Selected',
                'SBR(InputIndex,Inputs[InputIndex]);',
                'OutputIndex:=2;',
                'RET(Inputs[InputIndex-1]);')

        e = self.checked(['XIC(IndirectEnabled)JSR(Selected,2,2,InputValue,Outputs[OutputIndex]);'], setup)
        e.step()
        self.assertEqual(e.memory.read('Inputs'), [None, None, None])
        e.memory.write('InputIndex', 1)
        e.memory.write('OutputIndex', 0)
        e.memory.write('IndirectEnabled', True)
        e.step()
        self.assertEqual(e.memory.read('Inputs'), [None, 7, None])
        self.assertEqual(e.memory.read('InputIndex'), 2)
        self.assertEqual(e.memory.read('OutputIndex'), 2)
        self.assertEqual(e.memory.read('Outputs'), [7, None, None])
        self.assertEqual(e.calls.stack, [])

    def test_structured_callee_checks_actual_sbr_overlap_before_copying(self):
        def setup(root):
            self.structured_routine('Selected',
                'SBR(Inputs[InputIndex],Inputs[OutputIndex]);',
                'RET(Inputs[InputIndex],Inputs[OutputIndex]);')

        e = self.checked(['JSR(Selected,2,17,23,Outputs[0],Outputs[1]);'], setup)
        e.memory.write('InputIndex', 1)
        e.memory.write('OutputIndex', 1)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Overlapping parameter destinations'):
            e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('OutputIndex', 2)
        e.step()
        self.assertEqual(e.memory.read('Inputs'), [None, 17, 23])
        self.assertEqual(e.memory.read('Outputs'), [17, 23, None])

    def test_unreached_structured_ret_leaves_live_index_unevaluated(self):
        def setup(root):
            self.structured_routine('Selected',
                'WorkValue:=77;',
                'IF EarlyReturn THEN RET(Inputs[InputIndex]); END_IF;',
                'RET(Inputs[1]);')

        e = self.checked(['JSR(Selected,0,Outputs[0]);'], setup)
        e.memory.write('Inputs[1]', 29)
        e.memory.write('InputIndex', 99)
        e.memory.write('EarlyReturn', False)
        e.step()
        self.assertEqual(e.memory.read('Outputs'), [29, None, None])
        e.memory.write('WorkValue', 11)
        e.memory.write('EarlyReturn', True)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Array index outside bounds'):
            e.step()
        self.assertEqual(self.snapshot(e), before)

    def test_packed_bool_parameters_preserve_signed_words_and_captured_destination(self):
        for dtype, width in (('SINT', 8), ('INT', 16), ('DINT', 32)):
            with self.subTest(dtype=dtype):
                sign = 1 << (width - 1)

                def setup(root):
                    tags = root.find('./Controller/Tags')
                    for name, value in (('CallerBits', 17-sign), ('FormalBits', 5-sign)):
                        tag = E.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType=dtype)
                        data = E.SubElement(tag, 'Data', Format='Decorated')
                        E.SubElement(data, 'DataValue', DataType=dtype, Value=str(value))
                    E.SubElement(tags, 'Tag', Name='FirstBit', TagType='Alias', AliasFor='CallerBits.0')
                    self.structured_routine('BitWorker',
                        f'SBR(FormalBits.1,FormalBits.{width-1});',
                        'OutputIndex:=3;',
                        f'RET(FormalBits.1,FormalBits.{width-1});')

                e = self.checked([
                    f'JSR(BitWorker,2,FirstBit,FALSE,CallerBits.[OutputIndex],CallerBits.{width-1});',
                ], setup)
                e.memory.write('OutputIndex', 2)
                e.step()
                self.assertEqual(e.memory.read('OutputIndex'), 3)
                self.assertEqual(e.memory.read('FormalBits'), 7)
                self.assertEqual(e.memory.read('CallerBits'), 21)

    def test_packed_bool_dynamic_destinations_reject_the_same_bit(self):
        def setup(root):
            tags = root.find('./Controller/Tags')
            E.SubElement(tags, 'Tag', Name='InputBit', TagType='Alias', AliasFor='PackedWord.[InputIndex]')
            E.SubElement(tags, 'Tag', Name='OutputBit', TagType='Alias', AliasFor='PackedWord.[OutputIndex]')
            self.routine('BitWorker', ['SBR(InputBit,OutputBit);'])

        e = self.checked(['JSR(BitWorker,2,TRUE,FALSE);'], setup)
        e.memory.write('PackedWord', 21)
        e.memory.write('InputIndex', 1)
        e.memory.write('OutputIndex', 1)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Overlapping parameter destinations'):
            e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('OutputIndex', 2)
        e.step()
        self.assertEqual(e.memory.read('PackedWord'), 19)

    def test_packed_bool_return_to_unknown_word_rolls_back_earlier_copies(self):
        def setup(root):
            self.routine('BitWorker', ['RET(TRUE,TRUE);'])

        e = self.checked(['JSR(BitWorker,0,PackedWord.1,Outputs[0].1);'], setup)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown initial byte/value'):
            e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('Outputs[0]', 8)
        e.step()
        self.assertTrue(e.memory.read('PackedWord.1'))
        self.assertEqual(e.memory.read('Outputs[0]'), 10)

    def test_packed_bool_guards_keep_word_overlap_and_nonqualified_profiles_blocked(self):
        def word_overlap(root):
            self.routine('BitWorker', ['SBR(PackedWord,PackedWord.1);'])

        e = self.engine(['AFI()JSR(BitWorker,2,12,TRUE);'], word_overlap)
        self.assertIn('Overlapping parameter destinations', str(e.blockers))

        def old(root):
            root.find('Controller').set('MajorRev', '34')
            self.routine('BitWorker', ['RET(TRUE);'])

        e = self.engine(['AFI()JSR(BitWorker,0,PackedWord.1);'], old)
        self.assertIn('Routine parameter bit selections require', str(e.blockers))

    def test_matching_time_types_copy_exact_values_through_ladder_and_st(self):
        for dtype, raw, ticks in (
            ('TIME32', 'T32#-1ms_2us', -1002),
            ('TIME', 'T#1s_3us', 1000003),
            ('LTIME', 'LT#1s_1ns', 1000000001),
            ('DT', 'DT#2020-03-05-08:11:44.345_678(UTC+08:00)', 1583367104345678),
            ('LDT', 'LDT#2020-10-25-11:05:20.123_456_789', 1603623920123456789),
        ):
            with self.subTest(dtype=dtype):
                def setup(root):
                    tags = root.find('./Controller/Tags')
                    for name, value in (('TimeSource', raw), ('TimeFormal', '0'), ('TimeResult', '0')):
                        tag = E.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType=dtype)
                        data = E.SubElement(tag, 'Data', Format='Decorated')
                        E.SubElement(data, 'DataValue', DataType=dtype, Value=value)
                    self.structured_routine('TimeWorker', 'SBR(TimeFormal);', 'RET(TimeFormal);')

                e = self.checked(['JSR(TimeWorker,1,TimeSource,TimeResult);'], setup)
                self.assertEqual(e.memory.read('TimeFormal', allow_time=True), 0)
                e.step()
                for name in ('TimeFormal', 'TimeResult'):
                    self.assertEqual(e.memory.read(name, allow_time=True), ticks)
                call = next(event for visit in e.trace for event in visit['events'] if event['instruction'] == 'JSR')
                self.assertEqual(call['operand_samples'][2]['value'], str(ticks))
                self.assertEqual(call['operand_samples'][3]['value'], str(ticks))

    def test_indirect_timestamp_transfer_skips_false_indices_and_rolls_back_faults(self):
        ticks = 1603623920123456789

        def setup(root):
            tags = root.find('./Controller/Tags')
            for name in ('Timestamps', 'TimeWork', 'TimeResults'):
                tag = E.SubElement(tags, 'Tag', Name=name, DataType='LDT', TagType='Base', Dimensions='3')
                data = E.SubElement(tag, 'Data', Format='Decorated')
                array = E.SubElement(data, 'Array', DataType='LDT', Dimensions='3')
                if name == 'Timestamps':
                    E.SubElement(array, 'Element', Index='[1]', Value=str(ticks))
            E.SubElement(tags, 'Tag', Name='TimeSource', TagType='Alias', AliasFor='Timestamps')
            self.routine('TimeWorker', [
                'SBR(TimeWork[OutputIndex]);',
                'RET(TimeWork[OutputIndex]);',
            ])

        e = self.checked([
            'XIC(IndirectEnabled)JSR(TimeWorker,1,TimeSource[InputIndex],TimeResults[OutputIndex]);',
            'XIC(EarlyReturn)CPT(WorkValue,1/0);',
        ], setup)
        e.step()
        self.assertEqual(e.memory.read('TimeResults', allow_time=True), [None, None, None])
        e.memory.write('InputIndex', 0)
        e.memory.write('OutputIndex', 2)
        e.memory.write('IndirectEnabled', True)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'Unknown initial byte/value'):
            e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('InputIndex', 1)
        e.memory.write('EarlyReturn', True)
        before = self.snapshot(e)
        with self.assertRaisesRegex(ModelError, 'zero'):
            e.step()
        self.assertEqual(self.snapshot(e), before)
        e.memory.write('EarlyReturn', False)
        e.step()
        for name in ('TimeWork', 'TimeResults'):
            self.assertEqual(e.memory.read(name, allow_time=True), [None, None, ticks])

    def test_time_transfers_require_matching_declared_types(self):
        for types in (('TIME', 'LTIME', 'LTIME'), ('LDT', 'LDT', 'DT'), ('LINT', 'LDT', 'LDT')):
            with self.subTest(types=types):
                def setup(root):
                    tags = root.find('./Controller/Tags')
                    for name, dtype in zip(('TimeSource', 'TimeFormal', 'TimeResult'), types):
                        tag = E.SubElement(tags, 'Tag', Name=name, TagType='Base', DataType=dtype)
                        data = E.SubElement(tag, 'Data', Format='Decorated')
                        E.SubElement(data, 'DataValue', DataType=dtype, Value='0')
                    self.structured_routine('TimeWorker', 'SBR(TimeFormal);', 'RET(TimeFormal);')

                e = self.engine(['AFI()JSR(TimeWorker,1,TimeSource,TimeResult);'], setup)
                self.assertIn('parameter data types and array dimensions must match exactly', str(e.blockers))

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
        def older_st_callee(root):
            older(root)
            self.structured_routine('Bad', 'RET(Inputs[InputIndex]);')
        e = self.engine(['AFI()JSR(Bad,0,Result);'], older_st_callee)
        self.assertIn('Routine parameters require static array indices', str(e.blockers))
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
