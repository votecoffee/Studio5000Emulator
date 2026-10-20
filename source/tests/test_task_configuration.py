"""Task settings must be explicit and remain separate from native task IDs."""
import copy
from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest
from xml.etree import ElementTree as E

from logixlab.task_configuration import TaskConfiguration, TaskSettings

SOURCE = Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X'
HASH = 'a'*64


def source():
    root=E.fromstring(SOURCE.read_bytes())
    return root,root.find('Controller')


class TaskConfigurationTests(unittest.TestCase):
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
