"""MAXC/MINC extrema, reset priority, history and transaction boundaries."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project,coerce
from logixlab.runtime import Engine
from logixlab.st_capture import FIELDS,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def record(parent,name,dtype,values=None):
    tag=E.SubElement(parent,'Tag',Name=name,TagType='Base',DataType=dtype)
    data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType=dtype)
    for member,value in (default()|dict(values or {})).items():
        E.SubElement(data,'DataValueMember',Name=member,DataType=FIELDS[member],Value=str(float(value) if FIELDS[member]=='REAL' else int(value)))
    return tag


class StructuredCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,m=None,n=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        record(tags,'M','MAXIMUM_CAPTURE',m);record(tags,'N','MINIMUM_CAPTURE',n)
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else ['MAXC(M); MINC(N);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'capture.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def outputs(self,e):return e.memory.read('M.Out'),e.memory.read('N.Out')

    def push(self,e,value,dt=10):
        e.memory.write('M.In',value);e.memory.write('N.In',value);e.step(dt);return self.outputs(e)

    def test_first_call_seeds_input_not_saved_output_or_zero(self):
        for value in (-7,7):
            e=self.checked(m={'Out':1000},n={'Out':-1000})
            self.assertEqual(self.outputs(e),(1000.0,-1000.0));self.assertEqual(self.push(e,value),(value,value))

    def test_captures_positive_and_negative_extrema(self):
        e=self.checked()
        for value,expected in ((-7,(-7,-7)),(-3,(-3,-7)),(-12,(-3,-12)),(4,(4,-12)),(1,(4,-12))):
            self.assertEqual(self.push(e,value),expected)

    def test_reset_overrides_input_on_first_and_subsequent_calls(self):
        e=self.checked(m={'Reset':True,'ResetValue':10},n={'Reset':True,'ResetValue':-10})
        self.assertEqual(self.push(e,100),(10,-10));self.assertEqual(self.push(e,-100),(10,-10))
        e.memory.write('M.ResetValue',8);e.memory.write('N.ResetValue',-8);self.assertEqual(self.push(e,20),(8,-8))

    def test_releasing_reset_uses_reset_baseline_for_both_directions(self):
        e=self.checked(m={'Reset':True,'ResetValue':10},n={'Reset':True,'ResetValue':-10});self.push(e,100)
        e.memory.write('M.Reset',False);e.memory.write('N.Reset',False)
        self.assertEqual(self.push(e,0),(10,-10));self.assertEqual(self.push(e,20),(20,-10));self.assertEqual(self.push(e,-20),(20,-20))

    def test_negative_reset_baseline_can_establish_a_new_maximum(self):
        e=self.checked();self.push(e,100)
        for ref in ('M.Reset','N.Reset'):e.memory.write(ref,True)
        for ref in ('M.ResetValue','N.ResetValue'):e.memory.write(ref,-10)
        self.assertEqual(self.push(e,100),(-10,-10))
        for ref in ('M.Reset','N.Reset'):e.memory.write(ref,False)
        self.assertEqual(self.push(e,-5),(-5,-10))

    def test_finite_float32_values_are_compared_after_coercion(self):
        e=self.checked();value=coerce(1/3,'REAL');self.assertEqual(self.push(e,1/3),(value,value))
        self.assertEqual(self.push(e,1/3+1e-10),(value,value))

    def test_ties_preserve_retained_signed_zero(self):
        e=self.checked();self.push(e,-0.0);self.push(e,0.0)
        self.assertEqual(tuple(math.copysign(1,v) for v in self.outputs(e)),(-1.0,-1.0))
        for ref in ('M.Reset','N.Reset'):e.memory.write(ref,True)
        self.push(e,1)
        for ref in ('M.Reset','N.Reset'):e.memory.write(ref,False)
        self.push(e,-0.0);self.assertEqual(tuple(math.copysign(1,v) for v in self.outputs(e)),(1.0,1.0))

    def test_skipped_calls_retain_outputs_enable_bits_and_history(self):
        e=self.checked(['IF StartPB THEN MAXC(M); MINC(N); END_IF;']);e.memory.write('StartPB',True);self.push(e,3)
        before=copy.deepcopy(e.last_timer);e.memory.write('StartPB',False);self.push(e,100,dt=500)
        self.assertEqual(self.outputs(e),(3,3));self.assertEqual(e.last_timer,before);self.assertTrue(e.memory.read('M.EnableOut'))
        e.memory.write('StartPB',True);self.assertEqual(self.push(e,5),(5,3))

    def test_skipped_first_call_defers_initialization(self):
        e=self.checked(['IF StartPB THEN MAXC(M); MINC(N); END_IF;'],m={'Out':7},n={'Out':8})
        self.push(e,100);self.assertEqual(self.outputs(e),(7,8));self.assertEqual(e.last_timer,{})
        e.memory.write('StartPB',True);self.assertEqual(self.push(e,-4),(-4,-4))

    def test_st_ignores_stored_enable_in_false_on_reached_call(self):
        e=self.checked();self.assertFalse(e.memory.read('M.EnableIn'));self.push(e,2)
        for root in ('M','N'):
            e.memory.write(root+'.EnableIn',False);e.memory.write(root+'.EnableOut',False)
        self.assertEqual(self.push(e,4),(4,2))
        self.assertTrue(all(e.memory.read(root+'.'+name) for root in ('M','N') for name in ('EnableIn','EnableOut')))

    def test_visible_output_writes_do_not_replace_retained_extrema(self):
        e=self.checked();self.push(e,3);self.push(e,8);e.memory.write('M.Out',-100);e.memory.write('N.Out',100)
        self.assertEqual(self.push(e,5),(8,3))

    def test_repeated_calls_at_one_timestamp_compare_each_input(self):
        e=self.checked(['M.In:=2; MAXC(M); M.In:=6; MAXC(M); M.In:=1; MAXC(M);',
                        'N.In:=2; MINC(N); N.In:=-6; MINC(N); N.In:=1; MINC(N);'])
        e.step();self.assertEqual(self.outputs(e),(6,-6));self.assertEqual(e.time_ms,10)

    def test_unknown_unused_reset_value_is_not_read(self):
        def missing(root):
            for name in ('M','N'):
                obj=root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="ResetValue"]'))
        e=self.checked(mutate=missing);self.assertEqual(self.push(e,3),(3,3));self.assertIsNone(e.memory.read('M')['ResetValue'])

    def test_reset_does_not_read_unknown_input(self):
        def missing(root):
            for name in ('M','N'):
                obj=root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="In"]'))
        e=self.checked(m={'Reset':True,'ResetValue':5},n={'Reset':True,'ResetValue':-5},mutate=missing)
        e.step();self.assertEqual(self.outputs(e),(5,-5))

    def test_unknown_required_reset_input_or_reset_value_faults(self):
        for name,reset in (('Reset',False),('In',False),('ResetValue',True)):
            def missing(root):
                obj=root.find('./Controller/Tags/Tag[@Name="M"]/Data/Structure');obj.remove(obj.find(f'DataValueMember[@Name="{name}"]'))
            e=self.checked(m={'Reset':reset},mutate=missing);before=copy.deepcopy(e.memory.values)
            with self.subTest(name=name),self.assertRaisesRegex(ModelError,'unknown'):e.step()
            self.assertEqual(e.memory.values,before);self.assertEqual(e.last_timer,{})

    def test_nonfinite_or_out_of_range_required_value_rolls_back(self):
        for field,reset in (('In',False),('ResetValue',True)):
            for value in (float('nan'),float('inf'),3.5e38):
                e=self.checked(m={'Reset':reset});key,parts,_=e.memory.resolve('M.'+field);e.memory.store(key,parts,value)
                with self.subTest(field=field,value=value),self.assertRaises(ModelError):e.step()
                self.assertEqual((e.scan_count,e.time_ms,e.last_timer),(0,0,{}));self.assertEqual(e.memory.read('M.Out'),0)

    def test_extreme_finite_inputs_need_no_accumulation(self):
        e=self.checked();high=coerce(3.4e38,'REAL');self.assertEqual(self.push(e,high),(high,high))
        self.assertEqual(self.push(e,-high),(high,-high))

    def test_late_fault_discards_both_new_extrema_for_corrected_retry(self):
        e=self.checked(['MAXC(M); MINC(N); SpeedCommand:=1/SpeedSetpoint;']);e.memory.write('SpeedSetpoint',1);self.push(e,3)
        e.memory.write('M.In',10);e.memory.write('N.In',-10);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace))
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace),before)
        e.memory.write('M.In',5);e.memory.write('N.In',1);e.memory.write('SpeedSetpoint',1);e.step()
        self.assertEqual(self.outputs(e),(5,1))

    def test_late_reset_fault_does_not_change_retained_baselines(self):
        e=self.checked(['MAXC(M); MINC(N); SpeedCommand:=1/SpeedSetpoint;']);e.memory.write('SpeedSetpoint',1)
        self.push(e,2);self.push(e,8)
        for ref in ('M.Reset','N.Reset'):e.memory.write(ref,True)
        e.memory.write('M.ResetValue',100);e.memory.write('N.ResetValue',-100);e.memory.write('SpeedSetpoint',0)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        for ref in ('M.Reset','N.Reset'):e.memory.write(ref,False)
        e.memory.write('SpeedSetpoint',1);self.assertEqual(self.push(e,5),(8,2))

    def test_budget_fault_between_calls_rolls_back_the_first_capture(self):
        e=self.checked();self.push(e,3);history=copy.deepcopy(e.last_timer);e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'budget'):self.push(e,10)
        self.assertEqual(self.outputs(e),(3,3));self.assertEqual(e.last_timer,history)
        e.instruction_limit=100000;self.assertEqual(self.push(e,5),(5,3))

    def test_run_reentry_clears_history_but_defers_output_changes(self):
        e=self.checked();self.push(e,2);self.push(e,8);e.enter_run()
        self.assertEqual((self.outputs(e),e.last_timer),((8,2),{}));self.assertFalse(e.memory.read('M.EnableOut'))
        self.assertEqual(self.push(e,5),(5,5))

    def test_failed_prescan_restores_history_and_visible_values(self):
        e=self.checked();self.push(e,2);self.push(e,8);before=copy.deepcopy((e.memory.values,e.last_timer,e.prescan_count))
        e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan rolled back'):e.enter_run()
        self.assertEqual((e.memory.values,e.last_timer,e.prescan_count),before)

    def test_deferred_prescan_preserves_saved_outputs_and_first_reset_wins(self):
        e=self.checked(m={'Out':7,'Reset':True,'ResetValue':9},n={'Out':8,'Reset':True,'ResetValue':-9},defer=True)
        self.assertEqual(self.outputs(e),(7,8));self.assertEqual(e.last_timer,{})
        self.assertEqual(self.push(e,100),(9,-9));self.assertEqual(e.prescan_count,1)

    def test_wrong_record_arity_and_constant_destinations_block_even_when_skipped(self):
        for text in ('MAXC(N);','MINC(M);','MAXC(M,N);','MAXC();','MINC(SpeedCommand);'):
            with self.subTest(text=text):self.assertTrue(self.engine([text]).blockers)
        def const(root):root.find('./Controller/Tags/Tag[@Name="M"]').set('Constant','true')
        self.assertTrue(self.engine(['IF FALSE THEN MAXC(M); END_IF;'],mutate=const).blockers)

    def test_redefined_records_and_other_profiles_block(self):
        def redefine(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='MAXIMUM_CAPTURE',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='Out',DataType='REAL',Dimension='0')
        self.assertTrue(self.engine(mutate=redefine).blockers)
        for version,processor in (('34','1756-L85E'),('35','1756-L73')):
            def profile(root):root.find('Controller').set('MajorRev',version);root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(mutate=profile).blockers)

    def test_ladder_forms_are_blocked(self):
        for name in ('MAXC','MINC'):
            def ladder(root):
                rr=root.find('./Controller/Programs/Program/Routines/Routine');rr.remove(rr.find('STContent'));rr.set('Type','RLL')
                E.SubElement(E.SubElement(E.SubElement(rr,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text=name+'(M);'
            self.assertTrue(self.engine(mutate=ladder).blockers)

    def test_program_local_aliases_use_the_resolved_history(self):
        def local(root):
            tags=root.find('./Controller/Tags');program=root.find('./Controller/Programs/Program/Tags')
            for name in ('M','N'):
                tag=tags.find(f'./Tag[@Name="{name}"]');tags.remove(tag);program.append(tag)
                E.SubElement(tags,'Tag',Name='Alias'+name,TagType='Alias',AliasFor='Program:MainProgram.'+name)
        e=self.checked(['MAXC(AliasM); MINC(AliasN);'],mutate=local)
        for value in (2,8,5):
            for name in ('AliasM','AliasN'):e.memory.write(name+'.In',value)
            e.step()
        self.assertEqual((e.memory.read('AliasM.Out'),e.memory.read('AliasN.Out')),(8,2))

    def test_arrays_and_nested_udt_members_have_independent_extrema(self):
        def nested(root):
            tags=root.find('./Controller/Tags');members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='HolderType',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='Peak',DataType='MAXIMUM_CAPTURE',Dimension='0')
            tag=E.SubElement(tags,'Tag',Name='Holder',TagType='Base',DataType='HolderType')
            data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='HolderType')
            item=copy.deepcopy(tags.find('./Tag[@Name="M"]/Data/Structure'));item.tag='StructureMember';item.set('Name','Peak');data.append(item)
            tag=tags.find('./Tag[@Name="M"]');tag.set('Dimensions','2');data=tag.find('Data');item=copy.deepcopy(data[0]);data.clear();data.set('Format','Decorated')
            arr=E.SubElement(data,'Array',DataType='MAXIMUM_CAPTURE',Dimensions='2')
            for i in range(2):E.SubElement(arr,'Element',Index=f'[{i}]').append(copy.deepcopy(item))
        e=self.checked(['MAXC(M[0]); MAXC(M[1]); MAXC(Holder.Peak);'],mutate=nested)
        for ref,value in (('M[0].In',-5),('M[1].In',5),('Holder.Peak.In',10)):e.memory.write(ref,value)
        e.step()
        for ref,value in (('M[0].In',-2),('M[1].In',2),('Holder.Peak.In',20)):e.memory.write(ref,value)
        e.step();self.assertEqual((e.memory.read('M[0].Out'),e.memory.read('M[1].Out'),e.memory.read('Holder.Peak.Out')),(-2,5,20))

    def test_aoi_inout_capture_bindings_and_harness(self):
        def aoi(root):
            definition=E.SubElement(root.find('./Controller/AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='CaptureBlock',Revision='1.0');params=E.SubElement(definition,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):
                E.SubElement(params,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            for name,dtype in (('High','MAXIMUM_CAPTURE'),('Low','MINIMUM_CAPTURE')):
                E.SubElement(params,'Parameter',Name=name,TagType='Base',DataType=dtype,Usage='InOut',Required='true',Visible='true')
            E.SubElement(definition,'LocalTags');logic(E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='ST'),['MAXC(High); MINC(Low);'])
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='CaptureBlock',TagType='Base');data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='CaptureBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(data,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['CaptureBlock(Instance,M,N);'],mutate=aoi);self.push(e,2);self.push(e,8);self.assertEqual(self.push(e,5),(8,2))
        h=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(h.blockers,[])
        self.push(h,3);self.assertEqual(self.push(h,7),(7,3))

    def test_periodic_and_st_for_calls_sample_per_execution(self):
        def periodic(root):task=root.find('./Controller/Tasks/Task');task.set('Type','PERIODIC');task.set('Rate','20')
        e=self.checked(mutate=periodic)
        for value in (2,8,5):self.push(e,value,dt=20)
        self.assertEqual(self.outputs(e),(8,2));self.assertEqual(e.scheduler_description()['tasks'][0]['executions'],3)
        e=self.checked(['FOR SpeedCommand:=0 TO 2 DO M.In:=SpeedCommand; MAXC(M); END_FOR;']);e.step()
        self.assertEqual(e.memory.read('M.Out'),2.0)

    def test_ladder_for_target_st_compares_each_iteration(self):
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='FOR(Capture,SpeedCommand,-2,2,1);'
            logic(E.SubElement(routines,'Routine',Name='Capture',Type='ST'),['M.In:=SpeedCommand; N.In:=SpeedCommand; MAXC(M); MINC(N);'])
        e=self.checked(mutate=caller);e.step();self.assertEqual(self.outputs(e),(2,-2))

    def test_detached_routine_replacement_preserves_hidden_extrema(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(Capture,0);'
            logic(E.SubElement(routines,'Routine',Name='Capture',Type='ST'),['MAXC(M); MINC(N);'])
        e=self.checked(mutate=caller);self.push(e,2);self.push(e,8);before=copy.deepcopy((e.memory.values,e.last_timer))
        neutral=['JSR(Capture,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        source=decode(container(E.tostring(xml,encoding='utf-8')));candidate,_=prepare(e,source,tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e.last_timer),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.assertEqual(self.push(candidate,5),(8,2))

    def test_builtin_fields_instruction_counts_and_report_are_qualified(self):
        e=self.checked();self.assertEqual(len(ARITIES),101);self.assertEqual(len(ST_ONLY_ARITIES),15)
        self.assertTrue({'MAXIMUM_CAPTURE','MINIMUM_CAPTURE'}.isdisjoint(e.project.data_only_types))
        for root in ('M','N'):
            self.assertEqual(set(e.memory.read(root)),set(FIELDS))
            for name,kind in FIELDS.items():self.assertEqual(e.memory.resolve(root+'.'+name)[2],kind)
        self.assertEqual(e.report()['st_capture']['instructions'],['MAXC','MINC']);self.assertFalse(e.report()['st_capture']['native_runtime_parity'])

    def test_unknown_saved_output_is_initialized_without_reading_it(self):
        def missing(root):
            for name in ('M','N'):
                obj=root.find(f'./Controller/Tags/Tag[@Name="{name}"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="Out"]'))
        e=self.checked(mutate=missing);self.assertIsNone(e.memory.read('M')['Out']);self.assertEqual(self.push(e,-5),(-5,-5))

    def test_indirect_array_element_selection_keeps_each_record_history(self):
        def arr(root):
            tag=root.find('./Controller/Tags/Tag[@Name="M"]');tag.set('Dimensions','2');data=tag.find('Data');item=copy.deepcopy(data[0]);data.clear();data.set('Format','Decorated')
            array=E.SubElement(data,'Array',DataType='MAXIMUM_CAPTURE',Dimensions='2')
            for i in range(2):E.SubElement(array,'Element',Index=f'[{i}]').append(copy.deepcopy(item))
        e=self.checked(['MAXC(M[SpeedCommand]);'],mutate=arr)
        for index,value in ((0,2),(1,10),(0,5)):
            e.memory.write('SpeedCommand',index);e.memory.write(f'M[{index}].In',value);e.step()
        self.assertEqual((e.memory.read('M[0].Out'),e.memory.read('M[1].Out')),(5,10))

    def test_unused_nonfinite_value_is_ignored_by_selected_operand_path(self):
        e=self.checked();key,parts,_=e.memory.resolve('M.ResetValue');e.memory.store(key,parts,float('nan'))
        self.assertEqual(self.push(e,2),(2,2));e.memory.write('M.Reset',True);e.memory.write('M.ResetValue',4)
        key,parts,_=e.memory.resolve('M.In');e.memory.store(key,parts,float('inf'));e.step()
        self.assertEqual(e.memory.read('M.Out'),4)

    def test_public_capture_lab_and_res_consumer_limit(self):
        e=Engine(Project(SAMPLES/'CaptureLab.L5X'));self.assertEqual(e.blockers,[])
        for value in (-7,-3,-12):e.memory.write('Input',value);e.step()
        self.assertEqual((e.memory.read('Maximum'),e.memory.read('Minimum')),(-3,-12))
        self.assertTrue(self.engine(['RES(M);']).blockers)

    def event_engine(self,*,fault=False):
        def event(root):
            program=E.SubElement(root.find('./Controller/Programs'),'Program',Name='CaptureEvent',MainRoutineName='MainRoutine',Class='Standard',Disabled='false')
            E.SubElement(program,'Tags');routine=E.SubElement(E.SubElement(program,'Routines'),'Routine',Name='MainRoutine',Type='ST')
            lines=['M.In:=10; N.In:=-10; MAXC(M); MINC(N);']
            if fault:lines.append('SpeedCommand:=1/SpeedSetpoint;')
            logic(routine,lines)
            task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='CaptureEventTask',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
            E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='CaptureEvent')
        return self.checked(['M.In:=2; N.In:=2; MAXC(M); MINC(N);','EVENT(CaptureEventTask);',
                             'M.In:=4; N.In:=4; MAXC(M); MINC(N);'],mutate=event)

    def test_preempting_event_can_update_shared_record_extrema(self):
        e=self.event_engine();e.step();self.assertEqual(self.outputs(e),(10,-10))
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],1)
        self.assertTrue(any(row['task']=='CaptureEventTask' and row.get('detail')=='MAXC' for row in e.trace))

    def test_event_fault_restores_capture_history_and_scheduler_for_retry(self):
        e=self.event_engine(fault=True);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual((e.memory.values,e.last_timer,e.scheduler_description()),before)
        e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual(self.outputs(e),(10,-10))
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],1)


if __name__=='__main__':unittest.main()
