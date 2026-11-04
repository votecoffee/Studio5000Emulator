"""Typed REAL remainder/truncation, DINT BCD roundtrips and transaction boundaries."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.fbd_convert import SCHEMAS,default
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from test_st_timers import logic

SAMPLE=Path(__file__).resolve().parents[1]/'samples/FBDConversionLab.L5X'
RECORDS=('RemainderState','TruncateState','EncodeState','RoundtripState','DecodeState')


class FBDConversionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="ConvertSignals"]/FBDContent/Sheet')

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        p=Path(self.tmp.name)/'convert.L5X';E.ElementTree(root).write(p,encoding='utf-8',xml_declaration=True)
        return Engine(Project(p),mode,'MainProgram/ConvertSignals' if mode=='routine' else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    @staticmethod
    def settings(e,**values):
        for tag,value in values.items():e.memory.write(tag,value)

    @staticmethod
    def corrupt(e,ref,value=None):
        key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,value)

    @staticmethod
    def snapshot(e):return copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace,e.scheduler_description()))

    def step(self,e):
        e.step(10);return tuple(e.memory.read(t) for t in ('Remainder','Truncated','PackedBCD','Roundtrip','Decoded'))

    @staticmethod
    def unwire(root,ident,pin):
        sheet=FBDConversionTests.sheet(root);sheet.remove(sheet.find(f'Wire[@ToID="{ident}"][@ToParam="{pin}"]'))

    def test_default_two_chains_and_exact_types(self):
        e=self.checked();self.assertEqual(self.step(e),(2.75,2,0x12345678,12345678,12345684));self.assertIs(type(e.memory.read('Remainder')),float)
        for tag in ('Truncated','PackedBCD','Roundtrip','Decoded'):self.assertIs(type(e.memory.read(tag)),int)
        self.assertIs(e.memory.read('ConversionEnabled'),True);self.assertEqual(e.last_timer,{})

    def test_mod_uses_dividend_sign_for_all_sign_combinations(self):
        e=self.checked()
        for a,b,result,truncated in ((17.75,5,2.75,2),(-17.75,5,-2.75,-2),(17.75,-5,2.75,2),(-17.75,-5,-2.75,-2),(4,5,4,4),(5,5,0,0)):
            self.settings(e,Value=a,Divisor=b);self.step(e);self.assertEqual((e.memory.read('Remainder'),e.memory.read('Truncated')),(result,truncated))

    def test_mod_signed_zero_and_float32_operand_rounding(self):
        e=self.checked();self.settings(e,Value=-0.0);self.step(e);self.assertEqual(math.copysign(1,e.memory.read('Remainder')),-1);self.assertEqual(e.memory.read('Truncated'),0)
        self.settings(e,Value=16777217,Divisor=3);self.step(e);self.assertEqual(e.memory.read('Remainder'),1)

    def test_mod_zero_divisor_rolls_back_without_native_zero_result_substitution(self):
        e=self.checked();self.step(e);self.settings(e,Divisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'MOD zero-divisor minor-fault'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_trn_truncates_both_signs_toward_zero(self):
        e=self.checked(lambda root:self.unwire(root,200,'Source'))
        for value,wanted in ((3.9,3),(-3.9,-3),(.9,0),(-.9,0),(0,0),(-0.0,0)):
            self.settings(e,**{'TruncateState.Source':value});self.step(e);self.assertEqual(e.memory.read('Truncated'),wanted)

    def test_trn_signed_dint_boundaries_after_real_rounding(self):
        e=self.checked(lambda root:self.unwire(root,200,'Source'))
        for value in (-(1<<31),2147483520):self.settings(e,**{'TruncateState.Source':value});self.step(e);self.assertEqual(e.memory.read('Truncated'),value)
        for value in ((1<<31)-1,-2147483904):
            self.settings(e,**{'TruncateState.Source':value});before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'TRN result outside'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_bcd_roundtrips_and_signed_packed_results(self):
        e=self.checked()
        for value,packed in ((0,0),(9,9),(10,16),(12345678,0x12345678),(80000000,-(1<<31)),(99999999,-1717986919)):
            self.settings(e,DecimalInput=value);self.step(e);self.assertEqual((e.memory.read('PackedBCD'),e.memory.read('Roundtrip')),(packed,value))

    def test_frd_weights_a_through_f_nibbles_and_sign_bit(self):
        e=self.checked()
        for value,wanted in ((0,0),(0x1234567e,12345684),(-1,166666665),(-(1<<31),80000000),(-1717986919,99999999)):
            self.settings(e,RawBCD=value);self.step(e);self.assertEqual(e.memory.read('Decoded'),wanted)

    def test_tod_excluded_ranges_do_not_saturate_or_commit(self):
        for value in (-1,100000000,(1<<31)-1):
            e=self.checked();self.step(e);self.settings(e,Value=18.75,DecimalInput=value);before=self.snapshot(e)
            with self.assertRaisesRegex(ModelError,'TOD source outside'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_rll_and_fbd_bcd_share_calculations(self):
        def ladder(root):
            tags=root.find('./Controller/Tags');body=root.find('.//Routine[@Name="MainRoutine"]/RLLContent')
            for i,(op,ref,name) in enumerate((('TOD','DecimalInput','LadderPacked'),('FRD','RawBCD','LadderDecoded')),3):
                tag=E.SubElement(tags,'Tag',Name=name,TagType='Base',DataType='DINT');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0');E.SubElement(E.SubElement(body,'Rung',Number=str(i),Type='N'),'Text').text=op+'('+ref+','+name+');'
        e=self.checked(ladder);self.settings(e,DecimalInput=99999999,RawBCD=-1);self.step(e)
        self.assertEqual(e.memory.read('PackedBCD'),e.memory.read('LadderPacked'));self.assertEqual(e.memory.read('Decoded'),e.memory.read('LadderDecoded'))

    def test_each_required_input_rejects_unknown_at_own_algorithm(self):
        for ident,op,tag,pin in ((100,'MOD','RemainderState','SourceA'),(100,'MOD','RemainderState','SourceB'),(200,'TRN','TruncateState','Source'),(300,'TOD','EncodeState','Source'),(400,'FRD','RoundtripState','Source'),(500,'FRD','DecodeState','Source')):
            e=self.checked(lambda root:self.unwire(root,ident,pin));self.corrupt(e,tag+'.'+pin);before=self.snapshot(e)
            with self.subTest(op=op,pin=pin),self.assertRaisesRegex(ModelError,'FBD '+op+' '+pin+' is unknown'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_trn_and_mod_reject_nonfinite_inputs(self):
        for ident,tag,pin in ((100,'RemainderState','SourceA'),(100,'RemainderState','SourceB'),(200,'TruncateState','Source')):
            for value in (float('nan'),float('inf'),float('-inf')):
                e=self.checked(lambda root:self.unwire(root,ident,pin));self.corrupt(e,tag+'.'+pin,value)
                with self.assertRaisesRegex(ModelError,'finite REAL'):self.step(e)
                self.assertEqual(e.scan_count,0)

    def test_bcd_rejects_unwired_bool_float_string_or_out_of_range_values(self):
        for ident,tag in ((300,'EncodeState'),(500,'DecodeState')):
            for value in (True,1.0,'1',1<<31):
                e=self.checked(lambda root:self.unwire(root,ident,'Source'));self.corrupt(e,tag+'.Source',value)
                with self.assertRaisesRegex(ModelError,'signed DINT'):self.step(e)

    def test_missing_saved_trn_operand_stays_unknown(self):
        def missing(root):
            self.unwire(root,200,'Source');obj=root.find('./Controller/Tags/Tag[@Name="TruncateState"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="Source"]'))
        e=self.checked(missing)
        with self.assertRaisesRegex(ModelError,'TRN Source is unknown'):self.step(e)

    def test_trn_schema_and_builtin_member_types(self):
        e=self.checked();self.assertNotIn('FBD_TRUNCATE',e.project.data_only_types)
        for pin,kind in SCHEMAS['FBD_TRUNCATE'].items():self.assertEqual(e.memory.resolve('TruncateState.'+pin)[2],kind)
        self.assertTrue(default('FBD_TRUNCATE')['EnableIn']);self.assertIs(type(default('FBD_TRUNCATE')['Dest']),int)
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(104,29))

    def test_prescan_and_run_retain_enables_dest_and_no_hidden_state(self):
        def saved(root):
            for obj in root.findall('./Controller/Tags/Tag/Data/Structure'):
                obj.find('DataValueMember[@Name="EnableOut"]').set('Value','1');obj.find('DataValueMember[@Name="Dest"]').set('Value','99')
        e=self.checked(saved)
        for tag in RECORDS:self.assertTrue(e.memory.read(tag+'.EnableOut'));self.assertEqual(e.memory.read(tag+'.Dest'),99)
        self.step(e);before=copy.deepcopy(e.memory.values);e.enter_run();self.assertEqual(e.memory.values,before);self.assertEqual(e.last_timer,{})

    def test_disabled_blocks_hold_results_without_consuming_invalid_inputs(self):
        e=self.checked();expected=self.step(e);self.settings(e,BlockEnable=False,Divisor=0,DecimalInput=-1)
        self.corrupt(e,'Value');self.corrupt(e,'RawBCD');self.assertEqual(self.step(e),expected);self.assertFalse(e.memory.read('ConversionEnabled'))

    def test_skipped_and_direct_output_writes(self):
        e=self.checked();self.step(e);self.settings(e,ExecuteGraph=False,**{'EncodeState.Dest':99});self.step(e);self.assertEqual(e.memory.read('PackedBCD'),0x12345678)
        self.settings(e,ExecuteGraph=True,BlockEnable=False);self.step(e);self.assertEqual(e.memory.read('PackedBCD'),99)
        self.settings(e,BlockEnable=True);self.step(e);self.assertEqual(e.memory.read('PackedBCD'),0x12345678)

    def test_unwired_enables_execute_despite_saved_false(self):
        def unwire(root):
            for wire in list(self.sheet(root).findall('Wire')):
                if wire.get('ToParam')=='EnableIn':self.sheet(root).remove(wire)
        e=self.checked(unwire);self.settings(e,BlockEnable=False)
        for tag in RECORDS:self.settings(e,**{tag+'.EnableIn':False})
        self.assertEqual(self.step(e),(2.75,2,0x12345678,12345678,12345684))

    def test_late_ladder_failure_and_corrected_retry(self):
        e=self.checked();self.step(e);self.settings(e,Value=-17.75,DecimalInput=99999999,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,FaultDivisor=1);self.assertEqual(self.step(e),(-2.75,-2,-1717986919,99999999,12345684))

    def test_local_alias_and_nested_trn_array_record(self):
        def nested(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="EncodeState"]');tags.remove(tag);root.find('./Controller/Programs/Program/Tags').append(tag);E.SubElement(tags,'Tag',Name='LocalEncode',TagType='Alias',AliasFor='Program:MainProgram.EncodeState');self.sheet(root).find('Block[@Type="TOD"]').set('Operand','LocalEncode')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='ConversionCell',Class='User',Family='NoFamily'),'Members');E.SubElement(members,'Member',Name='Truncation',DataType='FBD_TRUNCATE',Dimension='0')
            tag=tags.find('Tag[@Name="TruncateState"]');obj=tag.find('Data/Structure');tags.remove(tag);array=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='ConversionCell',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='ConversionCell',Dimensions='2')
            for i in range(2):
                cell=E.SubElement(E.SubElement(array,'Element',Index=f'[{i}]'),'Structure',DataType='ConversionCell');item=copy.deepcopy(obj);item.tag='StructureMember';item.set('Name','Truncation');cell.append(item)
            self.sheet(root).find('Block[@Type="TRN"]').set('Operand','Cells[1].Truncation')
        e=self.checked(nested);self.assertEqual(self.step(e)[1],2);self.assertEqual(e.memory.read('Cells[0].Truncation.Dest'),0)

    def test_profile_type_constant_and_pin_guards(self):
        for kind in ('profile','constant','record','redefined','wire','pin','function','alias'):
            def mutate(root):
                if kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                elif kind=='constant':root.find('./Controller/Tags/Tag[@Name="TruncateState"]').set('Constant','true')
                elif kind=='record':self.sheet(root).find('Block[@Type="TRN"]').set('Operand','EncodeState')
                elif kind=='redefined':
                    m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_TRUNCATE',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Dest',DataType='DINT',Dimension='0')
                elif kind=='wire':self.sheet(root).find('IRef[@ID="3"]').set('Operand','Value')
                elif kind=='pin':self.sheet(root).find('Wire[@ToID="300"]').set('ToParam','Dest')
                elif kind=='function':self.sheet(root).find('Block').tag='Function'
                else:self.sheet(root).find('Block[@Type="TRN"]').set('Type','TRUNC')
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def test_record_call_rll_and_st_overloads_remain_blocked(self):
        for language in ('RLL','ST'):
            def wrong(root):
                routine=root.find('.//Routine[@Name="MainRoutine"]')
                if language=='ST':logic(routine,['TOD(EncodeState);'])
                else:routine.find('RLLContent/Rung/Text').text='TRN(TruncateState);'
            self.assertTrue(self.engine(wrong).blockers)

    def test_periodic_and_routine_harness(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','Periodic');t.set('Rate','10')
        for e in (self.checked(periodic),self.checked(mode='routine',defer=True)):self.assertEqual(self.step(e),(2.75,2,0x12345678,12345678,12345684))

    def test_budget_failure_rolls_back(self):
        e=self.checked();e.instruction_limit=20;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def event_engine(self,fault=False):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(ConvertSignals,0); EVENT(ConversionEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='MainRoutine' if fault else 'ConvertSignals',Class='Standard',Disabled='false');E.SubElement(p,'Tags');rs=E.SubElement(p,'Routines')
            if fault:logic(E.SubElement(rs,'Routine',Name='MainRoutine',Type='ST'),['GuardResult:=1/FaultDivisor;'])
            else:rs.append(copy.deepcopy(root.find('.//Routine[@Name="ConvertSignals"]')))
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='ConversionEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        return self.checked(event)

    def test_event_calls_are_stateless_and_deterministic(self):
        e=self.event_engine();self.assertEqual(self.step(e),(2.75,2,0x12345678,12345678,12345684));self.assertEqual(e.last_timer,{})

    def test_event_fault_restores_earlier_conversions(self):
        e=self.event_engine(True);self.step(e);self.settings(e,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_unrelated_truncate_prefix_udt_keeps_declared_member_types(self):
        def extra(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_TRUNCATE_CUSTOM',Class='User',Family='NoFamily'),'Members');E.SubElement(members,'Member',Name='Count',DataType='DINT',Dimension='0')
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Custom',TagType='Base',DataType='FBD_TRUNCATE_CUSTOM');obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='FBD_TRUNCATE_CUSTOM');E.SubElement(obj,'DataValueMember',Name='Count',DataType='DINT',Value='7')
        e=self.checked(extra);self.assertEqual(e.memory.resolve('Custom.Count')[2],'DINT');self.assertEqual(e.memory.read('Custom.Count'),7)

    def test_detached_rll_replacement_preserves_values_and_instruction_counts(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();self.step(e);before=self.snapshot(e);texts=['JSR(ConvertSignals,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(texts):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(texts),'MainProgram',0);self.assertEqual(self.snapshot(e),before);self.assertEqual(self.step(candidate),(2.75,2,0x12345678,12345678,12345684));self.assertEqual(candidate.project.instruction_counts['FRD'],2)

    def test_report_inventories_and_excluded_native_ranges(self):
        p=self.checked().report()['function_blocks'];self.assertEqual(len(p['instructions']),63);self.assertEqual(len(p['blocks']['math']['instructions']),19)
        self.assertEqual(p['blocks']['conversion']['instructions'],['FRD','TOD','TRN']);self.assertIn('saturation',p['blocks']['conversion']['remaining'][0]);self.assertFalse(p['native_runtime_parity'])


if __name__=='__main__':unittest.main()
