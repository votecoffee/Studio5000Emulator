"""Signed online scalar reads resolve committed addresses to current model values."""
import copy
import struct
from types import MappingProxyType
import unittest

from logixlab.download_namespace import VALUE_BASE
from logixlab.installed_memory import read_scalar,scalar_word
from logixlab.download_image import ImageError
import test_installed_symbol_control as controls


class InstalledMemoryTests(controls.logs.NamespaceFixture,unittest.TestCase):
    setUp=controls.InstalledSymbolControlTests.setUp
    complete_tasks=controls.InstalledSymbolControlTests.complete_tasks
    configure=controls.InstalledSymbolControlTests.configure
    ready_setup=controls.InstalledSymbolControlTests.ready_setup
    ready_routines=controls.InstalledSymbolControlTests.ready_routines
    next_routines=controls.InstalledSymbolControlTests.next_routines
    ready_map=controls.InstalledSymbolControlTests.ready_map
    ready_log=controls.InstalledSymbolControlTests.ready_log
    proposal=controls.InstalledSymbolControlTests.proposal
    ready_install=controls.InstalledSymbolControlTests.ready_install
    installed=controls.InstalledSymbolControlTests.installed

    def read_value(self,address=VALUE_BASE,words=1,path=bytes.fromhex('20722400')):
        return self.send(bytes((0x4C,len(path)//2))+path+struct.pack('<IH',address,words))

    def test_scalar_word_preserves_dint_and_canonical_bool_without_accepting_other_storage(self):
        self.assertEqual(scalar_word('DINT',0xC4,struct.pack('<i',-123)),struct.pack('<i',-123))
        self.assertEqual(scalar_word('BOOL',0xC1,b'\1'),bytes.fromhex('01000000'))
        self.assertEqual(scalar_word('BOOL',0xC1,b'\0'),bytes(4))
        for dtype,code,value in (('BOOL',0xC1,b'\2'),('BOOL',0xC1,bytes(4)),('BOOL',0xC4,b'\1'),
                                  ('DINT',0xC4,b'\1'),('USINT',0xC6,b'\1'),('BOOL',0xC1,bytearray(b'\1'))):
            with self.subTest(dtype=dtype,code=code,value=value),self.assertRaises(ImageError):scalar_word(dtype,code,value)

    def test_installed_address_reads_current_dint_without_scans_or_model_mutation(self):
        self.assertEqual(self.read_value()[2],12)
        self.installed();self.app.engine.memory.write('SpeedSetpoint',87);before=copy.deepcopy(self.app.state())
        self.assertNotEqual(self.cip(bytes.fromhex('4c0220722400')+struct.pack('<IH',VALUE_BASE,1))[2],0)
        self.assertEqual(self.read_value(),bytes.fromhex('cc000000')+struct.pack('<i',87))
        for key in ('tags','scan','ms','controller','routines','routine_edits'):
            self.assertEqual(self.app.state()[key],before[key])
        self.app.engine.memory.write('SpeedSetpoint',-2147483648)
        self.assertEqual(self.read_value()[4:],struct.pack('<i',-2147483648))
        self.assertEqual(self.app.engine.scan_count,0)

    def test_unknown_interior_descriptor_and_auxiliary_addresses_never_read_other_storage(self):
        self.installed()
        for address in (0,VALUE_BASE+1,VALUE_BASE+4,VALUE_BASE+8,0x70000000,0x71000000,0x50000000,0xFFFFFFFF):
            with self.subTest(address=address):self.assertEqual(self.read_value(address)[2],12)
        for words in (0,2,65535):self.assertEqual(self.read_value(words=words)[2],3)
        for path in (bytes.fromhex('20722401'),bytes.fromhex('207224003001'),bytes.fromhex('2068240220722400')):
            self.assertEqual(self.read_value(path=path)[2],4)
        for service in (4,0x10,0x4D,0x53):self.assertEqual(self.send(bytes((service,2))+bytes.fromhex('20722400')+bytes(6))[2],15)

    def test_changed_source_effect_or_declared_type_revokes_value_reads(self):
        self.installed();engine=self.app.engine;original=self.app.native_project_identity
        self.app.native_project_identity=None;self.assertEqual(self.read_value()[2],12)
        self.app.native_project_identity=original;engine.project.runtime_revision=1
        self.assertEqual(self.read_value()[2],12);engine.project.runtime_revision=0
        stage=engine.installed_download.namespace._incremental;headers=dict(stage._headers)
        row=dict(headers[0x6B,0,1]);row[6]=bytes(4);headers[0x6B,0,1]=tuple(sorted(row.items()));stage._headers=MappingProxyType(headers)
        self.assertEqual(self.read_value()[2],12)

    def test_constants_private_access_and_reset_do_not_keep_old_addresses(self):
        self.installed();tag=self.app.engine.project.tags['speedsetpoint']
        tag.constant=True;self.assertEqual(self.read_value()[2],12);tag.constant=False
        tag.external_access='None';self.assertNotEqual(self.read_value()[2],0);tag.external_access='Read/Write'
        self.app.command('reset',{})
        with self.assertRaises(ImageError):read_scalar(self.app,self.endpoint.router,VALUE_BASE,1)


if __name__=='__main__':unittest.main()
