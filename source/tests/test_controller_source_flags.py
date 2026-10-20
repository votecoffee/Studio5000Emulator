"""v35 controller source flags have exact byte reads and no write authority."""
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


FIELDS = {'MatchProjectToController': 15, 'InhibitAutomaticFirmwareUpdate': 17,
          'CanUseRPIFromProducer': 23, 'ReportMinorOverflow':31}


class ControllerSourceFlagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.root = E.parse(Path(__file__).resolve().parents[1] / 'samples/ConveyorDemo.L5X').getroot()
        self.controller = self.root.find('Controller')
        self.controller.set('MatchProjectToController', 'false')
        self.controller.set('InhibitAutomaticFirmwareUpdate', '0')
        self.controller.set('CanUseRPIFromProducer', 'false')
        self.controller.set('ReportMinorOverflow', 'false')
        self.load()
        self.endpoint = Endpoint(self.app, 0, False, 'logix-v35-l85e')
        self.app.endpoint = self.endpoint

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def load(self):
        self.app.command('load', {'name': 'controller-flags.L5X',
            'content': base64.b64encode(E.tostring(self.root)).decode()})

    def settings(self):
        return ControllerConfiguration.from_controller(self.controller, self.root)

    def flag_values(self):
        return {key: value for key, value in self.settings().attributes().items() if key in FIELDS.values()}

    def send(self, service=0x0E, attribute=15, data=b'', *, path=None):
        if path is None:
            path=bytes.fromhex('208e2401')+(bytes((0x30,attribute)) if attribute is not None else b'')
        return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data,Session())

    def test_native_export_flags_map_to_independent_v35_byte_attributes(self):
        self.assertEqual(self.flag_values(), {15:b'\0',17:b'\0',23:b'\0',31:b'\0'})
        for enabled in (False, True):
            self.controller.set('MatchProjectToController',str(enabled).lower())
            self.controller.set('CanUseRPIFromProducer',str(not enabled).lower())
            self.controller.set('InhibitAutomaticFirmwareUpdate','255')
            self.controller.set('ReportMinorOverflow',str(enabled).lower())
            values=self.flag_values()
            self.assertEqual(values,{15:bytes((enabled,)),17:b'\xff',23:bytes((not enabled,)),31:bytes((enabled,))})
            self.assertTrue(all(len(raw)==1 for raw in values.values()))

    def test_firmware_setting_preserves_byte_range_without_wrapping_or_boolean_coercion(self):
        for text,value in (('0',0),('1',1),('128',128),('255',255),('001',1)):
            with self.subTest(text=text):
                self.controller.set('InhibitAutomaticFirmwareUpdate',text)
                self.assertEqual(self.flag_values()[17],bytes((value,)))
        for text in ('256','-1','+1','1.0','0x01','16#01','true','',' 1','1 ','１２８','0'*1000):
            with self.subTest(text=text):
                self.controller.set('InhibitAutomaticFirmwareUpdate',text)
                self.assertNotIn(17,self.flag_values())
                self.assertEqual(self.flag_values()[15],b'\0')
                self.assertEqual(self.flag_values()[23],b'\0')

    def test_source_booleans_require_canonical_true_or_false(self):
        for name,number in (('MatchProjectToController',15),('CanUseRPIFromProducer',23),('ReportMinorOverflow',31)):
            original=self.controller.get(name)
            for text in ('TRUE','False','0','1','',' true','false ','unknown'):
                with self.subTest(name=name,text=text):
                    self.controller.set(name,text)
                    self.assertNotIn(number,self.flag_values())
            self.controller.set(name,original)

    def test_missing_source_flags_do_not_gain_defaults(self):
        for name,number in FIELDS.items():
            del self.controller.attrib[name]
            self.assertNotIn(number,self.flag_values())
        self.assertEqual(self.flag_values(),{})
        self.assertEqual(ControllerConfiguration.from_controller(self.controller).attributes(),{})

    def test_context_partial_and_ambiguous_source_withholds_flags(self):
        for mode in ('context','target','missing-context','duplicate-controller','controller-use',
                     'missing-tags','duplicate-tags','namespaced-tags'):
            root=copy.deepcopy(self.root);controller=root.find('Controller')
            if mode=='context':root.set('ContainsContext','true')
            elif mode=='target':root.set('TargetType','Program')
            elif mode=='missing-context':del root.attrib['ContainsContext']
            elif mode=='duplicate-controller':root.append(copy.deepcopy(controller))
            elif mode=='controller-use':controller.set('Use','Context')
            elif mode=='missing-tags':controller.remove(controller.find('Tags'))
            elif mode=='duplicate-tags':controller.append(copy.deepcopy(controller.find('Tags')))
            else:controller.find('Tags').tag='{extra}Tags'
            with self.subTest(mode=mode):
                self.assertFalse(set(FIELDS.values())&ControllerConfiguration.from_controller(controller,root).attributes().keys())

    def test_case_namespace_uid_and_suffix_variants_withhold_only_related_flag(self):
        for name,number in FIELDS.items():
            for alternate in (name.lower(),'{extra}'+name,name+'UId',name+'Extra'):
                with self.subTest(name=name,alternate=alternate):
                    self.controller.set(alternate,'1')
                    self.assertNotIn(number,self.flag_values())
                    self.assertEqual(len(self.flag_values()),3)
                    del self.controller.attrib[alternate]
            value=self.controller.attrib.pop(name)
            self.controller.set(name.lower(),value)
            self.assertNotIn(number,self.flag_values())
            del self.controller.attrib[name.lower()]
            self.controller.set(name,value)

    def test_single_wire_reads_and_ordered_duplicate_lists_have_exact_widths(self):
        self.controller.set('MatchProjectToController','true')
        self.controller.set('InhibitAutomaticFirmwareUpdate','128')
        self.controller.set('ReportMinorOverflow','true')
        self.load()
        for attribute,value in ((15,b'\1'),(17,b'\x80'),(23,b'\0'),(31,b'\1')):
            self.assertEqual(self.send(attribute=attribute),bytes.fromhex('8e000000')+value)
        order=(31,23,17,15,31)
        expected=(bytes.fromhex('83000000')+struct.pack('<H',5)+
                  struct.pack('<HHBHHBHHBHHBHHB',31,0,1,23,0,0,17,0,128,15,0,1,31,0,1))
        self.assertEqual(self.send(3,None,struct.pack('<6H',5,*order)),expected)

    def test_unknown_or_invalid_flag_in_a_list_preserves_known_fields_and_repetitions(self):
        self.controller.set('MatchProjectToController','TRUE')
        self.load()
        order=(17,15,23,24,17)
        expected=(bytes.fromhex('83000a00')+struct.pack('<H',5)+struct.pack('<HHB',17,0,0)+
                  struct.pack('<HH',15,0x14)+struct.pack('<HHB',23,0,0)+
                  struct.pack('<HH',24,0x14)+struct.pack('<HHB',17,0,0))
        self.assertEqual(self.send(3,None,struct.pack('<6H',5,*order)),expected)

    def test_native_read_model_reuses_source_values_without_defaults_or_handler_pointers(self):
        self.controller.set('MatchProjectToController','true')
        self.controller.set('InhibitAutomaticFirmwareUpdate','5')
        self.load()
        self.endpoint = Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True)
        self.app.endpoint=self.endpoint
        self.assertEqual(self.send(attribute=15),bytes.fromhex('8e00000001'))
        self.assertEqual(self.send(attribute=17),bytes.fromhex('8e00000005'))
        self.assertEqual(self.send(attribute=23),bytes.fromhex('8e00000000'))
        self.assertEqual(self.send(attribute=31),bytes.fromhex('8e00000000'))
        for attr in (1,6):self.assertEqual(self.send(attribute=attr)[2],0x14)
        self.assertEqual(self.send(1,None)[2],8)

    def test_reads_do_not_match_projects_update_firmware_negotiate_io_or_modify_values(self):
        before=copy.deepcopy(self.app.state())
        for attr in FIELDS.values():
            self.assertEqual(self.send(attribute=attr)[2],0)
            self.assertEqual(self.send(0x10,attr,b'\1')[2],8)
            self.assertEqual(self.send(4,None,struct.pack('<HHB',1,attr,1))[2],8)
        after=self.app.state()
        for key in ('tags','scan','ms','controller','routines','tasks'):
            self.assertEqual(after[key],before[key])
        info=self.settings().description()
        self.assertEqual(info['source_read_attributes'],[15,17,23,31])
        for key in ('project_serial_matching_enforced','firmware_update_services',
                    'producer_rpi_negotiation','source_settings_writable','native_minor_overflow_fault_reporting'):
            self.assertFalse(info[key])

    def test_project_replacement_removes_previous_source_settings(self):
        self.assertEqual(self.send(attribute=17)[2],0)
        for name in FIELDS:del self.controller.attrib[name]
        self.load()
        for attr in FIELDS.values():self.assertEqual(self.send(attribute=attr)[2],0x14)


if __name__=='__main__':
    unittest.main()
