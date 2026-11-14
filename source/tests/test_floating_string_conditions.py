"""Active-byte string relations composed with REAL/LREAL ladder conditions."""
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from test_string_operations import string_data
from logixlab.conditions import Condition
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine


def add_strings(root):
    types=root.find('./Controller/DataTypes')
    dtype=E.SubElement(types,'DataType',Name='CODE_12',Family='String',Class='User');members=E.SubElement(dtype,'Members')
    E.SubElement(members,'Member',Name='LEN',DataType='DINT',Dimension='0')
    E.SubElement(members,'Member',Name='DATA',DataType='SINT',Dimension='12')
    tags=root.find('./Controller/Tags')
    for name,dtype,value in [('Word','CODE_12','B'),('OtherWord','STRING','A')]:
        tag=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType=dtype)
        string_data(E.SubElement(tag,'Data',Format='Decorated'),value,12 if dtype=='CODE_12' else 82,dtype)
    tag=E.SubElement(tags,'Tag',Name='Codes',TagType='Base',DataType='STRING',Dimensions='5')
    array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='STRING',Dimensions='5')
    for i,value in enumerate(('A','B','C','D','GUARD')):string_data(E.SubElement(array,'Element',Index=f'[{i}]'),value)
    for obj in tags.iter():
        array=obj.find('./ArrayMember[@Name="DATA"]')
        if array is None:continue
        length=int(obj.find('./DataValueMember[@Name="LEN"]').get('Value'))
        for element in list(array):
            if int(element.get('Index')[1:-1])>=length:array.remove(element)


