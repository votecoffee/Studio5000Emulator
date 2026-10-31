"""DINT bit patterns, explicit masked targets, BOOL dataflow and rollback."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.fbd_bitwise import SCHEMAS,TYPES,default
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from test_st_timers import logic

SAMPLE=Path(__file__).resolve().parents[1]/'samples/FBDBitwiseLab.L5X'
RECORDS=('AndState','OrState','XorState','NotState','MoveState','MatchState')


class FBDBitwiseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def sheet(root):return root.find('.//Routine[@Name="BitSignals"]/FBDContent/Sheet')

    def engine(self,mutate=None,*,mode='project',defer=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        p=Path(self.tmp.name)/'bits.L5X';E.ElementTree(root).write(p,encoding='utf-8',xml_declaration=True)
        return Engine(Project(p),mode,'MainProgram/BitSignals' if mode=='routine' else '',defer_prescan=defer)

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
        e.step(10);return tuple(e.memory.read(t) for t in ('AndValue','OrValue','XorValue','Inverted','Merged','Matches'))

    def test_default_bit_patterns_and_exact_output_types(self):
        e=self.checked();self.assertEqual(self.step(e),(136,238,102,-103,250,True))
        self.assertIs(type(e.memory.read('Matches')),bool)
        for tag in ('AndValue','OrValue','XorValue','Inverted','Merged'):self.assertIs(type(e.memory.read(tag)),int)

    def test_every_bit_and_signed_boundaries(self):
        e=self.checked()
        for bit in range(32):
            a=1<<bit;a=a if a<1<<31 else -(1<<31);self.settings(e,A=a,B=a)
            self.assertEqual(self.step(e)[:4],(a,a,0,-1),bit)
        self.settings(e,A=-1,B=0);self.assertEqual(self.step(e)[:4],(0,-1,-1,0))
        self.settings(e,A=-(1<<31),B=(1<<31)-1);self.assertEqual(self.step(e)[:4],(0,-1,-1,0))

    def test_not_zero_all_ones_and_high_bit(self):
        def unwire(root):self.sheet(root).remove(self.sheet(root).find('Wire[@ToID="400"][@ToParam="Source"]'))
        e=self.checked(unwire)
        for value,result in ((0,-1),(-1,0),(-(1<<31),(1<<31)-1),((1<<31)-1,-(1<<31))):
            self.settings(e,**{'NotState.Source':value});self.step(e);self.assertEqual(e.memory.read('Inverted'),result)

    def test_zero_mask_takes_target_and_full_mask_takes_source(self):
        e=self.checked();self.settings(e,Mask=0,Target=-123);self.assertEqual(self.step(e)[4:],(-123,True))
        self.settings(e,Mask=-1,A=-456,CompareValue=-456);self.assertEqual(self.step(e)[4:],(-456,True))

    def test_partial_mask_keeps_target_bits_and_copies_source_bits(self):
        e=self.checked();self.settings(e,A=0x12345678,Target=0x23456701,Mask=0xffff,CompareValue=0x5678)
        self.assertEqual(self.step(e)[4:],(0x23455678,True))

    def test_sign_bit_mask_produces_signed_dint(self):
        e=self.checked();self.settings(e,A=-(1<<31),Mask=-(1<<31),Target=5,CompareValue=-(1<<31))
        self.assertEqual(self.step(e)[4:],(-(1<<31)+5,True))

    def test_meq_masks_both_source_and_compare(self):
        e=self.checked();self.settings(e,CompareValue=0x123a);self.assertTrue(self.step(e)[5])
        self.settings(e,CompareValue=0x123b);self.assertFalse(self.step(e)[5])

    def test_meq_bool_drives_selector_and_timer(self):
        e=self.checked();self.step(e);self.assertEqual(e.memory.read('SelectedValue'),100);self.assertEqual(e.memory.read('TimerACC'),0)
        self.step(e);self.assertEqual(e.memory.read('TimerACC'),10);self.step(e);self.assertTrue(e.memory.read('TimerDone'))
        self.settings(e,CompareValue=11);self.assertFalse(self.step(e)[5]);self.assertEqual(e.memory.read('SelectedValue'),0);self.assertEqual(e.memory.read('TimerACC'),0)

    def test_target_changes_replace_unmasked_bits_each_call(self):
        e=self.checked();self.step(e);self.settings(e,Target=0x120);self.assertEqual(self.step(e)[4],0x12a)
        self.settings(e,**{'MoveState.Dest':999});self.assertEqual(self.step(e)[4],0x12a)

    def test_prescan_clears_only_mvmt_enables_in_new_family(self):
        def saved(root):
            for tag in RECORDS:
                obj=root.find(f'./Controller/Tags/Tag[@Name="{tag}"]/Data/Structure')
                for member in ('EnableIn','EnableOut'):obj.find(f'DataValueMember[@Name="{member}"]').set('Value','1')
                obj.find('DataValueMember[@Name="Dest"]').set('Value','1')
        e=self.checked(saved)
        for tag in RECORDS:
            self.assertEqual(e.memory.read(tag+'.EnableIn'),tag!='MoveState');self.assertEqual(e.memory.read(tag+'.EnableOut'),tag!='MoveState')
            self.assertEqual(e.memory.read(tag+'.Dest'),1)

    def test_run_keeps_results_and_reapplies_family_prescan(self):
        e=self.checked();self.step(e);before=tuple(e.memory.read(t+'.Dest') for t in RECORDS);e.enter_run()
        self.assertEqual(tuple(e.memory.read(t+'.Dest') for t in RECORDS),before)
        self.assertFalse(e.memory.read('MoveState.EnableOut'));self.assertTrue(e.memory.read('MatchState.EnableOut'));self.assertEqual(e.last_timer,{})

    def test_disabled_blocks_do_not_consume_unknown_inputs(self):
        e=self.checked();expected=self.step(e);history=copy.deepcopy(e.last_timer);self.settings(e,BlockEnable=False)
        for tag in ('A','B','Mask','Target','CompareValue'):self.corrupt(e,tag)
        self.assertEqual(self.step(e),expected);self.assertEqual(e.last_timer,history);self.assertFalse(e.memory.read('BitwiseEnabled'))

    def test_unwired_enables_execute_despite_stored_false(self):
        def unwire(root):
            for wire in list(self.sheet(root).findall('Wire')):
                if wire.get('ToParam')=='EnableIn':self.sheet(root).remove(wire)
        e=self.checked(unwire);self.settings(e,BlockEnable=False)
        for tag in RECORDS:self.settings(e,**{tag+'.EnableIn':False})
        self.assertEqual(self.step(e),(136,238,102,-103,250,True));self.assertTrue(e.memory.read('MoveState.EnableOut'))

    def test_skip_retains_values_and_timer_history(self):
        e=self.checked();v=self.step(e);history=copy.deepcopy(e.last_timer);self.settings(e,ExecuteGraph=False,A=0)
        self.assertEqual(self.step(e),v);self.assertEqual(e.last_timer,history)

    def test_direct_output_write_holds_disabled_then_recalculates(self):
        e=self.checked();self.step(e);self.settings(e,BlockEnable=False,**{'MoveState.Dest':123,'MatchState.Dest':False})
        self.assertEqual(self.step(e)[4:],(123,False));self.settings(e,BlockEnable=True);self.assertEqual(self.step(e)[4:],(250,True))

    def test_every_required_input_unknown_causes_whole_advance_rollback(self):
        for tag in ('A','B','Mask','Target','CompareValue'):
            e=self.checked();self.step(e);self.corrupt(e,tag);before=self.snapshot(e)
            with self.subTest(tag=tag),self.assertRaisesRegex(ModelError,'unknown'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_zero_and_full_masks_still_require_known_operands(self):
        for mask,tag in ((0,'MoveState.Source'),(0,'MatchState.Compare'),(-1,'MoveState.Target')):
            def unwire(root):
                ident,pin=('600','Compare') if tag=='MatchState.Compare' else ('500',tag.split('.')[1])
                self.sheet(root).remove(self.sheet(root).find(f'Wire[@ToID="{ident}"][@ToParam="{pin}"]'))
            e=self.checked(unwire);self.settings(e,Mask=mask);self.corrupt(e,tag);before=self.snapshot(e)
            with self.subTest(mask=mask,tag=tag),self.assertRaisesRegex(ModelError,'unknown'):self.step(e)
            self.assertEqual(self.snapshot(e),before)

    def test_every_block_required_pin_rejects_unknown_at_its_own_algorithm(self):
        for ident,name,tag,pins in ((100,'AND','AndState',('SourceA','SourceB')),(200,'OR','OrState',('SourceA','SourceB')),(300,'XOR','XorState',('SourceA','SourceB')),(400,'NOT','NotState',('Source',)),(500,'MVMT','MoveState',('Source','Mask','Target')),(600,'MEQ','MatchState',('Source','Mask','Compare'))):
            for pin in pins:
                def unwire(root):self.sheet(root).remove(self.sheet(root).find(f'Wire[@ToID="{ident}"][@ToParam="{pin}"]'))
                e=self.checked(unwire);self.step(e);self.corrupt(e,tag+'.'+pin);before=self.snapshot(e)
                with self.subTest(name=name,pin=pin),self.assertRaisesRegex(ModelError,'FBD '+name+' '+pin+' is unknown'):self.step(e)
                self.assertEqual(self.snapshot(e),before)

    def test_unwired_input_rejects_bool_float_string_and_out_of_range_corruption(self):
        def unwire(root):self.sheet(root).remove(self.sheet(root).find('Wire[@ToID="400"][@ToParam="Source"]'))
        for value in (True,1.0,'1',1<<31,-(1<<31)-1):
            e=self.checked(unwire);self.corrupt(e,'NotState.Source',value)
            with self.subTest(value=value),self.assertRaisesRegex(ModelError,'signed DINT'):self.step(e)

    def test_omitted_saved_operand_stays_unknown(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="MoveState"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="Target"]'))
            self.sheet(root).remove(self.sheet(root).find('Wire[@ToID="500"][@ToParam="Target"]'))
        e=self.checked(missing)
        with self.assertRaisesRegex(ModelError,'Target is unknown'):self.step(e)

    def test_unknown_enable_rolls_back(self):
        e=self.checked();self.corrupt(e,'BlockEnable');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'EnableIn is unknown'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_late_ladder_failure_restores_bits_bool_timer_and_clock(self):
        e=self.checked();self.step(e);self.settings(e,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before);self.settings(e,FaultDivisor=1);self.step(e);self.assertEqual(e.memory.read('TimerACC'),10)

    def test_records_have_exact_typed_members_and_declaration_defaults(self):
        e=self.checked()
        for tag in RECORDS:
            dtype=e.memory.resolve(tag)[2];self.assertNotIn(dtype,e.project.data_only_types)
            for member,kind in SCHEMAS[dtype].items():self.assertEqual(e.memory.resolve(tag+'.'+member)[2],kind)
            self.assertTrue(default(dtype)['EnableIn'])
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(101,27))

    def test_local_alias_and_nested_array_record(self):
        def nested(root):
            tags=root.find('./Controller/Tags');tag=tags.find('Tag[@Name="AndState"]');tags.remove(tag);root.find('./Controller/Programs/Program/Tags').append(tag)
            E.SubElement(tags,'Tag',Name='LocalAnd',TagType='Alias',AliasFor='Program:MainProgram.AndState');self.sheet(root).find('Block[@Type="AND"]').set('Operand','LocalAnd')
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='BitCell',Class='User',Family='NoFamily'),'Members');E.SubElement(members,'Member',Name='Mover',DataType='FBD_MASKED_MOVE',Dimension='0')
            tag=tags.find('Tag[@Name="MoveState"]');obj=tag.find('Data/Structure');tags.remove(tag)
            array=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='BitCell',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='BitCell',Dimensions='2')
            for i in range(2):
                cell=E.SubElement(E.SubElement(array,'Element',Index=f'[{i}]'),'Structure',DataType='BitCell');item=copy.deepcopy(obj);item.tag='StructureMember';item.set('Name','Mover');cell.append(item)
            self.sheet(root).find('Block[@Type="MVMT"]').set('Operand','Cells[1].Mover')
        e=self.checked(nested);self.assertEqual(self.step(e)[4],250);self.assertEqual(e.memory.read('Cells[0].Mover.Dest'),0)

    def test_profile_constant_record_redefinition_and_wire_direction_guards(self):
        for kind in ('profile','version','constant','record','redefined','wiretype','output','boolsource'):
            def mutate(root):
                sheet=self.sheet(root)
                if kind=='profile':root.find('Controller').set('ProcessorType','1756-L73')
                elif kind=='version':root.find('Controller').set('MajorRev','34')
                elif kind=='constant':root.find('./Controller/Tags/Tag[@Name="AndState"]').set('Constant','true')
                elif kind=='record':sheet.find('Block[@Type="AND"]').set('Operand','MatchState')
                elif kind=='redefined':
                    m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FBD_LOGICAL',Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Dest',DataType='DINT',Dimension='0')
                elif kind=='wiretype':sheet.find('IRef[@ID="1"]').set('Operand','OnValue')
                elif kind=='output':sheet.find('Wire[@ToID="100"]').set('ToParam','Dest')
                else:wire=sheet.find('Wire[@ToID="100"]');wire.set('FromID','600');wire.set('FromParam','Dest')
            with self.subTest(kind=kind):self.assertTrue(self.engine(mutate).blockers)

    def test_tagless_functions_and_st_record_overloads_remain_blocked(self):
        for name in TYPES:
            def st(root):logic(root.find('.//Routine[@Name="MainRoutine"]'),[name+'(AndState);'])
            with self.subTest(name=name):self.assertTrue(self.engine(st).blockers)
        def function(root):self.sheet(root).find('Block').tag='Function'
        self.assertTrue(self.engine(function).blockers)

    def test_periodic_and_harness_execution(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','Periodic');t.set('Rate','10')
        self.assertEqual(self.step(self.checked(periodic)),(136,238,102,-103,250,True))
        self.assertEqual(self.step(self.checked(mode='routine',defer=True)),(136,238,102,-103,250,True))

    def event_engine(self,fault=False):
        def event(root):
            logic(root.find('.//Routine[@Name="MainRoutine"]'),['JSR(BitSignals,0); EVENT(BitEvent);'])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='MainRoutine' if fault else 'BitSignals',Class='Standard',Disabled='false');E.SubElement(p,'Tags');rs=E.SubElement(p,'Routines')
            if fault:logic(E.SubElement(rs,'Routine',Name='MainRoutine',Type='ST'),['GuardResult:=1/FaultDivisor;'])
            else:rs.append(copy.deepcopy(root.find('.//Routine[@Name="BitSignals"]')))
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='BitEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        return self.checked(event)

    def test_event_calls_share_values_and_timer_timestamp(self):
        e=self.event_engine();self.step(e);self.assertEqual(self.step(e),(136,238,102,-103,250,True));self.assertEqual(e.memory.read('TimerACC'),10)

    def test_event_failure_restores_earlier_bitwise_and_timer_changes(self):
        e=self.event_engine(True);self.step(e);self.settings(e,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_budget_failure_rolls_back(self):
        e=self.checked();e.instruction_limit=25;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):self.step(e)
        self.assertEqual(self.snapshot(e),before)

    def test_detached_ladder_replacement_preserves_values_and_timer(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        e=self.checked();self.step(e);self.step(e);before=self.snapshot(e)
        texts=['JSR(BitSignals,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(texts):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf8'))),tuple(texts),'MainProgram',0)
        self.assertEqual(self.snapshot(e),before);self.assertEqual(candidate.last_timer,e.last_timer);self.step(candidate);self.assertEqual(candidate.memory.read('TimerACC'),20)
        self.assertTrue(all(candidate.project.instruction_counts[n]==1 for n in TYPES))

    def test_report_lists_six_bitwise_forms_and_distinct_target_contract(self):
        p=self.checked().report()['function_blocks'];self.assertEqual(len(p['instructions']),46)
        self.assertEqual(p['blocks']['bitwise']['instructions'],['AND','MEQ','MVMT','NOT','OR','XOR'])
        self.assertIn('never read previous Dest',p['blocks']['bitwise']['masked_move']);self.assertFalse(p['native_runtime_parity'])


if __name__=='__main__':unittest.main()
