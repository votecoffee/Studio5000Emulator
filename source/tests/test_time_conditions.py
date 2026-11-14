"""Exact temporal CMP/FSC tag relations, eager operands and existing file modes."""
import itertools
import operator
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

import test_radix_expressions as fixtures
from test_floating_string_conditions import add_strings
from test_string_operations import string_data
from logixlab.conditions import Condition
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine
from logixlab import time_values


class TimeConditionTests(unittest.TestCase):
    engine=fixtures.RadixExpressionTests.engine
    snapshot=staticmethod(fixtures.RadixExpressionTests.snapshot)
    fault=fixtures.RadixExpressionTests.fault

    def make(self,rungs,*,source='LTIME',other='TIME',values=(1001,1,0),file=False,change=None,**kwargs):
        def fields(root):
            add_strings(root)
            if change:change(root)
        if not file:kwargs.update(types=(source,other,source),values=values)
        return self.engine(rungs,file=file,dtype=source,mutate=fields,**kwargs)

    def test_all_same_family_pairs_six_relations_and_exact_tick_increments(self):
        relations=[('=',operator.eq),('<>',operator.ne),('<',operator.lt),('<=',operator.le),('>',operator.gt),('>=',operator.ge)]
        for family in (('TIME32','TIME','LTIME'),('DT','LDT')):
            base=1000 if family[0]=='TIME32' else 1767225600000001000
            for left,right in itertools.product(family,repeat=2):
                a=base//time_values.ns_per_tick(left);b=base//time_values.ns_per_tick(right)
                for token,compare in relations:
                    e=self.make([f'CMP((Source{token}Mask)&&(Word>OtherWord))OTE(RunLatch);'],source=left,other=right,values=(a,b,0))
                    e.step();self.assertEqual(e.memory.read('RunLatch'),compare(base,base),(left,right,token))
                    e.memory.write('Source',a+1);e.step();self.assertEqual(e.memory.read('RunLatch'),compare(base+time_values.ns_per_tick(left),base))

    def test_negative_durations_and_nanosecond_dates_do_not_round_through_float(self):
        e=self.make(['CMP(Source<Mask)OTE(RunLatch);'],values=(-1001,-1,0));e.step();self.assertTrue(e.memory.read('RunLatch'))
        e.memory.write('Source',-1000);e.step();self.assertFalse(e.memory.read('RunLatch'))
        e=self.make(['CMP(Source>Mask)OTE(RunLatch);'],source='LDT',other='DT',values=(1767225600000001001,1767225600000001,0))
        e.step();self.assertTrue(e.memory.read('RunLatch'));e.memory.write('Source',1767225600000001000);e.step();self.assertFalse(e.memory.read('RunLatch'))

    def test_boolean_composition_supports_separate_time_families(self):
        def dates(root):
            tags=root.find('./Controller/Tags')
            for name,dtype,value in [('FineStamp','LDT',1767225600000001001),('Stamp','DT',1767225600000001)]:
                tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(value))
        for expression,want in [('(Source>Mask)&&(FineStamp>Stamp)',True),('(Source>Mask) AND !StartPB',True),
                ('(Source>Mask) XOR (FineStamp>Stamp)',False),('(Source<Mask)||(FineStamp>Stamp)',True),
                ('NOT (Source<Mask)&&!StartPB',True),('(Source>Mask)^^(Word>OtherWord)',False)]:
            e=self.make([f'CMP({expression})OTE(RunLatch);'],change=dates);e.step();self.assertEqual(e.memory.read('RunLatch'),want,expression)

    def test_family_numeric_literal_math_shape_and_controller_guards(self):
        for expression in ('Source>SpeedCommand','Source>1','Source>1UL','Source>1.0L','Source>T#1ns',
                '(Source+Mask)>Source','ABS(Source)>Mask','Source','-Source>Mask','Source>StartPB',
                '(Source>Mask)&&(SpeedCommand=SpeedCommand)','(Source>Mask)&&(Word=1)'):
            self.assertTrue(self.make([f'AFI()CMP({expression})OTE(RunLatch);'],checked=False).blockers,expression)
        self.assertTrue(self.make(['AFI()CMP(Source>Mask)OTE(RunLatch);'],source='LDT',other='TIME',checked=False).blockers)
        self.assertTrue(self.make(['AFI()CPT(Dest,Source);'],checked=False).blockers)
        self.assertTrue(self.make(['AFI()FAL(Ctl,?,?,ALL,Queue[Ctl.POS],Incoming);'],file=True,checked=False).blockers)
        for key,value in [('ProcessorType','1756-L75'),('MajorRev','34')]:
            self.assertTrue(self.make(['AFI()CMP(Source>Mask)OTE(RunLatch);'],change=lambda root:root.find('Controller').set(key,value),checked=False).blockers)
        def array(root):
            tag=root.find('./Controller/Tags/Tag[@Name="Source"]');tag.set('Dimensions','2');tag.remove(tag.find('Data'))
            E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='LTIME',Dimensions='2')
        self.assertTrue(self.make(['AFI()CMP(Source>Mask)OTE(RunLatch);'],change=array,checked=False).blockers)

    def test_false_prescan_alias_live_indices_and_unknown_coil(self):
        def selected(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="Source"]');tag.set('Dimensions','2');tag.remove(tag.find('Data'))
            array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='LTIME',Dimensions='2');E.SubElement(array,'Element',Index='[1]',Value='1001')
            E.SubElement(tags,'Tag',Name='SelectedTime',DataType='LTIME',TagType='Alias',AliasFor='Source[SpeedCommand]')
        e=self.make(['XIC(StartPB)CMP((SelectedTime>Mask)&&(Word>OtherWord))OTE(RunLatch);'],change=selected)
        e.memory.write('SpeedCommand',99);e.step();e.memory.write('StartPB',True);self.fault(e,'outside bounds')
        e.memory.write('SpeedCommand',0);self.fault(e,'Unknown');e.memory.write('SpeedCommand',1);e.memory.values['runlatch']=None;e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_eager_temporal_and_string_operands_fault_atomically(self):
        for expression in ('StartPB||(Source>Mask)','!StartPB&&(Source>Mask)'):
            e=self.make([f'CMP({expression})OTE(RunLatch);']);e.memory.write('StartPB',True);e.memory.values['source']=None;self.fault(e,'Unknown')
        for expression in ('(Source>Mask)||(Word=OtherWord)','(Source<Mask)&&(Word=OtherWord)'):
            e=self.make([f'CMP({expression})OTE(RunLatch);']);e.memory.values['word']['DATA'][0]=None;self.fault(e,'unknown active')
            e.memory.write('Word.DATA[0]',66);e.memory.write('Word.LEN',13);self.fault(e,'LEN/DATA')

    def test_udt_members_and_late_fault_rollback(self):
        def record(root):
            dtype=E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='TimeRecord',Family='NoFamily',Class='User');members=E.SubElement(dtype,'Members')
            for name,kind in [('Fine','LTIME'),('Coarse','TIME')]:E.SubElement(members,'Member',Name=name,DataType=kind,Dimension='0')
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Record',DataType='TimeRecord',TagType='Base');obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='TimeRecord')
            for name,kind,value in [('Fine','LTIME',1001),('Coarse','TIME',1)]:E.SubElement(obj,'DataValueMember',Name=name,DataType=kind,Value=str(value))
        e=self.make(['CMP(Record.Fine>Record.Coarse)OTE(RunLatch);','DIV(1,SpeedCommand,SpeedCommand);'],change=record)
        e.memory.write('SpeedCommand',0);self.fault(e,'zero');e.memory.write('SpeedCommand',1);e.step();self.assertTrue(e.memory.read('RunLatch'))

    def test_fsc_all_types_all_modes_hold_and_live_string_resume(self):
        for dtype in time_values.TYPES:
            for mode in ('ALL','1','INC'):
                e=self.make([f'XIC(StartPB)FSC(Ctl,?,?,{mode},(Queue[Ctl.POS]>Incoming)&&(Codes[Ctl.POS]=Word));'],source=dtype,file=True)
                e.memory.write('Incoming',0);e.memory.write('StartPB',True);e.step()
                if mode=='1':e.memory.write('StartPB',False);e.step()
                elif mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
                self.assertTrue(e.memory.read('Ctl.FD'));self.assertEqual(e.memory.read('Ctl.POS'),1)
                e.step();self.assertEqual(e.memory.read('Ctl.POS'),1);e.memory.write('Ctl.IN',False);e.memory.write_string('Word','D')
                if mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True)
                e.step()
                if mode=='1':e.step()
                elif mode=='INC':e.memory.write('StartPB',False);e.step();e.memory.write('StartPB',True);e.step()
                self.assertTrue(e.memory.read('Ctl.DN'));self.assertEqual(e.memory.read('Ctl.POS'),3)

    def test_fsc_mixed_precision_and_mid_search_unknowns_repair(self):
        def fine(root):
            tag=root.find('./Controller/Tags/Tag[@Name="Incoming"]');tag.set('DataType','LTIME');tag.find('./Data/DataValue').set('DataType','LTIME');tag.find('./Data/DataValue').set('Value','1000')
        e=self.make(['FSC(Ctl,?,?,ALL,(Queue[Ctl.POS]>=Incoming)&&(Codes[Ctl.POS]=Word));'],source='TIME',file=True,queue=(0,1,2,3,99),change=fine)
        e.step();self.assertEqual(e.memory.read('Ctl.POS'),1);self.assertTrue(e.memory.read('Ctl.FD'))
        for unknown in ('time','string'):
            e=self.make(['FSC(Ctl,?,?,ALL,(Queue[Ctl.POS]>Incoming)&&(Codes[Ctl.POS]=Word));'],file=True)
            e.memory.write('Incoming',0)
            if unknown=='time':e.memory.values['queue'][1]=None
            else:e.memory.values['codes'][1]['DATA'][0]=None
            self.fault(e,'Unknown|unknown active')
            e.memory.write('Queue[1]',4);e.memory.write('Codes[1].DATA[0]',66);e.step();self.assertTrue(e.memory.read('Ctl.FD'));self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_numeric_false_continuation_uses_live_temporal_values(self):
        e=self.make(['XIC(StartPB)FSC(Ctl,?,?,1,(Queue[Ctl.POS]>Incoming)&&(Codes[Ctl.POS]=Word));'],file=True)
        e.memory.write('Incoming',0);e.memory.write('StartPB',True);e.step();e.memory.write('StartPB',False);e.memory.values['queue'][1]=None
        self.fault(e,'Unknown');self.assertEqual(e.memory.read('Ctl.POS'),0);e.memory.write('Queue[1]',4);e.step();self.assertTrue(e.memory.read('Ctl.FD'));self.assertEqual(e.memory.read('Ctl.POS'),1)

    def test_warm_aoi_temporal_and_string_inout_bindings(self):
        import test_aoi_files as aois
        h=aois.AOIFileTests();h.setUp();self.addCleanup(h.doCleanups)
        def fields(root):
            tags=root.find('./Controller/Tags')
            for name,dtype,value in [('FineA','LTIME',1001),('FineB','LTIME',1000),('Coarse','TIME',1)]:
                tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(value))
            for name in ('LabelA','LabelB','Expected'):
                tag=E.SubElement(tags,'Tag',Name=name,DataType='STRING',TagType='Base');string_data(E.SubElement(tag,'Data',Format='Decorated'),'B')
            params=root.find('.//AddOnInstructionDefinition/Parameters')
            for name,dtype in [('Fine','LTIME'),('Coarse','TIME'),('Label','STRING'),('Expected','STRING')]:E.SubElement(params,'Parameter',Name=name,DataType=dtype,TagType='Base',Usage='InOut',Required='true',Visible='true',Constant='false')
            for text in root.findall('.//Programs/Program/Routines/Routine/RLLContent/Rung/Text'):
                for suffix in ('A','B'):text.text=text.text.replace(f'Calc{suffix},Find{suffix})',f'Calc{suffix},Find{suffix},Fine{suffix},Coarse,Label{suffix},Expected)')
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('Input[Find.POS]>=Threshold','(Fine>Coarse)&&(Label=Expected)')
        e=h.checked(fields,kind='1');e.memory.write('Search',True);e.step();self.assertTrue(e.memory.read('FindA.FD'));self.assertFalse(e.memory.read('FindB.FD'))
        e.memory.write('Search',False);e.memory.write('FineB',1001);e.step();self.assertTrue(e.memory.read('FindB.FD'));self.assertEqual(e.memory.read('FindB.POS'),1)

    def test_default_parser_options_and_cache_keys_stay_separate(self):
        e=self.make(['NOP();'])
        for options in ({},{'allow_wide':True},{'lreal':True}):
            with self.assertRaises(ModelError):Condition('Source>Mask',**options).validate(e.memory)
        condition=e.extensions.condition('Source>Mask',allow_wide=True,lreal=True);self.assertTrue(condition.evaluate(e.memory))
        other=e.extensions.condition('Source>Mask');self.assertIsNot(condition,other)
        with self.assertRaises(ModelError):other.validate(e.memory)

    def test_public_example_precision_strings_faults_false_gate_and_report(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/WideExpressionLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        e.memory.write('TemporalEnabled',True);self.fault(e,'outside bounds');e.memory.write('TemporalIndex',1);e.step()
        for name in ('DurationMatch','StampMatch','Combined'):self.assertTrue(e.memory.read('Temporal'+name),name)
        e.memory.write('TemporalHighDuration',1000);e.step();self.assertFalse(e.memory.read('TemporalDurationMatch'));self.assertFalse(e.memory.read('TemporalCombined'));self.assertTrue(e.memory.read('TemporalStampMatch'))
        e.memory.write('TemporalHighDuration',1001);e.memory.write('TemporalHighStamp',1767225600000001000);e.step();self.assertFalse(e.memory.read('TemporalStampMatch'));self.assertFalse(e.memory.read('TemporalCombined'))
        e.memory.write('TemporalHighStamp',1767225600000001001);e.memory.write('TemporalLateDivisor',0);self.fault(e,'zero');e.memory.write('TemporalLateDivisor',1);e.step();self.assertTrue(e.memory.read('TemporalCombined'))
        e.memory.write('StringNumericNeedle.DATA[5]',66);e.step();self.assertFalse(e.memory.read('TemporalCombined'));self.assertTrue(e.memory.read('TemporalStampMatch'))
        e.memory.write('TemporalEnabled',False);e.memory.write('TemporalIndex',99);e.memory.values['temporalhighstamp']=None;e.step()
        for name in ('DurationMatch','StampMatch','Combined'):self.assertFalse(e.memory.read('Temporal'+name))
        row=e.report()['numeric_comparisons']['time_date']['conditions'];self.assertEqual(row['consumers'],['CMP','FSC']);self.assertFalse(row['native_runtime_parity'])


if __name__=='__main__':unittest.main()
