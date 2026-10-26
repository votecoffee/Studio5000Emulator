"""Native constant descriptors need a proved source value and keep writes denied."""
import copy
import struct
from types import MappingProxyType
import unittest
from unittest.mock import patch

from logixlab.installed_memory import constant_keys,read_constant
from logixlab.download_image import ImageError
from logixlab.model import ModelError
import test_installed_memory as memory
import test_download_changelog as logs
import test_download_headers as headers


def constant_symbol(original):
    def symbol(instance,name,*args,**kwargs):
        row=original(instance,name,*args,**kwargs)
        if name!='SpeedSetpoint':return row
        values=headers.attributes(0x6B,row.request[2+2*row.request[1]:]);values[11]=b'\1'
        return headers.update(0x6B,instance,values)
    return symbol


class InstalledConstantTests(logs.NamespaceFixture,unittest.TestCase):
    complete_tasks=memory.InstalledMemoryTests.complete_tasks
    configure=memory.InstalledMemoryTests.configure
    ready_setup=memory.InstalledMemoryTests.ready_setup
    ready_routines=memory.InstalledMemoryTests.ready_routines
    next_routines=memory.InstalledMemoryTests.next_routines
    ready_map=memory.InstalledMemoryTests.ready_map
    ready_log=memory.InstalledMemoryTests.ready_log
    proposal=memory.InstalledMemoryTests.proposal
    ready_install=memory.InstalledMemoryTests.ready_install

    def setUp(self):
        original=logs.maps.map_route
        def route(test):
            result=original(test)
            result[1].find('./Tags/Tag[@Name="SpeedSetpoint"]').set('Constant','true')
            return result
        with patch.object(logs.maps,'map_route',route),patch.object(headers,'symbol',constant_symbol(headers.symbol)):
            memory.InstalledMemoryTests.setUp(self)
        self.assertTrue(self.app.engine.project.tags['speedsetpoint'].constant)

    def installed(self):
        with patch.object(headers,'symbol',constant_symbol(headers.symbol)):memory.InstalledMemoryTests.installed(self)

    def test_constant_table_has_complete_read_only_native_storage_after_install(self):
        router=self.endpoint.router;self.assertFalse(constant_keys(self.app,router))
        self.assertNotIn('speedsetpoint',router.scalar_storage().by_ref)
        self.installed();before=copy.deepcopy(self.app.state())
        self.assertEqual(constant_keys(self.app,router),{'speedsetpoint'})
        self.assertEqual(read_constant(self.app,router,'speedsetpoint'),bytes(4))
        self.assertEqual(self.send(bytes.fromhex('0302206a240107000100020003000600070008000900'))[2],0)
        self.assertEqual(self.send(bytes.fromhex('4f02206a2401000000000400')),bytes.fromhex('cf000000')+bytes(4))
        self.assertEqual(self.send(bytes.fromhex('0e03206b2401300b')),bytes.fromhex('8e00000001'))
        self.assertNotEqual(memory.InstalledMemoryTests.read_value(self)[2],0)
        for service in (4,0x10,0x4D,0x50):self.assertNotEqual(self.send(bytes((service,2))+bytes.fromhex('206a2401')+bytes(8))[2],0)
        with self.assertRaises(ModelError):self.app.command('write',dict(tag='SpeedSetpoint',value=1))
        for field in ('tags','scan','ms','routine_edits'):self.assertEqual(self.app.state()[field],before[field])

    def test_changed_value_or_effect_and_reset_revoke_constant_readback(self):
        self.installed();router=self.endpoint.router;engine=self.app.engine
        engine.memory.values['speedsetpoint']=1
        with self.assertRaises(ImageError):read_constant(self.app,router,'speedsetpoint')
        engine.memory.values['speedsetpoint']=0
        self.assertEqual(read_constant(self.app,router,'speedsetpoint'),bytes(4))
        stage=engine.installed_download.namespace._incremental;values=dict(stage._headers)
        row=dict(values[0x6B,0,1]);row[11]=b'\0';values[0x6B,0,1]=tuple(sorted(row.items()));stage._headers=MappingProxyType(values)
        self.assertNotEqual(self.send(bytes.fromhex('0e03206a24013003'))[2],0)
        self.app.command('reset',{});self.assertFalse(constant_keys(self.app,router))
        self.assertNotIn('speedsetpoint',router.scalar_storage().by_ref)
