"""Current RLL state follows verified edit source without exposing stale keys."""
import copy
from dataclasses import replace
import struct
from types import SimpleNamespace
import unittest

from logixlab import routine_state
from logixlab.ethernetip import logical
from tools.collection_inventory import decode_attribute_list
from tools.upload_inventory import logical_path
import test_accepted_routine_source as sources

BULK=(1,2,8,*range(9,25),26,27,28)
ZEROS=(2,*range(10,22),23,26,27,28)


class EditedRoutineMetadataTests(sources.wire.logs.NamespaceFixture,unittest.TestCase):
    setUp=sources.AcceptedRoutineSourceTests.setUp
    installed=sources.AcceptedRoutineSourceTests.installed
    complete_tasks=sources.AcceptedRoutineSourceTests.complete_tasks
    configure=sources.AcceptedRoutineSourceTests.configure
    ready_setup=sources.AcceptedRoutineSourceTests.ready_setup
    ready_routines=sources.AcceptedRoutineSourceTests.ready_routines
    next_routines=sources.AcceptedRoutineSourceTests.next_routines
    ready_map=sources.AcceptedRoutineSourceTests.ready_map
    ready_log=sources.AcceptedRoutineSourceTests.ready_log
    proposal=sources.AcceptedRoutineSourceTests.proposal
    ready_install=sources.AcceptedRoutineSourceTests.ready_install
    edit=sources.AcceptedRoutineSourceTests.edit

    def attribute(self,number,routine=1):
        path=logical_path(0x6D,routine,program=2)+bytes((0x30,number))
        return self.send(bytes((14,len(path)//2))+path)

    def revision(self,parent=None):
        path=logical_path(0x6D,0,program=parent)+b'\x30\1'
        return self.send(bytes((14,len(path)//2))+path)

    def bulk(self,routine=1):
        path=logical_path(0x6D,routine,program=2)
        raw=self.send(bytes((3,len(path)//2))+path+struct.pack('<'+'H'*(len(BULK)+1),len(BULK),*BULK))
        return decode_attribute_list(raw,BULK,0x6D,include_payloads=True)

    def labels(self,routine=1):
        path=logical_path(0x6D,routine,program=2)+logical(0x20,0x8C)+logical(0x24,0)
        return self.send(bytes((0x4B,len(path)//2))+path)

    def test_schema_and_clean_bulk_state_keep_pinned_configuration_keys_after_plain_logic_edit(self):
        self.installed();original_keys={n:self.attribute(22,routine=n) for n in (1,2)};old,_=self.edit()
        before=copy.deepcopy(self.app.state());project=self.app.engine.project
        for parent in (None,2):self.assertEqual(self.revision(parent),b'\x8e\0\0\0\x0b\0')
        for instance,key in ((1,'mainprogram/mainroutine'),(2,'mainprogram/reporting')):
            decoded=self.bulk(instance);rows=decoded['attributes']
            fields={r['attribute']:bytes.fromhex(r['data_hex']) for r in rows if not r['status']}
            self.assertEqual([r['attribute'] for r in rows if r['status']],[])
            self.assertTrue(all(not any(fields[n]) for n in ZEROS))
            self.assertEqual(int.from_bytes(fields[9],'little'),instance)
            self.assertEqual(int.from_bytes(fields[24],'little'),0 if instance==1 else 2)
            address=int.from_bytes(fields[8],'little')
            self.assertIs(self.app.engine.runtime_references.resolve(project,address,'routine'),project.routines[key])
            self.assertIsNone(old.runtime_references.resolve(old.project,address,'routine'))
        for instance in (1,2):self.assertEqual(self.attribute(22,routine=instance),original_keys[instance])
        for field in ('tags','scan','ms','routines','controller','routine_edits'):
            self.assertEqual(self.app.state()[field],before[field])

    def test_source_key_pins_original_catalog_and_does_not_serve_replacement_metadata(self):
        from logixlab.native_routines import NativeRoutines
        self.installed();expected=self.attribute(22);self.edit();original=self.app.native_routines
        rows=[row.manifest() for row in original.rows];rows[0]['source_key_hex']='0008'+'42'*64
        self.app.native_routines=NativeRoutines(original.source_acd_sha256,original.source_l5x_sha256,rows)
        self.assertEqual(self.attribute(22)[2],0x14)
        self.app.native_routines=original;self.assertEqual(self.attribute(22),expected)

    def test_missing_original_snapshot_withholds_key_while_current_edited_state_still_verifies(self):
        self.installed();self.edit();engine=self.app.engine
        engine.installed_download=replace(engine.installed_download,routine_sources=None)
        self.assertEqual(self.attribute(10)[2],0)
        self.assertEqual(self.attribute(22)[2],0x14)

    def test_repeated_plain_edits_keep_the_same_key_without_bypassing_source_checks(self):
        self.installed();expected=self.attribute(22);self.edit(region='42');self.edit(region='43')
        self.assertEqual(self.attribute(22),expected)
        self.app.engine.project.runtime_native_sources=()
        self.assertEqual(self.attribute(22)[2],0x14)

    def test_corrupted_edit_source_revokes_its_state_and_complete_schema_without_hiding_untouched_state(self):
        self.installed();self.edit();project=self.app.engine.project;record=project.runtime_native_sources[0]
        project.runtime_native_sources=(replace(record,data=record.data+b'X'),)
        self.assertEqual(self.attribute(10)[2],0x14);self.assertEqual(self.attribute(9)[2],0)
        self.assertEqual(self.attribute(10,routine=2)[2],0)
        self.assertEqual(self.revision(),b'\x8e\0\0\0\1\0')
        self.assertEqual(self.labels()[2],12)

    def test_live_reservation_revokes_state_for_both_routines_but_keeps_verified_schema(self):
        self.installed();self.edit();lease=self.endpoint.programming_lease
        owner=SimpleNamespace(stage='bound',key=b'test',deadline=lease.clock()+300)
        generation=self.app.generation;sha=self.app.engine.project.sha256
        lease.acquire(owner,generation,sha,selector=1);lease.reserve_program(owner,generation,sha,2)
        try:
            for instance in (1,2):
                self.assertEqual(self.attribute(10,instance)[2],0x14)
                self.assertEqual(self.attribute(9,instance)[2],0)
                self.assertEqual(self.labels(instance)[2],12)
            self.assertEqual(self.revision(),b'\x8e\0\0\0\x0b\0')
        finally:lease.clear()
        self.assertEqual(self.attribute(10)[2],0)

    def test_fault_history_still_withholds_edit_state_after_a_verified_source_edit(self):
        self.installed();self.edit();self.app.engine.fault='failed scan'
        for number in ZEROS:self.assertEqual(self.attribute(number)[2],0x14)
        self.assertEqual(self.attribute(9)[2],0)
        self.app.engine.fault=''
        self.assertEqual(self.attribute(10)[2],0x14)

    def test_empty_label_discovery_uses_current_source_for_edited_and_untouched_routines(self):
        self.installed();self.edit()
        self.assertEqual(self.labels(),b'\xcb\0\0\0')
        self.assertEqual(self.labels(2),b'\xcb\0\0\0')
        self.app.engine.project.runtime_native_sources=()
        self.assertEqual(self.labels()[2],12);self.assertEqual(self.labels(2)[2],0)

    def test_source_proof_cannot_be_reused_for_another_scope_or_engine(self):
        self.installed();old,_=self.edit();engine=self.app.engine
        self.assertFalse(routine_state.current_source(self.app,old,'MainProgram','MainRoutine',(2,1)))
        self.assertFalse(routine_state.current_source(self.app,engine,'MainProgram','MainRoutine',(2,2)))
        for target in (None,[2,1],(True,1),(2,3)):
            self.assertFalse(routine_state.current_source(self.app,engine,'MainProgram','MainRoutine',target))
        self.assertEqual(routine_state.attributes(engine,'MainProgram','MainRoutine',source_sha256=engine.project.sha256,
            idle=True,type_bound=True),{})


if __name__=='__main__':unittest.main()
