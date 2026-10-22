"""Pure simulator epochs, detached edits and in-memory native route stubs."""
import collections
import contextlib
import copy
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock,patch
from xml.etree import ElementTree as E

from logixlab.change_detection import ChangeDetection,UINT64_MAX
from logixlab.ethernetip import Router,Session,CIPError
from logixlab.model import Project,ModelError
from logixlab.runtime import Engine
from logixlab.server import Application
from logixlab.routine_edits import prepare
from logixlab.routine_source import decode
from tools.collection_inventory import decode_attribute_list
from test_routine_source import container,xml_source


class ChangeDetectionTests(unittest.TestCase):
    def value(self,state,sha='a'*64):return int.from_bytes(state.attributes(sha)[27],'little')

    def state(self,mask=UINT64_MAX,seed=99):
        with patch('logixlab.change_detection.secrets.randbits',return_value=seed):
            return ChangeDetection('a'*64,mask)

    def test_explicit_source_mask_generates_one_stable_little_endian_value_including_zero(self):
        for seed in (0,99,1<<63,UINT64_MAX):
            state=self.state(seed=seed)
            self.assertEqual(state.attributes('a'*64),{27:struct.pack('<Q',seed)})
            self.assertEqual(self.value(state),seed);self.assertEqual(state.attributes('b'*64),{})
        with patch('logixlab.change_detection.secrets.randbits') as random:
            self.assertEqual(ChangeDetection('a'*64,None).attributes('a'*64),{});random.assert_not_called()

    def test_missing_invalid_masks_and_source_digests_cannot_generate_values(self):
        for mask in (-1,True,1<<64,'0',0.0):
            with self.subTest(mask=mask),self.assertRaises(ValueError):self.state(mask)
        for sha in ('',None,'a'*63,'G'*64,'A'*64):
            with self.assertRaises(ValueError):ChangeDetection(sha,0)
        state=self.state(None)
        self.assertFalse(state.record('remote_mode'));self.assertFalse(state.description()['audit_value_available'])

    def test_zero_mask_still_has_initial_epoch_but_masked_events_do_not_update(self):
        state=self.state(0)
        for event in ('remote_mode','routine_transaction'):
            self.assertFalse(state.record(event));self.assertEqual(self.value(state),99)
        self.assertEqual(state.description()['updates'],0)

    def test_exact_mode_and_transaction_bits_include_high_word_without_double_updates(self):
        for bit in (2,13,32):
            state=self.state(1<<bit)
            event='remote_mode' if bit==13 else 'routine_transaction'
            other='routine_transaction' if bit==13 else 'remote_mode'
            self.assertFalse(state.record(other));self.assertTrue(state.record(event));self.assertEqual(self.value(state),100)
        state=self.state((1<<2)|(1<<32));self.assertTrue(state.record('routine_transaction'))
        self.assertEqual(state.description()['updates'],1)
        for bit in (0,1,14,15,16,31,33,63):
            state=self.state(1<<bit)
            self.assertFalse(state.record('remote_mode'));self.assertFalse(state.record('routine_transaction'))

    def test_wrap_does_not_reuse_a_value_before_exhaustion_and_exhaustion_withholds(self):
        state=self.state(seed=UINT64_MAX);self.assertTrue(state.record('remote_mode'));self.assertEqual(self.value(state),0)
        state._updates=UINT64_MAX
        self.assertFalse(state.record('remote_mode'));self.assertEqual(state.attributes('a'*64),{})
        self.assertTrue(state.description()['invalidated'])

    def test_fault_invalidation_is_sticky_and_unknown_events_do_not_mutate(self):
        state=self.state();before=state.attributes('a'*64)
        with self.assertRaises(ValueError):state.record('major_fault')
        self.assertEqual(state.attributes('a'*64),before)
        state.invalidate();self.assertFalse(state.record('remote_mode'));self.assertEqual(state.attributes('a'*64),{})

    def test_description_and_representation_omit_values_masks_and_source_hashes(self):
        state=self.state(seed=0x123456789abcdef);state.record('remote_mode')
        report=json.dumps(state.description())+repr(state)
        for private in ('a'*64,str(0x123456789abcdef),str(UINT64_MAX),'data_hex','audit_value_hex'):
            self.assertNotIn(private,report)
        self.assertEqual(state.description()['supported_event_bits'],{'remote_mode':[13],'routine_transaction':[2,32]})
        self.assertFalse(state.description()['native_value_generator'])


class ChangeDetectionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'controller.L5X'
        root=E.parse(Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').getroot()
        controller=root.find('Controller')
        E.SubElement(controller,'Security',Code='0',ChangesToDetect='16#ffff_ffff_ffff_ffff')
        E.ElementTree(root).write(self.path,encoding='utf8',xml_declaration=True)
        with patch('logixlab.change_detection.secrets.randbits',return_value=123):
            self.engine=Engine(Project(self.path),defer_prescan=True)
        # No Application constructor, socket, scan worker or native process.
        self.app=Application.__new__(Application)
        self.app.engine=self.engine;self.app.endpoint=None;self.app.generation=7
        self.app.running=False;self.app._closed=False;self.app.busy=False
        self.app.scan_interval_ms=10;self.app._scan_epoch=0;self.app._scan_thread=object()
        self.app._scan_condition=NS(notify_all=Mock());self.app._io_dirty=False
        self.app.allow_routine_edits=True
        self.app.native_project_identity=NS(source_l5x_sha256=self.engine.project.sha256)
        self.endpoint=NS(native_read_only=False,lock=contextlib.nullcontext(),
            record_attribute_gap=Mock(),record_native_rejection=Mock(),record=Mock(),counts=collections.Counter())
        self.router=Router(self.app,self.endpoint)

    def value(self,engine=None):
        engine=engine or self.app.engine
        return engine.change_detection.attributes(engine.project.sha256).get(27)

    def test_scans_tag_writes_reads_and_prescan_do_not_advance_audit_value(self):
        before=self.path.read_bytes();value=self.value()
        self.engine.memory.write('StartPB',True);self.engine.enter_run();self.engine.step(10)
        self.assertEqual(self.value(),value);self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.engine.change_detection.description()['updates'],0)

    def test_shared_mode_control_tracks_only_successful_requested_transitions(self):
        before=self.value();self.app.set_controller_mode('Run',remote_request=True)
        changed=self.value();self.assertNotEqual(changed,before)
        self.app.set_controller_mode('Run',remote_request=True);self.app.set_controller_mode('Run',20,remote_request=True)
        self.assertEqual(self.value(),changed)
        self.app.set_controller_mode('Program',remote_request=True);self.assertNotEqual(self.value(),changed)
        self.assertEqual(self.engine.change_detection.description()['updates'],2)
        self.app.set_controller_mode('Run');self.app.set_controller_mode('Program')
        self.assertEqual(self.engine.change_detection.description()['updates'],2)
        for mode,dt in (('Invalid',None),('Run',0),('Run',True)):
            before=self.value()
            with self.assertRaises(ModelError):self.app.set_controller_mode(mode,dt,remote_request=True)
            self.assertEqual(self.value(),before)

    def test_unclassified_fault_withholds_value_and_clearing_fault_does_not_restore_unknown_history(self):
        self.engine.fault='Unclassified interpreter failure'
        self.assertIsNone(self.value())
        with self.assertRaises(ModelError):self.app.set_controller_mode('Run',remote_request=True)
        self.engine.fault='';self.assertIsNone(self.value())
        replacement=Engine(self.engine.project,defer_prescan=True)
        self.assertIn(27,replacement.change_detection.attributes(replacement.project.sha256))

    def test_failed_run_entry_rolls_back_values_and_invalidates_without_recording_a_mode_change(self):
        before=copy.deepcopy(self.engine.memory.values)
        def fail():
            self.engine.memory.write('SpeedSetpoint',123)
            raise ModelError('Prescan test failure')
        with patch.object(self.engine,'_prescan',side_effect=fail),self.assertRaises(ModelError):
            self.app.set_controller_mode('Run',remote_request=True)
        self.assertFalse(self.app.running);self.assertEqual(self.engine.memory.values,before)
        self.assertIsNone(self.value());self.assertEqual(self.engine.change_detection.description()['updates'],0)

    def test_in_memory_controller_single_list_reads_and_write_rejections_use_live_epoch(self):
        value=self.value();session=Session()
        self.assertEqual(self.router.dispatch(bytes.fromhex('0e03208e2401301b'),session),(0,value))
        raw=bytes.fromhex('0302208e2401')+struct.pack('<6H',5,27,28,27,33,11)
        status,payload=self.router.dispatch(raw,session)
        rows=decode_attribute_list(bytes((0x83,0,status,0))+payload,[27,28,27,33,11],0x8e,include_payloads=True)['attributes']
        self.assertEqual([row['status'] for row in rows],[0,0,0,20,20]);self.assertEqual(rows[0],rows[2])
        self.app.set_controller_mode('Run',remote_request=True)
        self.assertNotEqual(self.router.dispatch(bytes.fromhex('0e03208e2401301b'),session)[1],value)
        for service in (4,16):
            with self.assertRaises(CIPError):self.router.dispatch(bytes((service,3))+bytes.fromhex('208e2401301b')+bytes(8),session)
        self.engine.fault='Unclassified'
        with self.assertRaises(CIPError) as error:self.router.dispatch(bytes.fromhex('0e03208e2401301b'),session)
        self.assertEqual(error.exception.status,20)

    def test_native_mode_handler_uses_shared_state_without_starting_a_worker(self):
        self.endpoint.programming_lease=NS(require_owner=Mock())
        native=NS(stage='bound');before=self.value()
        def send(raw):return self.router.native_read(bytes.fromhex(raw),Session(),native,0,500,None,registration=False)
        self.assertEqual(send('0602208e2401'),bytes.fromhex('86000000'))
        self.assertTrue(self.app.running);self.assertNotEqual(self.value(),before)
        self.assertEqual(send('0702208e2401'),bytes.fromhex('87000000'))
        self.assertFalse(self.app.running);self.assertEqual(self.engine.change_detection.description()['updates'],2)
        self.assertEqual(self.endpoint.counts,{'native_mode_run':1,'native_mode_program':1})

    def test_detached_routine_candidate_copies_audit_epoch_without_mutating_original(self):
        self.engine.change_detection.record('remote_mode');before=self.value()
        source=decode(container(E.tostring(xml_source(text='NOP();'))))
        candidate,_=prepare(self.engine,source,('NOP();',),'MainProgram',0)
        self.assertEqual(self.value(candidate),before)
        self.assertIsNot(candidate.change_detection,self.engine.change_detection)
        candidate.change_detection.record('routine_transaction')
        self.assertNotEqual(self.value(candidate),before);self.assertEqual(self.value(),before)

    def test_native_commit_updates_once_and_retransmission_does_not_update_or_reapply(self):
        source=NS(name='MainRoutine');clear=Mock()
        stage=NS(target=(300,700),source=source,base_revision=0,translated_rungs=('NOP();',),
            program_released=True,ready=lambda:True,clear=clear)
        lease=NS(require_edit_owner=Mock(),edit_phase_open=True,program_reservations=set(),
            applied_edit=None,edit_transfer=stage)
        self.endpoint.programming_lease=lease;self.app.native_symbols=None
        self.app.native_routines=None;self.app.native_types=None
        self.router.source_bound_program=lambda _:dict(name='MainProgram')
        self.router.zero_program_stack_supported=lambda _:True
        self.router.routines=lambda _:[dict(id=700,name='MainRoutine')]
        candidate=copy.copy(self.engine);candidate.change_detection=copy.deepcopy(self.engine.change_detection)
        before=self.value();native=NS(stage='bound')
        raw=bytes.fromhex('5902208e2401')+bytes(4)
        def send():return self.router.native_read(raw,Session(),native,0,500,None,registration=False)
        receipt=dict(applied=True)
        with patch('logixlab.routine_source.resolve',return_value=('NOP();',)),patch('logixlab.routine_edits.prepare',return_value=(candidate,receipt)) as planner:
            self.assertEqual(send(),bytes.fromhex('d9000000'))
            self.assertIs(self.app.engine,candidate)
            self.assertNotEqual(candidate.change_detection.attributes(self.engine.project.sha256)[27],before)
            self.assertEqual(send(),bytes.fromhex('d9000000'));planner.assert_called_once()
        self.assertEqual(candidate.change_detection.description()['updates'],1)
        self.assertEqual(self.value(self.engine),before);clear.assert_called_once()

    def test_rejected_native_requests_and_stale_source_never_advance_or_return_audit_values(self):
        self.endpoint.programming_lease=NS(require_owner=Mock())
        native=NS(stage='bound');before=self.value()
        self.app.native_project_identity.source_l5x_sha256='b'*64
        rejected=self.router.native_read(bytes.fromhex('0602208e2401'),Session(),native,0,500,None,registration=False)
        self.assertEqual(rejected[2],12);self.assertEqual(self.value(),before);self.assertFalse(self.app.running)
        self.engine.project.sha256='b'*64
        with self.assertRaises(CIPError) as error:self.router.dispatch(bytes.fromhex('0e03208e2401301b'),Session())
        self.assertEqual(error.exception.status,20)


if __name__=='__main__':unittest.main()
