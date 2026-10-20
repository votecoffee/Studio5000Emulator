"""Observed preparation exchanges have real ownership and zero-stack guards."""
import base64
import copy
from pathlib import Path
import struct
import unittest
from xml.etree import ElementTree as E

from logixlab.model import ModelError
from logixlab.programming_lease import LeaseError
import test_program_reservations as reservations
import test_programming_lease as leases

OPEN=bytes.fromhex('5502208e2401')
CLOSE=bytes.fromhex('5702208e2401')
STACK=bytes.fromhex('0403206825002c0101001b0000000000')
READ_STACK=bytes.fromhex('0e04206825002c01301b')


class EditPreparationModelTests(unittest.TestCase):
    setUp=leases.ProgrammingLeaseModelTests.setUp
    context=leases.ProgrammingLeaseModelTests.context

    def test_phase_and_zero_stack_require_edit_owner_phase_and_program_hold(self):
        for selector in (0,1):
            self.lease.acquire(self.first,1,'a'*64,selector=selector)
            if selector==0:
                with self.assertRaises(LeaseError):self.lease.open_edit_preparation(self.first,1,'a'*64)
                self.lease.release(self.first,1,'a'*64);continue
            with self.assertRaises(LeaseError):self.lease.prepare_zero_program_stack(self.first,1,'a'*64,300,0)
            for owner in (self.second,None):
                with self.assertRaises(LeaseError):self.lease.open_edit_preparation(owner,1,'a'*64)
            self.lease.open_edit_preparation(self.first,1,'a'*64)
            self.lease.open_edit_preparation(self.first,1,'a'*64)
            with self.assertRaises(LeaseError):self.lease.prepare_zero_program_stack(self.first,1,'a'*64,300,0)
            self.lease.reserve_program(self.first,1,'a'*64,300)
            for value in (True,False,1,-1,'0',None):
                with self.assertRaises(LeaseError):self.lease.prepare_zero_program_stack(self.first,1,'a'*64,300,value)
            self.lease.prepare_zero_program_stack(self.first,1,'a'*64,300,0)
            self.lease.open_edit_preparation(self.first,1,'a'*64)
            self.assertEqual(self.lease.program_stack_preparations,{300:0})
            with self.assertRaises(LeaseError):self.lease.close_edit_preparation(self.first,1,'a'*64)
            self.assertTrue(self.lease.edit_phase_open)
            self.lease.release_program(self.first,1,'a'*64,300)
            self.assertEqual(self.lease.program_stack_preparations,{})
            self.assertTrue(self.lease.scan_inhibited(1,'a'*64))
            self.assertEqual(self.lease.inhibit(1,'a'*64),0)
            self.lease.close_edit_preparation(self.first,1,'a'*64)
            self.lease.close_edit_preparation(self.first,1,'a'*64)
            self.assertFalse(self.lease.scan_inhibited(1,'a'*64))


