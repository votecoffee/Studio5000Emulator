"""Opaque Symbol Control readback is source-bound and never sets model flags."""
import copy
import struct
import unittest
from types import MappingProxyType

import test_routine_read as routines
import test_download_changelog as logs


class InstalledSymbolControlTests(logs.NamespaceFixture,unittest.TestCase):
    setUp=routines.RoutineReadWireTests.setUp
    complete_tasks=routines.RoutineReadWireTests.complete_tasks
    configure=routines.RoutineReadWireTests.configure
    ready_setup=routines.RoutineReadWireTests.ready_setup
    ready_routines=routines.RoutineReadWireTests.ready_routines
    next_routines=routines.RoutineReadWireTests.next_routines
    ready_map=routines.RoutineReadWireTests.ready_map
    ready_log=routines.RoutineReadWireTests.ready_log
    proposal=routines.RoutineReadWireTests.proposal
    ready_install=routines.RoutineReadWireTests.ready_install
    installed=routines.RoutineReadWireTests.installed

    def control(self):return self.send(bytes.fromhex('0e03206b24013006'))

    def test_committed_control_readback_preserves_model_flags_values_and_addresses(self):
        self.assertEqual(self.control(),bytes.fromhex('8e00000000000000'))
        self.installed();before=copy.deepcopy(self.app.state());router=self.endpoint.router
        symbol=next(s for s in router.symbols() if s.get('ref','').casefold()=='speedsetpoint')
        cell=router.scalar_storage().by_ref['speedsetpoint']
        self.assertEqual(self.control(),bytes.fromhex('8e00000078563412'))
        fields=router.symbol_attributes(symbol)
        self.assertEqual(fields[3],struct.pack('<I',cell.value_address))
        self.assertEqual(fields[5],struct.pack('<I',cell.symbol_address))
        self.assertEqual(fields[12],struct.pack('<I',cell.instance))
        for key in ('tags','routines','scan','ms','controller','routine_edits'):
            self.assertEqual(before[key],self.app.state()[key])
        self.app.engine.memory.write('SpeedSetpoint',37)
        self.assertEqual(self.control(),bytes.fromhex('8e00000078563412'))
        self.assertEqual(self.app.engine.memory.read('SpeedSetpoint'),37)

    def test_changed_effect_record_is_rejected_instead_of_serving_forged_control(self):
        self.installed();stage=self.app.engine.installed_download.namespace._incremental
        records=dict(stage._headers);values=dict(records[0x6B,0,1]);values[6]=bytes(4)
        records[0x6B,0,1]=tuple(sorted(values.items()));stage._headers=MappingProxyType(records)
        self.assertEqual(self.control()[2],12)

    def test_changed_type_or_source_binding_revokes_original_control(self):
        self.installed();router=self.endpoint.router
        symbol=next(s for s in router.symbols() if s.get('ref','').casefold()=='speedsetpoint')
        from logixlab.ethernetip import CIPError
        with self.assertRaises(CIPError):router.installed_symbol_control({**symbol,'type':0xC1})
        original=self.app.native_project_identity;self.app.native_project_identity=None
        self.assertEqual(self.control()[2],12);self.app.native_project_identity=original
        self.assertEqual(self.control()[2],0)

    def test_uncommitted_control_stays_modeled_and_forged_edit_revision_is_rejected(self):
        self.ready_install();self.assertEqual(self.control()[4:],bytes(4))
        self.assertEqual(self.send(logs.COMMIT)[2],0)
        self.app.engine.project.runtime_revision=1
        self.assertEqual(self.control()[2],12)


if __name__=='__main__':unittest.main()
