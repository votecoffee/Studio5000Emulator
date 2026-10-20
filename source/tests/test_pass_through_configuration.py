"""Native read-only controller metadata retains explicit source routing policy."""
import base64
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.controller_configuration import ControllerConfiguration
from logixlab.ethernetip import Endpoint, Session
from logixlab.server import Application


class PassThroughConfigurationTests(unittest.TestCase):
    def test_source_modes_use_the_native_roundtrip_mask_and_udint_width(self):
        for name,value in (('Disabled',0),('Enabled',1),('EnabledWithAppend',3)):
            node=E.Element('Controller',PassThroughConfiguration=name)
            config=ControllerConfiguration.from_controller(node)
            self.assertEqual(config.compatibility_attributes()[25],struct.pack('<I',value))
            self.assertNotIn(25,config.attributes())
            description=config.description()
            self.assertEqual(description['pass_through_configuration'],name)
            self.assertEqual(description['pass_through_configuration_code'],value)
            self.assertEqual(description['pass_through_source'],'Controller@PassThroughConfiguration')
            self.assertFalse(description['pass_through_routing'])

    def test_missing_noncanonical_and_ambiguous_settings_remain_unavailable(self):
        sources=['<Controller/>']
        for value in ('','0','1','2','3','enabled','EnabledwithAppend',' Enabled','Enabled ','DisabledWithAppend'):
            sources.append(E.tostring(E.Element('Controller',PassThroughConfiguration=value)))
        sources.extend((
            '<Controller xmlns:x="urn:unknown" x:PassThroughConfiguration="Enabled"/>',
            '<Controller PassThroughConfiguration="Enabled" passthroughconfiguration="Disabled"/>',
            '<Controller xmlns:x="urn:unknown" PassThroughConfiguration="Enabled" x:PassThroughConfiguration="Enabled"/>'))
        for text in sources:
            with self.subTest(source=text):
                config=ControllerConfiguration.from_controller(E.fromstring(text))
                self.assertNotIn(25,config.compatibility_attributes())
                self.assertIsNone(config.description()['pass_through_configuration_code'])

    def test_router_single_list_duplicates_refresh_and_missing_setting(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            endpoint=Endpoint(app,0,False,'logix-v35-l85e',native_read_only=True)
            fixture=Path(__file__).resolve().parents[1]/'samples/ConveyorDemo.L5X'
            try:
                for mode,value in (('EnabledWithAppend',3),('Disabled',0),('Enabled',1),(None,None)):
                    root=E.fromstring(fixture.read_bytes());controller=root.find('Controller')
                    controller.attrib.pop('PassThroughConfiguration',None)
                    if mode is not None:controller.set('PassThroughConfiguration',mode)
                    app.command('load',{'name':'policy.L5X','content':base64.b64encode(E.tostring(root)).decode()})
                    raw=bytes.fromhex('0e03208e24013019')
                    result=endpoint.router.handle(raw,Session())
                    expected=b'\x8E\0\x14\0' if value is None else b'\x8E\0\0\0'+struct.pack('<I',value)
                    self.assertEqual(result,expected)
                    # A mixed list preserves order, repeated fields and unsupported IDs.
                    data=struct.pack('<4H',3,25,99,25)
                    field=struct.pack('<HH',25,0x14 if value is None else 0)
                    if value is not None:field+=struct.pack('<I',value)
                    self.assertEqual(endpoint.router.handle(bytes.fromhex('0302208e2401')+data,Session()),
                        b'\x83\0\x0A\0'+struct.pack('<H',3)+field+struct.pack('<HH',99,0x14)+field)
            finally:app.close()

    def test_configuration_read_cannot_enable_routing_or_controller_setters(self):
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            endpoint=Endpoint(app,0,True,'logix-v35-l85e')
            before=copy.deepcopy(app.engine.memory.values)
            try:
                # Outside native compatibility mode, the field remains unsupported.
                self.assertEqual(endpoint.router.handle(bytes.fromhex('0e03208e24013019'),Session())[2],0x14)
                for service in (4,0x10):
                    self.assertEqual(endpoint.router.handle(bytes((service,3))+bytes.fromhex('208e24013019')+struct.pack('<I',3),Session())[2],8)
                # Unconnected forwarding still rejects any route outside modeled slot zero.
                forwarded=bytes.fromhex('5202200624010a0e060001022001240101000101')
                self.assertEqual(endpoint.router.handle(forwarded,Session())[2],5)
                self.assertEqual(app.engine.memory.values,before)
            finally:app.close()


if __name__=='__main__':unittest.main()
