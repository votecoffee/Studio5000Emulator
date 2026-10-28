"""Committed Tables need not share Symbol IDs; catalogs, storage and reads agree."""
import struct
import unittest
from types import MappingProxyType
from unittest.mock import patch

from logixlab import installed_memory
from logixlab.download_image import ImageError
import test_download_changelog as logs
import test_installed_symbol_control as control_tests


class InstalledTableIdentityTests(logs.NamespaceFixture,unittest.TestCase):
    setUp=control_tests.InstalledSymbolControlTests.setUp
    complete_tasks=control_tests.InstalledSymbolControlTests.complete_tasks
    configure=control_tests.InstalledSymbolControlTests.configure
    ready_setup=control_tests.InstalledSymbolControlTests.ready_setup
    ready_routines=control_tests.InstalledSymbolControlTests.ready_routines
    next_routines=control_tests.InstalledSymbolControlTests.next_routines
    ready_map=control_tests.InstalledSymbolControlTests.ready_map
    ready_log=control_tests.InstalledSymbolControlTests.ready_log
    proposal=control_tests.InstalledSymbolControlTests.proposal
    ready_install=control_tests.InstalledSymbolControlTests.ready_install
    installed=control_tests.InstalledSymbolControlTests.installed

    def test_mapping_requires_a_committed_verified_source_graph(self):
        self.assertIsNone(installed_memory.table_ids(self.app,self.endpoint.router))
        self.installed()
        self.assertEqual(installed_memory.table_ids(self.app,self.endpoint.router)['speedsetpoint'],1)
        original=self.app.native_project_identity;self.app.native_project_identity=None
        with self.assertRaises(ImageError):installed_memory.table_ids(self.app,self.endpoint.router)
        self.app.native_project_identity=original
        self.app.engine.project.runtime_revision=1
        with self.assertRaises(ImageError):installed_memory.table_ids(self.app,self.endpoint.router)

    def test_changed_header_effect_revokes_table_identity_instead_of_guessing(self):
        self.installed();stage=self.app.engine.installed_download.namespace._incremental
        rows=dict(stage._headers);values=dict(rows[0x6B,0,1]);values[6]=bytes(4)
        rows[0x6B,0,1]=tuple(sorted(values.items()));stage._headers=MappingProxyType(rows)
        with self.assertRaises(ImageError):installed_memory.table_ids(self.app,self.endpoint.router)

    def test_independent_symbol_table_ids_agree_in_descriptors_catalog_and_value_read(self):
        # The admission gate is tested above; vary its admitted ID to exercise
        # actual wire consumers without importing private native fixtures.
        self.app.engine.memory.write('SpeedSetpoint',87)
        with patch.object(installed_memory,'table_ids',return_value={'speedsetpoint':17}):
            self.assertEqual(self.send(bytes.fromhex('0e03206b2401300c')),bytes.fromhex('8e00000011000000'))
            self.assertEqual(self.send(bytes.fromhex('4b02206a2400')),bytes.fromhex('cb00000011000000'))
            result=self.send(bytes.fromhex('4f02206a2411')+struct.pack('<IH',0,4))
            self.assertEqual(result,bytes.fromhex('cf000000')+struct.pack('<i',87))
            cell=self.endpoint.router.scalar_storage().by_ref['speedsetpoint']
            self.assertEqual((cell.symbol_id,cell.instance),(1,17))
            self.assertEqual(cell.header()[16:20],struct.pack('<I',17))
            self.assertEqual(cell.symbol_header()[12:16],struct.pack('<I',1))
            self.assertEqual(self.send(bytes.fromhex('0e03206a24013002'))[2],5)

    def test_mapping_change_rebuilds_storage_even_when_symbol_identity_is_unchanged(self):
        with patch.object(installed_memory,'table_ids',return_value={'speedsetpoint':17}):
            before=self.endpoint.router.scalar_storage()
        with patch.object(installed_memory,'table_ids',return_value={'speedsetpoint':23}):
            after=self.endpoint.router.scalar_storage()
        self.assertIsNot(before,after)
        self.assertEqual(after.by_ref['speedsetpoint'].instance,23)
        self.assertEqual(after.by_ref['speedsetpoint'].symbol_id,1)

    def test_missing_admitted_root_is_unavailable_without_symbol_id_fallback(self):
        with patch.object(installed_memory,'table_ids',return_value={'foreign':17}):
            self.assertEqual(self.send(bytes.fromhex('0e03206b2401300c'))[2],12)
