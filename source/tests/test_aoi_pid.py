"""Saved local and InOut PID state in ladder AOIs; no native parity claim."""
import copy
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.model import ModelError, Project
from logixlab.runtime import Engine

SAMPLE=Path(__file__).resolve().parents[1]/'samples/AOIPIDLab.L5X'


class AOIPIDTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,mutate=None,*,harness=False):
        root=E.parse(SAMPLE).getroot()
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'aoi-pid.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),mode='routine' if harness else 'project',routine='MainProgram/MainRoutine' if harness else '')

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def write(self,e,**values):
        for name,value in values.items():e.memory.write(name.replace('__','.'),value)

    def active(self,*args,**kwargs):
        e=self.checked(*args,**kwargs);self.write(e,EnabledA=True,EnabledB=True);return e

    def snapshot(self,e):
        return copy.deepcopy((e.memory.values,e.memory.frames,e.memory._resolved,e.addons.instances,
                              e.last_timer,e.time_ms,e.scan_count,e.scheduler_description(),e.trace))

    def test_inout_and_saved_local_records_are_isolated_per_instance(self):
        e=self.active();e.step()
        self.assertEqual(tuple(e.memory.read(t) for t in ('CVA','CVB','DriverA.AuxValue','DriverB.AuxValue')),(45,22.5,5,0))
        e.step();self.assertEqual((e.memory.read('CVA'),e.memory.read('CVB')),(60,30))
        self.assertEqual(len(e.last_timer),4);self.assertEqual(len(e.addons.instances),2)

    def test_disabled_aoi_authored_false_routine_clears_both_en_but_keeps_history(self):
        e=self.active();e.step();saved=copy.deepcopy(e.last_timer);self.write(e,EnabledA=False);e.step()
        self.assertFalse(e.memory.read('ControlA.EN'));self.assertFalse(e.memory.read('DriverA.Local.EN'))
        self.assertTrue(e.memory.read('ControlB.EN'));self.assertFalse(e.memory.read('DriverA.EnableOut'))
        self.assertEqual(e.memory.read('CVA'),45)
        for key in saved:
            if 'controla' in str(key).lower() or 'drivera' in str(key).lower():self.assertEqual(e.last_timer[key],saved[key])
        self.write(e,EnabledA=True);e.step();self.assertEqual(e.memory.read('CVA'),60)

    def test_skipped_aoi_without_false_mode_retains_enable_and_state(self):
        def skip(root):root.find('.//AddOnInstructionDefinition').set('ExecuteEnableInFalse','false')
        e=self.active(skip);e.step();self.write(e,EnabledA=False);e.step()
        self.assertTrue(e.memory.read('ControlA.EN'));self.assertTrue(e.memory.read('DriverA.Local.EN'))
        self.write(e,EnabledA=True);e.step();self.assertEqual(e.memory.read('CVA'),60)

    def test_run_entry_prescans_bindings_and_restarts_integral_history(self):
        e=self.active();e.step();e.step();self.assertEqual(e.memory.read('CVA'),60);e.enter_run()
        self.assertFalse(e.memory.read('ControlA.EN'));self.assertFalse(e.memory.read('DriverA.Local.EN'))
        e.step();self.assertEqual(e.memory.read('CVA'),45)

    def test_local_and_inout_manual_tracking_and_inhold(self):
        e=self.active();self.write(e,ManualA=True,PVTrackingA=True);e.step()
        self.assertEqual((e.memory.read('CVA'),e.memory.read('ControlA.SP'),e.memory.read('DriverA.Local.SP')),(60,20,30))
        self.write(e,HoldA=True,ReadbackA=70);e.step()
        self.assertEqual((e.memory.read('CVA'),e.memory.read('DriverA.AuxValue')),(70,70))
        self.assertEqual(e.memory.read('ControlA.SP'),20)
        self.write(e,HoldA=False,ManualA=False);e.step();self.assertEqual(e.memory.read('CVA'),70)
        self.assertEqual(e.memory.read('DriverA.AuxValue'),70)

    def test_unknown_saved_local_is_not_filled_by_definition_default(self):
        def omit(root):
            member=root.find('./Controller/Tags/Tag[@Name="DriverA"]/Data/Structure/StructureMember/DataValueMember[@Name="KP"]')
            root.find('./Controller/Tags/Tag[@Name="DriverA"]/Data/Structure/StructureMember').remove(member)
        e=self.active(omit);self.assertIsNone(e.memory.values['drivera']['Local']['KP']);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'KP is unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_late_fault_restores_external_local_bindings_and_histories(self):
        e=self.active();e.step();self.write(e,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step()
        self.assertEqual((e.memory.read('CVA'),e.memory.read('CVB')),(60,30))

    def test_shared_external_record_twice_in_same_release_is_rejected_atomically(self):
        def shared(root):
            node=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung[@Number="1"]/Text');node.text=node.text.replace('ControlB','ControlA')
        e=self.active(shared);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'one true execution'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_inout_exact_type_and_constant_destinations_are_blocked(self):
        for actual in ('PVA','ControlA.OUT','0'):
            def wrong(root):
                node=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text');node.text=node.text.replace('ControlA',actual)
            with self.subTest(actual=actual):self.assertTrue(self.engine(wrong).blockers)
        def constant(root):root.find('./Controller/Tags/Tag[@Name="ControlA"]').set('Constant','true')
        self.assertTrue(self.engine(constant).blockers)

    def test_false_aoi_still_copies_required_inputs_and_unknown_actual_faults(self):
        e=self.checked();e.memory.values['pva']=None;before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'Unknown'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_routine_harness_executes_both_instances(self):
        e=self.active(harness=True);e.step();self.assertEqual((e.memory.read('CVA'),e.memory.read('CVB')),(45,22.5))

    def test_periodic_task_keeps_pid_upd_independent_of_scheduler_interval(self):
        def periodic(root):
            task=root.find('.//Task');task.set('Type','PERIODIC');task.set('Rate','20')
        e=self.active(periodic);e.step(20);self.assertEqual(e.memory.read('CVA'),45)
        e.step(20);self.assertEqual(e.memory.read('CVA'),60)

    def test_dynamic_inout_rebinding_restores_frame_on_late_fault(self):
        def rebound(root):
            tags=root.find('./Controller/Tags')
            tag=E.SubElement(tags,'Tag',Name='Index',DataType='DINT',TagType='Base');E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='0')
            saved=copy.deepcopy(tags.find('Tag[@Name="ControlA"]/Data/Structure'))
            tag=E.SubElement(tags,'Tag',Name='Bank',DataType='PID',Dimensions='2',TagType='Base')
            array=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='PID',Dimensions='2')
            for i in range(2):E.SubElement(array,'Element',Index='['+str(i)+']').append(copy.deepcopy(saved))
            node=root.find('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text');node.text=node.text.replace('ControlA','Bank[Index]')
        e=self.active(rebound);e.step();self.write(e,Index=1,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step()
        self.assertEqual((e.memory.read('Bank[0].OUT'),e.memory.read('Bank[1].OUT')),(45,45))
        self.write(e,Index=0);e.step();self.assertEqual(e.memory.read('CVA'),60)

    def test_own_record_overlap_inside_inout_is_blocked(self):
        def overlap(root):
            for node in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):node.text=node.text.replace('Tieback,CV,0','Tieback,State.OUT,0')
        self.assertTrue(self.engine(overlap).blockers)

    def test_cascade_master_binding_inside_aoi_is_read_only(self):
        def cascade(root):
            params=root.find('.//AddOnInstructionDefinition/Parameters')
            E.SubElement(params,'Parameter',Name='Master',DataType='PID',Usage='InOut',Required='true',Visible='true',Dimensions='0')
            for node in root.findall('.//AddOnInstructionDefinition/Routines/Routine/RLLContent/Rung/Text'):
                node.text=node.text.replace('Tieback,CV,0,','Tieback,CV,Master,')
            for i,suffix,other in ((0,'A','B'),(1,'B','A')):
                node=root.find(f'./Controller/Programs/Program/Routines/Routine/RLLContent/Rung[@Number="{i}"]/Text')
                node.text=node.text.replace('Readback'+suffix+')','Readback'+suffix+',Control'+other+')')
        e=self.checked(cascade);self.write(e,EnabledA=True,ControlA__CL=True,ControlB__CL=True,ControlB__CT=True,ControlB__OUT=60)
        e.step();self.assertEqual((e.memory.read('ControlA.SP'),e.memory.read('CVA')),(60,60))
        self.assertEqual(e.memory.read('ControlB.OUT'),60)
        self.write(e,ControlB__CT=False);before=self.snapshot(e)
        with self.assertRaisesRegex(ModelError,'master flags'):e.step()
        self.assertEqual(self.snapshot(e),before)

    def test_nested_aoi_instances_have_distinct_canonical_pid_history(self):
        def nested(root):
            definitions=root.find('./Controller/AddOnInstructionDefinitions');original=definitions[0]
            wrapper=copy.deepcopy(original);wrapper.set('Name','PIDWrapper');definitions.append(wrapper)
            local=wrapper.find('LocalTags/LocalTag');local.set('Name','Inner');local.set('DataType','LabPIDDriver')
            for content in wrapper.findall('Routines/Routine/RLLContent'):
                name=next(r.get('Name') for r in wrapper.findall('Routines/Routine') if r.find('RLLContent') is content)
                content.clear();text=('AFI()' if name=='EnableInFalse' else '')+'LabPIDDriver(Inner,PV,State,CV,Tieback,Inhold,Readback);'
                E.SubElement(E.SubElement(content,'Rung',Number='0',Type='N'),'Text').text=text
            for suffix in ('A','B'):
                tag=root.find(f'./Controller/Tags/Tag[@Name="Driver{suffix}"]');tag.set('DataType','PIDWrapper')
                obj=tag.find('Data/Structure');inner=copy.deepcopy(obj);inner.tag='StructureMember';inner.set('Name','Inner')
                obj.remove(obj.find('StructureMember'));obj.set('DataType','PIDWrapper');obj.append(inner)
            for node in root.findall('./Controller/Programs/Program/Routines/Routine/RLLContent/Rung/Text'):node.text=node.text.replace('LabPIDDriver(','PIDWrapper(')
        e=self.active(nested);e.step();e.step()
        self.assertEqual((e.memory.read('CVA'),e.memory.read('CVB'),e.memory.read('DriverA.Inner.AuxValue')),(60,30,5))
        self.assertEqual(len(e.last_timer),4);self.assertEqual(len(e.addons.instances),4)

    def test_event_dispatch_and_late_fault_restore_aoi_pid_state(self):
        def event(root):
            task=root.find('./Controller/Tasks/Task');task.attrib.update(Type='EVENT',Priority='1',DisableUpdateOutputs='true')
            E.SubElement(task,'EventInfo',EventTrigger='EVENT Instruction Only',EnableTimeout='false')
            program=E.SubElement(root.find('./Controller/Programs'),'Program',Name='Trigger',MainRoutineName='MainRoutine',Class='Standard',Disabled='false');E.SubElement(program,'Tags')
            content=E.SubElement(E.SubElement(E.SubElement(program,'Routines'),'Routine',Name='MainRoutine',Type='RLL'),'RLLContent')
            for i,text in enumerate(('EVENT(MainTask);','DIV(1,FaultDivisor,Quotient);')):E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
            trigger=E.SubElement(root.find('./Controller/Tasks'),'Task',Name='TriggerTask',Type='CONTINUOUS',Priority='10',Watchdog='500',Class='Standard',InhibitTask='false')
            E.SubElement(E.SubElement(trigger,'ScheduledPrograms'),'ScheduledProgram',Name='Trigger')
        e=self.active(event);e.step();self.assertEqual(e.memory.read('CVA'),45)
        self.write(e,FaultDivisor=0);before=self.snapshot(e)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(self.snapshot(e),before);self.write(e,FaultDivisor=1);e.step();self.assertEqual(e.memory.read('CVA'),60)


if __name__=='__main__':unittest.main()
