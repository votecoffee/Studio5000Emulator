"""Pure source and in-memory protocol checks; no application or native runtime."""
import copy
from dataclasses import FrozenInstanceError
import struct
from types import SimpleNamespace
import unittest
from xml.etree import ElementTree as E

from logixlab.attribute_gaps import AttributeGaps
from logixlab.controller_configuration import ControllerConfiguration
from logixlab.ethernetip import CIPError,Path,Router
from tools.collection_inventory import decode_attribute_list


class ControllerChangeMaskTests(unittest.TestCase):
    def source(self,mask='16#ffff_ffff_ffff_ffff'):
        root=E.fromstring('<RSLogix5000Content TargetType="Controller" ContainsContext="false"><Controller Name="MaskTest"><Security Code="0"/><Tags/><Programs/></Controller></RSLogix5000Content>')
        controller=root.find('Controller')
        if mask is not None:controller.find('Security').set('ChangesToDetect',mask)
        return root,controller

    def config(self,root,controller):return ControllerConfiguration.from_controller(controller,root)

    def test_uint64_mask_encoding_retains_all_bits_without_signed_conversion_or_bit_filtering(self):
        for text,value in (('16#0',0),('16#1',1),('16#0123456789abcdef',0x0123456789ABCDEF),
                ('16#8000_0000_0000_0000',1<<63),('16#FFFF_FFFF_FFFF_FFFF',(1<<64)-1),('16#0_0001',1)):
            root,c=self.source(text);before=E.tostring(root);config=self.config(root,c)
            with self.subTest(text=text):
                self.assertEqual(config.attributes()[28],struct.pack('<Q',value))
                self.assertEqual(config.compatibility_attributes()[28],struct.pack('<Q',value))
                self.assertEqual(config.changes_to_detect,value)
                self.assertEqual(E.tostring(root),before)
        with self.assertRaises(FrozenInstanceError):config.changes_to_detect=0

    def test_missing_malformed_overflow_and_unsupported_radices_never_become_zero(self):
        for text in (None,'','0','-1','+1','0xffff','2#1111','8#77','16#-1','16#+1','16#',
                '16#_ffff','16#ffff_','16#ffff__ffff','16#ff_ff','16#1_0000_0000_0000_0000',
                '16#10000000000000000','16#'+'0'*1000,' 16#0','16#0 ','16#１２３４','16#fg'):
            root,c=self.source(text);config=self.config(root,c)
            with self.subTest(text=text):
                self.assertNotIn(28,config.attributes());self.assertIsNone(config.changes_to_detect)
                self.assertEqual(config.attributes()[13],bytes(4))

    def test_canonical_security_declaration_is_required_without_using_legacy_code_as_authority(self):
        for mode in ('missing','duplicate','namespace','case','uid','child','text','context','opaque','shadow'):
            root,c=self.source();node=c.find('Security')
            if mode=='missing':c.remove(node)
            elif mode=='duplicate':c.append(copy.deepcopy(node))
            elif mode in ('namespace','case','uid'):node.tag={'namespace':'{test}Security','case':'security','uid':'SecurityUId'}[mode]
            elif mode=='child':E.SubElement(node,'Unknown')
            elif mode=='text':node.text='unknown'
            elif mode=='context':node.set('Use','Context')
            elif mode=='opaque':node.set('Unknown','0')
            else:node.set('{test}ChangesToDetect','16#0')
            with self.subTest(mode=mode):self.assertNotIn(28,self.config(root,c).attributes())
        root,c=self.source();c.find('Security').set('Code','123')
        config=self.config(root,c);self.assertEqual(config.attributes()[28],bytes.fromhex('ffffffffffffffff'))
        self.assertFalse(config.description()['authority_services'])

    def test_complete_source_context_is_required_for_the_configuration_mask(self):
        for mode in ('no-root','root-context','controller-context','duplicate-controller','missing-tags','tag-context'):
            root,c=self.source()
            if mode=='root-context':root.set('ContainsContext','true')
            elif mode=='controller-context':c.set('Use','Context')
            elif mode=='duplicate-controller':root.append(copy.deepcopy(c))
            elif mode=='missing-tags':c.remove(c.find('Tags'))
            elif mode=='tag-context':c.find('Tags').set('Use','Context')
            value=ControllerConfiguration.from_controller(c,None if mode=='no-root' else root)
            with self.subTest(mode=mode):self.assertNotIn(28,value.attributes())

    def test_configuration_does_not_create_live_audit_values_memory_percentages_or_signatures(self):
        for text in ('16#0','16#ffff_ffff_ffff_ffff'):
            root,c=self.source(text);config=self.config(root,c);info=config.description()
            self.assertTrue(info['changes_to_detect_available']);self.assertEqual(info['changes_to_detect_bits'],64)
            for key in ('change_detection_audit_value','change_detection_events_recorded','state_detection_signatures','source_settings_writable'):
                self.assertFalse(info[key])
            for number in (11,12,27,33,34):self.assertNotIn(number,config.compatibility_attributes())

    def test_in_memory_single_list_reads_and_write_rejection_preserve_source(self):
        root,c=self.source('16#8000_0000_0000_0001');config=self.config(root,c);before=E.tostring(root);calls=[]
        fake=SimpleNamespace(endpoint=SimpleNamespace(record_attribute_gap=lambda path,missing,service:calls.append((tuple(missing),service))))
        path=Path(class_id=0x8E,instance=1,attribute=28)
        self.assertEqual(Router.attribute_read(fake,14,path,b'',config.attributes()),(0,struct.pack('<Q',0x8000000000000001)))
        requested=(28,27,28,33,11);payload=struct.pack('<6H',len(requested),*requested)
        status,data=Router.attribute_read(fake,3,Path(class_id=0x8E,instance=1),payload,config.attributes())
        rows=decode_attribute_list(bytes((0x83,0,status,0))+data,requested,0x8E,include_payloads=True)['attributes']
        self.assertEqual([r['status'] for r in rows],[0,20,0,20,20]);self.assertEqual(rows[0],rows[2])
        self.assertEqual(rows[0]['data_hex'],'0100000000000080');self.assertEqual(calls,[((27,33,11),3)])
        for service in (4,16):
            with self.assertRaises(CIPError) as caught:Router.attribute_read(fake,service,path,bytes(8),config.attributes())
            self.assertEqual(caught.exception.status,8)
        self.assertEqual(E.tostring(root),before)

    def test_named_controller_gaps_distinguish_configuration_from_live_audit_and_signature_state(self):
        gaps=AttributeGaps();gaps.record(0x8E,1,None,'',(11,12,27,28,33,34,65000),7,3)
        rows=gaps.snapshot(7);names={x['id']:x['name'] for x in rows[0]['attributes']}
        self.assertEqual(names[28],'CCUID Configuration (ChangesToDetect)')
        self.assertEqual(names[27],'CCUID Value (Audit Value)')
        self.assertEqual(names[11],'Percent Free I/O Memory')
        self.assertEqual(names[33],'State Detection Static Signature')
        self.assertEqual(names[65000],'Attribute 65000')
        self.assertNotIn('data_hex',str(rows));self.assertEqual(gaps.snapshot(8),[])


if __name__=='__main__':unittest.main()
