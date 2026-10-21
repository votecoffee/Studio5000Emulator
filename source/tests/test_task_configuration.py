"""Task settings must be explicit and remain separate from native task IDs."""
import copy
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest
import struct
from xml.etree import ElementTree as E
from unittest.mock import patch

from logixlab.task_configuration import TaskConfiguration, TaskSettings

SOURCE = Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X'
HASH = 'a'*64
ACD_HASH = 'c'*64


def source():
    root=E.fromstring(SOURCE.read_bytes())
    return root,root.find('Controller')


def scheduled(config, task='MainTask', **updates):
    arguments=dict(source_sha256=HASH,source_acd_sha256=ACD_HASH,program_ids={'MainProgram':26038},
                   program_source_l5x_sha256=HASH,program_source_acd_sha256=ACD_HASH)
    arguments.update(updates)
    return config.scheduled_attributes(task,**arguments)


class TaskConfigurationTests(unittest.TestCase):
    def test_inverse_owner_uses_actual_task_id_and_same_source_pairs(self):
        root,controller=source();config=TaskConfiguration.from_source(root,controller,HASH)
        args=dict(source_sha256=HASH,source_acd_sha256=ACD_HASH,task_ids={'MainTask':77},
            task_source_l5x_sha256=HASH,task_source_acd_sha256=ACD_HASH)
        self.assertEqual(config.owner_attributes('MAINPROGRAM',**args),{13:struct.pack('<I',77)})
        for update in ({'task_ids':{}},{'task_ids':{'MainTask':True}},{'task_ids':{'MainTask':65536}},
                       {'task_ids':{'MainTask':1,'Other':1}},{'task_ids':{'MainTask':1,'MAINTASK':2}},
                       {'source_sha256':'d'*64},{'source_acd_sha256':'x'},
                       {'task_source_l5x_sha256':'d'*64},{'task_source_acd_sha256':'d'*64}):
            self.assertEqual(config.owner_attributes('MainProgram',**{**args,**update}),{})
        self.assertEqual(config.owner_attributes('Missing',**args),{})
        self.assertEqual(config.owner_attributes(None,**args),{})

    def test_missing_foreign_or_ambiguous_task_schedule_does_not_invent_an_owner(self):
        for mode in ('missing','duplicate-owner','foreign-task','unknown-program','unscheduled','phase','kind-alias'):
            root,controller=source();task=controller.find('./Tasks/Task')
            if mode=='missing':task.remove(task.find('ScheduledPrograms'))
            elif mode=='duplicate-owner':
                other=copy.deepcopy(task);other.set('Name','Other');controller.find('Tasks').append(other)
            elif mode=='foreign-task':
                other=copy.deepcopy(task);other.set('Class','Safety');other.set('Name','Other');controller.find('Tasks').append(other)
            elif mode=='unknown-program':task.find('./ScheduledPrograms/ScheduledProgram').set('Name','Unknown')
            elif mode=='phase':controller.find('./Programs/Program').set('Type','EquipmentPhase')
            elif mode=='kind-alias':controller.find('./Programs/Program').set('type','Normal')
            else:task.find('ScheduledPrograms').clear()
            config=TaskConfiguration.from_source(root,controller,HASH)
            self.assertEqual(config.owner_attributes('MainProgram',source_sha256=HASH,source_acd_sha256=ACD_HASH,
                task_ids={'MainTask':1},task_source_l5x_sha256=HASH,task_source_acd_sha256=ACD_HASH),
                {13:bytes(4)} if mode=='unscheduled' else {})

    def test_constructor_does_not_accept_ambiguous_owner_claims(self):
        rows={'one':TaskSettings('One',scheduled_programs=('Program',)),
              'two':TaskSettings('Two',scheduled_programs=('Program',))}
        with self.assertRaises(ValueError):TaskConfiguration(HASH,True,rows,_program_owners={'program':'one'})

    def test_program_list_preserves_source_order_using_real_bound_ids_instead_of_source_order_ids(self):
        root,controller=source();programs=controller.find('Programs')
        for name in ('Second','Third'):
            other=copy.deepcopy(programs[0]);other.set('Name',name);programs.append(other)
        target=controller.find('./Tasks/Task/ScheduledPrograms');target.clear()
        for name in ('third','MainProgram','SECOND'):E.SubElement(target,'ScheduledProgram',Name=name)
        config=TaskConfiguration.from_source(root,controller,HASH)
        result=scheduled(config,program_ids={'MainProgram':70000,'Second':12,'Third':0x12345678})
        self.assertEqual(result,{1:struct.pack('<HIII',3,0x12345678,70000,12)})
        self.assertEqual(config._tasks['maintask'].scheduled_programs,('Third','MainProgram','Second'))
        self.assertEqual(config.attributes('MainTask',source_sha256=HASH),{6:b'\x0a\0',18:bytes(4),19:bytes(4)})
        self.assertNotIn(16,result)

    def test_only_explicit_canonical_empty_program_list_can_establish_zero_entries(self):
        root,controller=source();task=controller.find('./Tasks/Task');task.find('ScheduledPrograms').clear()
        config=TaskConfiguration.from_source(root,controller,HASH)
        self.assertEqual(scheduled(config,program_ids={}),{1:b'\0\0'})
        task.remove(task.find('ScheduledPrograms'))
        unknown=TaskConfiguration.from_source(root,controller,HASH)
        self.assertIsNone(unknown._tasks['maintask'].scheduled_programs)
        self.assertEqual(scheduled(unknown,program_ids={}),{})
        self.assertEqual(config.attributes('MainTask',source_sha256=HASH),unknown.attributes('MainTask',source_sha256=HASH))

    def test_malformed_unknown_duplicate_and_safety_schedule_targets_do_not_hide_other_settings(self):
        for kind in ('dangling','duplicate','case-duplicate','safety','unknown-class','missing-name','alias',
                'namespace','tagcase','list-context','entry-context','unknown-child','nested-list','second-list','entry-child',
                'list-text','entry-tail'):
            root,controller=source();task=controller.find('./Tasks/Task');group=task.find('ScheduledPrograms');entry=group[0]
            if kind=='dangling':entry.set('Name','UnknownProgram')
            elif kind in ('duplicate','case-duplicate'):
                other=copy.deepcopy(entry)
                if kind=='case-duplicate':other.set('Name','MAINPROGRAM')
                group.append(other)
            elif kind=='safety':controller.find('./Programs/Program').set('Class','Safety')
            elif kind=='unknown-class':controller.find('./Programs/Program').set('Class','Unknown')
            elif kind=='missing-name':entry.attrib.pop('Name')
            elif kind=='alias':entry.set('name','UnknownProgram')
            elif kind=='namespace':entry.tag='{other}ScheduledProgram'
            elif kind=='tagcase':entry.tag='scheduledprogram'
            elif kind=='list-context':group.set('Use','Context')
            elif kind=='entry-context':entry.set('Use','Context')
            elif kind=='unknown-child':E.SubElement(group,'VendorProgramList')
            elif kind=='nested-list':E.SubElement(task,'Wrapper').append(copy.deepcopy(group))
            elif kind=='second-list':task.append(copy.deepcopy(group))
            elif kind=='list-text':group.text='Unmodeled scheduling data'
            elif kind=='entry-tail':entry.tail='Unmodeled scheduling data'
            else:E.SubElement(entry,'VendorData')
            with self.subTest(kind=kind):
                config=TaskConfiguration.from_source(root,controller,HASH)
                self.assertTrue(config.source_complete)
                self.assertEqual(scheduled(config),{})
                self.assertEqual(config.attributes('MainTask',source_sha256=HASH),{6:b'\x0a\0',18:bytes(4),19:bytes(4)})

    def test_ambiguous_program_declarations_and_cross_task_scheduling_withhold_the_lists(self):
        for kind in ('duplicate-program','alias-program','nested-program','two-task-owners','unscoped-list'):
            root,controller=source();program=controller.find('./Programs/Program')
            if kind=='duplicate-program':controller.find('Programs').append(copy.deepcopy(program))
            elif kind=='alias-program':program.set('{other}Name','OtherProgram')
            elif kind=='nested-program':E.SubElement(controller,'Wrapper').append(copy.deepcopy(program))
            elif kind=='unscoped-list':E.SubElement(controller,'Wrapper').append(copy.deepcopy(controller.find('./Tasks/Task/ScheduledPrograms')))
            else:
                other=copy.deepcopy(controller.find('./Tasks/Task'));other.set('Name','OtherTask');controller.find('Tasks').append(other)
            with self.subTest(kind=kind):
                config=TaskConfiguration.from_source(root,controller,HASH)
                self.assertEqual(scheduled(config),{})
                self.assertTrue(config.attributes('MainTask',source_sha256=HASH))
                if kind=='two-task-owners':self.assertEqual(scheduled(config,'OtherTask'),{})

    def test_source_and_program_binding_hashes_missing_ids_and_invalid_maps_never_return_a_partial_list(self):
        root,controller=source();config=TaskConfiguration.from_source(root,controller,HASH)
        self.assertEqual(scheduled(config),{1:struct.pack('<HI',1,26038)})
        changes=({'source_sha256':'b'*64},{'program_source_l5x_sha256':'b'*64},
                 {'source_acd_sha256':'d'*64},{'source_acd_sha256':''},{'program_source_acd_sha256':'d'*64},
                 {'program_ids':{}},{'program_ids':None},{'program_ids':[]},{'program_ids':{'MainProgram':0}},
                 {'program_ids':{'MainProgram':True}},{'program_ids':{'MainProgram':-1}},
                 {'program_ids':{'MainProgram':0x100000000}},{'program_ids':{'MainProgram':1,'MAINPROGRAM':2}},
                 {'program_ids':{'MainProgram':1,'Other':1}},{'program_ids':{'MainProgram':1,'bad.name':2}})
        for change in changes:
            with self.subTest(change=change):self.assertEqual(scheduled(config,**change),{})
        self.assertEqual(scheduled(config,program_ids={'MainProgram':0xFFFFFFFF}),{1:struct.pack('<HI',1,0xFFFFFFFF)})
        self.assertEqual(scheduled(config,'MissingTask'),{})
        self.assertEqual(scheduled(config,None),{})
        with patch('logixlab.task_configuration.MAX_PROGRAMS',0):self.assertEqual(scheduled(config),{})

    def test_schedule_snapshot_order_and_returned_bytes_cannot_be_changed_by_mutating_source_or_bindings(self):
        root,controller=source();config=TaskConfiguration.from_source(root,controller,HASH)
        bindings={'mainprogram':26038};before=scheduled(config,program_ids=bindings)
        controller.find('./Tasks/Task/ScheduledPrograms').clear();bindings['mainprogram']=5
        self.assertEqual(before,{1:struct.pack('<HI',1,26038)})
        self.assertEqual(scheduled(config),before)
        with self.assertRaises(FrozenInstanceError):config._tasks['maintask'].scheduled_programs=()
        for invalid in ([],('MainProgram','MAINPROGRAM'),('bad.name',),('Program'+str(i) for i in range(2))):
            with self.assertRaises(ValueError):TaskSettings('MainTask',scheduled_programs=invalid)
        self.assertEqual(TaskSettings('MainTask',scheduled_programs=()).scheduled_programs,())

    def test_excessive_explicit_schedule_is_unavailable_while_explicit_settings_still_read_back(self):
        root,controller=source();programs=controller.find('Programs');programs.clear()
        group=controller.find('./Tasks/Task/ScheduledPrograms');group.clear()
        for index in range(1029):
            name='Program'+str(index)
            program=E.SubElement(programs,'Program',Name=name,Class='Standard');E.SubElement(program,'Tags')
            E.SubElement(group,'ScheduledProgram',Name=name)
        config=TaskConfiguration.from_source(root,controller,HASH)
        self.assertTrue(config.source_complete);self.assertEqual(scheduled(config),{})
        self.assertTrue(config.attributes('MainTask',source_sha256=HASH))
        with self.assertRaises(ValueError):TaskSettings('MainTask',scheduled_programs=tuple('Program'+str(i) for i in range(1029)))

    def test_independent_explicit_fields_keep_their_exact_wire_widths(self):
        root,controller=source();tasks=controller.find('Tasks')
        other=copy.deepcopy(tasks[0]);other.set('Name','Other');other.set('Priority','1')
        other.set('DisableUpdateOutputs','true');other.set('InhibitTask','true');tasks.append(other)
        config=TaskConfiguration.from_source(root,controller,HASH)
        self.assertTrue(config.source_complete)
        self.assertEqual(config.attributes('MAINTASK',source_sha256=HASH),{6:b'\x0a\0',18:bytes(4),19:bytes(4)})
        self.assertEqual(config.attributes('Other',source_sha256=HASH),{6:b'\1\0',18:b'\1\0\0\0',19:b'\1\0\0\0'})
        self.assertEqual(config.names,('MainTask','Other'))
        self.assertFalse(config.description()['native_id_inferred'])

    def test_missing_and_malformed_fields_never_default_or_hide_valid_siblings(self):
        for value in (None,'','TRUE','0','false ','yes'):
            root,controller=source();task=controller.find('./Tasks/Task')
            if value is None:task.attrib.pop('InhibitTask')
            else:task.set('InhibitTask',value)
            with self.subTest(value=value):
                config=TaskConfiguration.from_source(root,controller,HASH)
                self.assertEqual(config.attributes('MainTask',source_sha256=HASH),{6:b'\x0a\0',18:bytes(4)})
        for value in ('0','16','65535','01','+1',' 1','1.0'):
            root,controller=source();controller.find('./Tasks/Task').set('Priority',value)
            self.assertNotIn(6,TaskConfiguration.from_source(root,controller,HASH).attributes('MainTask',source_sha256=HASH))

    def test_context_aliases_duplicate_names_and_shadow_scopes_withhold_inventory(self):
        for kind in ('context','target','major','container','duplicate','case','nested','namespace','tagcase','fieldalias','fieldns','use'):
            root,controller=source();tasks=controller.find('Tasks');task=tasks[0]
            if kind=='context':root.set('ContainsContext','true')
            elif kind=='target':root.set('TargetType','Task')
            elif kind=='major':controller.set('MajorRev','34')
            elif kind=='container':controller.append(copy.deepcopy(tasks))
            elif kind in ('duplicate','case'):
                other=copy.deepcopy(task)
                if kind=='case':other.set('Name','MAINTASK')
                tasks.append(other)
            elif kind=='nested':E.SubElement(controller,'Wrapper').append(copy.deepcopy(tasks))
            elif kind=='namespace':task.tag='{other}Task'
            elif kind=='tagcase':task.tag='task'
            elif kind=='fieldalias':task.set('inhibittask','true')
            elif kind=='fieldns':task.set('{other}InhibitTask','true')
            else:task.set('Use','Context')
            with self.subTest(kind=kind):
                config=TaskConfiguration.from_source(root,controller,HASH)
                self.assertFalse(config.source_complete)
                self.assertEqual(config.names,())

    def test_native_missing_class_is_ordinary_but_safety_and_unknown_are_not_exposed(self):
        for value in (None,'Safety','Unknown'):
            root,controller=source();task=controller.find('./Tasks/Task')
            if value is None:task.attrib.pop('Class')
            else:task.set('Class',value)
            config=TaskConfiguration.from_source(root,controller,HASH)
            self.assertTrue(config.source_complete)
            self.assertEqual(bool(config.attributes('MainTask',source_sha256=HASH)),value is None)

    def test_hash_guard_and_immutable_snapshot_prevent_stale_readback(self):
        root,controller=source();config=TaskConfiguration.from_source(root,controller,HASH)
        controller.find('./Tasks/Task').set('InhibitTask','true')
        self.assertEqual(config.attributes('MainTask',source_sha256=HASH)[19],bytes(4))
        self.assertEqual(config.attributes('MainTask',source_sha256='b'*64),{})
        self.assertEqual(config.attributes('Other',source_sha256=HASH),{})
        with self.assertRaises(TypeError):config._tasks['other']=TaskSettings('Other')
        with self.assertRaises(FrozenInstanceError):config.source_complete=False
        attributes=config.attributes('MainTask',source_sha256=HASH);attributes[19]=bytes(1)
        self.assertEqual(config.attributes('MainTask',source_sha256=HASH)[19],bytes(4))

    def test_invalid_names_types_and_limits_cannot_create_a_snapshot(self):
        for args in (('bad.name',),('MainTask',True),('MainTask',16),('MainTask',1,1),('MainTask',1,None,0)):
            with self.assertRaises(ValueError):TaskSettings(*args)
        for digest in ('',None,'A'*64):
            with self.assertRaises(ValueError):TaskConfiguration(digest)
        with self.assertRaises(ValueError):TaskConfiguration(HASH,False,{'task':TaskSettings('task')})
        root,controller=source();tasks=controller.find('Tasks')
        for i in range(32):
            other=copy.deepcopy(tasks[0]);other.set('Name','Task'+str(i));tasks.append(other)
        self.assertFalse(TaskConfiguration.from_source(root,controller,HASH).source_complete)


if __name__=='__main__':unittest.main()
