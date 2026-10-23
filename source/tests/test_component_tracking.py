"""Empty modeled tracking group; never infer a native ACD's tracking state."""
import copy
from dataclasses import FrozenInstanceError
import hashlib
import struct
import unittest
from xml.etree import ElementTree as E

from logixlab.component_tracking import EmptyComponentTracking
from logixlab.ethernetip import Endpoint
from logixlab.native_project import NativeProjectIdentity
from logixlab.runtime import Engine
from tools.anonymous_client import AnonymousClient
from tools.collection_inventory import decode_attribute_list
import test_controller_source_flags as flags


class ComponentTrackingTests(unittest.TestCase):
    tearDown=flags.ControllerSourceFlagTests.tearDown
    load=flags.ControllerSourceFlagTests.load
    settings=flags.ControllerSourceFlagTests.settings
    send=flags.ControllerSourceFlagTests.send

    def setUp(self):
        flags.ControllerSourceFlagTests.setUp(self)
        self.root.find('./Controller/Programs/Program').set('TestEdits','false');self.load()

    def policy(self,**kwargs):
        digest=hashlib.sha256(E.tostring(self.root)).hexdigest()
        return EmptyComponentTracking.from_source(self.root,self.controller,digest,aoi_empty=True,io_empty=True,**kwargs)

    def test_omitted_and_explicit_zero_declarations_select_only_the_emulator_policy(self):
        before=E.tostring(self.root);policy=self.policy()
        self.assertEqual(policy.attributes(policy.source_sha256,idle=True),{33:bytes(32),34:bytes(32)})
        info=policy.description()
        self.assertEqual(info['modeled_tracked_components'],0)
        self.assertFalse(info['native_membership_imported']);self.assertFalse(info['absence_proves_native_membership'])
        self.assertFalse(info['native_signatures_imported']);self.assertFalse(info['signature_verification'])
        self.assertEqual(E.tostring(self.root),before)
        for node in (self.root.find('./Controller/Tags/Tag'),self.root.find('./Controller/Programs/Program/Routines/Routine')):
            node.set('TrackingGroups','0')
        self.assertTrue(self.policy().policy_available)
        with self.assertRaises(FrozenInstanceError):policy.policy_available=False

    def test_nonzero_malformed_and_shadow_declarations_never_become_empty(self):
        original=copy.deepcopy(self.root)
        for text in ('1','2','4294967295','-1','+0','00','0x0','16#0','',' 0','０','0'*1000):
            self.root=copy.deepcopy(original);self.controller=self.root.find('Controller')
            self.root.find('./Controller/Programs/Program/Routines/Routine').set('TrackingGroups',text)
            with self.subTest(text=text):self.assertFalse(self.policy().policy_available)
        for name in ('trackinggroups','TrackingGroupsUId','{test}TrackingGroups','TrackedState','StateDetectionSignature'):
            self.root=copy.deepcopy(original);self.controller=self.root.find('Controller');self.controller.set(name,'0')
            with self.subTest(name=name):self.assertFalse(self.policy().policy_available)
        self.root=copy.deepcopy(original);self.controller=self.root.find('Controller');E.SubElement(self.controller,'TrackingGroups')
        self.assertFalse(self.policy().policy_available)

    def test_partial_hidden_signed_aoi_io_and_test_state_do_not_select_the_policy(self):
        original=copy.deepcopy(self.root)
        for mode in ('context','old-version','different-processor','hidden','signature','test-edits','safety','aoi','io'):
            self.root=copy.deepcopy(original);self.controller=self.root.find('Controller')
            if mode=='context':self.root.set('ContainsContext','true')
            elif mode=='old-version':self.controller.set('MajorRev','34')
            elif mode=='different-processor':self.controller.set('ProcessorType','1756-L73')
            elif mode=='hidden':E.SubElement(self.controller,'EncodedData')
            elif mode=='signature':self.controller.set('Signature','unknown')
            elif mode=='test-edits':self.root.find('./Controller/Programs/Program').set('TestEdits','true')
            elif mode=='safety':self.root.find('./Controller/Programs/Program').set('Class','Safety')
            digest=hashlib.sha256(E.tostring(self.root)).hexdigest()
            policy=EmptyComponentTracking.from_source(self.root,self.controller,digest,aoi_empty=mode!='aoi',io_empty=mode!='io')
            with self.subTest(mode=mode):self.assertFalse(policy.policy_available)

    def test_source_idle_and_clean_runtime_guards_withhold_values(self):
        policy=self.policy()
        self.assertEqual(policy.attributes('f'*64,idle=True),{})
        for idle in (False,None,1):self.assertEqual(policy.attributes(policy.source_sha256,idle=idle),{})
        engine=self.app.engine;self.assertTrue(engine.project.component_tracking.policy_available)
        self.assertEqual(engine.component_tracking_attributes(idle=True),{33:bytes(32),34:bytes(32)})
        engine.step();self.assertEqual(engine.component_tracking_attributes(idle=True),{33:bytes(32),34:bytes(32)})
        engine.fault='Unclassified simulator error';engine.fault=''
        self.assertEqual(engine.component_tracking_attributes(idle=True),{})
        fresh=Engine(engine.project);self.assertEqual(fresh.component_tracking_attributes(idle=True),{33:bytes(32),34:bytes(32)})
        harness=Engine(engine.project,'routine','MainProgram/MainRoutine')
        self.assertEqual(harness.component_tracking_attributes(idle=True),{})

    def native(self):
        self.app.native_project_identity=NativeProjectIdentity('a'*64,self.app.engine.project.sha256,1,1,1,1,1,1)
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True)
        self.app.endpoint=self.endpoint;self.endpoint.start()

    def test_signed_empty_group_reads_repeat_mix_and_deny_writes_without_changing_state(self):
        self.native();before=copy.deepcopy(self.app.state());requested=(34,33,34,36)
        with AnonymousClient(self.endpoint) as client:
            client.bind();reply=client.request(bytes.fromhex('0302208e2401')+struct.pack('<5H',4,*requested))
            rows=decode_attribute_list(reply,requested,0x8e,include_payloads=True)['attributes']
            self.assertEqual([row['status'] for row in rows],[0,0,0,20])
            self.assertEqual([row['data_hex'] for row in rows[:3]],['00'*32]*3);self.assertEqual(rows[0],rows[2])
            for number in (33,34):self.assertEqual(client.request(bytes.fromhex('1003208e240130')+bytes((number,))+bytes(32))[2],15)
        for key in ('tags','scan','ms','routines','tasks','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_native_binding_is_required_and_research_profile_remains_unavailable(self):
        self.assertEqual(self.send(attribute=33)[2],20)
        self.native();self.assertEqual(self.send(attribute=33),bytes.fromhex('8e000000')+bytes(32))
        self.assertTrue(self.app.state()['connectivity']['controller_component_tracking']['reads_available'])
        self.app.native_project_identity=NativeProjectIdentity('a'*64,'f'*64,1,1,1,1,1,1)
        self.assertEqual(self.send(attribute=33)[2],20)
        self.assertFalse(self.app.state()['connectivity']['controller_component_tracking']['reads_available'])


if __name__=='__main__':unittest.main()
