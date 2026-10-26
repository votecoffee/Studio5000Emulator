"""Partial tag exports must prove targeted definitions and current backing data."""
import copy
import hashlib
import unittest
from xml.etree import ElementTree as ET

from tools import upload_tag_definitions as tags
import test_upload_content as content


class UploadedTagDefinitionTests(unittest.TestCase):
    setUp=content.UploadContentTests.setUp
    plan=content.UploadContentTests.plan

    def artifact(self):
        root=ET.fromstring(self.project.path.read_bytes())
        root.attrib.update(SchemaRevision='1.0',SoftwareRevision='35.03',TargetType='Tag',TargetName='SpeedSetpoint',ContainsContext='true')
        controller=root.find('Controller');controller.set('Use','Context')
        for child in list(controller):
            if child.tag not in ('Tags','DataTypes'):controller.remove(child)
        for node in controller.findall('./Tags/Tag'):node.set('Use','Target')
        path=self.folder/tags.FILENAME;path.write_bytes(ET.tostring(root))
        return dict(offlineOnly=True,sourceL5xSha256=self.project.sha256,
            controllerTags=dict(fileName=tags.FILENAME,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))

    def verify(self,receipt=None):
        return tags.verify(self.folder,self.plan(),self.types,receipt or self.artifact(),self.project)

    def mutate(self,root,receipt):
        path=self.folder/tags.FILENAME;path.write_bytes(ET.tostring(root))
        receipt['controllerTags']['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()

    def test_complete_targeted_definition_and_values_are_distinct_from_acd_persistence(self):
        result=self.verify()
        self.assertTrue(result['verified'] and result['definitions_verified'] and result['serialized_values_verified'])
        self.assertEqual((result['controller_tags_verified'],result['value_bytes']),(14,45))
        self.assertTrue(result['partial_export']);self.assertFalse(result['native_acd_saved'])

    def test_source_value_is_not_accepted_when_current_uploaded_value_differs(self):
        receipt=self.artifact()
        next(row for row in self.state['tags'] if row['name']=='SpeedSetpoint')['value']=87
        self.assertFalse(self.verify(receipt)['verified'])
        root=ET.fromstring((self.folder/tags.FILENAME).read_bytes())
        root.find(".//Tag[@Name='SpeedSetpoint']/Data[@Format='Decorated']/DataValue").set('Value','87')
        self.mutate(root,receipt);self.assertTrue(self.verify(receipt)['verified'])

    def test_changed_definitions_values_context_or_coverage_fail_despite_matching_hash(self):
        changes=('type','constant','access','class','alias','value','dimension','context','missing','duplicate','extra','no-data','ambiguous-data','wrong-controller','wrong-target')
        for change in changes:
            receipt=self.artifact();root=ET.fromstring((self.folder/tags.FILENAME).read_bytes())
            node=root.find(".//Tag[@Name='SpeedSetpoint']");parent=root.find('./Controller/Tags')
            if change in ('type','constant','access','class','alias','dimension','context'):
                field,value={'type':('DataType','INT'),'constant':('Constant','true'),'access':('ExternalAccess','None'),
                    'class':('Class','Safety'),'alias':('AliasFor','SpeedCommand'),'dimension':('Dimensions','2'),
                    'context':('Use','Context')}[change]
                node.set(field,value)
            elif change=='value':node.find("Data[@Format='Decorated']/DataValue").set('Value','51')
            elif change=='missing':parent.remove(node)
            elif change=='duplicate':parent.append(copy.deepcopy(node))
            elif change=='extra':
                extra=copy.deepcopy(node);extra.set('Name','Foreign');parent.append(extra)
            elif change=='no-data':node.remove(node.find("Data[@Format='Decorated']"))
            elif change=='ambiguous-data':node.append(copy.deepcopy(node.find("Data[@Format='Decorated']")))
            elif change=='wrong-controller':root.find('Controller').set('Name','Foreign')
            else:root.set('TargetType','Program')
            self.mutate(root,receipt)
            with self.subTest(change=change):self.assertFalse(self.verify(receipt)['verified'])

    def test_bad_or_incomplete_native_receipts_and_wrong_file_do_not_count(self):
        receipt=self.artifact()
        for altered in (None,{},dict(receipt,offlineOnly=False),dict(receipt,sourceL5xSha256='a'*64),
                        dict(receipt,controllerTags=None),dict(receipt,controllerTags=dict(fileName='../foreign.L5X',sha256=receipt['controllerTags']['sha256'])),
                        dict(receipt,controllerTags=dict(fileName=tags.FILENAME,sha256='a'*64))):
            with self.subTest(receipt=altered):self.assertFalse(tags.verify(self.folder,self.plan(),self.types,altered,self.project)['verified'])

    def test_malformed_xml_and_entities_are_failed_evidence(self):
        for raw in (b'<RSLogix5000Content malformed',b'<!DOCTYPE evil><RSLogix5000Content/>'):
            receipt=self.artifact();path=self.folder/tags.FILENAME;path.write_bytes(raw)
            receipt['controllerTags']['sha256']=hashlib.sha256(raw).hexdigest()
            self.assertFalse(self.verify(receipt)['verified'])

    def test_declared_bool_bits_remain_distinct_from_packed_table_words(self):
        import base64
        root=ET.fromstring(self.project.path.read_bytes());parent=root.find('./Controller/Tags')
        node=ET.SubElement(parent,'Tag',Name='Bits',TagType='Base',DataType='BOOL',Dimensions='32',Constant='true',ExternalAccess='Read Only')
        array=ET.SubElement(ET.SubElement(node,'Data',Format='Decorated'),'Array',DataType='BOOL',Dimensions='32')
        for i in range(32):ET.SubElement(array,'Element',Index=f'[{i}]',Value=str(int(i in (0,7,31))))
        path=self.folder/'bits.L5X';path.write_bytes(ET.tostring(root))
        self.app.command('load',dict(name=path.name,content=base64.b64encode(path.read_bytes()).decode()))
        self.project=self.app.engine.project;self.state=self.app.state()
        self.state['connectivity']['source_l5x_sha256']=self.project.sha256;self.types.source_l5x_sha256=self.project.sha256
        receipt=self.artifact();self.assertTrue(self.verify(receipt)['verified'])
        exported=ET.fromstring((self.folder/tags.FILENAME).read_bytes())
        exported.find(".//Tag[@Name='Bits']").set('Dimensions','1')
        self.mutate(exported,receipt);self.assertFalse(self.verify(receipt)['verified'])

    def test_option_is_explicit_and_only_extends_an_existing_project_content_check(self):
        tags.validate_options('upload',True,'source.L5X')
        for operation in ('connection','modes','download','edits'):
            tags.validate_options(operation,False,None)
            with self.assertRaises(ValueError):tags.validate_options(operation,True,'source.L5X')
        for value in (1,None,'true',[]):
            with self.assertRaises(ValueError):tags.validate_options('upload',value,'source.L5X')
        with self.assertRaises(ValueError):tags.validate_options('upload',True,None)
        with self.assertRaises(ValueError):tags.validate_options('upload',True,'source.L5X',True)
