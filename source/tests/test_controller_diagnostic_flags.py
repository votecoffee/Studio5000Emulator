"""Explicit Controller retention/diagnostic settings do not enable their services."""
import copy
import struct
import unittest
from xml.etree import ElementTree as E
from logixlab.controller_configuration import ControllerConfiguration
from logixlab.ethernetip import Endpoint
from logixlab.native_project import NativeProjectIdentity
from tools.anonymous_client import AnonymousClient
from tools.collection_inventory import decode_attribute_list
import test_controller_source_flags as flags


class ControllerDiagnosticFlagTests(unittest.TestCase):
    tearDown=flags.ControllerSourceFlagTests.tearDown
    load=flags.ControllerSourceFlagTests.load
    send=flags.ControllerSourceFlagTests.send
    settings=flags.ControllerSourceFlagTests.settings

    def setUp(self):
        flags.ControllerSourceFlagTests.setUp(self);self.controller.set('AutoDiagsEnabled','true')
        self.redundancy=self.controller.find('RedundancyInfo')
        if self.redundancy is None:self.redundancy=E.SubElement(self.controller,'RedundancyInfo')
        self.redundancy.attrib={'Enabled':'false','KeepTestEditsOnSwitchOver':'false'}
        self.load()

    def values(self):return {n:v for n,v in self.settings().attributes().items() if n in (10,35)}

    def test_two_source_settings_have_independent_byte_values_and_no_simulated_feature_activation(self):
        for keep,diagnostics in ((False,True),(True,False),(True,True),(False,False)):
            self.redundancy.set('KeepTestEditsOnSwitchOver',str(keep).lower());self.controller.set('AutoDiagsEnabled',str(diagnostics).lower())
            self.assertEqual(self.values(),{10:bytes((keep,)),35:bytes((diagnostics,))})
            info=self.settings().description()
            self.assertEqual(info['continue_test_edits'],keep);self.assertEqual(info['automatic_diagnostics_enabled'],diagnostics)
            self.assertFalse(info['redundant_switchover_execution']);self.assertFalse(info['automatic_diagnostics_delivery'])

    def test_missing_or_noncanonical_booleans_withhold_only_the_affected_field(self):
        for text in (None,'TRUE','False','0','1','',' true','false ','unknown'):
            if text is None:self.controller.attrib.pop('AutoDiagsEnabled',None)
            else:self.controller.set('AutoDiagsEnabled',text)
            self.assertEqual(self.values(),{10:b'\0'})
        self.controller.set('AutoDiagsEnabled','true')
        for text in (None,'TRUE','False','0','1','',' true','false ','unknown'):
            if text is None:self.redundancy.attrib.pop('KeepTestEditsOnSwitchOver',None)
            else:self.redundancy.set('KeepTestEditsOnSwitchOver',text)
            self.assertEqual(self.values(),{35:b'\1'})

    def test_ambiguous_opaque_and_context_redundancy_declarations_are_unavailable(self):
        original=copy.deepcopy(self.root)
        for mode in ('missing','duplicate','namespace','case','uid','child','text','opaque','context','invalid-enabled'):
            self.root=copy.deepcopy(original);self.controller=self.root.find('Controller');node=self.controller.find('RedundancyInfo')
            if mode=='missing':self.controller.remove(node)
            elif mode=='duplicate':self.controller.append(copy.deepcopy(node))
            elif mode in ('namespace','case','uid'):node.tag={'namespace':'{test}RedundancyInfo','case':'redundancyinfo','uid':'RedundancyInfoUId'}[mode]
            elif mode=='child':E.SubElement(node,'Unknown')
            elif mode=='text':node.text='unknown configuration'
            elif mode=='opaque':node.set('OtherSetting','unknown')
            elif mode=='context':node.set('Use','Context')
            else:node.set('Enabled','unknown')
            with self.subTest(mode=mode):self.assertEqual(self.values(),{35:b'\1'})

    def test_shadow_diagnostics_attributes_and_incomplete_sources_do_not_default_to_enabled(self):
        original=copy.deepcopy(self.root)
        for name in ('autodiagsenabled','AutoDiagsEnabledUId','{test}AutoDiagsEnabled'):
            self.controller.set(name,'false');self.assertEqual(self.values(),{10:b'\0'});self.controller.attrib.pop(name)
        for mode in ('no-root','context','controller-context','missing-tags','namespaced-tags'):
            self.root=copy.deepcopy(original);self.controller=self.root.find('Controller')
            if mode=='context':self.root.set('ContainsContext','true')
            elif mode=='controller-context':self.controller.set('Use','Context')
            elif mode=='missing-tags':self.controller.remove(self.controller.find('Tags'))
            elif mode=='namespaced-tags':self.controller.find('Tags').tag='{test}Tags'
            value=ControllerConfiguration.from_controller(self.controller,None if mode=='no-root' else self.root)
            with self.subTest(mode=mode):self.assertNotIn(10,value.attributes());self.assertNotIn(35,value.attributes())

    def test_signed_mixed_reads_preserve_order_values_and_write_policy(self):
        self.app.native_project_identity=NativeProjectIdentity('a'*64,self.app.engine.project.sha256,1,1,1,1,1,1)
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint;self.endpoint.start()
        before=copy.deepcopy(self.app.state());requested=(35,10,32,35,33)
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            raw=client.request(bytes.fromhex('0302208e2401')+struct.pack('<6H',len(requested),*requested))
            rows=decode_attribute_list(raw,requested,0x8E,include_payloads=True)['attributes']
            self.assertEqual([r['status'] for r in rows],[0,0,20,0,20]);self.assertEqual(rows[0],rows[3])
            self.assertEqual(rows[0]['data_hex'],'01');self.assertEqual(rows[1]['data_hex'],'00')
            for number in (10,35):
                response=client.request(bytes.fromhex('1003208e240130')+bytes((number,0)))
                self.assertEqual(response[2],15)
        for key in ('tags','scan','ms','routines','tasks','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_reset_retains_configured_values_without_changing_them_through_reads(self):
        self.redundancy.set('KeepTestEditsOnSwitchOver','true');self.controller.set('AutoDiagsEnabled','false');self.load()
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.send(attribute=10),bytes.fromhex('8e00000001'))
        self.assertEqual(self.send(attribute=35),bytes.fromhex('8e00000000'))
        self.app.command('reset',{})
        self.assertEqual(self.app.engine.project.controller_configuration.attributes()[10],b'\1')
        self.assertEqual(self.app.engine.project.controller_configuration.attributes()[35],b'\0')
        self.assertEqual(self.app.state()['tags'],before['tags'])


if __name__=='__main__':unittest.main()
