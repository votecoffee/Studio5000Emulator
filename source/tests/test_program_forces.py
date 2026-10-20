"""Source absence checks and exact native SFC status without force operations."""
import base64
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint, Session, logical
from logixlab.native_symbols import NativeSymbols
from logixlab.program_forces import ProgramForces
from logixlab.server import Application


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = bytes.fromhex('8300000003000f000000000018000000000000001900000000000000')
QUERY = bytes.fromhex('03022068240003000f0018001900')


def source():
    root = E.fromstring((ROOT/'samples/ConveyorDemo.L5X').read_bytes())
    return root, root.find('Controller')


class ProgramForceTests(unittest.TestCase):
    def test_non_sfc_source_yields_uint_and_null_address_fields(self):
        root, controller = source()
        forces = ProgramForces.from_source(root, controller)
        self.assertEqual(forces.attributes(), {15:bytes(2),24:bytes(4),25:bytes(4)})
        self.assertEqual(forces.attributes('MAINPROGRAM'), forces.attributes())
        self.assertEqual(forces.attributes('Missing'), {})
        self.assertTrue(forces.description()['controller_empty'])
        self.assertFalse(forces.description()['sfc_force_engine'])

    def test_partial_context_and_ambiguous_source_cannot_assert_absence(self):
        for kind in ('context','target','use','namespaced','duplicate','missing-name'):
            root, controller = source()
            if kind=='context':root.set('ContainsContext','true')
            elif kind=='target':root.set('TargetType','Program')
            elif kind=='use':controller.find('./Programs/Program').set('Use','Context')
            elif kind=='namespaced':controller.find('./Programs/Program/Routines/Routine').tag='{urn:unknown}Routine'
            elif kind=='duplicate':controller.find('Programs').append(copy.deepcopy(controller.find('./Programs/Program')))
            else:controller.find('./Programs/Program').attrib.pop('Name')
            with self.subTest(kind=kind):
                forces=ProgramForces.from_source(root,controller)
                self.assertEqual(forces.attributes(),{})
                self.assertEqual(forces.attributes('MainProgram'),{})

    def test_sfc_unknown_protected_and_explicit_force_content_remain_unavailable(self):
        for kind in ('SFC','Unknown','missing-type','encoded','protected','sfc-child','force-data'):
            root,controller=source();routine=controller.find('./Programs/Program/Routines/Routine')
            if kind in ('SFC','Unknown'):routine.set('Type',kind)
            elif kind=='missing-type':routine.attrib.pop('Type')
            elif kind=='encoded':E.SubElement(routine,'EncodedData')
            elif kind=='protected':routine.set('Protected','true')
            elif kind=='sfc-child':E.SubElement(routine,'SFCContent')
            else:E.SubElement(routine,'SFCForceList')
            with self.subTest(kind=kind):
                forces=ProgramForces.from_source(root,controller)
                self.assertEqual(forces.attributes(),{})
                self.assertEqual(forces.attributes('MainProgram'),{})

    def test_program_scopes_keep_independent_absence_information(self):
        root,controller=source();programs=controller.find('Programs')
        second=copy.deepcopy(programs[0]);second.set('Name','ChartProgram')
        second.find('./Routines/Routine').set('Type','SFC');programs.append(second)
        forces=ProgramForces.from_source(root,controller)
        self.assertEqual(forces.attributes(),{})
        self.assertEqual(forces.attributes('ChartProgram'),{})
        self.assertEqual(set(forces.attributes('MainProgram')),{15,24,25})
        self.assertEqual(forces.description()['attributes'],[])

    def test_incomplete_or_ambiguous_routine_inventory_cannot_assert_absence(self):
        for kind in ('missing-container','duplicate-container','missing-main','missing-fault',
                     'duplicate-routine','missing-name','unknown-child','protected-program'):
            root,controller=source();program=controller.find('./Programs/Program')
            routines=program.find('Routines')
            if kind=='missing-container':program.remove(routines)
            elif kind=='duplicate-container':program.append(copy.deepcopy(routines))
            elif kind=='missing-main':program.set('MainRoutineName','HiddenChart')
            elif kind=='missing-fault':program.set('FaultRoutineName','HiddenChart')
            elif kind=='duplicate-routine':routines.append(copy.deepcopy(routines[0]))
            elif kind=='missing-name':routines[0].attrib.pop('Name')
            elif kind=='unknown-child':E.SubElement(routines,'VendorContent')
            else:program.set('ProtectedContent','true')
            with self.subTest(kind=kind):
                forces=ProgramForces.from_source(root,controller)
                self.assertEqual(forces.attributes(),{})
                self.assertEqual(forces.attributes('MainProgram'),{})

    def test_router_class_and_source_bound_instance_lists_agree_without_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            endpoint=Endpoint(app,0,False,'logix-v35-l85e',native_read_only=True)
            app.native_symbols=NativeSymbols('1'*64,app.engine.project.sha256,[],[{'name':'MainProgram','instance':70000}])
            before=copy.deepcopy(app.engine.memory.values)
            try:
                self.assertEqual(endpoint.router.handle(QUERY,Session()),EXPECTED)
                path=logical(0x20,0x68)+logical(0x24,70000)
                self.assertEqual(endpoint.router.handle(bytes((3,len(path)//2))+path+QUERY[6:],Session()),EXPECTED)
                for attr,size in ((15,2),(24,4),(25,4)):
                    self.assertEqual(endpoint.router.handle(bytes.fromhex('0e032068240030')+bytes((attr,)),Session()),b'\x8E\0\0\0'+bytes(size))
                mixed=bytes.fromhex('030220682400')+struct.pack('<5H',4,24,99,15,24)
                self.assertEqual(endpoint.router.handle(mixed,Session()),bytes.fromhex('83000a0004001800000000000000630014000f00000000001800000000000000'))
                for service in (4,0x10,0x53):
                    self.assertEqual(endpoint.router.handle(bytes((service,3))+bytes.fromhex('20682400300f')+b'\1\0',Session())[2],8)
                self.assertEqual(app.engine.memory.values,before)
            finally:app.close()

    def test_reload_sfc_source_removes_former_empty_state(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            endpoint=Endpoint(app,0,False,'logix-v35-l85e',native_read_only=True)
            try:
                self.assertEqual(endpoint.router.handle(QUERY,Session()),EXPECTED)
                root,controller=source();controller.find('./Programs/Program/Routines/Routine').set('Type','SFC')
                app.command('load',{'name':'chart.L5X','content':base64.b64encode(E.tostring(root)).decode()})
                result=endpoint.router.handle(QUERY,Session())
                self.assertEqual(result,bytes.fromhex('83000a0003000f0014001800140019001400'))
            finally:app.close()


if __name__=='__main__':unittest.main()
