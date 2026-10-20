"""Empty I/O status must not conceal configured or ambiguous module source."""
import base64
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as E
from logixlab.io_map import IOMap
from logixlab.ethernetip import Endpoint, Session
from logixlab.server import Application


def source():
    root=E.fromstring((Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X').read_bytes())
    return root,root.find('Controller')


class IOMapTests(unittest.TestCase):
    def test_empty_and_controller_only_source_report_no_modules_or_forces(self):
        root,controller=source()
        self.assertEqual(IOMap.from_source(root,controller).attributes(),{9:bytes(2),11:bytes(2)})
        E.SubElement(controller.find('Modules'),'Module',Name='Local',ParentModule='Local',Vendor='1',ProductType='14',CatalogNumber='1756-L85E')
        self.assertTrue(IOMap.from_source(root,controller).empty)

    def test_incomplete_ambiguous_external_and_force_sources_stay_unavailable(self):
        for kind in ('context','missing','duplicate','namespaced','module-context','external',
                     'wrong-local','nested','unknown-content','io-tag','force','unknown-module','protected-local'):
            root,controller=source();modules=controller.find('Modules')
            if kind=='context':root.set('ContainsContext','true')
            elif kind=='missing':controller.remove(modules)
            elif kind=='duplicate':E.SubElement(controller,'Modules')
            elif kind=='namespaced':modules.tag='{urn:unknown}Modules'
            elif kind=='module-context':modules.set('Use','Context')
            elif kind=='external':E.SubElement(modules,'Module',Name='RemoteRack',CatalogNumber='1756-EN2T')
            elif kind in ('wrong-local','nested','unknown-content','unknown-module','protected-local'):
                module=E.SubElement(modules,'Module',Name='Local',ParentModule='Local',Vendor='1',ProductType='14',CatalogNumber='1756-L85E')
                if kind=='wrong-local':module.set('CatalogNumber','1756-EN2T')
                elif kind=='nested':E.SubElement(module,'Module',Name='Remote')
                elif kind=='unknown-content':E.SubElement(module,'UnknownConnectionData')
                elif kind=='unknown-module':module.tag='VendorModule'
                else:module.set('EncodedConnectionData','hidden')
            elif kind=='io-tag':controller.find('./Tags/Tag').set('Name','Local:1:I')
            else:E.SubElement(controller,'ForceData')
            with self.subTest(kind=kind):self.assertFalse(IOMap.from_source(root,controller).empty)

    def test_wire_fields_widths_setter_denial_and_source_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            endpoint=Endpoint(app,0,True)
            query=bytes.fromhex('030220692400020009000b00')
            try:
                self.assertEqual(endpoint.router.handle(query,Session()),bytes.fromhex('8300000002000900000000000b0000000000'))
                self.assertEqual(endpoint.router.handle(bytes.fromhex('0e03206924003001'),Session()),bytes.fromhex('8e0000000100'))
                for attr in (9,11):
                    self.assertEqual(endpoint.router.handle(bytes.fromhex('0e032069240030')+bytes((attr,)),Session()),bytes.fromhex('8e0000000000'))
                    self.assertEqual(endpoint.router.handle(bytes.fromhex('10032069240030')+bytes((attr,))+bytes(2),Session())[2],8)
                root,controller=source();E.SubElement(controller.find('Modules'),'Module',Name='Remote')
                app.command('load',{'name':'io.L5X','content':base64.b64encode(E.tostring(root)).decode()})
                self.assertEqual(endpoint.router.handle(query,Session()),bytes.fromhex('83000a000200090014000b001400'))
                self.assertEqual(endpoint.router.handle(bytes.fromhex('0e03206924013009'),Session())[2],5)
            finally:app.close()