class FloatingStringConditionTests(unittest.TestCase):
    engine=fixtures.RadixExpressionTests.engine
    snapshot=staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault=fixtures.RadixExpressionTests.fault

    def make(self,rungs,*,precision='REAL',file=False,change=None,**kwargs):
        def fields(root):
            add_strings(root)
            if change:change(root)
        return self.engine(rungs,file=file,dtype='ULINT' if precision=='REAL' else 'LREAL',mutate=fields,**kwargs)

    def test_six_relations_cross_capacity_active_bytes_and_both_precisions(self):
        for precision in ('REAL','LREAL'):
            for op,want in [('=',False),('<>',True),('<',False),('<=',False),('>',True),('>=',True)]:
                e=self.make([f'CMP((Source+0.0>0)&&(Word{op}OtherWord))OTE(RunLatch);'],precision=precision)
                e.step();self.assertEqual(e.memory.read('RunLatch'),want,(precision,op))
                e.memory.write_string('OtherWord','B');e.step();self.assertEqual(e.memory.read('RunLatch'),op in ('=','<=','>='))
            for left,right,want in [('A','AB',True),('a','B',False),('\x7f','\x80',True),('','A',True)]:
                e=self.make(['CMP((Source+0.0>0)&&(Word<OtherWord))OTE(RunLatch);'],precision=precision)
                e.memory.write_string('Word',left);e.memory.write_string('OtherWord',right);e.step();self.assertEqual(e.memory.read('RunLatch'),want)

    def test_numeric_precision_typed_literals_implicit_functions_and_bool_composition(self):
        for expression,want in [('(16777217U+0.0=16777216U)&&(Word>OtherWord)',True),
                ('(16777217U-16777216.0L=1)&&(Word>OtherWord)',True),
                ('(SIN(1UL)>0) AND (Word>OtherWord)',True),
                ('(Word>OtherWord) XOR (Source+0.0>0)',False),
                ('NOT (Word<OtherWord)&&!StartPB',True)]:
            # Last expression includes a REAL selector but leaves its truth value unchanged.
            if 'Source' not in expression and not any(s in expression for s in ('U','L')):expression+='&&(Source+0.0>0)'
            e=self.make([f'CMP({expression})OTE(RunLatch);']);e.step();self.assertEqual(e.memory.read('RunLatch'),want,expression)

    def test_false_prescan_selected_alias_and_unknown_destination_coil(self):
        def aliases(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='SelectedCode',DataType='STRING',TagType='Alias',AliasFor='Codes[SpeedCommand]')
        e=self.make(['XIC(StartPB)CMP((Source+0.0>0)&&(SelectedCode=Word))OTE(RunLatch);'],change=aliases)
        e.memory.write('SpeedCommand',99);e.memory.values['source']=None;e.step()
        e.memory.write('StartPB',True);self.fault(e,'Unknown|outside bounds')
        e.memory.write('Source',1);e.memory.write('SpeedCommand',1);e.memory.values['runlatch']=None;e.step();self.assertTrue(e.memory.read('RunLatch'))
        e.memory.write_string('Word','C');e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_eager_false_and_true_sides_require_string_length_bytes_and_numbers(self):
        for precision in ('REAL','LREAL'):
            for expression in ('(Source+0.0>0)||(Word=OtherWord)','(Source+0.0<0)&&(Word=OtherWord)'):
                e=self.make([f'CMP({expression})OTE(RunLatch);'],precision=precision)
                e.memory.values['word']['DATA'][0]=None;self.fault(e,'unknown active')
                e.memory.write('Word.DATA[0]',66);e.memory.write('Word.LEN',13);self.fault(e,'LEN/DATA')
            e=self.make(['CMP((Word=OtherWord)&&(Source+0.0>0))OTE(RunLatch);'],precision=precision)
            e.memory.values['source']=None;self.fault(e,'Unknown')
            e=self.make(['CMP((Word>OtherWord)||(1UL/0.0>0))OTE(RunLatch);'],precision=precision);self.fault(e,'zero')

    def test_udt_string_members_and_aliases_keep_active_byte_rules(self):
        def record(root):
            dtype=E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='CodeRecord',Family='NoFamily',Class='User')
            members=E.SubElement(dtype,'Members');E.SubElement(members,'Member',Name='Part',DataType='STRING',Dimension='0')
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Record',DataType='CodeRecord',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='CodeRecord');string_data(obj,'B',member='Part')
            E.SubElement(root.find('./Controller/Tags'),'Tag',Name='AliasPart',DataType='STRING',TagType='Alias',AliasFor='Record.Part')
        for precision in ('REAL','LREAL'):
            e=self.make(['CMP((Source+0.0>0)&&(AliasPart=Word))OTE(RunLatch);'],precision=precision,change=record)
            e.step();self.assertTrue(e.memory.read('RunLatch'));e.memory.write_string('Record.Part','A');e.step();self.assertFalse(e.memory.read('RunLatch'))
            e.memory.values['record']['Part']['DATA'][0]=None;self.fault(e,'unknown active')

    def test_invalid_string_math_mismatches_and_cpt_stay_blocked(self):
        for precision in ('REAL','LREAL'):
            for expression in ('(Source+0.0>0)&&(Word=1)','(Source+0.0>0)&&(Word=StartPB)',
                    '(Source+Word>0)','(Source+0.0>0)&&Word','(Source+0.0>0)&&(SIN(Word)>0)',
                    '(Source+0.0>0)&&(-Word=OtherWord)',"(Source+0.0>0)&&(Word='B')"):
                e=self.make([f'AFI()CMP({expression})OTE(RunLatch);'],precision=precision,checked=False);self.assertTrue(e.blockers,expression)
            self.assertTrue(self.make(['AFI()CPT(Dest,Source+Word+0.0);'],precision=precision,checked=False).blockers)
            self.assertTrue(self.make(['AFI()FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Word+0.0);'],precision=precision,file=True,checked=False).blockers)

    def test_structural_string_schema_and_controller_guards(self):
        def invalid(root):root.find('.//DataType[@Name="CODE_12"]/Members/Member[@Name="DATA"]').set('DataType','DINT')
        self.assertTrue(self.make(['AFI()CMP((Source+0.0>0)&&(Word=OtherWord))OTE(RunLatch);'],change=invalid,checked=False).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.make(['AFI()CMP((Source+0.0>0)&&(Word=OtherWord))OTE(RunLatch);'],change=lambda root:root.find('Controller').set(key,value),checked=False).blockers)

    def test_fsc_all_numeric_inc_match_hold_and_live_string_resume(self):
        for precision in ('REAL','LREAL'):
            for mode in ('ALL','1','INC'):
                e=self.make([f'XIC(StartPB)FSC(Ctl,?,?,{mode},(Queue[Ctl.POS]+0.0>0)&&(Codes[Ctl.POS]=Word));'],precision=precision,file=True)
                e.memory.write('StartPB',True);e.step()
                if mode=='1':e.memory.write('StartPB',False);e.step()
                elif mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
                self.assertTrue(e.memory.read('Ctl.FD'));self.assertEqual(e.memory.read('Ctl.POS'),1)
                e.step();self.assertEqual(e.memory.read('Ctl.POS'),1)
                e.memory.write('Ctl.IN',False);e.memory.write_string('Word','D')
                if mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True)
                e.step()
                if mode=='1':e.step()
                elif mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
                self.assertEqual(e.memory.read('Ctl.POS'),3);self.assertTrue(e.memory.read('Ctl.FD'));self.assertTrue(e.memory.read('Ctl.DN'))

    def test_mid_search_unknown_active_byte_rolls_back_and_repairs(self):
        for precision in ('REAL','LREAL'):
            e=self.make(['FSC(Ctl,?,?,ALL,(Queue[Ctl.POS]+0.0>0)&&(Codes[Ctl.POS]=Word));'],precision=precision,file=True)
            e.memory.values['codes'][1]['DATA'][0]=None;self.fault(e,'unknown active')
            e.memory.write('Codes[1].DATA[0]',66);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('Ctl.FD'))

    def test_numeric_false_continuation_fault_and_repair_preserve_committed_cursor(self):
        e=self.make(['XIC(StartPB)FSC(Ctl,?,?,1,(Queue[Ctl.POS]+0.0>0)&&(Codes[Ctl.POS]=Word));'],file=True)
        e.memory.write('StartPB',True);e.step();e.memory.write('StartPB',False);e.memory.values['codes'][1]['DATA'][0]=None
        self.fault(e,'unknown active');self.assertEqual(e.memory.read('Ctl.POS'),0)
        e.memory.write('Codes[1].DATA[0]',66);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('Ctl.FD'))

    def test_late_fault_and_unused_string_bytes_remain_transactional(self):
        e=self.make(['CMP((Source+0.0>0)&&(Word>OtherWord))OTE(RunLatch);','DIV(1,SpeedCommand,SpeedCommand);'])
        e.memory.write('SpeedCommand',0);self.fault(e,'zero');e.memory.write('SpeedCommand',1);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertIsNone(e.memory.values['word']['DATA'][2]);e.memory.write('Word.LEN',0);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_warm_aoi_string_inout_binding_and_generic_parser_scope(self):
        import test_aoi_files as aois
        h=aois.AOIFileTests();h.setUp();self.addCleanup(h.doCleanups)
        def fields(root):
            tags=root.find('./Controller/Tags')
            for name,value in [('LabelA','B'),('LabelB','A'),('Expected','B')]:
                tag=E.SubElement(tags,'Tag',Name=name,DataType='STRING',TagType='Base');string_data(E.SubElement(tag,'Data',Format='Decorated'),value)
            params=root.find('.//AddOnInstructionDefinition/Parameters')
            for name in ('Label','Expected'):E.SubElement(params,'Parameter',Name=name,DataType='STRING',TagType='Base',Usage='InOut',Required='true',Visible='true',Constant='false')
            for text in root.findall('.//Programs/Program/Routines/Routine/RLLContent/Rung/Text'):
                for suffix in ('A','B'):text.text=text.text.replace(f'Calc{suffix},Find{suffix})',f'Calc{suffix},Find{suffix},Label{suffix},Expected)')
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                text.text=text.text.replace('Input[Find.POS]>=Threshold','(Input[Find.POS]+0UL+0.5>0)&&(Label=Expected)')
        e=h.checked(fields,kind='1');e.memory.write('Search',True);e.step();self.assertTrue(e.memory.read('FindA.FD'));self.assertFalse(e.memory.read('FindB.FD'))
        e.memory.write('Search',False);e.memory.write_string('LabelB','B');e.step();self.assertTrue(e.memory.read('FindB.FD'));self.assertEqual(e.memory.read('FindB.POS'),1)
        e=self.make(['NOP();'])
        with self.assertRaises(ModelError):Condition('(Source+0.0>0)&&(Word=OtherWord)').validate(e.memory)

    def test_public_example_both_precisions_active_bytes_faults_and_report(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('StringNumericEnabled',True);self.fault(e,'outside bounds');e.memory.write('StringNumericIndex',1);e.step()
        self.assertTrue(e.memory.read('StringNumericRealMatch'));self.assertTrue(e.memory.read('StringNumericDoubleMatch'))
        e.memory.write('StringNumericNeedle.DATA[5]',66);e.step();self.assertFalse(e.memory.read('StringNumericRealMatch'));self.assertFalse(e.memory.read('StringNumericDoubleMatch'))
        e.memory.write('StringNumericNeedle.DATA[5]',65);e.memory.write('StringNumericLateDivisor',0);self.fault(e,'zero')
        e.memory.write('StringNumericLateDivisor',1);e.step();self.assertTrue(e.memory.read('StringNumericRealMatch'))
        self.assertIsNone(e.memory.values['stringnumericneedle']['DATA'][6]);e.memory.write('StringNumericInhibit',True);e.step();self.assertFalse(e.memory.read('StringNumericRealMatch'))
        for name in ('real_expression_execution','lreal_expression_execution'):
            row=e.report()[name];self.assertIn('active bytes',row['strings']);self.assertFalse(row['native_runtime_parity'])


if __name__=='__main__':unittest.main()
