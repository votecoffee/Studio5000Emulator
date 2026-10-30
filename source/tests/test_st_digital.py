"""Boolean memory truth tables, sampled clocks and transaction boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project
from logixlab.runtime import Engine
from logixlab.st_digital import SCHEMAS,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'
TAGS={'D':'FLIP_FLOP_D','J':'FLIP_FLOP_JK','R':'DOMINANT_RESET','S':'DOMINANT_SET'}


def record(parent,name,dtype,values=None):
    tag=E.SubElement(parent,'Tag',Name=name,TagType='Base',DataType=dtype)
    data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType=dtype)
    for member,value in (default(dtype)|dict(values or {})).items():
        E.SubElement(data,'DataValueMember',Name=member,DataType='BOOL',Value=str(int(value)))
    return tag


class StructuredDigitalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,values=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        for name,dtype in TAGS.items():record(tags,name,dtype,dict(values or {}).get(name))
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else ['DFF(D); JKFF(J); RESD(R); SETD(S);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'digital.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def outputs(self,e):return tuple(e.memory.read(ref) for ref in ('D.Q','J.Q','R.Out','S.Out'))

    def controls(self,e,*,clock=None,clear=None,data=None,set_=None,reset=None):
        for root in ('D','J'):
            if clock is not None:e.memory.write(root+'.Clock',clock)
            if clear is not None:e.memory.write(root+'.Clear',clear)
        if data is not None:e.memory.write('D.D',data)
        for root in ('R','S'):
            if set_ is not None:e.memory.write(root+'.Set',set_)
            if reset is not None:e.memory.write(root+'.Reset',reset)

    def step(self,e):
        e.step();out=self.outputs(e)
        self.assertEqual(tuple(e.memory.read(ref) for ref in ('D.QNot','J.QNot','R.OutNot','S.OutNot')),tuple(not v for v in out))
        return out

    def test_first_run_uses_documented_output_and_previous_clock_states(self):
        e=self.checked(values={'D':{'Q':True,'QNot':False},'J':{'Q':True},'R':{'Out':True},'S':{'Out':False}})
        self.assertEqual(self.step(e),(False,False,False,True))

    def test_initial_high_clock_does_not_capture_or_toggle(self):
        e=self.checked();self.controls(e,clock=True,data=True)
        self.assertEqual(self.step(e)[:2],(False,False));self.assertEqual(self.step(e)[:2],(False,False))

    def test_dff_captures_data_only_on_reached_rising_edge(self):
        e=self.checked();self.step(e);self.controls(e,clock=True,data=True);self.assertTrue(self.step(e)[0])
        self.controls(e,data=False);self.assertTrue(self.step(e)[0]);self.controls(e,clock=False);self.assertTrue(self.step(e)[0])
        self.controls(e,clock=True);self.assertFalse(self.step(e)[0])

    def test_jkff_is_a_toggle_without_j_or_k_fields(self):
        e=self.checked();self.step(e)
        for expected in (True,False,True):
            self.controls(e,clock=True);self.assertEqual(self.step(e)[1],expected)
            self.assertEqual(self.step(e)[1],expected);self.controls(e,clock=False);self.step(e)
        self.assertEqual(set(e.memory.read('J')),{'EnableIn','Clear','Clock','EnableOut','Q','QNot'})

    def test_clear_wins_over_rising_edge_and_samples_clock(self):
        e=self.checked();self.step(e);self.controls(e,clock=True,clear=True,data=True)
        self.assertEqual(self.step(e)[:2],(False,False));self.controls(e,clear=False)
        self.assertEqual(self.step(e)[:2],(False,False))
        self.controls(e,clock=False);self.step(e);self.controls(e,clock=True);self.assertEqual(self.step(e)[:2],(True,True))

    def test_clear_resets_held_outputs_without_a_clock_edge(self):
        e=self.checked();self.step(e);self.controls(e,clock=True,data=True);self.step(e);self.controls(e,clear=True)
        self.assertEqual(self.step(e)[:2],(False,False));self.assertEqual(self.step(e)[:2],(False,False))

    def test_latch_truth_tables_for_both_previous_outputs(self):
        for previous in (False,True):
            for set_ in (False,True):
                for reset in (False,True):
                    e=self.checked();self.controls(e,set_=previous,reset=not previous);self.step(e)
                    self.controls(e,set_=set_,reset=reset);out=self.step(e)
                    self.assertEqual(out[2:],((False if reset else True if set_ else previous),
                                              (True if set_ else False if reset else previous)))

    def test_dominance_stays_level_sensitive_and_releases_to_current_inputs(self):
        e=self.checked();self.controls(e,set_=True,reset=True);self.assertEqual(self.step(e)[2:],(False,True))
        self.assertEqual(self.step(e)[2:],(False,True));self.controls(e,reset=False);self.assertEqual(self.step(e)[2:],(True,True))
        self.controls(e,set_=False);self.assertEqual(self.step(e)[2:],(True,True));self.controls(e,reset=True)
        self.assertEqual(self.step(e)[2:],(False,False))

    def test_neither_latch_input_retains_state_and_recomputes_complement(self):
        e=self.checked();self.controls(e,set_=True);self.step(e);self.controls(e,set_=False)
        e.memory.write('R.OutNot',True);e.memory.write('S.OutNot',True)
        self.assertEqual(self.step(e)[2:],(True,True))

    def test_hidden_retained_values_ignore_direct_output_writes(self):
        e=self.checked();self.step(e);self.controls(e,clock=True,data=True,set_=True);self.step(e)
        self.controls(e,set_=False)
        for ref in ('D.Q','J.Q','R.Out','S.Out'):e.memory.write(ref,False)
        self.assertEqual(self.step(e),(True,True,True,True))

    def test_skipped_calls_retain_outputs_and_do_not_sample_clock_pulses(self):
        e=self.checked(['IF StartPB THEN DFF(D); JKFF(J); RESD(R); SETD(S); END_IF;'])
        e.memory.write('StartPB',True);self.step(e);history=copy.deepcopy(e.last_timer)
        e.memory.write('StartPB',False);self.controls(e,clock=True,data=True,set_=True);self.step(e)
        self.controls(e,clock=False);self.step(e);self.assertEqual(e.last_timer,history)
        e.memory.write('StartPB',True);self.controls(e,set_=False);self.assertEqual(self.step(e),(False,False,False,True))

    def test_skipped_first_call_defers_startup_until_reached(self):
        e=self.checked(['IF StartPB THEN DFF(D); JKFF(J); RESD(R); SETD(S); END_IF;'],values={'R':{'Out':True},'S':{'Out':False}})
        e.step();self.assertEqual((e.memory.read('R.Out'),e.memory.read('S.Out'),e.last_timer),(True,False,{}))
        e.memory.write('StartPB',True);self.assertEqual(self.step(e),(False,False,False,True))

    def test_resume_with_clock_high_samples_only_the_reached_transition(self):
        e=self.checked(['IF StartPB THEN DFF(D); JKFF(J); END_IF;']);e.memory.write('StartPB',True);e.step()
        e.memory.write('StartPB',False);self.controls(e,clock=True,data=True);e.step();e.memory.write('StartPB',True);e.step()
        self.assertEqual(self.outputs(e)[:2],(True,True))

    def test_repeated_calls_at_one_timestamp_toggle_only_on_each_sampled_edge(self):
        e=self.checked(['J.Clock:=FALSE; JKFF(J); J.Clock:=TRUE; JKFF(J); JKFF(J);',
                        'J.Clock:=FALSE; JKFF(J); J.Clock:=TRUE; JKFF(J);']);e.step()
        self.assertFalse(e.memory.read('J.Q'));self.assertEqual(e.time_ms,10)

    def test_st_call_forces_enable_pair_even_when_saved_values_are_false(self):
        e=self.checked();self.step(e)
        for root in TAGS:
            for name in ('EnableIn','EnableOut'):e.memory.write(root+'.'+name,False)
        self.step(e);self.assertTrue(all(e.memory.read(root+'.'+name) for root in TAGS for name in ('EnableIn','EnableOut')))

    def test_dff_d_is_read_only_on_uncleared_rising_edge(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="D"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="D"]'))
        e=self.checked(mutate=missing);self.controls(e,clock=True);self.step(e)
        self.controls(e,clock=False);self.step(e);self.controls(e,clock=True,clear=True);self.step(e)
        self.controls(e,clear=False);self.step(e);self.controls(e,clock=False);self.step(e);self.controls(e,clock=True)
        before=copy.deepcopy(e.last_timer)
        with self.assertRaisesRegex(ModelError,'D is unknown'):e.step()
        self.assertEqual(e.last_timer,before);e.memory.write('D.D',True);e.step();self.assertTrue(e.memory.read('D.Q'))

    def test_dominant_input_can_bypass_unknown_subordinate_input(self):
        def missing(root):
            for tag,name in (('R','Set'),('S','Reset')):
                obj=root.find(f'./Controller/Tags/Tag[@Name="{tag}"]/Data/Structure');obj.remove(obj.find(f'DataValueMember[@Name="{name}"]'))
        e=self.checked(values={'R':{'Reset':True},'S':{'Set':True}},mutate=missing)
        self.assertEqual(self.step(e)[2:],(False,True))

    def test_unknown_clock_is_required_even_when_clear_is_true(self):
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="J"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="Clock"]'))
        e=self.checked(values={'J':{'Clear':True}},mutate=missing)
        with self.assertRaisesRegex(ModelError,'Clock is unknown'):e.step()
        self.assertEqual(e.last_timer,{})

    def test_missing_required_inputs_are_not_treated_as_false(self):
        for tag,name in (('D','Clear'),('R','Reset'),('S','Set')):
            def missing(root):
                obj=root.find(f'./Controller/Tags/Tag[@Name="{tag}"]/Data/Structure');obj.remove(obj.find(f'DataValueMember[@Name="{name}"]'))
            e=self.checked(mutate=missing)
            with self.subTest(tag=tag,name=name),self.assertRaisesRegex(ModelError,'unknown'):e.step()

    def test_unknown_saved_outputs_are_initialized_without_reading_them(self):
        def missing(root):
            for tag,dtype in TAGS.items():
                obj=root.find(f'./Controller/Tags/Tag[@Name="{tag}"]/Data/Structure')
                for name in (('Q','QNot') if dtype.startswith('FLIP') else ('Out','OutNot')):obj.remove(obj.find(f'DataValueMember[@Name="{name}"]'))
        e=self.checked(mutate=missing);self.assertEqual(self.step(e),(False,False,False,True))

    def test_late_edge_fault_preserves_clock_and_all_values_for_retry(self):
        e=self.checked(['DFF(D); JKFF(J); RESD(R); SETD(S); SpeedCommand:=1/SpeedSetpoint;']);e.memory.write('SpeedSetpoint',1);self.step(e)
        self.controls(e,clock=True,data=True,set_=True);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace))
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace),before)
        e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e),(True,True,True,True))

    def test_failed_clear_does_not_consume_the_clock_or_latched_values(self):
        e=self.checked(['DFF(D); JKFF(J); RESD(R); SETD(S); SpeedCommand:=1/SpeedSetpoint;']);e.memory.write('SpeedSetpoint',1)
        self.step(e);self.controls(e,clock=True,data=True,set_=True);self.step(e)
        self.controls(e,clear=True,set_=False,reset=True);e.memory.write('SpeedSetpoint',0)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.controls(e,clear=False,reset=False);e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e),(True,True,True,True))

    def test_budget_failure_between_blocks_rolls_back_first_output_and_history(self):
        e=self.checked();self.step(e);self.controls(e,clock=True,data=True);before=copy.deepcopy((e.memory.values,e.last_timer));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual((e.memory.values,e.last_timer),before);e.instruction_limit=100000
        self.assertEqual(self.step(e)[:2],(True,True))

    def test_run_reentry_reinitializes_history_on_next_reached_call(self):
        e=self.checked();self.step(e);self.controls(e,clock=True,data=True,set_=True);self.step(e);self.controls(e,set_=False)
        e.enter_run();self.assertEqual(e.last_timer,{});self.assertTrue(e.memory.read('D.Q'))
        self.assertEqual(self.step(e),(False,False,False,True))

    def test_deferred_prescan_and_failed_prescan_preserve_visible_values(self):
        e=self.checked(values={'D':{'Q':True},'R':{'Out':True},'S':{'Out':False}},defer=True)
        self.assertTrue(e.memory.read('D.Q'));self.assertEqual(e.last_timer,{})
        self.step(e);before=copy.deepcopy((e.memory.values,e.last_timer,e.prescan_count));e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan rolled back'):e.enter_run()
        self.assertEqual((e.memory.values,e.last_timer,e.prescan_count),before)

    def test_wrong_types_arities_and_constants_block_even_unreached(self):
        for text in ('DFF(J);','JKFF(D);','RESD(S);','SETD(R);','DFF();','JKFF(J,J);','RESD(StartPB);'):
            with self.subTest(text=text):self.assertTrue(self.engine([text]).blockers)
        def const(root):root.find('./Controller/Tags/Tag[@Name="D"]').set('Constant','true')
        self.assertTrue(self.engine(['IF FALSE THEN DFF(D); END_IF;'],mutate=const).blockers)

    def test_redefinitions_rll_forms_and_other_profiles_block(self):
        def redefine(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FLIP_FLOP_D',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='Q',DataType='BOOL',Dimension='0')
        self.assertTrue(self.engine(mutate=redefine).blockers)
        def ladder(root):
            rr=root.find('./Controller/Programs/Program/Routines/Routine');rr.remove(rr.find('STContent'));rr.set('Type','RLL');E.SubElement(E.SubElement(E.SubElement(rr,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JKFF(J);'
        self.assertTrue(self.engine(mutate=ladder).blockers)
        for version,processor in (('34','1756-L85E'),('35','1756-L73')):
            def profile(root):root.find('Controller').set('MajorRev',version);root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(mutate=profile).blockers)

    def test_periodic_repeated_calls_sample_edges_once(self):
        def periodic(root):task=root.find('./Controller/Tasks/Task');task.set('Type','PERIODIC');task.set('Rate','20')
        e=self.checked(['DFF(D); JKFF(J); DFF(D); JKFF(J);'],mutate=periodic);e.step(20)
        self.controls(e,clock=True,data=True);e.step(20);self.assertEqual(self.outputs(e)[:2],(True,True))
        self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],2)

    def test_detached_routine_replacement_preserves_clock_and_latch_history(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(Digital,0);'
            logic(E.SubElement(routines,'Routine',Name='Digital',Type='ST'),['DFF(D); JKFF(J); RESD(R); SETD(S);'])
        e=self.checked(mutate=caller);self.step(e);self.controls(e,clock=True,data=True,set_=True);self.step(e);self.controls(e,set_=False)
        before=copy.deepcopy((e.memory.values,e.last_timer));neutral=['JSR(Digital,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        source=decode(container(E.tostring(xml,encoding='utf-8')));candidate,_=prepare(e,source,tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e.last_timer),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.assertEqual(self.step(candidate),(True,True,True,True))

    def test_count_classification_schemas_and_report_are_qualified(self):
        e=self.checked();self.assertEqual(len(ARITIES),101);self.assertEqual(len(ST_ONLY_ARITIES),22)
        self.assertTrue(set(TAGS.values()).isdisjoint(e.project.data_only_types))
        for name,dtype in TAGS.items():
            self.assertEqual(set(e.memory.read(name)),set(SCHEMAS[dtype]))
            for member in SCHEMAS[dtype]:self.assertEqual(e.memory.resolve(name+'.'+member)[2],'BOOL')
        p=e.report()['st_digital'];self.assertEqual(p['instructions'],['DFF','JKFF','RESD','SETD']);self.assertFalse(p['native_runtime_parity'])

    def test_program_local_aliases_share_resolved_record_history(self):
        def local(root):
            tags=root.find('./Controller/Tags');program=root.find('./Controller/Programs/Program/Tags')
            for name in TAGS:
                tag=tags.find(f'./Tag[@Name="{name}"]');tags.remove(tag);program.append(tag)
                E.SubElement(tags,'Tag',Name='Alias'+name,TagType='Alias',AliasFor='Program:MainProgram.'+name)
        e=self.checked(['DFF(AliasD); JKFF(AliasJ); RESD(AliasR); SETD(AliasS);'],mutate=local);e.step()
        for ref in ('AliasD.Clock','AliasJ.Clock','AliasD.D','AliasR.Set','AliasS.Set'):e.memory.write(ref,True)
        e.step();e.step();self.assertEqual(tuple(e.memory.read(ref) for ref in ('AliasD.Q','AliasJ.Q','AliasR.Out','AliasS.Out')),(True,True,True,True))

    def test_indirect_array_and_nested_udt_members_keep_independent_history(self):
        def nested(root):
            tags=root.find('./Controller/Tags');tag=tags.find('./Tag[@Name="D"]');tag.set('Dimensions','2');data=tag.find('Data');item=copy.deepcopy(data[0]);data.clear();data.set('Format','Decorated')
            arr=E.SubElement(data,'Array',DataType='FLIP_FLOP_D',Dimensions='2')
            for i in range(2):E.SubElement(arr,'Element',Index=f'[{i}]').append(copy.deepcopy(item))
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='MemoryHolder',Class='User',Family='NoFamily'),'Members');E.SubElement(members,'Member',Name='Toggle',DataType='FLIP_FLOP_JK',Dimension='0')
            holder=E.SubElement(tags,'Tag',Name='Holder',TagType='Base',DataType='MemoryHolder');obj=E.SubElement(E.SubElement(holder,'Data',Format='Decorated'),'Structure',DataType='MemoryHolder')
            item=copy.deepcopy(tags.find('./Tag[@Name="J"]/Data/Structure'));item.tag='StructureMember';item.set('Name','Toggle');obj.append(item)
        e=self.checked(['DFF(D[SpeedCommand]); JKFF(Holder.Toggle);'],mutate=nested)
        for index in (0,1):e.memory.write('SpeedCommand',index);e.step()
        e.memory.write('SpeedCommand',0);e.memory.write('D[0].Clock',True);e.memory.write('D[0].D',True);e.memory.write('Holder.Toggle.Clock',True);e.step()
        e.memory.write('SpeedCommand',1);e.memory.write('D[1].Clock',True);e.step()
        e.memory.write('SpeedCommand',0);e.step()
        self.assertEqual((e.memory.read('D[0].Q'),e.memory.read('D[1].Q'),e.memory.read('Holder.Toggle.Q')),(True,False,True))

    def test_aoi_inout_records_and_routine_harness(self):
        def aoi(root):
            definition=E.SubElement(root.find('./Controller/AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='DigitalBlock',Revision='1.0');params=E.SubElement(definition,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(params,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            for name,dtype in TAGS.items():E.SubElement(params,'Parameter',Name='Mem'+name,TagType='Base',DataType=dtype,Usage='InOut',Required='true',Visible='true')
            E.SubElement(definition,'LocalTags');logic(E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='ST'),['DFF(MemD); JKFF(MemJ); RESD(MemR); SETD(MemS);'])
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='DigitalBlock',TagType='Base');obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='DigitalBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['DigitalBlock(Instance,D,J,R,S);'],mutate=aoi);self.step(e);self.controls(e,clock=True,data=True,set_=True);self.assertEqual(self.step(e),(True,True,True,True))
        h=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(h.blockers,[]);self.step(h);self.controls(h,clock=True,data=True,set_=True)
        self.assertEqual(self.step(h),(True,True,True,True))

    def test_st_and_ladder_for_can_sample_multiple_edges_at_one_timestamp(self):
        e=self.checked(['FOR SpeedCommand:=0 TO 2 DO J.Clock:=FALSE; JKFF(J); J.Clock:=TRUE; JKFF(J); END_FOR;']);e.step();self.assertTrue(e.memory.read('J.Q'))
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='FOR(Toggle,SpeedCommand,0,2,1);'
            logic(E.SubElement(routines,'Routine',Name='Toggle',Type='ST'),['J.Clock:=FALSE; JKFF(J); J.Clock:=TRUE; JKFF(J);'])
        e=self.checked(mutate=caller);e.step();self.assertTrue(e.memory.read('J.Q'))

    def event_engine(self,fault=False):
        def event(root):
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='DigitalEvent',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            rr=E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='ST')
            lines=['D.Clock:=TRUE; J.Clock:=TRUE; D.D:=TRUE; DFF(D); JKFF(J); R.Set:=TRUE; R.Reset:=TRUE; S.Set:=TRUE; S.Reset:=TRUE; RESD(R); SETD(S);']
            if fault:lines.append('SpeedCommand:=1/SpeedSetpoint;')
            logic(rr,lines)
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='DigitalEventTask',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='DigitalEvent')
        return self.checked(['D.Clock:=FALSE; J.Clock:=FALSE; DFF(D); JKFF(J); EVENT(DigitalEventTask); DFF(D); JKFF(J); RESD(R); SETD(S);'],mutate=event)

    def test_preempting_event_shares_sampled_clock_and_latch_history(self):
        e=self.event_engine();self.assertEqual(self.step(e),(True,True,False,True))
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],1)

    def test_event_fault_rolls_back_clocks_outputs_and_scheduler(self):
        e=self.event_engine(fault=True);e.memory.write('SpeedSetpoint',0);before=copy.deepcopy((e.memory.values,e.last_timer,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual((e.memory.values,e.last_timer,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);self.assertEqual(self.step(e),(True,True,False,True))

    def test_non_bool_raw_value_faults_instead_of_coercing_truthiness(self):
        e=self.checked();key,parts,_=e.memory.resolve('J.Clock');e.memory.store(key,parts,1)
        with self.assertRaisesRegex(ModelError,'not BOOL'):e.step()
        self.assertEqual(e.last_timer,{})

    def test_public_digital_lab_startup_dominance_and_edges(self):
        e=Engine(Project(SAMPLES/'DigitalLab.L5X'));self.assertEqual(e.blockers,[]);e.step()
        self.assertEqual((e.memory.read('DOutput'),e.memory.read('ToggleOutput'),e.memory.read('ResetDominantOutput'),e.memory.read('SetDominantOutput')),(False,False,False,True))
        for ref in ('Clock','DInput','SetInput','ResetInput'):e.memory.write(ref,True)
        e.step();self.assertEqual((e.memory.read('DOutput'),e.memory.read('ToggleOutput'),e.memory.read('ResetDominantOutput'),e.memory.read('SetDominantOutput')),(True,True,False,True))


if __name__=='__main__':unittest.main()
