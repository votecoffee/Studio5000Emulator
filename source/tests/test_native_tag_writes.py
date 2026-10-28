"""Native scalar table writes require explicit access and complete installed backing."""
import copy
import struct
import time
import unittest
from unittest.mock import patch

from logixlab.model import ModelError
import test_installed_memory as memory


class NativeTagWriteTests(memory.controls.logs.NamespaceFixture,unittest.TestCase):
    def write_value(self,value=37,instance=1,selector=0,marker=0,raw=None):
        data=struct.pack('<i',value) if raw is None else raw
        path=bytes((0x20,0x6A,0x24,instance))
        return self.send(bytes((0x50,2))+path+struct.pack('<IBH',selector,marker,len(data))+data)

    def test_default_denial_then_opt_in_updates_same_value_read_online(self):
        self.installed();before=copy.deepcopy(self.app.state())
        self.assertEqual(self.write_value()[2],15)
        self.app.allow_native_tag_writes=True
        self.assertEqual(self.write_value(),bytes.fromhex('d0000000'))
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'),37)
        self.assertEqual(self.read_value()[4:],struct.pack('<i',37))
        for key in ('routines','controller','scan','ms','routine_edits'):
            self.assertEqual(self.app.state()[key],before[key])
        self.assertFalse(self.endpoint.allow_writes)
        unsigned=bytes.fromhex('5002206a2401')+struct.pack('<IBHi',0,0,4,19)
        self.assertNotEqual(self.cip(unsigned)[2],0)
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'),37)

    def test_partial_selectors_markers_unknown_tables_and_wrong_sizes_preserve_values(self):
        self.installed();self.app.allow_native_tag_writes=True;before=copy.deepcopy(self.app.engine.memory.values)
        for options in (dict(selector=1),dict(marker=1),dict(instance=0),dict(instance=2),dict(raw=b''),dict(raw=b'\1'),dict(raw=bytes(8))):
            with self.subTest(options=options):self.assertNotEqual(self.write_value(**options)[2],0)
        malformed=bytes.fromhex('5002206a2401')+struct.pack('<IBH',0,0,4)+bytes(3)
        self.assertNotEqual(self.send(malformed)[2],0)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_source_access_constants_and_running_mode_revoke_write_path(self):
        self.installed();self.app.allow_native_tag_writes=True;tag=self.app.engine.project.tags['speedsetpoint']
        before=copy.deepcopy(self.app.engine.memory.values)
        for field,value in (('constant',True),('external_access','Read Only'),('external_access','None'),('dtype','INT')):
            original=getattr(tag,field);setattr(tag,field,value)
            try:self.assertNotEqual(self.write_value()[2],0)
            finally:setattr(tag,field,original)
        with patch.object(self.app,'controller_state',return_value=dict(mode='Run')):
            self.assertNotEqual(self.write_value()[2],0)
        identity=self.app.native_project_identity;self.app.native_project_identity=None
        try:self.assertNotEqual(self.write_value()[2],0)
        finally:self.app.native_project_identity=identity
        self.assertEqual(self.app.engine.memory.values,before)
        self.assertEqual(self.write_value()[2],0)

    def test_configuration_requires_boolean_program_native_endpoint_and_disconnected_clients(self):
        self.assertFalse(self.app.state()['native_tag_writes']['enabled'])
        for value in (None,1,'true'):
            with self.assertRaises(ModelError):self.app.command('native-tag-writes-configure',dict(allow_writes=value))
        with self.assertRaises(ModelError):self.app.command('native-tag-writes-configure',dict(allow_writes=True))
        self.client.close()
        for _ in range(50):
            if not self.endpoint.state()['active_tcp_clients']:break
            time.sleep(.01)
        self.assertTrue(self.app.command('native-tag-writes-configure',dict(allow_writes=True))['native_tag_writes']['enabled'])
        self.app.running=True
        try:
            with self.assertRaises(ModelError):self.app.command('native-tag-writes-configure',dict(allow_writes=False))
        finally:self.app.running=False
        self.assertFalse(self.app.command('native-tag-writes-configure',dict(allow_writes=False))['native_tag_writes']['enabled'])


for _name in ('setUp','complete_tasks','configure','ready_setup','ready_routines','next_routines','ready_map','ready_log',
              'proposal','ready_install','installed','read_value'):
    setattr(NativeTagWriteTests,_name,getattr(memory.InstalledMemoryTests,_name))


if __name__=='__main__':unittest.main()
