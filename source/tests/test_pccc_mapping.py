"""Empty legacy mapping metadata must not conceal configured or unknown maps."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.model import Project
from logixlab.pccc_mapping import PcccMapping
from logixlab.server import Application


class PcccMappingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=Endpoint(self.app,0,True,'logix-v35-l85e');self.app.endpoint=self.endpoint
        self.root=E.parse(self.app.engine.project.path).getroot()

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def mapping(self,root):return PcccMapping.from_source(root,root.find('Controller'))

    def send(self,path=bytes.fromhex('20672401'),service=0x0E,data=b''):
        return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data,Session())

    def test_complete_unmapped_source_has_exact_zero_descriptors_and_truthful_limits(self):
        mapping=self.mapping(self.root)
        self.assertEqual(mapping.attributes(),{1:bytes(2),2:bytes(4)})
        self.assertTrue(mapping.description()['empty_mapping_available'])
        for name in ('configured_mapping_upload','pccc_commands','mapping_execution','compiled_addresses'):
            self.assertFalse(mapping.description()[name])

    def test_explicit_disabled_plc2_flags_are_recognized_only_on_produce_info(self):
        for flag in ('false','0'):
            root=copy.deepcopy(self.root);tag=root.find('./Controller/Tags/Tag')
            tag.set('TagType','Produced');E.SubElement(tag,'ProduceInfo',PLC2Mapping=flag)
            self.assertTrue(self.mapping(root).empty)
        root=copy.deepcopy(self.root);tag=root.find('./Controller/Tags/Tag')
        E.SubElement(tag,'ProduceInfo',ProduceCount='2')
        self.assertTrue(self.mapping(root).empty)

    def test_configured_or_malformed_mapping_fields_never_become_empty(self):
        for key,values in (('PLC2Mapping',('true','1','FALSE','',' false','2')),
                           ('PLCMappingFile',('7','0','','-1','NaN'))):
            for value in values:
                with self.subTest(key=key,value=value):
                    root=copy.deepcopy(self.root)
                    E.SubElement(root.find('./Controller/Tags/Tag'),'ProduceInfo',**{key:value})
                    mapping=self.mapping(root);self.assertFalse(mapping.empty)
                    self.assertEqual(mapping.attributes(),{})
                    self.assertIsNone(mapping.description()['plc2_file'])

    def test_mapping_fields_on_tags_or_program_tags_are_ambiguous(self):
        for mode in ('tag','program'):
            root=copy.deepcopy(self.root)
            if mode=='tag':root.find('./Controller/Tags/Tag').set('PLC2Mapping','false')
            else:
                tag=E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='Local',DataType='INT')
                E.SubElement(tag,'ProduceInfo',PLC2Mapping='false')
            self.assertFalse(self.mapping(root).empty)

    def test_namespaces_case_variants_uid_only_and_duplicate_declarations_are_unknown(self):
        for mode in ('namespace','lowercase','attribute_namespace','attribute_case','uid','element','duplicate'):
            with self.subTest(mode=mode):
                root=copy.deepcopy(self.root);tag=root.find('./Controller/Tags/Tag')
                if mode=='namespace':E.SubElement(tag,'{extra}ProduceInfo')
                elif mode=='lowercase':E.SubElement(tag,'produceinfo')
                elif mode=='element':E.SubElement(tag,'PLCMappingFile')
                elif mode=='duplicate':E.SubElement(tag,'ProduceInfo');E.SubElement(tag,'ProduceInfo')
                else:
                    key={'attribute_namespace':'{extra}PLC2Mapping','attribute_case':'plc2mapping','uid':'PLC2MappingUId'}[mode]
                    E.SubElement(tag,'ProduceInfo',**{key:'0'})
                self.assertFalse(self.mapping(root).empty)

    def test_incomplete_exports_and_context_tags_cannot_establish_absence(self):
        for mode in ('context','target','missing_tags','tag_context','program_context','namespace_tags'):
            root=copy.deepcopy(self.root);controller=root.find('Controller')
            if mode=='context':root.set('ContainsContext','true')
            elif mode=='target':root.set('TargetType','Tag')
            elif mode=='missing_tags':controller.remove(controller.find('Tags'))
            elif mode=='tag_context':controller.find('./Tags/Tag').set('Use','Context')
            elif mode=='program_context':controller.find('./Programs/Program').set('Use','Context')
            else:E.SubElement(controller,'{extra}Tags')
            self.assertFalse(self.mapping(root).empty)

    def test_single_and_native_requested_list_match_field_widths(self):
        self.assertEqual(self.send(bytes.fromhex('206724013001')),bytes.fromhex('8e0000000000'))
        self.assertEqual(self.send(bytes.fromhex('206724013002')),bytes.fromhex('8e00000000000000'))
        self.assertEqual(self.send(service=3,data=struct.pack('<3H',2,1,2)),
                         bytes.fromhex('8300000002000100000000000200000000000000'))

    def test_class_inventory_and_revision_describe_one_model_object(self):
        self.assertEqual(self.send(bytes.fromhex('206724003001')),bytes.fromhex('8e0000000100'))
        self.assertEqual(self.send(bytes.fromhex('206724003002')),bytes.fromhex('8e0000000100'))
        self.assertEqual(self.send(bytes.fromhex('206724003003')),bytes.fromhex('8e0000000100'))
        result=self.send(bytes.fromhex('20022401'),service=1)
        ids=struct.unpack('<'+'H'*((len(result)-4)//2),result[4:])
        self.assertEqual(ids[0],len(ids)-1);self.assertEqual(ids.count(0x67),1)

    def test_mixed_list_preserves_supported_values_and_reports_missing_fields(self):
        result=self.send(service=3,data=struct.pack('<4H',3,1,99,2))
        self.assertEqual(result,bytes.fromhex('83000a000300010000000000630014000200000000000000'))
        row=self.endpoint.state()['attribute_gaps'][0]
        self.assertEqual(row['class_name'],'PCCC Mapping')
        self.assertEqual([a['id'] for a in row['attributes']],[99])

    def test_nonempty_source_is_unavailable_and_replacing_project_restores_empty(self):
        E.SubElement(self.root.find('./Controller/Tags/Tag'),'ProduceInfo',PLCMappingFile='7')
        path=Path(self.tmp.name)/'mapped.L5X';E.ElementTree(self.root).write(path)
        self.app.engine.project=Project(path)
        self.assertFalse(self.app.engine.project.pccc_mapping.description()['empty_mapping_available'])
        self.assertEqual(self.send(bytes.fromhex('206724013001'))[2],0x14)
        self.assertEqual(self.send(service=3,data=struct.pack('<3H',2,1,2)),
                         bytes.fromhex('83000a0002000100140002001400'))
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.send(bytes.fromhex('206724013002'))[2],0)

    def test_paths_lengths_and_pccc_execution_or_setters_preserve_tags(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        path=bytes.fromhex('20672401')
        cases=((bytes.fromhex('2067'),0x0E,b'',4),(bytes.fromhex('20672402'),0x0E,b'',5),
               (symbol_path('Program:MainProgram')+path,0x0E,b'',4),
               (bytes.fromhex('20682401')+path,0x0E,b'',4),
               (path+bytes.fromhex('3001'),0x0E,b'\0',0x15),
               (path,3,bytes.fromhex('02000100'),0x13),(path,3,bytes(2),3),
               (path,0x4B,b'',8),(path,0x10,bytes(4),8),(path,1,b'',8))
        for target,service,data,status in cases:
            with self.subTest(target=target.hex(),service=service):
                self.assertEqual(self.send(target,service,data)[2],status)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_stopped_endpoint_does_not_report_available_mapping_metadata(self):
        self.assertIsNone(self.endpoint.state()['pccc_mapping'])
        self.app.endpoint=None
        self.assertIsNone(self.app.connectivity()['pccc_mapping'])


if __name__=='__main__':unittest.main()
