"""Qualified temporal constants: exact lexer boundaries, units, dates and files."""
import itertools
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_time_conditions as fixtures
from test_string_operations import string_data
from logixlab.conditions import Condition
from logixlab.expressions import Expression
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine
from logixlab import time_values

TOKENS={'TIME32':'T32#1us','TIME':'T#1us','LTIME':'LT#1us',
        'DT':'DT#2026-01-01-00:00:00.000_001','LDT':'LDT#2026-01-01-00:00:00.000_001_000'}


class TimeConditionLiteralTests(unittest.TestCase):
    engine=fixtures.TimeConditionTests.engine
    make=fixtures.TimeConditionTests.make
    snapshot=staticmethod(fixtures.TimeConditionTests.snapshot)
    fault=fixtures.TimeConditionTests.fault

    def test_constant_pairs_all_families_and_six_relations(self):
        for family in (('TIME32','TIME','LTIME'),('DT','LDT')):
            for left,right in itertools.product(family,repeat=2):
                for token,want in [('=',True),('<>',False),('<',False),('<=',True),('>',False),('>=',True)]:
                    e=self.make([f'CMP(({TOKENS[left]}{token}{TOKENS[right]})&&(Word>OtherWord))OTE(RunLatch);'])
                    e.step();self.assertEqual(e.memory.read('RunLatch'),want,(left,right,token))

    def test_tag_literal_both_orders_all_family_pairs_and_one_tick(self):
        for dtype,token in TOKENS.items():
            value=time_values.literal(token)[1]
            for other,threshold in TOKENS.items():
                if not time_values.same_family(dtype,other):continue
                for expr in (f'Source>{threshold}',f'{threshold}<Source'):
                    e=self.make([f'CMP({expr})OTE(RunLatch);'],source=dtype,other=dtype,values=(value,0,0))
                    e.step();self.assertFalse(e.memory.read('RunLatch'));e.memory.write('Source',value+1);e.step();self.assertTrue(e.memory.read('RunLatch'),(dtype,expr))

    def test_negative_zero_and_declared_range_endpoints(self):
        for expression in ('LT#-1us_1ns<T#-1us','T32#-2147483647us=T#-2147483647us',
                'LT#0ns=T#0s','LT#31d_12h_59m_59s_999ms_999us_999ns> T#31d_12h_59m_59s_999ms_999us',
                'LDT#2250-12-31-23:59:59.999_999_999>DT#2250-12-31-23:59:59.999_999'):
            e=self.make([f'CMP({expression})OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'),expression)

    def test_grouped_date_fractions_offsets_and_case(self):
        for expression in ('DT#2026-01-01-08:00:00(UTC+08:00)=LDT#2026-01-01-00:00:00',
                'DT#2025-12-31-19:00:00 (UTC-05:00)=LDT#2026-01-01-00:00:00',
                'DT#2026-01-01-00:00:00.123_456=LDT#2026-01-01-00:00:00.123_456_000',
                'LDT#2026-01-01-00:00:00.123456789>DT#2026-01-01-00:00:00.123456',
                'ldt#2026-01-01-08:00:00.000_000_001 (utc+08:00)>dt#2026-01-01-00:00:00',
                'lt#1us_1ns>t32#1us'):
            e=self.make([f'CMP({expression})OTE(RunLatch);']);e.step();self.assertTrue(e.memory.read('RunLatch'),expression)

    def test_scanner_positions_and_expression_delimiters(self):
        for token in (*TOKENS.values(),'LT#-1us_1ns','DT#2026-01-01-08:00:00 (UTC+08:00)'):
            dtype,value=time_values.literal(token)
            for ending in (')','>=Source',' && StartPB',','):
                end,result=time_values.scan('xx '+token+ending,3);self.assertEqual((end,result),(3+len(token),(value,dtype)),(token,ending))
        self.assertIsNone(time_values.scan('Source',0))

    def test_invalid_constants_are_blockers_on_false_rungs(self):
        for token in ('T#1ns','T32#2147483648us','T32#-2147483648us','T#32d','LT#32d',
                'LT#1s_1m','LT#1s_1s','T#','T#-','T#1','T#1s_',
                'DT#2026-02-30-00:00:00','DT#1969-12-31-23:59:59','LDT#2251-01-01-00:00:00',
                'DT#2026-01-01-00:00:00.000_000_001','DT#2026-01-01-00:00:00(UTC+24:00)',
                'LDT#2026-01-01-00:00:00.123_4567','LDT#2026-01-01-00:00:00.1234567890'):
            self.assertTrue(self.make([f'AFI()CMP(Source>{token})OTE(RunLatch);'],checked=False).blockers,token)

    def test_parser_scope_cache_keys_and_literal_boundaries(self):
        for create in (Expression,lambda t:Expression(t,structured=True),lambda t:Expression(t,subscript=True),
                Condition,lambda t:Condition(t,allow_wide=True),lambda t:Condition(t,lreal=True)):
            with self.assertRaises(ModelError):create('T#1us>T#0s')
        with self.assertRaises(ModelError):Expression('T#1us',temporal_literals=True).validate(None)
        with self.assertRaises(ModelError):Expression('T#1us',condition=True,structured=True,temporal_literals=True)
        for text in ('LT#1nsabc','DT#2026-01-01-00:00:00foo','LT#1ns_','LT#1ns#2'):
            self.assertTrue(self.make([f'AFI()CMP({text}>T#0s)OTE(RunLatch);'],checked=False).blockers,text)
        e=self.make(['NOP();']);condition=e.extensions.condition('LT#1ns>T#0s',allow_wide=True,lreal=True)
        self.assertEqual(condition.temporal_types,{'LTIME','TIME'});self.assertTrue(condition.evaluate(e.memory))
        self.assertIs(condition,e.extensions.condition('LT#1ns>T#0s',allow_wide=True,lreal=True))
        with self.assertRaises(ModelError):e.extensions.condition('LT#1ns>T#0s')
        self.assertTrue(self.make(['AFI()CPT(Dest,DT#1970-01-01-00:00:00);'],checked=False).blockers)
        self.assertTrue(self.make(['AFI()FAL(Ctl,?,?,ALL,Queue[Ctl.POS],DT#1970-01-01-00:00:00);'],file=True,checked=False).blockers)

    def test_cross_family_numeric_and_arithmetic_exclusions(self):
        for expression in ('T#1us>DT#2026-01-01-00:00:00','T#1us>1','T#1us>1UL','T#1us>1.0L',
                'T#1us*LT#1ns>T#0s','-DT#1970-01-01-00:00:00<DT#1970-01-01-00:00:00','ABS(T#1us)>T#0s',
                '(T#1us>T#0s)&&(SpeedCommand=SpeedCommand)','(T#1us>T#0s)&&(Word=1)'):
            self.assertTrue(self.make([f'AFI()CMP({expression})OTE(RunLatch);'],checked=False).blockers,expression)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.make(['AFI()CMP(T#1us>T#0s)OTE(RunLatch);'],change=lambda root:root.find('Controller').set(key,value),checked=False).blockers)

    def test_constant_truth_does_not_hide_required_unknowns(self):
        e=self.make(['CMP((LT#1ns>T#0s)||(Word=OtherWord))OTE(RunLatch);']);e.memory.values['word']['DATA'][0]=None;self.fault(e,'unknown active')
        e=self.make(['CMP((LT#1ns<T#0s)&&(Source>Mask))OTE(RunLatch);']);e.memory.values['source']=None;self.fault(e,'Unknown')
        e=self.make(['CMP(Source>T#1us)OTE(RunLatch);','DIV(1,SpeedCommand,SpeedCommand);'])
        e.memory.write('SpeedCommand',0);self.fault(e,'zero');e.memory.write('SpeedCommand',1);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_fsc_all_types_modes_and_live_string_resume(self):
        for dtype in time_values.TYPES:
            threshold='LDT#1970-01-01-00:00:00' if dtype in time_values.DATE_TYPES else 'LT#0ns'
            for mode in ('ALL','1','INC'):
                e=self.make([f'XIC(StartPB)FSC(Ctl,?,?,{mode},(Queue[Ctl.POS]>{threshold})&&(Codes[Ctl.POS]=Word));'],source=dtype,file=True)
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

    def test_literal_only_file_conditions_do_not_require_temporal_tags(self):
        for mode in ('ALL','1','INC'):
            e=self.make([f'XIC(StartPB)FSC(Ctl,?,?,{mode},(LT#1ns>T#0s)&&(DT#2026-01-01-00:00:00=LDT#2026-01-01-00:00:00));'],source='DINT',file=True)
            e.memory.write('StartPB',True);e.step();self.assertTrue(e.memory.read('Ctl.FD'));self.assertEqual(e.memory.read('Ctl.POS'),0)

    def test_mid_search_unknown_temporal_or_string_and_false_continuation_repair(self):
        for mode,missing in itertools.product(('ALL','1'),('time','string')):
            e=self.make([f'XIC(StartPB)FSC(Ctl,?,?,{mode},(Queue[Ctl.POS]>T#0s)&&(Codes[Ctl.POS]=Word));'],source='TIME',file=True)
            if missing=='time':e.memory.values['queue'][1]=None
            else:e.memory.values['codes'][1]['DATA'][0]=None
            e.memory.write('StartPB',True)
            if mode=='1':e.step();e.memory.write('StartPB',False)
            self.fault(e,'Unknown|unknown active');e.memory.write('Queue[1]',4);e.memory.write('Codes[1].DATA[0]',66);e.step();self.assertTrue(e.memory.read('Ctl.FD'));self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_warm_aoi_temporal_literal_and_string_inout_bindings(self):
        import test_aoi_files as aois
        h=aois.AOIFileTests();h.setUp();self.addCleanup(h.doCleanups)
        def fields(root):
            tags=root.find('./Controller/Tags')
            for name,value in [('FineA',1001),('FineB',1000)]:
                tag=E.SubElement(tags,'Tag',Name=name,DataType='LTIME',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='LTIME',Value=str(value))
            for name in ('LabelA','LabelB','Expected'):
                tag=E.SubElement(tags,'Tag',Name=name,DataType='STRING',TagType='Base');string_data(E.SubElement(tag,'Data',Format='Decorated'),'B')
            params=root.find('.//AddOnInstructionDefinition/Parameters')
            for name,dtype in [('Fine','LTIME'),('Label','STRING'),('Expected','STRING')]:E.SubElement(params,'Parameter',Name=name,DataType=dtype,TagType='Base',Usage='InOut',Required='true',Visible='true',Constant='false')
            for text in root.findall('.//Programs/Program/Routines/Routine/RLLContent/Rung/Text'):
                for suffix in ('A','B'):text.text=text.text.replace(f'Calc{suffix},Find{suffix})',f'Calc{suffix},Find{suffix},Fine{suffix},Label{suffix},Expected)')
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('Input[Find.POS]>=Threshold','(Fine>T#1us)&&(Label=Expected)')
        e=h.checked(fields,kind='1');e.memory.write('Search',True);e.step();self.assertTrue(e.memory.read('FindA.FD'));self.assertFalse(e.memory.read('FindB.FD'))
        e.memory.write('Search',False);e.memory.write('FineB',1001);e.step();self.assertTrue(e.memory.read('FindB.FD'));self.assertEqual(e.memory.read('FindB.POS'),1)

    def test_public_example_live_sources_codes_faults_and_literal_report(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('TimeLiteralEnabled',True);self.fault(e,'outside bounds');e.memory.write('TimeLiteralIndex',1);e.step()
        names=('DurationMatch','StampMatch','ConstantMatch','Combined')
        self.assertEqual([e.memory.read('TimeLiteral'+n) for n in names],[True]*4)
        e.memory.write('TemporalHighDuration',1000);e.step();self.assertEqual([e.memory.read('TimeLiteral'+n) for n in names],[False,True,True,True])
        e.memory.write('TemporalHighDuration',1001);e.memory.write('TemporalHighStamp',1767225600000001000);e.step();self.assertEqual([e.memory.read('TimeLiteral'+n) for n in names],[True,False,True,False])
        e.memory.write('TemporalHighStamp',1767225600000001001);e.memory.write('TimeLiteralLateDivisor',0);self.fault(e,'zero');e.memory.write('TimeLiteralLateDivisor',1);e.step();self.assertTrue(e.memory.read('TimeLiteralCombined'))
        e.memory.write('StringNumericNeedle.DATA[5]',66);e.step();self.assertFalse(e.memory.read('TimeLiteralCombined'));self.assertTrue(e.memory.read('TimeLiteralConstantMatch'))
        row=e.report()['numeric_comparisons']['time_date']['conditions'];self.assertTrue(row['literal_only']);self.assertEqual(set(row['literal_types']),set(time_values.TYPES));self.assertFalse(row['native_runtime_parity'])


if __name__=='__main__':unittest.main()
