"""Empty I/O status must not conceal configured or ambiguous module source."""
import base64
import copy
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
    def local_route(self):
        root,controller=source()
        module=E.SubElement(controller.find('Modules'),'Module',Name='Local',ParentModule='Local',Vendor='1',
                            ProductType='14',CatalogNumber='1756-L85E',ParentModPortId='1')
        ports=E.SubElement(module,'Ports')
        port=E.SubElement(ports,'Port',Id='1',Type='ICP',Address='0',Upstream='false')
        E.SubElement(port,'Bus',Size='17')
        return root,controller,module,ports,port

    def test_root_link_address_requires_canonical_supported_local_backplane(self):
        root,controller,module,ports,port=self.local_route()
        catalog=IOMap.from_source(root,controller)
        self.assertTrue(catalog.empty);self.assertEqual(catalog.root_link_address,0)
        self.assertTrue(catalog.description()['root_link_address_available'])
        self.assertIsNone(IOMap.from_source(*source()).root_link_address)

    def test_root_link_address_is_withheld_for_ambiguous_missing_or_unsupported_route(self):
        for kind in ('missing-address','other-slot','wrong-type','upstream','parent-port','duplicate-port','nested-port','duplicate-ports'):
            root,controller,module,ports,port=self.local_route()
            if kind=='missing-address':del port.attrib['Address']
            elif kind=='other-slot':port.set('Address','1')
            elif kind=='wrong-type':port.set('Type','Ethernet')
            elif kind=='upstream':port.set('Upstream','true')
            elif kind=='parent-port':module.set('ParentModPortId','2')
            elif kind=='duplicate-port':ports.append(copy.deepcopy(port))
            elif kind=='nested-port':E.SubElement(port.find('Bus'),'Port',Id='1',Address='0')
            else:E.SubElement(module,'Ports')
            with self.subTest(kind=kind):
                self.assertIsNone(IOMap.from_source(root,controller).root_link_address)

    def test_root_route_wire_widths_partial_lists_and_write_denials(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            endpoint=Endpoint(app,0,True)
            try:
                root,controller,*_=self.local_route()
                app.command('load',{'name':'local.L5X','content':base64.b64encode(E.tostring(root)).decode()})
                before=copy.deepcopy(app.engine.memory.values)
                call=lambda raw:endpoint.router.handle(bytes.fromhex(raw),Session())
                self.assertEqual(call('03022069240101000a00'),bytes.fromhex('8300000001000a00000000000000'))
                self.assertEqual(call('0e0320692401300a'),bytes.fromhex('8e00000000000000'))
                self.assertEqual(call('03022069240102000a000c00'),bytes.fromhex('83000a0002000a000000000000000c001400'))
                self.assertEqual(call('100320692401300a01000000')[2],8)
                self.assertEqual(call('0e0320692402300a')[2],5)
                app.command('demo',{'sample':'ConveyorDemo'})
                self.assertEqual(call('0e0320692401300a')[2],5)
                self.assertEqual(app.engine.memory.values,before)
            finally:app.close()

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

    def test_empty_instance_lists_counts_and_cursors_require_source_proof(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            endpoint=Endpoint(app,0,True)
            try:
                before=copy.deepcopy(app.engine.memory.values)
                for path in ('20692400','20692401','20692600ffffffff'):
                    raw=bytes.fromhex(path)
                    self.assertEqual(endpoint.router.handle(bytes((0x4B,len(raw)//2))+raw,Session()),bytes.fromhex('cb000000'))
                query=bytes.fromhex('030220692400020002000300')
                self.assertEqual(endpoint.router.handle(query,Session()),bytes.fromhex('83000000020002000000000000000300000000000000'))
                app.engine.project.io_map=IOMap(False)
                self.assertEqual(endpoint.router.handle(bytes.fromhex('4b0220692400'),Session())[2],0x0C)
                self.assertEqual(endpoint.router.handle(query,Session()),bytes.fromhex('83000a0002000200140003001400'))
                self.assertEqual(app.engine.memory.values,before)
            finally:app.close()

    def test_discovery_rejects_scopes_payloads_and_mutations(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            endpoint=Endpoint(app,0,True)
            try:
                for raw,status in (('4b012069',4),('4b03206924003001',4),('4b022069240000',0x15),
                                   ('4b042068240120692400',4),('100320692400300301000000',8)):
                    self.assertEqual(endpoint.router.handle(bytes.fromhex(raw),Session())[2],status)
                self.assertEqual(app.engine.scan_count,0)
            finally:app.close()