class EditPreparationWireTests(unittest.TestCase):
    setUp=reservations.ProgramReservationTests.setUp
    tearDown=reservations.ProgramReservationTests.tearDown
    cip=reservations.ProgramReservationTests.cip
    begin=reservations.ProgramReservationTests.begin
    signed=reservations.ProgramReservationTests.signed
    bind=reservations.ProgramReservationTests.bind
    prepare=reservations.ProgramReservationTests.prepare
    send=reservations.ProgramReservationTests.send

    def ready(self):
        self.prepare();self.assertEqual(self.send(reservations.CONTROLLER_ACQUIRE)[2],0)

    def test_observed_exchange_stages_only_zero_stack_and_preserves_active_model(self):
        self.ready();before=copy.deepcopy(self.app.state())
        self.assertEqual(self.send(OPEN),bytes.fromhex('d5000000'))
        with self.assertRaises(ModelError):self.app.command('controller-mode',{'mode':'Run'})
        self.assertEqual(self.send(reservations.message())[2],0)
        self.assertEqual(self.send(STACK),bytes.fromhex('8400000001001b000000'))
        self.assertEqual(self.send(READ_STACK),bytes.fromhex('8e00000000000000'))
        edit=self.endpoint.state()['native_programming_lease']['edit_preparation']
        self.assertEqual((edit['status'],edit['program_stack_preparations']),('open',1))
        for key in ('active_changes','accepted','testing','assembled','commit','active_stack_changed'):
            self.assertFalse(edit[key])
        for key in ('tags','routines','tasks','scan','ms','controller'):
            self.assertEqual(self.app.state()[key],before[key])
        self.assertEqual(self.send(CLOSE)[2],12)
        self.assertEqual(self.send(reservations.message(0x4C,payload=b''))[2],0)
        self.assertEqual(self.send(CLOSE),bytes.fromhex('d7000000'))
        self.assertFalse(self.endpoint.state()['native_programming_lease']['scan_inhibited'])
        self.assertEqual(self.send(reservations.CONTROLLER_RELEASE)[2],0)

    def test_phase_requires_bound_owner_current_source_program_mode_and_empty_payload(self):
        self.prepare()
        for raw in (OPEN,CLOSE):
            self.assertEqual(self.cip(raw)[2],8)
            self.assertEqual(self.send(raw)[2],15)
        self.send(reservations.CONTROLLER_ACQUIRE[:-1]+b'\0')
        self.assertEqual(self.send(OPEN)[2],15)
        self.send(reservations.CONTROLLER_RELEASE);self.send(reservations.CONTROLLER_ACQUIRE)
        for raw,status in ((OPEN+b'x',21),(OPEN[:5]+b'\2',5),
                           (bytes.fromhex('5503208e24013001'),4)):
            self.assertEqual(self.send(raw)[2],status)
        self.app.command('controller-mode',{'mode':'Run'})
        self.assertEqual(self.send(OPEN)[2],12)
        self.app.command('controller-mode',{'mode':'Program'})
        self.app.native_project_identity=None
        self.assertEqual(self.send(OPEN)[2],12)

    def test_stack_requires_phase_hold_zero_exact_payload_and_original_program_binding(self):
        self.ready();self.assertEqual(self.send(STACK)[2],12)
        self.send(OPEN);self.assertEqual(self.send(STACK)[2],12)
        self.send(reservations.message())
        for raw,status in ((STACK[:-1],19),(STACK+b'x',21),(STACK[:-4]+struct.pack('<I',1),12),
                           (STACK[:5]+b'\0\x2d\1'+STACK[8:],5),
                           (STACK[:8]+b'\2\0'+STACK[10:],15),
                           (STACK[:10]+b'\x1c\0'+STACK[12:],15)):
            self.assertEqual(self.send(raw)[2],status,(raw.hex(),status))
        self.app.native_symbols=None
        self.assertEqual(self.send(STACK)[2],12)
        self.assertEqual(self.endpoint.programming_lease.program_stack_preparations,{})

    def test_stack_unavailable_when_aoi_absence_or_complete_executable_source_is_unproven(self):
        original=Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X'
        for kind in ('missing','nonempty','protected','incomplete'):
            tree=E.parse(original);root=tree.getroot();controller=root.find('Controller')
            if kind=='missing':controller.remove(controller.find('AddOnInstructionDefinitions'))
            elif kind=='nonempty':E.SubElement(controller.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='Unknown')
            elif kind=='protected':controller.find('./Programs/Program/Routines/Routine').set('Protected','true')
            else:root.set('ContainsContext','true')
            self.app.command('load',{'name':'source.L5X','content':base64.b64encode(E.tostring(root)).decode()})
            from test_ethernetip import Client
            self.client.close();self.client=Client(self.endpoint.port);self.client.register()
            self.ready();self.send(OPEN)
            if kind!='incomplete':self.send(reservations.message())
            with self.subTest(kind=kind):
                self.assertEqual(self.send(READ_STACK)[2],20)
                self.assertEqual(self.send(STACK)[2],12)
            self.send(reservations.CONTROLLER_RELEASE)

    def test_phase_and_stack_clear_on_source_replacement_and_endpoint_stop(self):
        for action in ('source','stop'):
            self.ready();self.send(OPEN);self.send(reservations.message());self.send(STACK)
            if action=='source':self.app.command('demo',{'sample':'ConveyorDemo'})
            else:self.endpoint.stop()
            self.assertFalse(self.endpoint.programming_lease.edit_phase_open)
            self.assertEqual(self.endpoint.programming_lease.program_stack_preparations,{})
            if action=='source':
                from test_ethernetip import Client
                self.client.close();self.client=Client(self.endpoint.port);self.client.register()


if __name__=='__main__':unittest.main()
