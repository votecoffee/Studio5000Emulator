"""Piecewise curves, delayed arrays, resizing, health and transaction boundaries."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ARITIES,ST_ONLY_ARITIES,ModelError,Op,Project,operand_problem
from logixlab.runtime import Engine
from logixlab.st_curves import MAX_DT,SCHEMAS,default
from test_st_timers import logic

SAMPLES=Path(__file__).resolve().parents[1]/'samples'


def record(parent,name,dtype,values=None):
    tag=E.SubElement(parent,'Tag',Name=name,TagType='Base',DataType=dtype)
    obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType=dtype)
    for member,value in (default(dtype)|dict(values or {})).items():
        E.SubElement(obj,'DataValueMember',Name=member,DataType=SCHEMAS[dtype][member],Value=str(int(value)) if isinstance(value,bool) else str(value))
    return tag


def array(parent,name,values):
    tag=E.SubElement(parent,'Tag',Name=name,TagType='Base',DataType='REAL',Dimensions=str(len(values)))
    data=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='REAL',Dimensions=str(len(values)))
    for i,value in enumerate(values):E.SubElement(E.SubElement(data,'Element',Index=f'[{i}]'),'DataValue',DataType='REAL',Value=str(value))
    return tag


class StructuredCurveTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,lines=None,*,f=None,d=None,buffer=None,mutate=None,defer=False):
        root=E.parse(SAMPLES/'ConveyorDemo.L5X').getroot();tags=root.find('./Controller/Tags')
        record(tags,'F','FUNCTION_GENERATOR',dict(XY1Size=3,XY2Size=3)|dict(f or {}))
        record(tags,'D','DEADTIME',dict(TimingMode=1,OversampleDT=0.25,Deadtime=0.5)|dict(d or {}))
        for name,values in [('X1',[0,10,20]),('Y1',[0,100,50]),('X2',[0,10,20]),('Y2',[100,200,400]),('Buffer',[0,0,9,8] if buffer is None else buffer),('Other',[0,0,0,0])]:array(tags,name,values)
        logic(root.find('./Controller/Programs/Program/Routines/Routine'),lines if lines is not None else ['FGEN(F,X1,Y1,X2,Y2); DEDT(D,Buffer);'])
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'curves.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def step(self,e,dt=250):e.step(dt);return e.memory.read('F'),e.memory.read('D'),e.memory.read('Buffer')

    def test_fgen_linear_segments_endpoints_and_outside_clamping(self):
        e=self.checked()
        for value,expected in ((-5,0),(0,0),(5,50),(10,100),(15,75),(20,50),(25,50)):
            e.memory.write('F.In',value);f,_,_=self.step(e);self.assertEqual((f['Out'],f['Status']),(expected,0))

    def test_fgen_one_point_is_constant_and_does_not_require_input(self):
        e=self.checked(f={'XY1Size':1});key,parts,_=e.memory.resolve('F.In');e.memory.store(key,parts,None)
        self.assertEqual(self.step(e)[0]['Out'],0)

    def test_fgen_optional_second_table_and_selected_size_diagnostics(self):
        e=self.checked(['FGEN(F,X1,Y1);']);self.step(e);e.memory.write('F.Select',True);e.memory.write('F.Out',77)
        f,_,_=self.step(e);self.assertEqual((f['Out'],f['Status']),(77,5))
        e=self.checked(f={'Select':True,'In':15});self.assertEqual(self.step(e)[0]['Out'],300)

    def test_fgen_invalid_active_size_holds_visible_out_and_recovers(self):
        e=self.checked(f={'In':5});self.step(e)
        for count in (0,-1,4):
            e.memory.write('F.XY1Size',count);e.memory.write('F.Out',77);f,_,_=self.step(e)
            self.assertEqual((f['Out'],f['Status']),(77,3))
        e.memory.write('F.XY1Size',3);self.assertEqual(self.step(e)[0]['Out'],50)

    def test_fgen_inactive_counts_tables_and_unused_y_values_can_be_unknown(self):
        e=self.checked(f={'In':-1})
        for ref in ('F.XY2Size','X2[0]','Y2[0]','Y1[1]','Y1[2]'):
            key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,None)
        self.assertEqual(self.step(e)[0]['Out'],0)
        e.memory.write('F.In',5)
        with self.assertRaisesRegex(ModelError,'unknown'):self.step(e)

    def test_fgen_active_x_must_all_be_sorted_even_when_input_outside_curve(self):
        for last in (10,5):
            e=self.checked(f={'In':-1,'Out':77});e.memory.write('X1[2]',last);f,_,_=self.step(e)
            self.assertEqual((f['Out'],f['Status']),(77,9))
            e.memory.write('X1[2]',20);self.assertEqual(self.step(e)[0]['Status'],0)

    def test_fgen_reads_current_table_changes_without_modifying_arrays(self):
        e=self.checked(f={'In':5});self.assertEqual(self.step(e)[0]['Out'],50)
        e.memory.write('Y2[1]',300);e.memory.write('F.Select',True);before=copy.deepcopy(e.memory.read('Y2'))
        self.assertEqual(self.step(e)[0]['Out'],200);self.assertEqual(e.memory.read('Y2'),before)
        e.memory.write('F.Select',False);self.assertEqual(self.step(e)[0]['Out'],50)

    def test_fgen_read_only_constant_arrays_are_accepted(self):
        def constant(root):
            for name in ('X1','Y1','X2','Y2'):root.find(f'./Controller/Tags/Tag[@Name="{name}"]').set('Constant','true')
        e=self.checked(f={'In':5},mutate=constant);self.assertEqual(self.step(e)[0]['Out'],50)

    def test_fgen_unknown_selected_x_and_nonfinite_values_fault(self):
        for ref,value in (('X1[2]',None),('Y1[0]',float('inf')),('F.Select',None)):
            e=self.checked();key,parts,_=e.memory.resolve(ref);e.memory.store(key,parts,value)
            with self.subTest(ref=ref),self.assertRaises(ModelError):self.step(e)
            self.assertEqual((e.last_timer,e.time_ms),({},0))

    def test_dedt_startup_validates_without_changing_saved_out_or_buffer(self):
        e=self.checked(d={'In':10,'Out':77},buffer=[1,2,9,8]);_,d,b=self.step(e)
        self.assertEqual((d['Out'],b),(77,[1,2,9,8]));self.assertEqual(d['DeltaT'],0.25)
        _,d,b=self.step(e);self.assertEqual((d['Out'],b),(2,[10,1,9,8]))

    def test_dedt_two_interval_delay_and_gain_bias(self):
        e=self.checked(d={'Gain':2,'Bias':1});self.step(e)
        for value,out,prefix in ((10,0,[21,0]),(20,0,[41,21]),(30,21,[61,41])):
            e.memory.write('D.In',value);_,d,b=self.step(e);self.assertEqual((d['Out'],b[:2],b[2:]),(out,prefix,[9,8]))

    def test_dedt_rounds_half_intervals_upward(self):
        e=self.checked(d={'Deadtime':0.625,'In':9},buffer=[1,2,3,4]);self.step(e);_,d,b=self.step(e)
        self.assertEqual((d['Out'],b),(3,[9,1,2,4]))

    def test_dedt_runtime_growth_extends_oldest_and_shrink_discards_oldest(self):
        e=self.checked();self.step(e)
        for value in (1,2):e.memory.write('D.In',value);self.step(e)
        e.memory.write('D.Deadtime',1);e.memory.write('D.In',3);_,d,b=self.step(e)
        self.assertEqual((d['Out'],b),(1,[3,2,1,1]))
        e.memory.write('D.Deadtime',0.25);e.memory.write('D.In',4);_,d,b=self.step(e)
        self.assertEqual((d['Out'],b),(3,[4,2,1,1]))

    def test_dedt_zero_and_invalid_delay_pass_scaled_input_and_retain_request(self):
        for delay,status in ((0,0),(-1,5),(2,5)):
            e=self.checked(d={'Deadtime':delay,'In':3,'Gain':2,'Bias':1});self.step(e);_,d,b=self.step(e)
            self.assertEqual((d['Out'],d['Status'],d['Deadtime'],b),(7,status,delay,[0,0,9,8]))

    def test_dedt_growth_from_zero_seeds_current_scaled_input(self):
        e=self.checked(d={'Deadtime':0,'In':2});self.step(e);self.step(e)
        e.memory.write('D.Deadtime',0.5);e.memory.write('D.In',3);_,d,b=self.step(e)
        self.assertEqual((d['Out'],b),(3,[3,3,9,8]))

    def test_dedt_bad_health_holds_and_recovery_seeds_active_buffer(self):
        e=self.checked(d={'In':2});self.step(e);self.step(e);before=copy.deepcopy(e.memory.read('Buffer'))
        e.memory.write('D.InFault',True);key,parts,_=e.memory.resolve('D.In');e.memory.store(key,parts,None)
        _,d,b=self.step(e);self.assertEqual((d['Out'],d['Status'],b),(0,3,before))
        e.memory.write('D.InFault',False);e.memory.write('D.In',7);_,d,b=self.step(e)
        self.assertEqual((d['Out'],d['Status'],b),(7,0,[7,7,9,8]))

    def test_dedt_recovery_waits_through_zero_or_invalid_timing(self):
        e=self.checked(d={'InFault':True});self.step(e);e.memory.write('D.InFault',False);e.memory.write('D.In',7)
        for interval in (0,-1):e.memory.write('D.OversampleDT',interval);self.step(e)
        e.memory.write('D.OversampleDT',0.25);_,d,b=self.step(e);self.assertEqual((d['Out'],b),(7,[7,7,9,8]))

    def test_dedt_zero_invalid_intervals_and_modes_hold_buffer(self):
        for interval,status in ((0,0),(-1,-2147483647),(5000,-2147483647)):
            e=self.checked(d={'OversampleDT':interval,'Out':77});self.step(e);_,d,b=self.step(e)
            self.assertEqual((d['Out'],d['DeltaT'],d['Status'],b),(77,0,status,[0,0,9,8]))
        e=self.checked(d={'TimingMode':3,'Out':77});self.step(e);self.assertEqual(self.step(e)[1]['Status'],134217729)
        e.memory.write('D.TimingMode',2)
        with self.assertRaisesRegex(ModelError,'real time sampling'):self.step(e)

    def test_dedt_unknown_health_is_not_false_and_unknown_active_buffer_faults(self):
        e=self.checked();key,parts,_=e.memory.resolve('D.InFault');e.memory.store(key,parts,None)
        with self.assertRaisesRegex(ModelError,'InFault is unknown'):self.step(e)
        e=self.checked();self.step(e);key,parts,_=e.memory.resolve('Buffer[1]');e.memory.store(key,parts,None)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms))
        with self.assertRaisesRegex(ModelError,'unknown'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms),before)

    def test_dedt_elapsed_time_includes_skipped_calls_without_sampling_them(self):
        e=self.checked(['IF StartPB THEN DEDT(D,Buffer); END_IF;'],d={'TimingMode':0,'Deadtime':0.75})
        e.memory.write('StartPB',True);self.step(e);e.memory.write('StartPB',False);self.step(e);self.step(e)
        e.memory.write('StartPB',True);e.memory.write('D.In',7);_,d,b=self.step(e)
        self.assertEqual((d['DeltaT'],d['Out'],b),(0.75,0,[7,0,9,8]))

    def test_dedt_periodic_timing_and_explicit_repeated_calls(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','PERIODIC');t.set('Rate','100')
        e=self.checked(d={'TimingMode':0,'Deadtime':0.2},mutate=periodic);self.step(e,100);self.assertAlmostEqual(self.step(e,100)[1]['DeltaT'],0.1,places=6)
        e=self.checked(['DEDT(D,Buffer); DEDT(D,Buffer);'],d={'In':3},buffer=[1,2,9,8]);self.assertEqual(self.step(e)[1]['Out'],2)

    def test_dedt_maximum_interval_and_backwards_clock(self):
        e=self.checked(d={'OversampleDT':MAX_DT});self.assertEqual(self.step(e)[1]['DeltaT'],MAX_DT)
        e=self.checked(d={'TimingMode':0});self.step(e);next(v for k,v in e.last_timer.items() if k[0]=='ST-DEADTIME')['at']=1000
        with self.assertRaisesRegex(ModelError,'backwards'):self.step(e)

    def test_dedt_fixed_binding_and_shared_storage_are_rejected_during_run(self):
        e=self.checked(['IF StartPB THEN DEDT(D,Buffer); ELSE DEDT(D,Other); END_IF;']);self.step(e);e.memory.write('StartPB',True)
        with self.assertRaisesRegex(ModelError,'binding'):self.step(e)
        def extra(root):record(root.find('./Controller/Tags'),'D2','DEADTIME')
        e=self.checked(['DEDT(D,Buffer); DEDT(D2,Buffer);'],mutate=extra)
        with self.assertRaisesRegex(ModelError,'share'):self.step(e)
        self.assertEqual(e.last_timer,{})

    def test_dedt_overflow_does_not_commit_curve_or_storage_changes(self):
        e=self.checked(d={'Gain':3e38,'In':2},f={'In':5});before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms))
        with self.assertRaisesRegex(ModelError,'REAL'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms),before)

    def test_late_fault_restores_both_outputs_buffer_and_resize_state(self):
        e=self.checked(['FGEN(F,X1,Y1); DEDT(D,Buffer); SpeedCommand:=1/SpeedSetpoint;']);e.memory.write('SpeedSetpoint',1);self.step(e)
        e.memory.write('F.In',5);e.memory.write('D.Deadtime',1);e.memory.write('D.In',3);e.memory.write('SpeedSetpoint',0)
        before=copy.deepcopy((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.time_ms,e.scan_count,e.scheduler_description()),before)
        e.memory.write('D.Deadtime',0.5);e.memory.write('SpeedSetpoint',1);f,d,b=self.step(e)
        self.assertEqual((f['Out'],d['Out'],b),(50,0,[3,0,9,8]))

    def test_point_and_sample_budgets_roll_back(self):
        e=self.checked(['FGEN(F,X1,Y1);']);e.instruction_limit=2
        with self.assertRaisesRegex(ModelError,'point budget'):self.step(e)
        e=self.checked(['DEDT(D,Buffer);']);self.step(e);before=copy.deepcopy((e.memory.values,e.last_timer));e.instruction_limit=2
        with self.assertRaisesRegex(ModelError,'sample budget'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer),before)

    def test_run_reentry_resets_history_and_failed_prescan_preserves_it(self):
        e=self.checked(defer=True);self.step(e);e.memory.write('D.In',3);self.step(e);before=copy.deepcopy((e.memory.values,e.last_timer,e.prescan_count))
        e.instruction_limit=1
        with self.assertRaisesRegex(ModelError,'Prescan rolled back'):e.enter_run()
        self.assertEqual((e.memory.values,e.last_timer,e.prescan_count),before)
        e.fault='';e.instruction_limit=100;e.enter_run();buffer=copy.deepcopy(e.memory.read('Buffer'));self.step(e)
        self.assertEqual(e.memory.read('Buffer'),buffer)

    def test_enables_skips_and_for_write_effects(self):
        e=self.checked(['IF StartPB THEN FGEN(F,X1,Y1); DEDT(D,Buffer); END_IF;']);e.memory.write('StartPB',True);self.step(e)
        for tag in ('F','D'):
            for member in ('EnableIn','EnableOut'):e.memory.write(tag+'.'+member,False)
        e.memory.write('StartPB',False);before=copy.deepcopy(e.last_timer);self.step(e);self.assertEqual(e.last_timer,before)
        e.memory.write('StartPB',True);self.step(e);self.assertTrue(all(e.memory.read(tag+'.'+m) for tag in ('F','D') for m in ('EnableIn','EnableOut')))
        for line in ('FOR SpeedCommand:=0 TO F.Status DO FGEN(F,X1,Y1); END_FOR;',
                     'FOR SpeedCommand:=0 TO D.Status DO DEDT(D,Buffer); END_FOR;'):
            self.assertTrue(self.engine([line]).blockers)

    def test_defaults_member_types_status_aliases_and_operand_forms(self):
        e=self.checked();self.assertEqual((len(SCHEMAS['FUNCTION_GENERATOR']),len(SCHEMAS['DEADTIME'])),(8,14))
        for tag,dtype in (('F','FUNCTION_GENERATOR'),('D','DEADTIME')):
            self.assertNotIn(dtype,e.project.data_only_types)
            for member,kind in SCHEMAS[dtype].items():self.assertEqual(e.memory.resolve(tag+'.'+member)[2],kind)
        e.memory.write('F.XisOutofOrder',True);self.assertEqual(e.memory.read('F.Status'),8)
        e.memory.write('D.TimingModeInv',True);self.assertEqual(e.memory.read('D.Status'),134217728)
        self.assertEqual(e.memory.resolve('D.TimingMode')[2],'DINT')
        self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(101,26))
        self.assertFalse(operand_problem(Op('FGEN',['F','X1','Y1'])))
        self.assertTrue(operand_problem(Op('FGEN',['F','X1','Y1','X2'])))
        self.assertFalse(e.report()['st_curves']['native_runtime_parity'])

    def test_wrong_arity_arrays_constants_redefinitions_and_ladder_are_blocked(self):
        for text in ('FGEN();','FGEN(F,X1,Y1,X2);','FGEN(D,X1,Y1);','FGEN(F,SpeedCommand,Y1);','DEDT(D);','DEDT(F,Buffer);','DEDT(D,Buffer[0]);'):
            self.assertTrue(self.engine([text]).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="Buffer"]').set('Constant','true')
        self.assertTrue(self.engine(mutate=constant).blockers)
        for dtype in SCHEMAS:
            def redefine(root):
                m=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name=dtype,Class='User',Family='NoFamily'),'Members');E.SubElement(m,'Member',Name='Out',DataType='REAL',Dimension='0')
            self.assertTrue(self.engine(mutate=redefine).blockers)
        def ladder(root):
            t=root.find('./Controller/Programs/Program/Routines/Routine');t.remove(t.find('STContent'));t.set('Type','RLL');E.SubElement(E.SubElement(E.SubElement(t,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='DEDT(D,Buffer);'
        self.assertTrue(self.engine(mutate=ladder).blockers)

    def test_other_profiles_are_blocked(self):
        for version,processor in (('34','1756-L85E'),('35','1756-L73')):
            def profile(root):root.find('Controller').set('MajorRev',version);root.find('Controller').set('ProcessorType',processor)
            self.assertTrue(self.engine(mutate=profile).blockers)

    def test_alias_program_local_storage_and_harness(self):
        def local(root):
            tags=root.find('./Controller/Tags');local_tags=root.find('./Controller/Programs/Program/Tags')
            for name in ('F','D','Buffer'):
                t=tags.find(f'./Tag[@Name="{name}"]');tags.remove(t);local_tags.append(t)
                E.SubElement(tags,'Tag',Name='Alias'+name,TagType='Alias',AliasFor='Program:MainProgram.'+name)
        e=self.checked(['FGEN(AliasF,X1,Y1); DEDT(AliasD,AliasBuffer);'],mutate=local);e.step(250);e.memory.write('AliasD.In',3);e.step(250)
        self.assertEqual(e.memory.read('AliasBuffer'),[3,0,9,8])
        h=Engine(e.project,'routine','MainProgram/MainRoutine');self.assertEqual(h.blockers,[]);h.step(250)

    def test_aoi_inout_records_and_arrays_share_the_same_models(self):
        def aoi(root):
            a=E.SubElement(root.find('./Controller/AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='CurveBlock',Revision='1.0');p=E.SubElement(a,'Parameters')
            for name,usage in (('EnableIn','Input'),('EnableOut','Output')):E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType='BOOL',Usage=usage,Required='false',Visible='false')
            for name,dtype,dim in (('Curve','FUNCTION_GENERATOR','0'),('Delay','DEADTIME','0'),('X','REAL','3'),('Y','REAL','3'),('Storage','REAL','4')):
                E.SubElement(p,'Parameter',Name=name,TagType='Base',DataType=dtype,Dimensions=dim,Usage='InOut',Required='true',Visible='true')
            E.SubElement(a,'LocalTags');logic(E.SubElement(E.SubElement(a,'Routines'),'Routine',Name='Logic',Type='ST'),['FGEN(Curve,X,Y); Delay.In:=Curve.Out; DEDT(Delay,Storage);'])
            t=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Instance',TagType='Base',DataType='CurveBlock');obj=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Structure',DataType='CurveBlock')
            for name in ('EnableIn','EnableOut'):E.SubElement(obj,'DataValueMember',Name=name,DataType='BOOL',Value='0')
        e=self.checked(['CurveBlock(Instance,F,D,X1,Y1,Buffer);'],f={'In':5},mutate=aoi)
        self.step(e);self.step(e);self.assertEqual(self.step(e)[2],[50,50,9,8])
        self.assertEqual(self.step(e)[1]['Out'],50)

    def test_nested_udt_records_and_member_buffers_are_independent(self):
        def nested(root):
            members=E.SubElement(E.SubElement(root.find('./Controller/DataTypes'),'DataType',Name='DelayCell',Class='User',Family='NoFamily'),'Members')
            E.SubElement(members,'Member',Name='State',DataType='DEADTIME',Dimension='0');E.SubElement(members,'Member',Name='Queue',DataType='REAL',Dimension='4')
            tags=root.find('./Controller/Tags');t=E.SubElement(tags,'Tag',Name='Cells',TagType='Base',DataType='DelayCell',Dimensions='2');arr=E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'Array',DataType='DelayCell',Dimensions='2')
            for i in range(2):
                obj=E.SubElement(E.SubElement(arr,'Element',Index=f'[{i}]'),'Structure',DataType='DelayCell')
                item=copy.deepcopy(tags.find('./Tag[@Name="D"]/Data/Structure'));item.tag='StructureMember';item.set('Name','State');obj.append(item)
                item=copy.deepcopy(tags.find('./Tag[@Name="Buffer"]/Data/Array'));item.tag='ArrayMember';item.set('Name','Queue');obj.append(item)
        e=self.checked(['DEDT(Cells[0].State,Cells[0].Queue); DEDT(Cells[1].State,Cells[1].Queue);'],mutate=nested)
        e.step(250);e.memory.write('Cells[0].State.In',2);e.memory.write('Cells[1].State.In',7);e.step(250)
        self.assertEqual((e.memory.read('Cells[0].Queue'),e.memory.read('Cells[1].Queue')),([2,0,9,8],[7,0,9,8]))

    def test_ladder_for_target_advances_curve_and_delay_per_iteration(self):
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='FOR(Curves,SpeedCommand,0,2,1);'
            logic(E.SubElement(routines,'Routine',Name='Curves',Type='ST'),['F.In:=SpeedCommand; FGEN(F,X1,Y1); D.In:=F.Out; DEDT(D,Buffer);'])
        e=self.checked(mutate=caller);f,d,b=self.step(e);self.assertEqual((f['Out'],d['Out'],b),(20,0,[20,10,9,8]))

    def test_oversized_rank_two_and_dynamic_array_operands_block(self):
        def oversized(root):
            tags=root.find('./Controller/Tags');tags.remove(tags.find('./Tag[@Name="Buffer"]'));array(tags,'Buffer',[0]*4097)
        self.assertTrue(self.engine(mutate=oversized).blockers)
        def rank(root):
            tag=root.find('./Controller/Tags/Tag[@Name="Buffer"]');tag.set('Dimensions','2,2');data=tag.find('Data/Array');data.clear();data.set('DataType','REAL');data.set('Dimensions','2,2')
            for i in range(2):
                for j in range(2):E.SubElement(data,'Element',Index=f'[{i},{j}]',Value='0')
        self.assertTrue(self.engine(mutate=rank).blockers)
        self.assertTrue(self.engine(['DEDT(D,Buffer[SpeedCommand]);']).blockers)

    def event_engine(self,fault=False):
        def event(root):
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='CurveEvent',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(p,'Tags')
            routine=E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='MainRoutine',Type='ST');lines=['D.In:=2; DEDT(D,Buffer);']
            if fault:lines.append('SpeedCommand:=1/SpeedSetpoint;')
            logic(routine,lines);task=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='CurveEventTask',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(task,'ScheduledPrograms'),'ScheduledProgram',Name='CurveEvent')
        return self.checked(['DEDT(D,Buffer); EVENT(CurveEventTask); D.In:=3; DEDT(D,Buffer);'],buffer=[1,1,9,8],mutate=event)

    def test_event_dispatch_shares_queue_and_failure_restores_scheduler(self):
        e=self.event_engine();_,d,b=self.step(e);self.assertEqual((d['Out'],b),(1,[3,2,9,8]))
        e=self.event_engine(fault=True);e.memory.write('SpeedSetpoint',0);before=copy.deepcopy((e.memory.values,e.last_timer,e.scheduler_description()))
        with self.assertRaisesRegex(ModelError,'zero'):self.step(e)
        self.assertEqual((e.memory.values,e.last_timer,e.scheduler_description()),before)

    def test_detached_replacement_preserves_delay_length_binding_and_storage(self):
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import container,xml_source
        def caller(root):
            routines=root.find('./Controller/Programs/Program/Routines');main=routines[0];main.remove(main.find('STContent'));main.set('Type','RLL')
            E.SubElement(E.SubElement(E.SubElement(main,'RLLContent'),'Rung',Number='0',Type='N'),'Text').text='JSR(Curves,0);'
            logic(E.SubElement(routines,'Routine',Name='Curves',Type='ST'),['FGEN(F,X1,Y1); DEDT(D,Buffer);'])
        e=self.checked(mutate=caller);self.step(e);e.memory.write('D.In',3);self.step(e);before=copy.deepcopy((e.memory.values,e.last_timer))
        neutral=['JSR(Curves,0);','NOP();'];xml=xml_source();content=xml.find('RLLContent')
        for child in list(content):content.remove(child)
        for i,text in enumerate(neutral):E.SubElement(E.SubElement(content,'Rung',Type='N',RegionId=str(i+1)),'TextIOI').text=text
        candidate,_=prepare(e,decode(container(E.tostring(xml,encoding='utf-8'))),tuple(neutral),'MainProgram',0)
        self.assertEqual((e.memory.values,e.last_timer),before);self.assertEqual(candidate.last_timer,e.last_timer)
        self.assertEqual(self.step(candidate)[2],[3,3,9,8])


if __name__=='__main__':unittest.main()
