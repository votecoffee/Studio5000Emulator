"""Controller compatibility settings keep defaults distinct from source data."""
import struct
import unittest
from xml.etree import ElementTree as E

from logixlab.controller_configuration import ControllerConfiguration


class ControllerUploadMetadataTests(unittest.TestCase):
    def test_null_handler_aggregate_preserves_observed_order_and_live_inhibit_without_inventing_configured_references(self):
        root,c=self.source(TimeSlice='30');value=ControllerConfiguration.from_controller(c,root)
        fields=value.compatibility_attributes();fields[7]=b'\1\0'
        self.assertEqual(value.compatibility_get_all(fields),struct.pack('<HIIHHH',30,0,0,1,0,0))
        for key,bad in ((1,bytes(6)),(6,b'\1'+bytes(3)),(3,b''),(7,b'\0'),(8,None)):
            self.assertIsNone(value.compatibility_get_all({**fields,key:bad}))
        c.set('MajorFaultProgram','Configured');other=ControllerConfiguration.from_controller(c,root)
        self.assertIsNone(other.compatibility_get_all(fields))

    def source(self, **attributes):
        root=E.fromstring('<RSLogix5000Content TargetType="Controller" ContainsContext="false"><Controller Use="Target" Name="Test"><Tags/><Programs/></Controller></RSLogix5000Content>')
        controller=root.find('Controller');controller.attrib.update(attributes)
        return root,controller

    def test_explicit_time_slice_fields_have_uint_width_and_valid_ranges(self):
        for time_slice,share in (('10','0'),('20','1'),('90','0')):
            root,c=self.source(TimeSlice=time_slice,ShareUnusedTimeSlice=share)
            value=ControllerConfiguration.from_controller(c,root)
            self.assertEqual(value.compatibility_attributes()[3],struct.pack('<H',int(time_slice)))
            self.assertEqual(value.compatibility_attributes()[16],struct.pack('<H',int(share)))
            self.assertFalse(value.description()['time_slice_defaulted'])
            self.assertFalse(value.description()['share_unused_defaulted'])
            self.assertNotIn(3,value.attributes())  # Compatibility does not expand the ordinary endpoint.

    def test_missing_time_slice_uses_declared_model_defaults_and_invalid_source_is_omitted(self):
        root,c=self.source();value=ControllerConfiguration.from_controller(c,root)
        self.assertEqual(value.compatibility_attributes()[3],b'\x14\0')
        self.assertEqual(value.compatibility_attributes()[16],b'\1\0')
        self.assertTrue(value.description()['time_slice_defaulted'])
        self.assertFalse(value.description()['native_time_slice_scheduling'])
        for text in ('','9','91','-1','1.5','true','020','x'*1000):
            c.set('TimeSlice',text)
            self.assertNotIn(3,ControllerConfiguration.from_controller(c,root).compatibility_attributes())
        for text in ('','true','false','2','-1','01'):
            c.set('ShareUnusedTimeSlice',text)
            self.assertNotIn(16,ControllerConfiguration.from_controller(c,root).compatibility_attributes())

    def test_empty_handlers_require_complete_source_and_do_not_claim_execution(self):
        root,c=self.source();value=ControllerConfiguration.from_controller(c,root)
        self.assertTrue(value.empty_power_loss_handler);self.assertTrue(value.empty_fault_handler)
        self.assertFalse(value.description()['handler_execution'])
        self.assertEqual(value.description()['handler_reference_encoding'],'null_uint32_only')
        self.assertFalse(value.description()['configured_handler_references'])
        self.assertEqual(value.compatibility_attributes()[1],bytes(4));self.assertEqual(value.compatibility_attributes()[6],bytes(4))
        self.assertNotIn(1,value.attributes());self.assertNotIn(6,value.attributes())
        for modify in (lambda:root.set('ContainsContext','true'),lambda:c.set('Use','Context'),lambda:c.remove(c.find('Tags'))):
            root,c=self.source();modify();value=ControllerConfiguration.from_controller(c,root)
            self.assertNotIn(1,value.compatibility_attributes());self.assertNotIn(6,value.compatibility_attributes())
        root,c=self.source();self.assertNotIn(1,ControllerConfiguration.from_controller(c).compatibility_attributes())

    def test_configured_alias_names_uids_and_namespaced_handlers_are_unavailable(self):
        for name in ('PowerLossProgram','PowerUpHandlerProgram','PowerLossProgramUId','MajorFaultProgram','MajorFaultProgramUId','powerlossprogram','MAJORFAULTPROGRAM'):
            for qualified in (name,'{urn:test}'+name):
                root,c=self.source();c.set(qualified,'Handler')
                value=ControllerConfiguration.from_controller(c,root)
                attr=6 if 'fault' in name.lower() else 1
                self.assertNotIn(attr,value.compatibility_attributes())
        root,c=self.source(PowerLossProgram='',MajorFaultProgram='')
        self.assertTrue(ControllerConfiguration.from_controller(c,root).empty_fault_handler)

    def test_anonymous_context_never_claims_a_multi_workstation_edit_slot(self):
        root,c=self.source();value=ControllerConfiguration.from_controller(c,root)
        self.assertEqual(value.compatibility_attributes()[8],bytes(2))
        self.assertFalse(value.description()['multi_workstation_edit_slot'])
        self.assertFalse(value.description()['operator_registration'])
        self.assertFalse(value.description()['authority_services'])


if __name__=='__main__':unittest.main()
