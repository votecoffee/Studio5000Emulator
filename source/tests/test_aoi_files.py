"""AOI FAL/FSC modes, per-CONTROL progress and transactional array work."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine

SAMPLE=Path(__file__).resolve().parents[1]/'samples/AOIFileLab.L5X'


def body(root):return root.find('.//AddOnInstructionDefinition/Routines/Routine[@Name="Logic"]/RLLContent')


def mode(root,value):
    for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace(',INC,',','+value+',')


class AOIFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,mutate=None,*,kind='INC',harness=False,defer=False):
        root=E.parse(SAMPLE).getroot();mode(root,kind)
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'files.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),mode='routine' if harness else 'project',routine='MainProgram/MainRoutine' if harness else '',defer_prescan=defer)

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def write(self,e,**values):
        for name,value in values.items():e.memory.write(name,value)

    def pulse(self,e,**values):
        self.write(e,Transform=False,Search=False);e.step();self.write(e,**values);self.write(e,Transform=True,Search=True);e.step()

    def snapshot(self,e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.addons.instances,e._file_incremental,e.scan_count,e.time_ms,e.scheduler_description(),e.trace))

    def test_inc_transforms_and_searches_are_independent_per_instance_and_control(self):
        e=self.checked()
        for _ in range(4):self.pulse(e)
        self.assertEqual(e.memory.read('OutputA'),[5,9,13,17,901]);self.assertEqual(e.memory.read('OutputB'),[2,8,14,20,902])
        self.assertEqual(e.memory.read('DriverA.Scratch'),[3,5,7,9,777]);self.assertEqual(e.memory.read('DriverB.Scratch'),[0,2,4,6,777])
        self.assertEqual((e.memory.read('DriverA.Total'),e.memory.read('DriverB.Total')),(24,12))
        self.assertEqual((e.memory.read('CalcA.POS'),e.memory.read('CalcB.POS')),(3,3));self.assertTrue(e.memory.read('CalcA.DN'))
        self.assertEqual(e.memory.read('FindA.POS'),2);self.assertTrue(e.memory.read('FindA.IN'));self.assertFalse(e.memory.read('FindA.DN'))
        self.assertEqual(e.memory.read('FindB.POS'),3);self.assertTrue(e.memory.read('FindB.DN'));self.assertFalse(e.memory.read('FindB.FD'))
        self.assertEqual(len(e._file_incremental),6)

    def test_held_inc_calls_keep_current_element_and_live_inputs_apply_next_edge(self):
        e=self.checked();self.write(e,Transform=True,Search=True);e.step();before=copy.deepcopy(e.memory.read('OutputA'))
        self.write(e,GainA=4);e.step();self.assertEqual(e.memory.read('OutputA'),before);self.assertEqual(e.memory.read('CalcA.POS'),0)
        self.pulse(e);self.assertEqual(e.memory.read('OutputA'),[5,17,0,0,901])

    def test_all_mode_completes_remaining_regions_in_one_call(self):
        e=self.checked(kind='ALL');self.write(e,Transform=True,Search=True);e.step()
        self.assertEqual(e.memory.read('OutputA'),[5,9,13,17,901]);self.assertEqual(e.memory.read('OutputB'),[2,8,14,20,902])
        self.assertTrue(e.memory.read('CalcA.DN'));self.assertEqual(e.memory.read('FindA.POS'),2);self.assertTrue(e.memory.read('FindA.IN'))
        self.assertTrue(e.memory.read('FindB.DN'));self.assertFalse(e.memory.read('FindB.FD'));self.assertEqual(e._file_incremental,set())

    def test_numeric_work_continues_on_false_calls_then_cleans_up(self):
        e=self.checked(kind='2');self.write(e,Transform=True,Search=True);e.step();self.assertEqual(e.memory.read('OutputA'),[5,9,0,0,901])
        self.write(e,Transform=False,Search=False);e.step();self.assertEqual(e.memory.read('OutputA'),[5,9,13,17,901]);self.assertTrue(e.memory.read('CalcA.DN'));self.assertFalse(e.memory.read('CalcA.EN'))
        self.assertEqual(e.memory.read('FindA.POS'),2);self.assertTrue(e.memory.read('FindA.IN'));self.assertTrue(e.memory.read('FindB.DN'))
        e.step();self.assertFalse(e.memory.read('CalcA.DN'));self.assertEqual(e.memory.read('CalcA.POS'),0)

    def test_numeric_enable_in_false_can_continue_authored_work(self):
        e=self.checked(kind='2');self.write(e,Transform=True);e.step();self.write(e,EnabledA=False);e.step()
        self.assertEqual(e.memory.read('OutputA'),[5,9,13,17,901]);self.assertTrue(e.memory.read('CalcA.DN'));self.assertFalse(e.memory.read('DriverA.EnableOut'))

    def test_skipped_aoi_without_false_mode_suspends_numeric_and_preserves_inc_latch(self):
        def no_false(root):root.find('.//AddOnInstructionDefinition').set('ExecuteEnableInFalse','false')
        for kind in ('INC','2'):
            e=self.checked(no_false,kind=kind);self.write(e,Transform=True);e.step();prior=copy.deepcopy(e.memory.read('OutputA'));self.write(e,EnabledA=False);e.step();self.assertEqual(e.memory.read('OutputA'),prior)
            self.write(e,EnabledA=True);e.step()
            if kind=='INC':self.assertEqual(e.memory.read('CalcA.POS'),0)
            else:self.assertEqual(e.memory.read('OutputA'),[5,9,13,17,901])

    def test_enable_in_false_rearms_inc_for_one_instance_only(self):
        e=self.checked();self.write(e,Transform=True,Search=True);e.step();self.write(e,EnabledA=False);e.step()
        self.assertFalse(e.memory.read('CalcA.EN'));self.assertTrue(e.memory.read('CalcB.EN'));self.write(e,EnabledA=True);e.step()
        self.assertEqual(e.memory.read('CalcA.POS'),1);self.assertEqual(e.memory.read('CalcB.POS'),0);self.assertEqual(e.memory.read('OutputA[1]'),9)

    def test_search_inhibit_needs_clear_and_observed_false_before_next_inc_match(self):
        e=self.checked()
        for _ in range(3):self.pulse(e)
        self.assertTrue(e.memory.read('FindA.IN'));self.assertTrue(e.memory.read('DriverA.Found'));self.assertEqual(e.memory.read('FindA.POS'),2)
        e.memory.write('FindA.IN',False);e.step();self.assertEqual(e.memory.read('FindA.POS'),2)
        self.pulse(e);self.assertEqual(e.memory.read('FindA.POS'),3);self.assertTrue(e.memory.read('FindA.DN'));self.assertTrue(e.memory.read('FindA.IN'))
        e.memory.write('FindA.IN',False);self.write(e,Search=False,Transform=False);e.step();self.assertEqual(e.memory.read('FindA.POS'),0);self.assertFalse(e.memory.read('FindA.DN'))

    def test_res_clears_canonical_progress_but_retains_arrays_and_length(self):
        e=self.checked();self.pulse(e);saved=copy.deepcopy(e.memory.read('OutputA'));self.write(e,Transform=False,Search=False,Reset=True);e.step()
        self.assertEqual(e._file_incremental,set());self.assertEqual(e.memory.read('CalcA.LEN'),4);self.assertEqual(e.memory.read('OutputA'),saved)
        self.write(e,Reset=False,Transform=True,Search=True,GainA=4);e.step();self.assertEqual(e.memory.read('OutputA[0]'),9);self.assertEqual(e.memory.read('CalcA.POS'),0)

    def test_run_entry_preserves_incremental_progress_and_held_enable(self):
        e=self.checked();self.write(e,Transform=True,Search=True);e.step();progress=e._file_incremental.copy();e.enter_run();self.assertEqual(e._file_incremental,progress)
        e.step();self.assertEqual(e.memory.read('CalcA.POS'),0);self.pulse(e);self.assertEqual(e.memory.read('CalcA.POS'),1)

    def test_inc_rejects_saved_active_or_unknown_controls_even_on_false_calls(self):
        for target,field,value in (('CalcA','POS','1'),('FindA','IN','1'),('CalcB','EN','1'),('local','POS','1'),('local','EN',None)):
            def active(root):
                path='./Controller/Tags/Tag[@Name="DriverA"]/Data/Structure/StructureMember[@Name="LocalCalc"]' if target=='local' else f'./Controller/Tags/Tag[@Name="{target}"]/Data/Structure'
                obj=root.find(path);node=obj.find(f'DataValueMember[@Name="{field}"]')
                if value is None:obj.remove(node)
                else:node.set('Value',value)
            self.assertTrue(any('idle source' in b for b in self.engine(active).blockers))

    def test_all_saved_position_profile_is_retained_inside_aoi(self):
        def saved(root):
            obj=root.find('./Controller/Tags/Tag[@Name="CalcA"]/Data/Structure');obj.find('DataValueMember[@Name="POS"]').set('Value','1');obj.find('DataValueMember[@Name="EN"]').set('Value','1')
        e=self.checked(saved,kind='ALL');self.write(e,Transform=True);e.step();self.assertEqual(e.memory.read('OutputA'),[0,0,13,17,901])

    def test_unknown_sources_are_not_read_by_false_or_completed_calls(self):
        e=self.checked(kind='ALL');e.memory.values['inputa'][0]=None;e.step();self.write(e,Transform=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before);e.memory.write('CalcA.DN',True);e.memory.write('DriverA.LocalCalc.DN',True);e.step();self.assertIsNone(e.memory.values['inputa'][0])

    def test_omitted_local_elements_remain_unknown_and_definition_defaults_do_not_fill_them(self):
        def hidden(root):
            for obj in root.findall('./Controller/Tags/Tag[@DataType="LabFileDriver"]/Data/Structure'):obj.remove(obj.find('ArrayMember[@Name="Scratch"]'))
            body(root).find('Rung[@Number="5"]/Text').text='NOP();'
            local=root.find('.//LocalTag[@Name="Scratch"]');a=E.SubElement(E.SubElement(local,'DefaultData',Format='Decorated'),'Array',DataType='DINT',Dimensions='5')
            for i in range(5):E.SubElement(a,'Element',Index=f'[{i}]',Value='999')
        e=self.checked(hidden);e.step();self.assertEqual(e.memory.values['drivera']['Scratch'],[None]*5);self.write(e,Transform=True);e.step()
        self.assertEqual(e.memory.values['drivera']['Scratch'],[3,None,None,None,None])

    def test_existing_narrow_numeric_array_types_work_with_exact_bindings(self):
        for dtype in ('SINT','INT','DINT','REAL'):
            def types(root):
                for name in ('Input','Output'):root.find(f'.//Parameter[@Name="{name}"]').set('DataType',dtype)
                for name in ('InputA','InputB','OutputA','OutputB'):
                    tag=root.find(f'./Controller/Tags/Tag[@Name="{name}"]');tag.set('DataType',dtype);a=tag.find('Data/Array');a.set('DataType',dtype);a.find('Element[@Index="[4]"]').set('Value','90')
            e=self.checked(types,kind='ALL');self.write(e,Transform=True,Search=True);e.step();self.assertEqual(e.memory.read('OutputA'),[5,9,13,17,90])

    def test_late_arithmetic_fault_restores_both_instances_and_incremental_keys(self):
        e=self.checked();e.step();self.write(e,Transform=True,Search=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('OutputA[0]'),5);self.assertEqual(len(e._file_incremental),6)

    def test_all_mode_partial_expression_error_rolls_back_all_earlier_iterations(self):
        def divide(root):body(root).find('Rung[@Number="1"]/Text').text='XIC(Transform)FAL(Calc,?,?,ALL,Output[Calc.POS],Input[Calc.POS]/(2-Calc.POS));'
        e=self.checked(divide,kind='ALL');self.write(e,Transform=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_inc_fault_retains_prior_committed_element_and_retries_pending_edge(self):
        def divide(root):body(root).find('Rung[@Number="1"]/Text').text='XIC(Transform)FAL(Calc,?,?,INC,Output[Calc.POS],Input[Calc.POS]/(Gain-Calc.POS));'
        e=self.checked(divide);self.write(e,GainA=1,GainB=1,Transform=True);e.step();self.assertEqual(e.memory.read('OutputA[0]'),2)
        self.write(e,Transform=False);e.step();self.write(e,Transform=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,GainA=2,GainB=2);e.step();self.assertEqual(e.memory.read('OutputA'),[2,4,0,0,901]);self.assertEqual(e.memory.read('OutputB'),[1,3,0,0,902])

    def test_fsc_eager_boolean_expression_cannot_hide_division_fault(self):
        def eager(root):body(root).find('Rung[@Number="2"]/Text').text='XIC(Search)FSC(Find,?,?,INC,EnableIn||(Input[Find.POS]/(Gain-Gain)>0));'
        e=self.checked(eager);self.write(e,Search=True);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_destination_control_overlap_is_blocked_and_dynamic_overlap_faults_atomically(self):
        def overlap(root):body(root).find('Rung[@Number="1"]/Text').text='FAL(Calc,?,?,ALL,Calc.POS,1);'
        self.assertTrue(self.engine(overlap,kind='ALL').blockers)
        def dynamic(root):
            d=root.find('.//AddOnInstructionDefinition');E.SubElement(d.find('LocalTags'),'LocalTag',Name='States',DataType='CONTROL',Dimensions='2',ExternalAccess='None')
            for obj in root.findall('./Controller/Tags/Tag[@DataType="LabFileDriver"]/Data/Structure'):
                a=E.SubElement(obj,'ArrayMember',Name='States',DataType='CONTROL',Dimensions='2')
                for i in range(2):
                    state=copy.deepcopy(obj.find('StructureMember[@Name="LocalCalc"]'));state.tag='Structure';state.attrib.pop('Name');state.find('DataValueMember[@Name="LEN"]').set('Value','2');E.SubElement(a,'Element',Index=f'[{i}]').append(state)
            b=body(root);b.clear();E.SubElement(E.SubElement(b,'Rung',Number='0',Type='N'),'Text').text='FAL(States[1],?,?,ALL,States[States[1].POS].POS,1);'
        e=self.checked(dynamic,kind='ALL');before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'overlap'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_instruction_budget_and_length_cap_restore_all_progress(self):
        e=self.checked(kind='ALL');self.write(e,Transform=True);e.instruction_limit=8;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'budget'):e.step()
        self.assertEqual(self.snapshot(e),before)
        e=self.checked();self.write(e,Transform=True);e.memory.write('CalcA.LEN',4097);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'4096'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_type_dimension_constant_and_unsupported_expression_guards_remain(self):
        for kind in ('type','dimensions','constant','wide','expression'):
            def bad(root):
                if kind=='type':root.find('.//Parameter[@Name="Output"]').set('DataType','REAL')
                elif kind=='dimensions':root.find('.//Parameter[@Name="Input"]').set('Dimensions','4')
                elif kind=='constant':root.find('./Controller/Tags/Tag[@Name="OutputA"]').set('Constant','true')
                elif kind=='wide':body(root).find('Rung[@Number="1"]/Text').text='FAL(Calc,?,?,ALL,Output[Calc.POS],2147483648L);'
                else:body(root).find('Rung[@Number="1"]/Text').text='FAL(Calc,?,?,ALL,Output[Calc.POS],EXP(Input[Calc.POS]));'
            self.assertTrue(self.engine(bad).blockers)

    def test_periodic_and_routine_harness_use_same_file_state(self):
        def periodic(root):t=root.find('./Controller/Tasks/Task');t.set('Type','Periodic');t.set('Rate','10')
        for e in (self.checked(periodic),self.checked(harness=True,defer=True)):
            self.write(e,Transform=True,Search=True);e.step(10);self.assertEqual(e.memory.read('OutputA[0]'),5);self.assertEqual(len(e._file_incremental),6)

    def test_exact_multidimensional_inout_arrays_preserve_other_rows(self):
        def matrix(root):
            for name in ('Input','Output'):root.find(f'.//Parameter[@Name="{name}"]').set('Dimensions','2,3')
            values={'InputA':[701,702,703,2,4,999],'InputB':[704,705,706,1,3,998],'OutputA':[801,802,803,0,0,901],'OutputB':[804,805,806,0,0,902]}
            for name,items in values.items():
                tag=root.find(f'./Controller/Tags/Tag[@Name="{name}"]');tag.set('Dimensions','2,3');a=tag.find('Data/Array');a.clear();a.attrib.update(DataType='DINT',Dimensions='2,3')
                for i,v in enumerate(items):E.SubElement(a,'Element',Index=f'[{i//3},{i%3}]',Value=str(v))
            for text in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                for index in ('Calc.POS','Find.POS','LocalCalc.POS'):
                    text.text=text.text.replace('Input['+index+']','Input[1,'+index+']').replace('Output['+index+']','Output[1,'+index+']')
            for member in root.findall('.//DataValueMember[@Name="LEN"]'):member.set('Value','2')
        e=self.checked(matrix,kind='ALL');self.write(e,Transform=True,Search=True);e.step()
        self.assertEqual(e.memory.read('OutputA'),[[801,802,803],[5,9,901]]);self.assertEqual(e.memory.read('OutputB'),[[804,805,806],[2,8,902]])

    def test_dynamic_bank_rebinding_uses_canonical_control_progress_and_rolls_back(self):
        def banks(root):
            c=root.find('Controller');tags=c.find('Tags');members=E.SubElement(E.SubElement(c.find('DataTypes'),'DataType',Name='FileBank',Family='NoFamily',Class='User'),'Members')
            for name,kind,dim in [('Input','DINT','5'),('Output','DINT','5'),('Calc','CONTROL','0'),('Find','CONTROL','0')]:E.SubElement(members,'Member',Name=name,DataType=kind,Dimension=dim)
            a=E.SubElement(E.SubElement(E.SubElement(tags,'Tag',Name='Banks',DataType='FileBank',TagType='Base',Dimensions='2'),'Data',Format='Decorated'),'Array',DataType='FileBank',Dimensions='2')
            for i,suffix in enumerate(('A','B')):
                obj=E.SubElement(E.SubElement(a,'Element',Index=f'[{i}]'),'Structure',DataType='FileBank')
                for name in ('Input','Output','Calc','Find'):
                    item=copy.deepcopy(tags.find(f'Tag[@Name="{name+suffix}"]/Data')[0]);item.tag='ArrayMember' if name in ('Input','Output') else 'StructureMember';item.set('Name',name);obj.append(item)
            t=E.SubElement(tags,'Tag',Name='Which',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(t,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
            root.find('.//AddOnInstructionDefinition').set('ExecuteEnableInFalse','false');root.find('./Controller/Tags/Tag[@Name="EnabledB"]/Data/DataValue').set('Value','0')
            text=root.find('.//Program/Routines/Routine/RLLContent/Rung[@Number="1"]/Text');text.text=text.text.replace('InputA,OutputA,CalcA,FindA',','.join('Banks[Which].'+n for n in ('Input','Output','Calc','Find')))
        e=self.checked(banks);self.write(e,Transform=True,Search=True);e.step();self.write(e,Transform=False,Search=False);e.step()
        self.assertEqual(e.memory.frames['@AOI:drivera']['calc'],('Banks[0].Calc',''))
        self.write(e,Which=1,Transform=True,Search=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step()
        self.assertEqual(e.memory.read('Banks[1].Output[0]'),3);self.assertEqual(e.memory.read('Banks[0].Output[0]'),5)
        self.assertEqual(e.memory.frames['@AOI:drivera']['calc'],('Banks[1].Calc',''));self.assertEqual(len(e._file_incremental),5)
        self.write(e,Which=0,Transform=False,Search=False);e.step();self.write(e,Transform=True,Search=True);e.step();self.assertEqual(e.memory.read('Banks[0].Output[1]'),9)

    def test_nested_aoi_local_controls_have_distinct_progress_identities(self):
        def nested(root):
            definitions=root.find('./Controller/AddOnInstructionDefinitions');wrapper=copy.deepcopy(definitions[0]);wrapper.set('Name','LabFileWrapper');wrapper.set('ExecuteEnableInFalse','false')
            wrapper.remove(wrapper.find('LocalTags'));E.SubElement(E.SubElement(wrapper,'LocalTags'),'LocalTag',Name='Core',DataType='LabFileDriver',ExternalAccess='None')
            wrapper.remove(wrapper.find('Routines'));b=E.SubElement(E.SubElement(E.SubElement(wrapper,'Routines'),'Routine',Name='Logic',Type='RLL'),'RLLContent')
            for i,text in enumerate(('LabFileDriver(Core,Transform,Search,Reset,Gain,Bias,Threshold,Input,Output,Calc,Find);','MOV(Core.Total,Total)MOV(Core.Position,Position);','XIC(Core.Found)OTE(Found);')):E.SubElement(E.SubElement(b,'Rung',Number=str(i),Type='N'),'Text').text=text
            definitions.append(wrapper)
            for tag in root.findall('./Controller/Tags/Tag[@DataType="LabFileDriver"]'):
                tag.set('DataType','LabFileWrapper');obj=tag.find('Data/Structure');core=copy.deepcopy(obj);core.tag='StructureMember';core.set('Name','Core')
                for item in list(obj):
                    if item.tag!='DataValueMember':obj.remove(item)
                obj.set('DataType','LabFileWrapper');obj.append(core)
            for text in root.findall('.//Program/Routines/Routine/RLLContent/Rung/Text'):text.text=text.text.replace('LabFileDriver(','LabFileWrapper(')
        e=self.checked(nested);self.pulse(e);self.pulse(e)
        self.assertEqual(e.memory.read('DriverA.Core.Scratch'),[3,5,0,0,777]);self.assertEqual(e.memory.read('DriverB.Core.Scratch'),[0,2,0,0,777])
        self.assertIn(('drivera',('Core','LocalCalc')),e._file_incremental);self.assertIn(('driverb',('Core','LocalCalc')),e._file_incremental)

    def test_event_task_fault_restores_file_progress_and_outputs(self):
        def event(root):
            b=root.find('.//Program/Routines/Routine/RLLContent');original=list(b);b.clear();b.append(original[0]);E.SubElement(E.SubElement(b,'Rung',Number='1',Type='N'),'Text').text='EVENT(FileEvent);';original[3].set('Number','2');b.append(original[3])
            p=E.SubElement(root.find('./Controller/Programs'),'Program',Name='EventProgram',MainRoutineName='EventFiles',Class='Standard',Disabled='false');E.SubElement(p,'Tags');content=E.SubElement(E.SubElement(E.SubElement(p,'Routines'),'Routine',Name='EventFiles',Type='RLL'),'RLLContent')
            for i,r in enumerate(original[1:3]):r.set('Number',str(i));content.append(r)
            t=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='FileEvent',Type='EVENT',Priority='1',Watchdog='500',Class='Standard',InhibitTask='false');E.SubElement(t,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false');E.SubElement(E.SubElement(t,'ScheduledPrograms'),'ScheduledProgram',Name='EventProgram')
        e=self.checked(event);e.step();self.write(e,Transform=True,Search=True,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'zero'):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('OutputA[0]'),5);self.assertEqual(len(e._file_incremental),6)

    def test_report_and_bundled_ladder_fixture_keep_native_limits_explicit(self):
        from logixlab.model import ARITIES,ST_ONLY_ARITIES
        from logixlab.server import SAMPLES
        self.assertIn('AOIFileLab',SAMPLES);e=self.checked();self.assertEqual((len(ARITIES),len(ST_ONLY_ARITIES)),(108,29))
        for name in ('file_arithmetic','file_search'):
            p=e.report()[name];self.assertIn('InOut',p['aoi']);self.assertFalse(p['native_cursor_parity'])


if __name__=='__main__':unittest.main()
