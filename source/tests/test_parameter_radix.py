"""Typed radix constants cross exact AOI and routine boundaries transactionally."""
import copy
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_aoi_literals as aois
import test_call_literals as calls
from logixlab.model import ModelError,Project,literal
from logixlab.runtime import Engine

RADIX=dict(Signed='16#0020000000000001L',Unsigned='8#37777777777U',Largest='2#'+'1'*64+'UL')


class ParameterRadixTests(unittest.TestCase):
    def aoi(self,values=None,**kwargs):
        h=aois.AOILiteralTests();h.setUp();self.addCleanup(h.doCleanups)
        return h.typed(RADIX|dict(values or {}),**kwargs)

    def call(self,*args,**kwargs):
        h=calls.CallLiteralTests();h.setUp();self.addCleanup(h.doCleanups)
        return h.literal(*args,**kwargs)

    @staticmethod
    def token(base,value,suffix):return f'{base}#{format(value,{2:"b",8:"o",16:"x"}[base])}{suffix}'

    @staticmethod
    def snapshot(e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e.calls.stack,
                              e.scan_count,e.time_ms,e.scheduler_description(),e.trace,e.last_timer))

    def fault(self,e,pattern):
        before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,pattern):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_aoi_three_bases_exact_types_full_width_signs_and_zero_fill(self):
        for base,(suffix,bits,want) in itertools.product((2,8,16),(('L',64,-1),('u',32,4294967295),('uL',64,18446744073709551615))):
            name={'L':'Signed','u':'Unsigned','uL':'Largest'}[suffix]
            e=self.aoi({name:self.token(base,(1<<bits)-1,suffix)})
            self.assertEqual(e.memory.read('TypedInputs.'+name),want)
            e.memory.write('Enabled',True);e.step();self.assertEqual(e.memory.read(name+'Result'),want)
        for text,want in [('16#FFFFFFFFL',4294967295),('16#8000000000000000l',-(1<<63)),('2#1L',1)]:
            e=self.aoi({'Signed':text});self.assertEqual(e.memory.read('TypedInputs.Signed'),want)

    def test_aoi_prescan_false_refresh_warm_outputs_and_late_fault_retry(self):
        e=self.aoi(tail=['DIV(1,TestDivisor,TestGuard);'])
        self.assertEqual(e.memory.read('TypedInputs.Signed'),9007199254740993)
        e.memory.write('TypedInputs.Signed',7);e.memory.write('SignedResult',-9);e.step()
        self.assertEqual((e.memory.read('TypedInputs.Signed'),e.memory.read('SignedResult')),(9007199254740993,-9))
        e.memory.write('Enabled',True);e.step();e.memory.write('SignedResult',77);e.memory.write('TestDivisor',0)
        self.fault(e,'zero');e.memory.write('TestDivisor',1);e.step()
        self.assertEqual((e.memory.read('SignedResult'),e.memory.read('LargestResult')),(9007199254740993,(1<<64)-1))

    def test_aoi_invalid_patterns_mismatches_permissions_and_old_profiles_block_false_calls(self):
        for name,text in [('Signed','16#10000000000000000L'),('Unsigned','16#100000000U'),('Largest','2#2UL'),
                          ('Signed','8#8L'),('Unsigned','16#FF U'),('Signed','16#FF_L'),('Signed','16#FFLU'),
                          ('Signed','-16#FFL'),('Signed','16#FFU'),('Largest','16#FFL'),('Precise','16#1L')]:
            self.assertTrue(self.aoi({name:text},checked=False).blockers,(name,text))
        def output(root):
            text=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text')
            text.text=text.text.replace(',SignedResult,',',16#1L,')
        def inout(root):root.find('.//Parameter[@Name="Signed"]').set('Usage','InOut')
        for mutate in (output,inout,lambda root:root.find('Controller').set('ProcessorType','1756-L75'),
                       lambda root:root.find('Controller').set('MajorRev','34')):
            self.assertTrue(self.aoi(mutate=mutate,checked=False).blockers)

    def test_aoi_existing_st_call_preserves_exact_radix_and_floating_input_precision(self):
        def st(root):
            routine=root.find('./Controller/Programs/Program/Routines/Routine')
            text=routine.find('./RLLContent/Rung/Text').text.split('XIC(Enabled)',1)[1]
            routine.remove(routine.find('RLLContent'));routine.set('Type','ST')
            E.SubElement(E.SubElement(routine,'STContent'),'Line',Number='0').text=text
        e=self.aoi(mutate=st);e.step()
        for name,value in aois.VALUES.items():self.assertEqual(e.memory.read(name+'Result'),value)

    def test_aoi_public_sample_report_and_guarded_fault_recovery(self):
        e=Engine(Project(aois.SAMPLE));self.assertEqual(e.blockers,[])
        e.memory.write('Enabled',True);e.step()
        for name,value in aois.VALUES.items():self.assertEqual(e.memory.read(name+'Result'),value)
        e.memory.write('LargestResult',17);e.memory.write('ParameterLateDivisor',0);self.fault(e,'zero')
        e.memory.write('ParameterLateDivisor',1);e.step();self.assertEqual(e.memory.read('LargestResult'),(1<<64)-1)
        p=e.report()['add_on_instructions']['typed_inputs'];self.assertEqual(p['radix_bases'],[2,8,16]);self.assertFalse(p['native_runtime_parity'])

    def test_jsr_and_ret_three_bases_preserve_declared_values_and_signs(self):
        for base,(dtype,suffix,bits) in itertools.product((2,8,16),(('LINT','l',64),('UDINT','U',32),('ULINT','Ul',64))):
            token=self.token(base,(1<<bits)-1,suffix);want=-1 if dtype=='LINT' else (1<<bits)-1
            e=self.call(dtype,token);e.step();self.assertEqual((e.memory.read('WideFormal'),e.memory.read('WideResult')),(want,want))
            e=self.call(dtype,calls.ZERO[dtype],ret=token);e.step();self.assertEqual(e.memory.read('WideResult'),want)
        e=self.call('LINT','16#FFFFFFFFL');e.step();self.assertEqual(e.memory.read('WideResult'),4294967295)

    def test_jsr_false_prescan_skip_indices_then_capture_unknown_selected_return(self):
        e=self.call('LINT',RADIX['Signed'],gate=True,dest='WideResults[CallOutputIndex]',middle=['MOV(2,CallOutputIndex);'])
        e.memory.values['wideformal']=None;e.memory.write('CallOutputIndex',99);e.step()
        self.assertIsNone(e.memory.values['wideformal'])
        e.memory.write('TypedCallEnabled',True);self.fault(e,'outside bounds')
        e.memory.write('CallOutputIndex',1);e.memory.values['wideresults'][1]=None;e.step()
        self.assertEqual(e.memory.read('WideResults'),[0,9007199254740993,0]);self.assertEqual(e.memory.read('CallOutputIndex'),2)

    def test_nested_calls_and_radix_ret_keep_exact_values_and_trace_samples(self):
        def nested(root):
            content=E.SubElement(E.SubElement(root.find('./Controller/Programs/Program/Routines'),'Routine',Name='RadixInner',Type='RLL'),'RLLContent')
            for i,text in enumerate(['SBR(InnerFormal);','RET(16#7FFFFFFFFFFFFFFFL);']):
                E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        e=self.call('LINT',RADIX['Signed'],middle=['JSR(RadixInner,1,16#FFFFFFFFFFFFFFFFL,WideFormal);'],extra=nested)
        e.step();self.assertEqual(e.memory.read('WideResult'),(1<<63)-1);self.assertEqual(e.calls.stack,[])
        events=[event for visit in e.trace for event in visit['events']]
        ret=next(event for event in events if event['instruction']=='RET' and event['args']==['16#7FFFFFFFFFFFFFFFL'])
        self.assertEqual(ret['operand_samples'],[dict(address=None,type='LINT',value=str((1<<63)-1))])

    def test_later_fault_rolls_back_warm_radix_transfers_then_retries(self):
        e=self.call('ULINT',RADIX['Largest'],ret='16#0020000000000001UL',tail=['DIV(1,LiteralDivisor,Result);'])
        e.step();e.memory.write('WideResult',77);e.memory.write('WideFormal',79);e.memory.write('LiteralDivisor',0)
        self.fault(e,'zero');e.memory.write('LiteralDivisor',1);e.step()
        self.assertEqual((e.memory.read('WideFormal'),e.memory.read('WideResult')),((1<<64)-1,9007199254740993))

    def test_call_invalid_ranges_exact_types_destinations_and_parser_boundaries_remain_guarded(self):
        for dtype,token in [('LINT','16#10000000000000000L'),('UDINT','16#100000000U'),('ULINT','8#8UL'),
                            ('LINT','16#FFLU'),('LINT','16#FF_L'),('LINT','16#FF U'),('LINT','-16#FFL'),
                            ('DINT','16#FFFFFFFF'),('LREAL','16#1L'),('LINT','16#1UL')]:
            self.assertTrue(self.call(dtype,token,gate=True,checked=False).blockers,(dtype,token))
        def constant_sbr(root):root.find('./Controller/Programs/Program/Routines/Routine[@Name="LiteralWorker"]/RLLContent/Rung/Text').text='SBR(16#1L);'
        for kwargs in [dict(dest='16#1L'),dict(ret='16#1U'),dict(extra=lambda root:root.find('Controller').set('ProcessorType','1756-L75')),
                       dict(extra=lambda root:root.find('Controller').set('MajorRev','34')),
                       dict(extra=constant_sbr),dict(tail=['CPT(Result,16#1L);'])]:
            self.assertTrue(self.call('LINT',RADIX['Signed'],checked=False,**kwargs).blockers)
        with self.assertRaises(ValueError):literal('16#FFUL')

    def test_existing_st_jsr_ret_calls_use_exact_radix_types(self):
        e=self.call('LINT',RADIX['Signed'],ret='16#FFFFFFFFFFFFFFFFL',main_st=True,callee_st=True)
        e.step();self.assertEqual((e.memory.read('WideFormal'),e.memory.read('WideResult')),(9007199254740993,-1))

    def test_public_call_sample_keeps_exact_results_direct_ret_and_late_retry(self):
        path=Path(__file__).resolve().parents[1]/'samples/CallLab.L5X';e=Engine(Project(path));self.assertEqual(e.blockers,[])
        e.memory.write('TypedCallEnabled',True);e.step()
        for name,(_,_,value) in zip(('TypedSigned','TypedUnsigned','TypedLargest','TypedPrecise'),calls.CASES):self.assertEqual(e.memory.read(name),value)
        e.memory.write('TypedSigned',77);e.memory.write('TypedCallLateDivisor',0);self.fault(e,'zero')
        e.memory.write('TypedCallLateDivisor',1);e.step();self.assertEqual(e.memory.read('TypedSigned'),9007199254740993)
        p=e.report()['routine_parameters']['typed_constants'];self.assertEqual(p['radix_bases'],[2,8,16]);self.assertFalse(p['native_runtime_parity'])


if __name__=='__main__':unittest.main()
