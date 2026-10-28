"""Routine edits preserve committed tag identities and live value readback."""
import copy
from dataclasses import replace
import struct
from types import MappingProxyType
import unittest

from logixlab import installed_memory,routine_read
from logixlab.download_image import ImageError
from logixlab.download_namespace import VALUE_BASE
import test_accepted_routine_source as source
import test_installed_memory as memory
import test_installed_constants as constants


class TagEditFixture:
    setUp=source.AcceptedRoutineSourceTests.setUp
    installed=source.AcceptedRoutineSourceTests.installed
    complete_tasks=source.AcceptedRoutineSourceTests.complete_tasks
    configure=source.AcceptedRoutineSourceTests.configure
    ready_setup=source.AcceptedRoutineSourceTests.ready_setup
    ready_routines=source.AcceptedRoutineSourceTests.ready_routines
    next_routines=source.AcceptedRoutineSourceTests.next_routines
    ready_map=source.AcceptedRoutineSourceTests.ready_map
    ready_log=source.AcceptedRoutineSourceTests.ready_log
    proposal=source.AcceptedRoutineSourceTests.proposal
    ready_install=source.AcceptedRoutineSourceTests.ready_install
    edit=source.AcceptedRoutineSourceTests.edit
    read_value=memory.InstalledMemoryTests.read_value
    control=memory.controls.InstalledSymbolControlTests.control


class EditedTagBindingTests(TagEditFixture,source.wire.logs.NamespaceFixture,unittest.TestCase):
    def test_edited_model_reads_current_values_and_keeps_committed_table_control_and_addresses(self):
        self.installed();router=self.endpoint.router
        table_ids=installed_memory.table_ids(self.app,router);control=self.control()
        self.app.engine.memory.write('SpeedSetpoint',87);self.edit()
        before=copy.deepcopy(self.app.state());project=self.app.engine.project
        self.assertEqual(installed_memory.table_ids(self.app,router),table_ids)
        self.assertEqual(self.control(),control)
        self.assertEqual(self.read_value(),bytes.fromhex('cc000000')+struct.pack('<i',87))
        self.assertEqual(self.send(bytes.fromhex('4f02206a2401')+struct.pack('<IH',0,4)),
            bytes.fromhex('cf000000')+struct.pack('<i',87))
        symbol=next(s for s in router.symbols() if s.get('ref','').casefold()=='speedsetpoint')
        fields=router.symbol_attributes(symbol);cell=router.scalar_storage().by_ref['speedsetpoint']
        self.assertEqual(fields[3],struct.pack('<I',cell.value_address))
        self.assertEqual(fields[12],struct.pack('<I',table_ids['speedsetpoint']))
        self.assertIs(self.app.engine.memory.project,project)
        for key in ('tags','scan','ms','routines','controller','routine_edits'):
            self.assertEqual(self.app.state()[key],before[key])
        self.app.engine.memory.write('SpeedSetpoint',-12)
        self.assertEqual(self.read_value()[4:],struct.pack('<i',-12))

    def test_repeated_edits_rebind_immutable_views_without_rewriting_the_previous_installation(self):
        self.installed();original=self.app.engine.installed_download.tag_bindings
        self.edit();first=self.app.engine.installed_download.tag_bindings;first_engine=self.app.engine
        self.edit(region='43');current=self.app.engine.installed_download
        self.assertEqual((original.revision,first.revision,current.tag_bindings.revision),(0,1,2))
        self.assertIs(first.project,first_engine.project);self.assertIsNot(first.project,current.project)
        self.assertIs(first.rows,current.tag_bindings.rows)
        with self.assertRaises(ImageError):first.check(self.app,current)
        self.assertEqual(self.read_value()[2],0)

    def test_changed_tag_shape_access_and_initial_source_revoke_the_view(self):
        self.installed();self.edit();project=self.app.engine.project;tag=project.tags['speedsetpoint']
        for name,value in (('dtype','BOOL'),('constant',True),('external_access','None'),('value',999)):
            old=getattr(tag,name);setattr(tag,name,value)
            try:
                with self.subTest(name=name),self.assertRaises(ImageError):
                    installed_memory.table_ids(self.app,self.endpoint.router)
            finally:setattr(tag,name,old)
        project.initial['speedsetpoint']=999
        self.assertEqual(self.read_value()[2],12)

    def test_altered_committed_symbol_header_and_value_handle_cannot_return_forged_data(self):
        self.installed();self.edit();ns=self.app.engine.installed_download.namespace
        stage=ns._incremental;original=stage._headers
        headers=dict(original);row=dict(headers[0x6B,0,1]);row[6]=bytes(4)
        headers[0x6B,0,1]=tuple(sorted(row.items()));stage._headers=MappingProxyType(headers)
        self.assertEqual(self.control()[2],12);self.assertEqual(self.read_value()[2],12)
        stage._headers=original;handles=ns._tables
        ns._tables=tuple(replace(h,value_address=h.value_address+1) if h.value_address==VALUE_BASE else h for h in handles)
        self.assertEqual(self.read_value()[2],12);ns._tables=handles
        self.assertEqual(self.read_value()[2],0)

    def test_missing_view_and_foreign_identity_reject_instead_of_falling_back_to_symbol_ids(self):
        self.installed();self.edit();engine=self.app.engine;installed=engine.installed_download
        engine.installed_download=replace(installed,tag_bindings=None)
        self.assertEqual(self.read_value()[2],12);self.assertEqual(self.control()[2],12)
        self.assertEqual(self.send(bytes.fromhex('4b02206a2400'))[2],12)
        engine.installed_download=installed;identity=self.app.native_project_identity
        self.app.native_project_identity=replace(identity,source_acd_sha256='b'*64)
        self.assertEqual(self.read_value()[2],12)

    def test_tag_reads_do_not_require_stale_routine_components_or_an_edit_source_cache(self):
        self.installed();self.edit();engine=self.app.engine;engine.project.runtime_native_sources=()
        with self.assertRaises(ImageError):routine_read.source(self.app,2,1)
        engine.fault='failed scan'
        self.assertEqual(self.read_value()[2],0)
        self.assertEqual(self.control()[4:],bytes.fromhex('78563412'))
        self.assertEqual(engine.scan_count,0)


