"""Moving statistics: queues, equations, guarded sampling and scan history."""
import copy
import math
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Project,coerce
from logixlab.runtime import Engine
from logixlab.st_moving import SCHEMAS,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def record(parent,name,dtype,values=None):
    tag=E.SubElement(parent,'Tag',Name=name,DataType=dtype,TagType='Base')
    data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType=dtype)
    for member,value in (default(dtype)|dict(values or {})).items():
        E.SubElement(data,'DataValueMember',Name=member,DataType=SCHEMAS[dtype][member],Value=str(float(value) if SCHEMAS[dtype][member]=='REAL' else int(value)))
    return tag


def array(parent,name,values,dtype='REAL'):
    tag=E.SubElement(parent,'Tag',Name=name,TagType='Base',DataType=dtype,Dimensions=str(len(values)))
    data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType=dtype,Dimensions=str(len(values)),Radix='Float' if dtype=='REAL' else 'Decimal')
    for i,value in enumerate(values):
        if value is not None:E.SubElement(data,'Element',Index=f'[{i}]',Value=str(value))
    return tag


class StructuredMovingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,m=None,d=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        record(tags,'M','MOVING_AVERAGE',{'NumberOfSamples':3}|dict(m or {}))
        record(tags,'D','MOVING_STD_DEV',{'NumberOfSamples':3,'SampleEnable':True}|dict(d or {}))
        for name,values in (('S',[90.0,91.0,92.0,93.0]),('T',[80.0,81.0,82.0,83.0]),('W',[0.5,0.25,0.125,0.0625])):array(tags,name,values)
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else ['MAVE(M,S,W); MSTD(D,T);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'moving.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def push(self,e,value,dt=10):
        e.memory.write('M.In',value);e.memory.write('D.In',value);e.step(dt)
        return e.memory.read('M'),e.memory.read('D')

    def test_uniform_startup_fill_and_oldest_discard(self):
        e=self.checked()
        for value,out in ((2,2),(4,3),(6,4),(8,6)):
            m,d=self.push(e,value);self.assertEqual((m['Out'],d['Average']),(out,out))
        self.assertEqual(e.memory.read('S'),[8.0,6.0,4.0,93.0]);self.assertEqual(e.memory.read('T'),[8.0,6.0,4.0,83.0])

    def test_population_deviation_uses_active_count_not_sample_divisor(self):
        e=self.checked();self.assertEqual(self.push(e,2)[1]['Out'],0.0)
        d=self.push(e,4)[1];self.assertEqual((d['Average'],d['Out']),(3.0,1.0))
        d=self.push(e,6)[1];self.assertAlmostEqual(d['Out'],math.sqrt(8/3),places=6)

    def test_weighted_sum_is_not_normalized_and_newest_uses_weight_zero(self):
        e=self.checked(m={'UseWeights':True})
        for value,out in ((2,1),(4,2.5),(6,4.25),(8,6.0)):
            self.assertEqual(self.push(e,value)[0]['Out'],out)
        self.assertEqual(e.memory.read('W'),[0.5,0.25,0.125,0.0625])

    def test_negative_weights_and_zero_weight_sum_are_valid(self):
        e=self.checked(m={'UseWeights':True,'NumberOfSamples':2});e.memory.write('W[0]',1.0);e.memory.write('W[1]',-1.0)
        self.push(e,2);self.assertEqual(self.push(e,4)[0]['Out'],2.0)

    def test_uniform_two_operand_form_and_unused_weights_stay_unknown(self):
        e=self.checked(['MAVE(M,S);']);self.assertEqual(self.push(e,2)[0]['Out'],2.0)
        def missing(root):
            a=root.find('./Controller/Tags/Tag[@Name="W"]/Data/Array');a.clear();a.set('DataType','REAL');a.set('Dimensions','4')
        e=self.checked(mutate=missing);self.assertEqual(self.push(e,2)[0]['Out'],2.0)

    def test_weighted_sampling_without_weights_faults_and_rolls_back(self):
        e=self.checked(['MAVE(M,S);'],m={'UseWeights':True});before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'weight array'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.last_timer,{})

    def test_constant_weight_array_is_read_only_input(self):
        def const(root):root.find('./Controller/Tags/Tag[@Name="W"]').set('Constant','true')
        e=self.checked(m={'UseWeights':True},mutate=const);self.assertEqual(self.push(e,8)[0]['Out'],4.0)

    def test_sample_disabled_first_call_initializes_outputs_without_sampling(self):
        e=self.checked(m={'SampleEnable':False,'Out':99},d={'SampleEnable':False,'In':7,'Out':88,'Average':66})
        e.step();self.assertEqual((e.memory.read('M.Out'),e.memory.read('D.Out'),e.memory.read('D.Average')),(0.0,0.0,7.0))
        self.assertEqual(e.memory.read('S'),[90.0,91.0,92.0,93.0])

    def test_sample_disabled_holds_outputs_and_queue_then_resumes(self):
        e=self.checked();self.push(e,2)
        for ref in ('M.SampleEnable','D.SampleEnable'):e.memory.write(ref,False)
        before=copy.deepcopy((e.memory.read('S'),e.memory.read('T')));self.push(e,20)
        self.assertEqual((e.memory.read('S'),e.memory.read('T')),before);self.assertEqual(e.memory.read('M.Out'),2)
        for ref in ('M.SampleEnable','D.SampleEnable'):e.memory.write(ref,True)
        m,d=self.push(e,4);self.assertEqual((m['Out'],d['Average'],d['Out']),(3.0,3.0,1.0))

    def test_skipped_calls_do_not_sample_or_change_history(self):
        e=self.checked(['IF StartPB THEN MAVE(M,S,W); MSTD(D,T); END_IF;']);e.memory.write('StartPB',True);self.push(e,2)
        history=copy.deepcopy(e.last_timer);e.memory.write('StartPB',False);self.push(e,100,dt=200)
        self.assertEqual(e.last_timer,history);e.memory.write('StartPB',True)
        self.assertEqual(self.push(e,4)[0]['Out'],3.0)

    def test_initialize_holds_input_and_clears_active_count_without_erasing_storage(self):
        e=self.checked();self.push(e,2);self.push(e,4);stored=copy.deepcopy(e.memory.read('S'))
        e.memory.write('M.Initialize',True);e.memory.write('D.Initialize',True);m,d=self.push(e,10)
        self.assertEqual((m['Out'],d['Average'],d['Out']),(10.0,10.0,0.0));self.assertEqual(e.memory.read('S'),stored)
        e.memory.write('M.Initialize',False);e.memory.write('D.Initialize',False);m,d=self.push(e,20)
        self.assertEqual((m['Out'],d['Average'],d['Out']),(20.0,20.0,0.0))

    def test_input_fault_holds_even_with_initialize_and_recovers_empty(self):
        e=self.checked();self.push(e,2);self.push(e,4);stored=copy.deepcopy(e.memory.read('S'))
        for ref in ('M.InFault','D.InFault','M.Initialize','D.Initialize'):e.memory.write(ref,True)
        m,d=self.push(e,100);self.assertEqual((m['Out'],d['Average'],d['Out'],m['Status'],d['Status']),(3.0,3.0,1.0,3,3))
        self.assertEqual(e.memory.read('S'),stored)
        for ref in ('M.InFault','D.InFault','M.Initialize','D.Initialize'):e.memory.write(ref,False)
        m,d=self.push(e,8);self.assertEqual((m['Out'],d['Average'],d['Out'],m['Status']),(8.0,8.0,0.0,0))

    def test_invalid_length_holds_sets_aliases_and_recovers_empty(self):
        for size in (0,-1,5):
            e=self.checked();self.push(e,2);e.memory.write('M.NumberOfSamples',size);e.memory.write('D.NumberOfSamples',size)
            m,d=self.push(e,8);self.assertEqual((m['Out'],d['Average'],m['Status'],d['Status']),(2.0,2.0,5,5))
            self.assertTrue(e.memory.read('M.NumberOfSampInv'));self.assertTrue(e.memory.read('D.InstructFault'))
            for ref in ('M.NumberOfSamples','D.NumberOfSamples'):e.memory.write(ref,3)
            m,d=self.push(e,10);self.assertEqual((m['Out'],d['Out'],m['Status']),(10.0,0.0,0))

    def test_combined_input_and_length_faults_use_status_bits_one_and_two(self):
        e=self.checked(m={'InFault':True,'NumberOfSamples':0,'Out':7},d={'InFault':True,'NumberOfSamples':0,'Out':8,'Average':9})
        e.step();self.assertEqual((e.memory.read('M.Status'),e.memory.read('D.Status')),(7,7))
        self.assertEqual((e.memory.read('M.Out'),e.memory.read('D.Out'),e.memory.read('D.Average')),(7,8,9))

    def test_weight_capacity_only_limits_weighted_mode(self):
        def short(root):
            tags=root.find('./Controller/Tags');tags.remove(tags.find('./Tag[@Name="W"]'));array(tags,'W',[1.0,0.5])
        e=self.checked(mutate=short);self.assertEqual(self.push(e,8)[0]['Status'],0)
        e.memory.write('M.UseWeights',True);self.assertEqual(self.push(e,10)[0]['Status'],5)
        e.memory.write('M.NumberOfSamples',2);self.assertEqual(self.push(e,4)[0]['Out'],4.0)

    def test_window_growth_fills_incrementally_and_shrink_keeps_newest(self):
        e=self.checked(m={'NumberOfSamples':2},d={'NumberOfSamples':2});self.push(e,2);self.push(e,4)
        for ref in ('M.NumberOfSamples','D.NumberOfSamples'):e.memory.write(ref,4)
        self.assertEqual(self.push(e,6)[0]['Out'],4.0);self.assertEqual(self.push(e,8)[0]['Out'],5.0)
        for ref in ('M.NumberOfSamples','D.NumberOfSamples'):e.memory.write(ref,2)
        m,d=self.push(e,10);self.assertEqual((m['Out'],d['Average'],d['Out']),(9.0,9.0,1.0))
        self.assertEqual(e.memory.read('S'),[10.0,8.0,4.0,2.0])

    def test_shrink_while_sampling_disabled_holds_output_but_drops_old_active_count(self):
        e=self.checked();self.push(e,2);self.push(e,4);self.push(e,6)
        e.memory.write('M.SampleEnable',False);e.memory.write('M.NumberOfSamples',1);self.push(e,8)
        self.assertEqual(e.memory.read('M.Out'),4.0);e.memory.write('M.NumberOfSamples',3);e.memory.write('M.SampleEnable',True)
        self.assertEqual(self.push(e,10)[0]['Out'],8.0)

    def test_repeated_calls_at_one_timestamp_each_take_a_sample(self):
        e=self.checked(['M.In:=2; MAVE(M,S); M.In:=4; MAVE(M,S); M.In:=6; MAVE(M,S);'])
        e.step();self.assertEqual((e.memory.read('M.Out'),e.memory.read('S')[:3]),(4.0,[6.0,4.0,2.0]))

    def test_external_active_storage_write_is_used_but_output_write_is_not_history(self):
        e=self.checked();self.push(e,2);e.memory.write('S[0]',10);e.memory.write('M.Out',99)
        self.assertEqual(self.push(e,4)[0]['Out'],7.0)

    def test_unknown_tail_is_not_read_and_cold_storage_is_ignored(self):
        def missing(root):
            tags=root.find('./Controller/Tags')
            for name in ('S','T'):
                tags.remove(tags.find(f'./Tag[@Name="{name}"]'));array(tags,name,[None,None,None,None])
        e=self.checked(mutate=missing);self.assertEqual(self.push(e,2)[0]['Out'],2.0)
        self.assertEqual(e.memory.at(*e.memory.resolve('S')[:2]),[2.0,None,None,None])

    def test_unknown_active_sample_faults_and_preserves_count_for_retry(self):
        e=self.checked();self.push(e,2);key,parts,_=e.memory.resolve('S[0]');e.memory.store(key,parts,None)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms));e.memory.write('M.In',4);e.memory.write('D.In',4)
        snapshot=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'active sample'):e.step()
        self.assertEqual((e.last_timer,e.time_ms),(before[1],before[2]));self.assertEqual(e.memory.values,snapshot)
        e.memory.write('S[0]',2);e.step();self.assertEqual(e.memory.read('M.Out'),3.0)

    def test_unknown_active_weight_faults_only_when_used(self):
        e=self.checked();key,parts,_=e.memory.resolve('W[0]');e.memory.store(key,parts,None);self.push(e,2)
        e.memory.write('M.UseWeights',True)
        with self.assertRaisesRegex(ModelError,'active weight'):self.push(e,4)
        e.memory.write('W[0]',0.5);e.step();self.assertEqual(e.memory.read('M.Out'),2.5)

    def test_unknown_unused_input_holds_during_fault_or_sampling_disabled(self):
        e=self.checked(m={'SampleEnable':False},d={'InFault':True})
        for ref in ('M.In','D.In'):
            key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,None)
        e.step();self.assertEqual((e.memory.read('M.Out'),e.memory.read('D.Status')),(0.0,3))

    def test_nonfinite_and_float32_intermediate_overflow_roll_back(self):
        e=self.checked(m={'UseWeights':True});e.memory.write('M.In',3e38);e.memory.write('W[0]',2.0)
        before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.last_timer,{})
        key,parts,_=e.memory.resolve('M.In');e.memory.store(key,parts,float('nan'))
        with self.assertRaisesRegex(ModelError,'Nonfinite'):e.step()

    def test_late_fault_rolls_back_queue_count_and_corrected_retry_samples_once(self):
        e=self.checked(['MAVE(M,S,W); MSTD(D,T); SpeedCommand:=1/SpeedSetpoint;']);e.memory.write('SpeedSetpoint',1);self.push(e,2)
        e.memory.write('SpeedSetpoint',0);e.memory.write('M.In',4);e.memory.write('D.In',4)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace))
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.trace),before)
        e.memory.write('SpeedSetpoint',1);e.step();self.assertEqual((e.memory.read('M.Out'),e.memory.read('D.Out')),(3.0,1.0))

    def test_element_budget_and_run_entry_reset_history(self):
        e=self.checked();self.push(e,2);self.push(e,4);history=copy.deepcopy(e.last_timer);e.instruction_limit=3
        with self.assertRaisesRegex(ModelError,'budget'):self.push(e,6)
        self.assertEqual(e.last_timer,history);e.instruction_limit=100000;e.step();e.enter_run()
        self.assertEqual(e.last_timer,{});self.assertEqual(self.push(e,10)[0]['Out'],10.0)

    def test_deferred_prescan_does_not_initialize_or_erase_saved_data(self):
        e=self.checked(m={'Out':17},d={'Out':18,'Average':19},defer=True)
        self.assertEqual((e.memory.read('M.Out'),e.memory.read('D.Out'),e.last_timer),(17.0,18.0,{}))
        self.push(e,2);self.assertEqual(e.memory.read('M.Out'),2.0)

    def test_constant_record_or_storage_blocks_even_unreached(self):
        for name in ('M','S'):
            def const(root):root.find(f'./Controller/Tags/Tag[@Name="{name}"]').set('Constant','true')
            self.assertTrue(self.engine(['IF FALSE THEN MAVE(M,S,W); END_IF;'],mutate=const).blockers)

    def test_wrong_records_array_types_rank_dynamic_reference_and_overlap_block(self):
        for text in ('MAVE(D,S,W);','MSTD(M,T);','MAVE(M,S[0],W);','MAVE(M,S,SpeedSetpoint);',
                     'MAVE(M,S[SpeedCommand],W);','MAVE(M,S,S);','MAVE(M,S); MSTD(D,S[0]);',
                     'MAVE(M);','MSTD(D,T,W);'):
            with self.subTest(text=text):self.assertTrue(self.engine([text]).blockers)
        def integer(root):root.find('./Controller/Tags/Tag[@Name="S"]').set('DataType','DINT')
        self.assertTrue(self.engine(mutate=integer).blockers)

    def test_storage_binding_change_is_explicitly_rejected(self):
        e=self.checked(['MAVE(M,S); MAVE(M,T);']);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'storage binding'):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual(e.last_timer,{})

    def test_status_aliases_share_backing_word_and_declared_types(self):
        e=self.checked();e.memory.write('M.InFaulted',True);self.assertEqual(e.memory.read('M.Status'),2)
        e.memory.write('D.Status',5);self.assertTrue(e.memory.read('D.NumberOfSampInv'))
        for dtype,fields in SCHEMAS.items():
            root='M' if dtype=='MOVING_AVERAGE' else 'D'
            for name,kind in fields.items():self.assertEqual(e.memory.resolve(root+'.'+name)[2],kind)

    def test_for_write_effects_protect_record_bounds(self):
        e=self.engine(['FOR SpeedCommand:=0 TO M.NumberOfSamples DO MAVE(M,S,W); END_FOR;'])
        self.assertTrue(e.blockers)

    def test_rll_forms_and_other_profiles_are_blocked(self):
        def rll(root):
            rr=root.find('./Controller/Programs/Program/Routines/Routine');rr.remove(rr.find('STContent'));rr.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(rr,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='MAVE(M,S,W);'
        self.assertTrue(self.engine(mutate=rll).blockers)
        for major,processor in (('34','1756-L85E'),('35','1756-L73')):
            def profile(root):root.find('Controller').set('MajorRev',major);root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(mutate=profile).blockers)

    def test_detached_routine_replacement_preserves_queue_count(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def sub(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0]
            main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(Statistics,0);'
            logic(E.SubElement(routines,'Routine',Name='Statistics',Type='ST'),['MAVE(M,S,W); MSTD(D,T);'])
        e=self.checked(mutate=sub);self.push(e,2);self.push(e,4);before=copy.deepcopy((e.memory.values,e.last_timer))
        neutral=['JSR(Statistics,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        source=decode(container(E.tostring(xml,encoding='utf-8')));candidate,_=prepare(e,source,tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e.last_timer),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.assertEqual(self.push(candidate,6)[0]['Out'],4.0)

    def test_instruction_counts_and_logical_type_classification(self):
        e=self.checked();self.assertEqual(len(ARITIES),101);self.assertEqual(len(ST_ONLY_ARITIES),20)
        self.assertTrue({'MOVING_AVERAGE','MOVING_STD_DEV'}.isdisjoint(e.project.data_only_types))
        self.assertEqual(e.report()['st_moving']['instructions'],['MAVE','MSTD']);self.assertFalse(e.report()['st_moving']['native_runtime_parity'])

    def test_program_local_record_and_storage_alias_share_resolved_history(self):
        def local(root):
            tags=root.find('./Controller/Tags');program=root.find('./Controller/Programs/Program/Tags')
            for name in ('M','S'):
                tag=tags.find(f'./Tag[@Name="{name}"]');tags.remove(tag);program.append(tag)
                E.SubElement(tags,'Tag',Name='Alias'+name,TagType='Alias',AliasFor='Program:MainProgram.'+name)
        e=self.checked(['MAVE(AliasM,AliasS,W);'],mutate=local)
        e.memory.write('AliasM.In',2);e.step();e.memory.write('AliasM.In',4);e.step()
        self.assertEqual(e.memory.read('AliasM.Out'),3.0);self.assertEqual(e.memory.read('AliasS')[:2],[4.0,2.0])

    def test_udt_array_records_and_member_queues_have_independent_history(self):
        def nested(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='FilterCell',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='State',DataType='MOVING_AVERAGE',Dimension='0')
            E.SubElement(members,'Member',Name='Queue',DataType='REAL',Dimension='4')
            tags=root.find('./Controller/Tags');tag=E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='FilterCell',Dimensions='2')
            data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='FilterCell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(data,'Element',Index=f'[{i}]'),'Structure',DataType='FilterCell')
                state=copy.deepcopy(tags.find('./Tag[@Name="M"]/Data/Structure'));state.tag='StructureMember';state.set('Name','State');obj.append(state)
                queue=copy.deepcopy(tags.find('./Tag[@Name="S"]/Data/Array'));queue.tag='ArrayMember';queue.set('Name','Queue');obj.append(queue)
        e=self.checked(['MAVE(Cells[0].State,Cells[0].Queue); MAVE(Cells[1].State,Cells[1].Queue);'],mutate=nested)
        for a,b in ((2,10),(4,20)):
            e.memory.write('Cells[0].State.In',a);e.memory.write('Cells[1].State.In',b);e.step()
        self.assertEqual((e.memory.read('Cells[0].State.Out'),e.memory.read('Cells[1].State.Out')),(3.0,15.0))

    def test_aoi_inout_record_array_bindings_and_routine_harness(self):
        def aoi(root):
            definition=E.SubElement(root.find('./Controller/AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='MovingBlock',Revision='1.0')
            params=E.SubElement(definition,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):
                E.SubElement(params,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            for name,dtype,dim in (('State','MOVING_AVERAGE','0'),('Storage','REAL','4'),('Weights','REAL','4')):
                E.SubElement(params,'Parameter',Name=name,TagType='Base',DataType=dtype,Dimensions=dim,Usage='InOut',Required='true',Visible='true')
            E.SubElement(definition,'LocalTags');logic(E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='ST'),['MAVE(State,Storage,Weights);'])
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',DataType='MovingBlock',TagType='Base')
            data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='MovingBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(data,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['MovingBlock(Instance,M,S,W);'],mutate=aoi);self.push(e,2);self.assertEqual(self.push(e,4)[0]['Out'],3.0)
        harness=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(harness.blockers,[])
        self.push(harness,2);self.assertEqual(self.push(harness,4)[0]['Out'],3.0)

    def test_weight_mode_changes_keep_existing_sample_count(self):
        e=self.checked();self.push(e,2);e.memory.write('M.UseWeights',True)
        self.assertEqual(self.push(e,4)[0]['Out'],2.5);e.memory.write('M.UseWeights',False)
        self.assertEqual(self.push(e,6)[0]['Out'],4.0)

    def test_periodic_task_takes_one_sample_per_release(self):
        def periodic(root):
            task=root.find('./Controller/Tasks/Task');task.set('Type','PERIODIC');task.set('Rate','20')
        e=self.checked(mutate=periodic)
        for value in (2,4,6):self.push(e,value,dt=20)
        self.assertEqual((e.memory.read('M.Out'),e.scheduler_description()['tasks'][0]['executions']),(4.0,3))

    def test_ladder_for_target_st_samples_each_iteration_at_same_time(self):
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0]
            main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='FOR(Sample,SpeedCommand,0,2,1);'
            logic(E.SubElement(routines,'Routine',Name='Sample',Type='ST'),['M.In:=SpeedCommand; MAVE(M,S);'])
        e=self.checked(mutate=caller);e.step()
        self.assertEqual((e.memory.read('M.Out'),e.memory.read('S')[:3]),(1.0,[2.0,1.0,0.0]))

    def test_multidimensional_or_oversized_storage_is_blocked(self):
        def rank(root):
            tag=root.find('./Controller/Tags/Tag[@Name="S"]');tag.set('Dimensions','2,2')
            data=tag.find('Data/Array');data.clear();data.set('DataType','REAL');data.set('Dimensions','2,2')
            for a in range(2):
                for b in range(2):E.SubElement(data,'Element',Index=f'[{a},{b}]',Value='0.0')
        self.assertTrue(self.engine(mutate=rank).blockers)
        def large(root):
            tags=root.find('./Controller/Tags');tags.remove(tags.find('./Tag[@Name="S"]'));array(tags,'S',[0.0]*4097)
        self.assertTrue(self.engine(mutate=large).blockers)

    def test_redefined_record_is_blocked_and_missing_required_field_stays_unknown(self):
        def redefine(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='MOVING_AVERAGE',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='Out',DataType='REAL',Dimension='0')
        self.assertTrue(self.engine(mutate=redefine).blockers)
        def missing(root):
            obj=root.find('./Controller/Tags/Tag[@Name="M"]/Data/Structure');obj.remove(obj.find('DataValueMember[@Name="SampleEnable"]'))
        e=self.checked(mutate=missing);self.assertIsNone(e.memory.read('M')['SampleEnable'])
        with self.assertRaisesRegex(ModelError,'SampleEnable is unknown'):e.step()

    def test_public_moving_lab_imports_and_defaults_to_uniform_sampling(self):
        e=Engine(Project(SAMPLES/'MovingLab.L5X'));self.assertEqual(e.blockers,[])
        for value in (2,4):e.memory.write('Input',value);e.step()
        self.assertEqual((e.memory.read('Average'),e.memory.read('PopulationMean'),e.memory.read('Deviation')),(3.0,3.0,1.0))


if __name__=='__main__':unittest.main()
