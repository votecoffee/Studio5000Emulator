"""Typed numeric JSR/RET constants preserve exact types, values and rollback."""
import copy
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_calls as fixtures
from logixlab.model import ModelError

CASES=(('LINT','9007199254740993L',9007199254740993),
       ('UDINT','4294967295U',4294967295),
       ('ULINT','18446744073709551615UL',18446744073709551615),
       ('LREAL','1.0000000000000002L',1.0000000000000002))
ZERO=dict(LINT='0L',UDINT='0U',ULINT='0UL',LREAL='0.0L')


class CallLiteralTests(unittest.TestCase):
    setUp=fixtures.CallTests.setUp
    engine=fixtures.CallTests.engine
    routine=fixtures.CallTests.routine

    def literal(self,dtype,value,*,ret=None,gate=False,dest='WideResult',middle=(),tail=(),extra=None,main_st=False,callee_st=False,checked=True):
        self.root=E.parse(Path(__file__).resolve().parents[1]/'samples/CallLab.L5X').getroot()
        tags=self.root.find('./Controller/Tags')
        for name,kind in (('WideFormal',dtype),('WideResult',dtype),('InnerFormal',dtype),('LiteralDivisor','DINT')):
            tag=E.SubElement(tags,'Tag',Name=name,DataType=kind,TagType='Base')
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=kind,Value='1' if name=='LiteralDivisor' else '0')
        tag=E.SubElement(tags,'Tag',Name='WideResults',DataType=dtype,Dimensions='3',TagType='Base')
        array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions='3')
        for i in range(3):E.SubElement(array,'Element',Index=f'[{i}]',Value='0')
        body=['SBR(WideFormal);',*middle,'RET('+('WideFormal' if ret is None else ret)+');']
        self.routine('LiteralWorker',body)
        call=f'JSR(LiteralWorker,1,{value},{dest});'
        lines=[('XIC(TypedCallEnabled)' if gate else '')+call,*tail]
        def change(root):
            if extra:extra(root)
            for name,texts in [('MainRoutine',([('IF TypedCallEnabled THEN '+call+' END_IF;') if gate else call,*tail] if main_st else None)),
                               ('LiteralWorker',body if callee_st else None)]:
                if texts is None:continue
                routine=root.find(f'./Controller/Programs/Program/Routines/Routine[@Name="{name}"]')
                routine.remove(routine.find('RLLContent'));routine.set('Type','ST');content=E.SubElement(routine,'STContent')
                for i,text in enumerate(texts):E.SubElement(content,'Line',Number=str(i)).text=text
        e=self.engine(lines,change)
        if checked:self.assertEqual(e.blockers,[])
        return e

    def snapshot(self,e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.calls.stack,
                              e.scan_count,e.time_ms,e.scheduler_description(),e.trace,e.last_timer))

    def test_all_typed_input_kinds_retain_declared_values(self):
        for dtype,text,expected in CASES:
            e=self.literal(dtype,text);e.step()
            self.assertEqual(e.memory.read('WideFormal'),expected);self.assertEqual(e.memory.read('WideResult'),expected)
            self.assertIs(type(e.memory.read('WideResult')),float if dtype=='LREAL' else int)

    def test_ret_typed_literals_match_exact_return_destinations(self):
        for dtype,text,expected in CASES:
            e=self.literal(dtype,ZERO[dtype],ret=text);e.step()
            self.assertEqual(e.memory.read('WideResult'),expected)

    def test_signed_limits_signs_and_suffix_spellings(self):
        for dtype,text,expected in [('LINT','-9223372036854775808l',-(1<<63)),
                                   ('LINT','+9223372036854775807L',(1<<63)-1),
                                   ('UDINT','+4294967295u',(1<<32)-1),
                                   ('ULINT','18446744073709551615uL',(1<<64)-1),
                                   ('ULINT','0Ul',0),('LREAL','-1.5e2l',-150.0)]:
            e=self.literal(dtype,text);e.step();self.assertEqual(e.memory.read('WideResult'),expected)

    def test_unsuffixed_real_keeps_float32_and_lreal_retains_binary64(self):
        e=self.literal('REAL','16777217.0');e.step();self.assertEqual(e.memory.read('WideResult'),16777216.0)
        e=self.literal('LREAL','16777217.0L');e.step();self.assertEqual(e.memory.read('WideResult'),16777217.0)
        e=self.literal('BOOL','TRUE');e.step();self.assertIs(e.memory.read('WideResult'),True)

    def test_out_of_range_and_excluded_constants_block_even_when_false(self):
        for dtype,text in [('LINT','9223372036854775808L'),('UDINT','-1U'),
                           ('ULINT','18446744073709551616UL'),('LREAL','1e309L'),
                           ('LINT','16#1_0000_0000_0000_0000L'),('DINT','4294967295'),
                           ('DINT','16#FFFFFFFF'),('LINT','T#1s')]:
            e=self.literal(dtype,text,gate=True,checked=False);self.assertTrue(e.blockers,text)

    def test_type_mismatches_are_not_implicitly_promoted_or_narrowed(self):
        for dtype,text in [('LINT','1U'),('UDINT','1L'),('LREAL','1'),('REAL','1.0L')]:
            self.assertTrue(self.literal(dtype,text,checked=False).blockers)
        self.assertTrue(self.literal('LINT','1L',ret='1U',checked=False).blockers)
        self.assertTrue(self.literal('LINT','1L',dest='1L',checked=False).blockers)

    def test_false_call_skips_live_return_indices_and_then_establishes_unknown_result(self):
        e=self.literal('LINT',CASES[0][1],gate=True,dest='WideResults[CallOutputIndex]')
        e.memory.write('CallOutputIndex',99);e.memory.values['wideformal']=None;before=copy.deepcopy(e.memory.values)
        e.step();self.assertEqual(e.memory.values,before)
        e.memory.write('CallOutputIndex',1);e.memory.values['wideresults'][1]=None
        e.memory.write('TypedCallEnabled',True);e.step()
        self.assertEqual(e.memory.read('WideResults')[1],CASES[0][2]);self.assertEqual(e.memory.read('WideFormal'),CASES[0][2])

    def test_return_address_is_captured_before_callee_changes_selector(self):
        e=self.literal('ULINT',CASES[2][1],dest='WideResults[CallOutputIndex]',middle=['MOV(2,CallOutputIndex);'])
        e.memory.write('CallOutputIndex',1);e.step()
        self.assertEqual(e.memory.read('WideResults'),[0,CASES[2][2],0]);self.assertEqual(e.memory.read('CallOutputIndex'),2)

    def test_later_fault_restores_formals_results_call_stack_and_schedule(self):
        e=self.literal('LREAL',CASES[3][1],tail=['DIV(1,LiteralDivisor,Result);'])
        e.memory.write('LiteralDivisor',0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before)
        e.memory.write('LiteralDivisor',1);e.step();self.assertEqual(e.memory.read('WideResult'),CASES[3][2])

    def test_nested_call_returns_typed_value_without_losing_integer_precision(self):
        def nested(root):self.routine('Inner',['SBR(InnerFormal);','RET(9223372036854775807L);'])
        e=self.literal('LINT',CASES[0][1],middle=['JSR(Inner,1,WideFormal,WideFormal);'],extra=nested)
        e.step();self.assertEqual(e.memory.read('WideResult'),(1<<63)-1);self.assertEqual(e.calls.stack,[])

    def test_existing_st_jsr_sbr_and_ret_use_typed_constants(self):
        e=self.literal('LREAL',CASES[3][1],ret='2.0000000000000004L',main_st=True,callee_st=True)
        e.step();self.assertEqual(e.memory.read('WideFormal'),CASES[3][2])
        self.assertEqual(e.memory.read('WideResult'),2.0000000000000004)

    def test_other_controller_profile_and_wider_for_bounds_remain_blocked(self):
        def older(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.literal('LINT','1L',extra=older,checked=False).blockers)
        self.root=E.parse(Path(__file__).resolve().parents[1]/'samples/CallLab.L5X').getroot()
        self.routine('NoParams',['NOP();'])
        self.assertTrue(self.engine(['FOR(NoParams,Result,0L,2L,1L);']).blockers)

    def test_trace_retains_exact_integer_text_and_literal_addresses(self):
        e=self.literal('LINT',CASES[0][1]);e.step()
        event=next(item for visit in e.trace for item in visit['events'] if item['instruction']=='JSR')
        self.assertEqual(event['operand_samples'][2],dict(address=None,type='LINT',value=str(CASES[0][2])))
        self.assertEqual(event['operand_samples'][3],dict(address='WideResult',type='LINT',value=str(CASES[0][2])))

    def test_public_sample_and_report_expose_typed_transfer_profile(self):
        e=self.engine();self.assertEqual(e.blockers,[]);e.memory.write('TypedCallEnabled',True);e.step()
        for name,(_,_,expected) in zip(('TypedSigned','TypedUnsigned','TypedLargest','TypedPrecise'),CASES):
            self.assertEqual(e.memory.read(name),expected)
        report=e.report()['routine_parameters']['typed_constants']
        self.assertEqual(set(report['types']),{'LINT','UDINT','ULINT','LREAL'})
        self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