class EditedConstantBindingTests(TagEditFixture,source.wire.logs.NamespaceFixture,unittest.TestCase):
    setUp=constants.InstalledConstantTests.setUp
    installed=constants.InstalledConstantTests.installed

    def test_constant_keeps_verified_read_only_table_storage_after_an_edit(self):
        self.installed();self.edit();before=copy.deepcopy(self.app.state())
        self.assertEqual(installed_memory.read_constant(self.app,self.endpoint.router,'speedsetpoint'),bytes(4))
        self.assertEqual(self.send(bytes.fromhex('4f02206a2401000000000400')),bytes.fromhex('cf000000')+bytes(4))
        self.assertEqual(self.send(bytes.fromhex('0e03206b2401300b')),bytes.fromhex('8e00000001'))
        self.assertNotEqual(self.read_value()[2],0)
        self.assertNotEqual(self.send(bytes.fromhex('4d02206b2401c400010005000000'))[2],0)
        for field in ('tags','scan','ms','controller','routines','routine_edits'):
            self.assertEqual(self.app.state()[field],before[field])

    def test_corrupted_constant_value_is_not_served_as_a_valid_source_constant(self):
        self.installed();self.edit();self.app.engine.memory.values['speedsetpoint']=123
        with self.assertRaises(ImageError):installed_memory.read_constant(self.app,self.endpoint.router,'speedsetpoint')
        self.assertEqual(self.send(bytes.fromhex('4f02206a2401000000000400'))[2],12)


if __name__=='__main__':unittest.main()
