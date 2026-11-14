"""Exact integer/string CMP/FSC composition without widening ST or arithmetic."""
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from test_floating_string_conditions import add_strings
from test_string_operations import string_data
from logixlab.conditions import Condition
from logixlab.expressions import Expression
from logixlab.model import INT_BITS, ModelError, Project
from logixlab.runtime import Engine
from logixlab import wide_st


class IntegerStringConditionTests(unittest.TestCase):
    engine=fixtures.RadixExpressionTests.engine
    snapshot=staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault=fixtures.RadixExpressionTests.fault

    def make(self,rungs,*,dtype='ULINT',file=False,change=None,**kwargs):
        def fields(root):
            add_strings(root)
            if change:change(root)
        return self.engine(rungs,file=file,dtype=dtype,mutate=fields,**kwargs)

    def test_all_integer_types_and_six_lexical_relations(self):
        for dtype in INT_BITS:
            for relation,want in [('=',False),('<>',True),('<',False),('<=',False),('>',True),('>=',True)]:
                e=self.make([f'CMP((Source+1>Source)&&(Word{relation}OtherWord))OTE(RunLatch);'],dtype=dtype)
                e.step();self.assertEqual(e.memory.read('RunLatch'),want,(dtype,relation))

    def test_adjacent_values_beyond_float_precision_and_declared_constants_stay_exact(self):
        for dtype,suffix in [('LINT','L'),('ULINT','UL')]:
            e=self.make([f'CMP((Source>9007199254740992{suffix})&&(Word>OtherWord))OTE(RunLatch);'],dtype=dtype)
            e.memory.write('Source',9007199254740993);e.step();self.assertTrue(e.memory.read('RunLatch'))
            e.memory.write('Source',9007199254740992);e.step();self.assertFalse(e.memory.read('RunLatch'))
        for expression in ('9007199254740993UL>9007199254740992UL','16#FFFFFFFFFFFFFFFFUL>16#FFFFFFFFFFFFFFFEUL',
                '-9223372036854775808L<0L','16#FFFFFFFF=-1'):
            e=self.make([f'CMP(({expression})&&(Word>OtherWord))OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'),expression)

    def test_strings_do_not_promote_homogeneous_bitwise_bcd_roots_or_power(self):
        for expression in ('(Source AND 1UL)=1UL','(NOT 0UL)=16#FFFFFFFFFFFFFFFFUL',
                'FRD(16#12UL)=12UL','TOD(12UL)=16#12UL',
                'SQR(16000000004000000001UL)=4000000001UL','2UL**63UL=16#8000000000000000UL'):
            e=self.make([f'CMP(({expression})&&(Word>OtherWord))OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'),expression)

    def test_mixed_numeric_range_and_common_subtree_rules_remain(self):
        e=self.make(['CMP((Source+Mask=9007199254740994L)&&(Word>OtherWord))OTE(RunLatch);'],types=('LINT','DINT','LINT'),values=(9007199254740993,1,0))
        e.step();self.assertTrue(e.memory.read('RunLatch'))
        for expression,types in [('Source+Mask>0',('ULINT','LINT','ULINT')),
                ('Source+(Mask+1)>0',('LINT','DINT','LINT')),
                ('(Source AND Mask)=1',('LINT','DINT','LINT')),
                ('Source+1UL>0',('LINT','DINT','LINT'))]:
            e=self.make([f'AFI()CMP(({expression})&&(Word>OtherWord))OTE(RunLatch);'],types=types,checked=False)
            self.assertTrue(e.blockers,expression)

    def test_selected_string_alias_false_skip_and_unknown_coil(self):
        def alias(root):E.SubElement(root.find('./Controller/Tags'),'Tag',Name='SelectedCode',DataType='STRING',TagType='Alias',AliasFor='Codes[SpeedCommand]')
        e=self.make(['XIC(StartPB)CMP((Source>0)&&(SelectedCode=Word))OTE(RunLatch);'],change=alias)
        e.memory.write('SpeedCommand',99);e.memory.values['source']=None;e.step();e.memory.write('StartPB',True)
        self.fault(e,'Unknown|outside bounds');e.memory.write('Source',1);e.memory.write('SpeedCommand',1);e.memory.values['runlatch']=None;e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_eager_required_strings_numeric_faults_and_late_rollback(self):
        for expression in ('(Source>0)||(Word=OtherWord)','(Source<0)&&(Word=OtherWord)'):
            e=self.make([f'CMP({expression})OTE(RunLatch);']);e.memory.values['word']['DATA'][0]=None;self.fault(e,'unknown active')
            e.memory.write('Word.DATA[0]',66);e.memory.write('Word.LEN',13);self.fault(e,'LEN/DATA')
        for expression in ('(Word>OtherWord)||(1UL/0UL>0)','(Word=OtherWord)&&(Source>0)'):
            e=self.make([f'CMP({expression})OTE(RunLatch);'])
            if 'Source' in expression:e.memory.values['source']=None
            self.fault(e,'zero|Unknown')
        e=self.make(['CMP((Source>0)&&(Word>OtherWord))OTE(RunLatch);','DIV(1,SpeedCommand,SpeedCommand);'])
        e.memory.write('SpeedCommand',0);self.fault(e,'zero');e.memory.write('SpeedCommand',1);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_string_math_category_mismatches_and_cpt_fal_remain_blocked(self):
        for expression in ('Source+Word>0','(Source>0)&&(Word=1)','(Source>0)&&(Word=StartPB)',
                '(Source>0)&&Word','(Source>0)&&(ABS(Word)>0)',"(Source>0)&&(Word='B')",'(Source>0)&&(-Word=OtherWord)'):
            self.assertTrue(self.make([f'AFI()CMP({expression})OTE(RunLatch);'],checked=False).blockers,expression)
        self.assertTrue(self.make(['AFI()CPT(Dest,Source+Word);'],checked=False).blockers)
        self.assertTrue(self.make(['AFI()FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Word);'],file=True,checked=False).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.make(['AFI()CMP((Source>0)&&(Word>OtherWord))OTE(RunLatch);'],change=lambda root:root.find('Controller').set(key,value),checked=False).blockers)

    def test_fsc_all_numeric_inc_match_inhibit_and_live_string_resume(self):
        for dtype in ('USINT','UINT','UDINT','LINT','ULINT'):
            for mode in ('ALL','1','INC'):
                e=self.make([f'XIC(StartPB)FSC(Ctl,?,?,{mode},(Queue[Ctl.POS]>0)&&(Codes[Ctl.POS]=Word));'],dtype=dtype,file=True)
                e.memory.write('StartPB',True);e.step()
                if mode=='1':e.memory.write('StartPB',False);e.step()
                elif mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
                self.assertTrue(e.memory.read('Ctl.FD'));self.assertEqual(e.memory.read('Ctl.POS'),1)
                e.step();self.assertEqual(e.memory.read('Ctl.POS'),1);e.memory.write('Ctl.IN',False);e.memory.write_string('Word','D')
                if mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True)
                e.step()
                if mode=='1':e.step()
                elif mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
                self.assertTrue(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Ctl.POS'),3)

    def test_mid_search_unknown_byte_and_numeric_false_continuation_repair(self):
        for mode in ('ALL','1'):
            e=self.make([f'XIC(StartPB)FSC(Ctl,?,?,{mode},(Queue[Ctl.POS]>0)&&(Codes[Ctl.POS]=Word));'],file=True)
            e.memory.values['codes'][1]['DATA'][0]=None;e.memory.write('StartPB',True)
            if mode=='1':e.step();e.memory.write('StartPB',False)
            self.fault(e,'unknown active');self.assertEqual(e.memory.read('Ctl.POS'),0)
            e.memory.write('Codes[1].DATA[0]',66);e.step();self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('Ctl.FD'))

    def test_udt_members_empty_prefix_extended_bytes_and_unused_data(self):
        def record(root):
            dtype=E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='CodeRecord',Family='NoFamily',Class='User');members=E.SubElement(dtype,'Members')
            E.SubElement(members,'Member',Name='Part',DataType='STRING',Dimension='0')
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Record',DataType='CodeRecord',TagType='Base')
            obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='CodeRecord');string_data(obj,'B',member='Part')
        e=self.make(['CMP((Source>0)&&(Record.Part=Word))OTE(RunLatch);'],change=record);e.step();self.assertTrue(e.memory.read('RunLatch'))
        self.assertIsNone(e.memory.values['word']['DATA'][1])
        for left,right,want in [('','A',True),('A','AB',True),('a','B',False),('\x7f','\x80',True)]:
            e=self.make(['CMP((Source>0)&&(Word<OtherWord))OTE(RunLatch);']);e.memory.write_string('Word',left);e.memory.write_string('OtherWord',right);e.step();self.assertEqual(e.memory.read('RunLatch'),want)

    def test_warm_aoi_string_inout_and_st_parser_scope(self):
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
                text.text=text.text.replace('Input[Find.POS]>=Threshold','(9007199254740993UL>9007199254740992UL)&&(Label=Expected)')
        e=h.checked(fields,kind='1');e.memory.write('Search',True);e.step();self.assertTrue(e.memory.read('FindA.FD'));self.assertFalse(e.memory.read('FindB.FD'))
        e.memory.write('Search',False);e.memory.write_string('LabelB','B');e.step();self.assertTrue(e.memory.read('FindB.FD'));self.assertEqual(e.memory.read('FindB.POS'),1)
        e=self.make(['NOP();']);condition=Condition('(Source>0)&&(Word>OtherWord)',allow_wide=True)
        self.assertIsNotNone(wide_st.analyze(condition,e.memory,consumer='CMP'))
        with self.assertRaises(ModelError):wide_st.analyze(condition,e.memory,consumer='ST')
        with self.assertRaises(ModelError):Condition('(Source>0)&&(Word>OtherWord)').validate(e.memory)
        with self.assertRaises(ModelError):Expression('1UL')

    def test_public_example_exact_values_code_changes_and_rollback(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('IntegerStringEnabled',True);self.fault(e,'outside bounds');e.memory.write('IntegerStringIndex',1);e.step()
        for name in ('Match','Exact','PatternMatch','Mixed'):self.assertTrue(e.memory.read('IntegerString'+name),name)
        e.memory.write('IntegerStringSource',9007199254740992);e.step();self.assertFalse(e.memory.read('IntegerStringMatch'));self.assertFalse(e.memory.read('IntegerStringExact'));self.assertFalse(e.memory.read('IntegerStringPatternMatch'));self.assertTrue(e.memory.read('IntegerStringMixed'))
        e.memory.write('IntegerStringSource',9007199254740993);e.memory.write('StringNumericNeedle.DATA[5]',66);e.step()
        for name in ('Match','Exact','PatternMatch','Mixed'):self.assertFalse(e.memory.read('IntegerString'+name))
        e.memory.write('StringNumericNeedle.DATA[5]',65);e.memory.write('IntegerStringLateDivisor',0);self.fault(e,'zero');e.memory.write('IntegerStringLateDivisor',1);e.step();self.assertTrue(e.memory.read('IntegerStringMatch'))
        e.memory.write('IntegerStringInhibit',True);e.step();self.assertFalse(e.memory.read('IntegerStringMatch'));self.assertTrue(e.memory.read('IntegerStringExact'))
        report=e.report()['wide_ladder_expressions']['string_conditions'];self.assertEqual(report['consumers'],['CMP','FSC']);self.assertFalse(report['native_runtime_parity'])


if __name__=='__main__':unittest.main()
