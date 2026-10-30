"""Typed source-bound GSV settings, language bindings and rollback."""
import copy
import struct
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E

from logixlab.model import ModelError, Project
from logixlab.runtime import Engine
import test_string_operations as strings


def scalar(tags,name,dtype,value=-7):
    tag=E.SubElement(tags,'Tag',Name=name,DataType=dtype,TagType='Base')
    E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType=dtype,Value=str(value))


class GsvConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)

    def engine(self,logic,*,st=False,mutate=None,harness=False):
        root=E.parse(Path(__file__).resolve().parents[1]/'samples/TaskLab.L5X').getroot()
        controller=root.find('Controller');controller.set('TimeSlice','30');controller.set('ShareUnusedTimeSlice','0')
        tags=controller.find('Tags')
        for name,dtype,value in (('Out','DINT',-7),('PriorityOut','INT',-7),('Index','DINT',0),('Limit','DINT',2),('Flag','BOOL',0)):
            scalar(tags,name,dtype,value)
        tag=E.SubElement(tags,'Tag',Name='NameOut',DataType='STRING',TagType='Base')
        strings.string_data(E.SubElement(tag,'Data',Format='Decorated'),'SAVED')
        routine=controller.find('./Programs/Program[@Name="BackgroundProgram"]/Routines/Routine[@Name="Main"]')
        for node in list(routine):routine.remove(node)
        routine.set('Type','ST' if st else 'RLL');content=E.SubElement(routine,'STContent' if st else 'RLLContent')
        for i,text in enumerate(logic.split('\n') if isinstance(logic,str) else logic):
            if st:E.SubElement(content,'Line',Number=str(i)).text=text
            else:E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
        if mutate:mutate(root)
        path=Path(self.tmp.name)/'fixture.L5X';E.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
        return Engine(Project(path),mode='routine' if harness else 'project',routine='BackgroundProgram/Main')

    def checked(self,*args,**kwargs):
        e=self.engine(*args,**kwargs);self.assertEqual(e.blockers,[]);return e

    def test_task_rate_and_watchdog_are_microseconds_with_exact_dint_destinations(self):
        for task,attribute,expected in (('FastTask','Rate',10000),('SlowTask','Rate',25000),
                                        ('FastTask','Watchdog',500000),('BackgroundTask','Watchdog',500000)):
            for st in (False,True):
                e=self.checked([f'GSV(Task,{task},{attribute},Out);'],st=st);e.step();self.assertEqual(e.memory.read('Out'),expected)

    def test_periodic_priority_uses_native_int_and_boolean_settings_use_dint(self):
        for task,priority in (('FastTask',2),('SlowTask',5)):
            e=self.checked([f'GSV(Task,{task},Priority,PriorityOut);']);e.step();self.assertEqual(e.memory.read('PriorityOut'),priority)
        for attr,field in (('InhibitTask','InhibitTask'),('DisableUpdateOutputs','DisableUpdateOutputs')):
            for value in ('true','false'):
                def setting(root):root.find('./Controller/Tasks/Task[@Name="SlowTask"]').set(field,value)
                e=self.checked([f'GSV(Task,SlowTask,{attr},Out);'],mutate=setting);e.step()
                self.assertEqual(e.memory.read('Out'),int(value=='true'))

    def test_controller_timeslice_and_sharing_require_explicit_settings(self):
        for attr,expected in (('TimeSlice',30),('ShareUnusedTimeSlice',0)):
            e=self.checked([f'GSV(Controller,,{attr},PriorityOut);']);e.step();self.assertEqual(e.memory.read('PriorityOut'),expected)
            def omitted(root):root.find('Controller').attrib.pop(attr)
            e=self.engine([f'GSV(Controller,,{attr},PriorityOut);'],mutate=omitted)
            self.assertTrue(e.blockers);self.assertIn('explicit',str(e.blockers))

    def test_controller_setting_case_or_namespace_shadows_are_not_silent_source_overrides(self):
        for attr in ('TimeSlice','ShareUnusedTimeSlice'):
            for shadow in (attr.lower(),'{urn:ambiguous}'+attr):
                def ambiguous(root):root.find('Controller').set(shadow,'1')
                self.assertTrue(self.engine([f'GSV(Controller,,{attr},PriorityOut);'],mutate=ambiguous).blockers)

    def test_controller_and_task_names_copy_strings_and_preserve_unused_bytes(self):
        for cls,instance,expected in (('Controller','','TaskLab'),('Task','FastTask','FastTask'),('Task','BackgroundTask','BackgroundTask')):
            for st in (False,True):
                e=self.checked([f'GSV({cls},{instance},Name,NameOut);'],st=st)
                e.memory.write('NameOut','abcdefghijklmnopqrst');e.step();self.assertEqual(e.memory.string('NameOut'),expected)
                self.assertEqual(e.memory.read(f'NameOut.DATA[{len(expected)}]'),ord('abcdefghijklmnopqrst'[len(expected)]))

    def test_identifiers_are_case_insensitive_and_names_keep_source_spelling(self):
        e=self.checked(['GSV(tAsK,fAsTtAsK,rAtE,Out);','GSV(TASK,fasttask,NAME,NameOut);']);e.step()
        self.assertEqual(e.memory.read('Out'),10000);self.assertEqual(e.memory.string('NameOut'),'FastTask')

    def test_named_configuration_is_readable_in_an_isolated_routine_harness(self):
        e=self.checked(['GSV(Task,FastTask,Rate,Out);'],harness=True);e.step()
        self.assertEqual(e.memory.read('Out'),10000);self.assertEqual(e.memory.read('FastCount'),0)

    def test_no_priority_or_period_is_inferred_for_continuous_tasks(self):
        for attribute,dest in (('Priority','PriorityOut'),('Rate','Out')):
            self.assertTrue(self.engine([f'GSV(Task,BackgroundTask,{attribute},{dest});']).blockers)

    def test_missing_malformed_and_zero_task_settings_are_unavailable(self):
        for attribute,field,value,dest in (('Watchdog','Watchdog',None,'Out'),('Watchdog','Watchdog','0','Out'),
                ('Watchdog','Watchdog','1.0001','Out'),('Rate','Rate',None,'Out'),('Priority','Priority',None,'PriorityOut'),
                ('InhibitTask','InhibitTask',None,'Out'),('DisableUpdateOutputs','DisableUpdateOutputs',None,'Out')):
            def missing(root):
                task=root.find('./Controller/Tasks/Task[@Name="FastTask"]')
                if value is None:task.attrib.pop(field)
                else:task.set(field,value)
            self.assertTrue(self.engine([f'GSV(Task,FastTask,{attribute},{dest});'],mutate=missing).blockers,attribute)

    def test_exact_source_decimal_milliseconds_do_not_round(self):
        def value(root):root.find('./Controller/Tasks/Task[@Name="FastTask"]').set('Watchdog','12.345000')
        e=self.checked(['GSV(Task,FastTask,Watchdog,Out);'],mutate=value);e.step();self.assertEqual(e.memory.read('Out'),12345)

    def test_current_task_aliases_unknown_tasks_and_runtime_attributes_stay_blocked(self):
        for instance,attribute in (('','Rate'),('THIS','Rate'),('Missing','Name'),('FastTask','Instance'),
                                  ('FastTask','LastScanTime'),('FastTask','Status'),('FastTask','OverlapCount')):
            self.assertTrue(self.engine([f'GSV(Task,{instance},{attribute},Out);']).blockers)
        for text in ('GSV(Controller,This,TimeSlice,PriorityOut);','GSV(Module,,EntryStatus,Out);',
                     'SSV(Task,FastTask,Rate,Out);','GSV(Task,FastTask,Rate);'):
            self.assertTrue(self.engine([text]).blockers,text)

    def test_false_rung_skipped_st_and_prescan_retain_outputs(self):
        for logic,st in ((['AFI()GSV(Task,FastTask,Rate,Out);','AFI()GSV(Controller,,Name,NameOut);'],False),
                         ('IF FALSE THEN GSV(Task,FastTask,Rate,Out); GSV(Controller,,Name,NameOut); END_IF;',True)):
            e=self.checked(logic,st=st);self.assertEqual(e.memory.read('Out'),-7);self.assertEqual(e.memory.string('NameOut'),'SAVED')
            e.step();self.assertEqual(e.memory.read('Out'),-7);self.assertEqual(e.memory.string('NameOut'),'SAVED')
        e=self.checked(['GSV(Task,FastTask,Rate,Out)OTE(Flag);']);e.step();self.assertTrue(e.memory.read('Flag'))

    def test_unknown_destinations_can_be_established_without_fabricating_sources(self):
        e=self.checked(['GSV(Task,FastTask,Rate,Out);','GSV(Task,FastTask,Name,NameOut);'])
        e.memory.values['out']=None;e.memory.values['nameout']['LEN']=None;e.memory.values['nameout']['DATA'][0]=None
        e.step();self.assertEqual(e.memory.read('Out'),10000);self.assertEqual(e.memory.string('NameOut'),'FastTask')

    def test_wrong_types_bits_whole_arrays_and_constant_destinations_are_blocked(self):
        for text in ('GSV(Task,FastTask,Rate,PriorityOut);','GSV(Task,FastTask,Priority,Out);',
                     'GSV(Task,FastTask,InhibitTask,Flag);','GSV(Task,FastTask,Rate,Out.0);',
                     'GSV(Task,FastTask,Name,Out);','GSV(Controller,,TimeSlice,NameOut);'):
            self.assertTrue(self.engine([text]).blockers,text)
        for attr,dest in (('Rate','Out'),('Priority','PriorityOut'),('Name','NameOut')):
            def constant(root):root.find(f'./Controller/Tags/Tag[@Name="{dest}"]').set('Constant','true')
            self.assertTrue(self.engine([f'GSV(Task,FastTask,{attr},{dest});'],mutate=constant).blockers)

    def test_alias_and_udt_string_destinations_and_program_local_shadow(self):
        def aliases(root):
            strings.StringOperationTests.custom_strings(root);tags=root.find('./Controller/Tags')
            E.SubElement(tags,'Tag',Name='OutAlias',TagType='Alias',DataType='DINT',AliasFor='Out')
            scalar(root.find('./Controller/Programs/Program[@Name="BackgroundProgram"]/Tags'),'PriorityOut','INT')
        e=self.checked(['GSV(Task,FastTask,Rate,OutAlias);','GSV(Task,FastTask,Name,Record.Text);','GSV(Task,FastTask,Priority,PriorityOut);'],mutate=aliases);e.step()
        self.assertEqual(e.memory.read('Out'),10000);self.assertEqual(e.memory.string('Record.Text'),'FastTask')
        self.assertEqual(e.memory.read('PriorityOut'),-7);self.assertEqual(e.memory.read('PriorityOut','BackgroundProgram'),2)

    def test_dynamic_scalar_destination_bounds_rechecked_and_prior_writes_rolled_back(self):
        def array(root):
            tag=E.SubElement(root.find('./Controller/Tags'),'Tag',Name='Words',DataType='DINT',TagType='Base',Dimensions='2')
            arr=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Array',DataType='DINT',Dimensions='2')
            for i in range(2):E.SubElement(arr,'Element',Index=f'[{i}]',Value='77')
        e=self.checked(['GSV(Task,FastTask,Rate,Words[Index]);'],mutate=array);e.memory.write('Index',1);e.step()
        self.assertEqual(e.memory.read('Words'),[77,10000])
        e.memory.write('Index',2);before=copy.deepcopy(e.memory.values);time,scans=e.time_ms,e.scan_count
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual((e.time_ms,e.scan_count),(time,scans))
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],1)

    def test_small_user_string_failure_and_later_fault_roll_back_all_state(self):
        def small(root):
            strings.StringOperationTests.custom_strings(root)
            member=root.find('./Controller/DataTypes/DataType[@Name="UserText"]/Members/Member[@Name="DATA"]');member.set('Dimension','4')
            for arr in root.findall('.//ArrayMember[@Name="DATA"]'):
                if arr.get('Dimensions')=='16':
                    arr.set('Dimensions','4')
                    for item in list(arr)[4:]:arr.remove(item)
        e=self.checked(['MOV(77,Out);','GSV(Task,FastTask,Name,Record.Text);'],mutate=small);before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'capacity'):e.step()
        self.assertEqual(e.memory.values,before)
        e=self.checked(['GSV(Task,FastTask,Rate,Out);','GSV(Task,FastTask,Priority,PriorityOut);','DIV(1,0,Out);']);before=copy.deepcopy(e.memory.values)
        with self.assertRaises(ModelError):e.step()
        self.assertEqual(e.memory.values,before);self.assertEqual((e.time_ms,e.scan_count),(0,0))
        self.assertEqual(e.scheduler_description()['tasks'][1]['executions'],0)

    def test_st_for_contract_protects_numeric_and_string_bound_destinations(self):
        for body,bound in (('GSV(Task,FastTask,Rate,Limit);','Limit'),('GSV(Task,FastTask,Priority,PriorityOut);','PriorityOut'),
                           ('GSV(Task,FastTask,Name,NameOut);','NameOut.LEN')):
            e=self.engine(f'FOR Index:=0 TO {bound} DO {body} END_FOR;',st=True)
            self.assertTrue(e.blockers);self.assertIn('bounds/step',str(e.blockers))
        e=self.checked('FOR Index:=0 TO Limit DO GSV(Task,FastTask,Rate,Out); END_FOR;',st=True);e.step();self.assertEqual(e.memory.read('Out'),10000)

    def test_source_configuration_bytes_equal_existing_task_and_controller_metadata(self):
        e=self.checked(['GSV(Task,FastTask,Rate,Out);','GSV(Task,FastTask,Priority,PriorityOut);']);e.step()
        self.assertEqual(struct.pack('<i',e.memory.read('Out')),e.project.task_timing.attributes('FastTask',source_sha256=e.project.sha256)[2])
        self.assertEqual(struct.pack('<h',e.memory.read('PriorityOut')),e.project.task_configuration.attributes('FastTask',source_sha256=e.project.sha256)[6])
        e=self.checked(['GSV(Controller,,TimeSlice,PriorityOut);']);e.step()
        self.assertEqual(struct.pack('<h',e.memory.read('PriorityOut')),e.project.controller_configuration.compatibility_attributes()[3])

    def test_missing_or_conflicting_controller_name_and_incomplete_source_block(self):
        for value in (None,''):
            def missing(root):
                c=root.find('Controller')
                if value is None:c.attrib.pop('Name')
                else:c.set('Name',value)
            self.assertTrue(self.engine(['GSV(Controller,,Name,NameOut);'],mutate=missing).blockers)
        def conflict(root):root.find('Controller').set('name','Other')
        self.assertTrue(self.engine(['GSV(Controller,,Name,NameOut);'],mutate=conflict).blockers)
        def context(root):root.set('ContainsContext','true')
        self.assertTrue(self.engine(['GSV(Task,FastTask,Rate,Out);'],mutate=context).blockers)

    def test_loaded_source_is_immutable_and_rebound_hash_or_profile_mismatch_is_rejected(self):
        def old(root):root.find('Controller').set('ProcessorType','1756-L75')
        self.assertTrue(self.engine(['GSV(Task,FastTask,Rate,Out);'],mutate=old).blockers)
        e=self.checked(['GSV(Task,FastTask,Rate,Out);']);e.project.path.write_bytes(e.project.path.read_bytes()+b'\n')
        # Runtime reads its loaded snapshot; a changed disk file is not a reload.
        e.step();self.assertEqual(e.memory.read('Out'),10000)
        e.project.sha256='0'*64
        before=copy.deepcopy(e.memory.values)
        with self.assertRaisesRegex(ModelError,'unavailable'):e.step()
        self.assertEqual(e.memory.values,before)

    def test_report_keeps_configuration_separate_from_native_runtime_and_ssv(self):
        e=self.checked(['GSV(Task,FastTask,Rate,Out);']);report=e.report()['system_values']
        self.assertTrue(report['ssv']);self.assertFalse(report['configuration']['native_runtime_equivalence'])
        self.assertIn('Microseconds',report['configuration']['times'])

    def test_aoi_typed_output_and_string_inout_bindings_in_rll_and_st(self):
        for st in (False,True):
            def aoi(root):
                c=root.find('Controller')
                definition=E.SubElement(c.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='ReadTask',Class='Standard',ExecutePrescan='false',ExecutePostscan='false',ExecuteEnableInFalse='false')
                params=E.SubElement(definition,'Parameters')
                for name,dtype,usage,required in (('EnableIn','BOOL','Input','false'),('EnableOut','BOOL','Output','false'),
                                               ('Prio','INT','Output','true'),('Text','STRING','InOut','true'),('Rate','DINT','Output','true')):
                    E.SubElement(params,'Parameter',Name=name,DataType=dtype,Usage=usage,Required=required,Visible=required,TagType='Base')
                E.SubElement(definition,'LocalTags')
                routine=E.SubElement(E.SubElement(definition,'Routines'),'Routine',Name='Logic',Type='ST' if st else 'RLL')
                content=E.SubElement(routine,'STContent' if st else 'RLLContent')
                for i,text in enumerate(('GSV(Task,FastTask,Priority,Prio);','GSV(Task,FastTask,Name,Text);','GSV(Task,FastTask,Rate,Rate);')):
                    if st:E.SubElement(content,'Line',Number=str(i)).text=text
                    else:E.SubElement(E.SubElement(content,'Rung',Number=str(i),Type='N'),'Text').text=text
                tag=E.SubElement(c.find('Tags'),'Tag',Name='Instance',DataType='ReadTask',TagType='Base')
                obj=E.SubElement(E.SubElement(tag,'Data',Format='Decorated'),'Structure',DataType='ReadTask')
                for name,dtype in (('EnableIn','BOOL'),('EnableOut','BOOL'),('Prio','INT'),('Rate','DINT')):
                    E.SubElement(obj,'DataValueMember',Name=name,DataType=dtype,Value='0')
            e=self.checked(['ReadTask(Instance,PriorityOut,NameOut,Out);'],mutate=aoi);e.step()
            self.assertEqual(e.memory.read('PriorityOut'),2);self.assertEqual(e.memory.string('NameOut'),'FastTask');self.assertEqual(e.memory.read('Out'),10000)


    def test_bundled_system_lab_rll_st_settings_and_schedule(self):
        e=Engine(Project(Path(__file__).resolve().parents[1]/'samples/SystemLab.L5X'));self.assertEqual(e.blockers,[]);e.step(25)
        self.assertEqual(e.memory.read('FastRate'),10000);self.assertEqual(e.memory.read('SlowRate'),25000)
        self.assertEqual(e.memory.read('FastPriority'),2);self.assertEqual(e.memory.read('CommTimeSlice'),30)
        self.assertEqual(e.memory.string('ControllerName'),'SystemLab');self.assertEqual(e.memory.string('FastTaskName'),'FastTask')
        self.assertEqual(e.memory.read('StSlowRate'),25000);self.assertEqual(e.memory.string('StFastTaskName'),'FastTask')
        self.assertEqual([t['executions'] for t in e.scheduler_description()['tasks']],[1,2,1])


if __name__=='__main__':unittest.main()
