"""Static reservation settings, independent of measured free RAM or signatures."""
import copy
import struct
import unittest
from xml.etree import ElementTree as E

from logixlab.controller_configuration import ControllerConfiguration,MEMORY_PAD_FIELDS
from logixlab.ethernetip import Endpoint
from logixlab.native_project import NativeProjectIdentity
from tools.anonymous_client import AnonymousClient
from tools.collection_inventory import decode_attribute_list
import test_controller_diagnostic_flags as diagnostics


class MemoryPaddingTests(unittest.TestCase):
    setUp=diagnostics.ControllerDiagnosticFlagTests.setUp
    tearDown=diagnostics.ControllerDiagnosticFlagTests.tearDown
    load=diagnostics.ControllerDiagnosticFlagTests.load
    settings=diagnostics.ControllerDiagnosticFlagTests.settings
    send=diagnostics.ControllerDiagnosticFlagTests.send

    def values(self):
        return {n:v for n,v in self.settings().attributes().items() if n in (11,12)}

    def test_disabled_redundancy_selects_zero_reservation_and_reports_its_origin(self):
        before=E.tostring(self.root)
        self.assertEqual(self.values(),{11:bytes(2),12:bytes(2)})
        info=self.settings().description()['memory_padding']
        self.assertEqual(info['defaulted'],dict.fromkeys(MEMORY_PAD_FIELDS,True))
        self.assertFalse(info['live_free_memory_measurement'])
        self.assertFalse(info['native_reservation_enforcement'])
        self.assertEqual(E.tostring(self.root),before)
        self.redundancy.set('Enabled','true')
        self.assertEqual(self.values(),{})
        self.assertEqual(self.settings().description()['memory_padding']['defaulted'],dict.fromkeys(MEMORY_PAD_FIELDS,False))

    def test_explicit_percentages_are_independent_settings_and_do_not_enable_redundancy(self):
        for enabled in ('true','false'):
            self.redundancy.set('Enabled',enabled)
            for io,table in ((0,100),(100,0),(90,50),(1,99)):
                for field,value in zip(MEMORY_PAD_FIELDS,(io,table)):self.redundancy.set(field,str(value))
                with self.subTest(enabled=enabled,io=io,table=table):
                    config=self.settings();self.assertEqual(self.values(),{11:struct.pack('<H',io),12:struct.pack('<H',table)})
                    self.assertEqual(config.attributes()[10],b'\0')
                    self.assertEqual(config.description()['memory_padding']['defaulted'],dict.fromkeys(MEMORY_PAD_FIELDS,False))
                    self.assertFalse(config.description()['redundant_switchover_execution'])
                    self.assertNotIn(33,config.attributes());self.assertNotIn(34,config.attributes())

    def test_invalid_explicit_percentages_never_fall_back_or_hide_independent_setting(self):
        for field,number,other in ((MEMORY_PAD_FIELDS[0],11,12),(MEMORY_PAD_FIELDS[1],12,11)):
            for text in ('','-1','+1','101','65535','0x32','16#32','50.0','01',' 1','1 ','５０','0'*1000):
                self.redundancy.set(field,text)
                with self.subTest(field=field,value=text):
                    self.assertEqual(self.values(),{other:bytes(2)})
                    self.assertFalse(self.settings().description()['memory_padding']['defaulted'][field])
            self.redundancy.attrib.pop(field)

    def test_ambiguous_opaque_and_partial_configuration_withholds_both_fields(self):
        original=copy.deepcopy(self.root)
        for kind in ('missing','duplicate','namespace','case','uid','nested','child','text','opaque',
                     'context','invalid-enabled','root-context','missing-tags','old-version','no-version','pad-shadow','pad-controller','pad-element'):
            self.root=copy.deepcopy(original);self.controller=self.root.find('Controller');self.redundancy=self.controller.find('RedundancyInfo')
            node=self.redundancy
            if kind=='missing':self.controller.remove(node)
            elif kind=='duplicate':self.controller.append(copy.deepcopy(node))
            elif kind in ('namespace','case','uid'):node.tag={'namespace':'{test}RedundancyInfo','case':'redundancyinfo','uid':'RedundancyInfoUId'}[kind]
            elif kind=='nested':self.controller.find('Tags').append(E.Element('RedundancyInfo',Enabled='false'))
            elif kind=='child':E.SubElement(node,'Unknown')
            elif kind=='text':node.text='unknown configuration'
            elif kind=='opaque':node.set('OtherSetting','unknown')
            elif kind=='context':node.set('Use','Context')
            elif kind=='invalid-enabled':node.set('Enabled','0')
            elif kind=='root-context':self.root.set('ContainsContext','true')
            elif kind=='missing-tags':self.controller.remove(self.controller.find('Tags'))
            elif kind=='old-version':self.controller.set('MajorRev','34')
            elif kind=='no-version':self.root.attrib.pop('SoftwareRevision')
            elif kind=='pad-shadow':node.set('{test}DataTablePadPercentage','50')
            elif kind=='pad-controller':self.controller.set('IOMemoryPadPercentage','90')
            else:E.SubElement(self.controller,'DataTablePadPercentage')
            with self.subTest(kind=kind):self.assertEqual(self.values(),{})
        self.root=copy.deepcopy(original);self.controller=self.root.find('Controller')
        config=ControllerConfiguration.from_controller(self.controller)
        self.assertNotIn(11,config.attributes());self.assertNotIn(12,config.attributes())

    def test_signed_lists_repeat_mix_and_deny_writes_without_changing_state(self):
        self.redundancy.set('IOMemoryPadPercentage','90');self.redundancy.set('DataTablePadPercentage','50');self.load()
        self.app.native_project_identity=NativeProjectIdentity('a'*64,self.app.engine.project.sha256,1,1,1,1,1,1)
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint;self.endpoint.start()
        before=copy.deepcopy(self.app.state());requested=(12,11,33,12,34,10)
        with AnonymousClient(self.endpoint) as client:
            client.bind();reply=client.request(bytes.fromhex('0302208e2401')+struct.pack('<7H',6,*requested))
            fields=decode_attribute_list(reply,requested,0x8E,include_payloads=True)['attributes']
            self.assertEqual([row['status'] for row in fields],[0,0,20,0,20,0])
            self.assertEqual(fields[0]['data_hex'],'3200');self.assertEqual(fields[1]['data_hex'],'5a00');self.assertEqual(fields[0],fields[3])
            for number in (11,12):self.assertEqual(client.request(bytes.fromhex('1003208e240130')+bytes((number,))+bytes(2))[2],15)
        for key in ('tags','scan','ms','routines','tasks','controller'):self.assertEqual(self.app.state()[key],before[key])
        self.app.command('reset',{})
        self.assertEqual(self.app.engine.project.controller_configuration.attributes()[12],struct.pack('<H',50))


if __name__=='__main__':unittest.main()
