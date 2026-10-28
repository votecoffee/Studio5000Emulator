"""Source-context reconstruction must consume actual complete upload artifacts."""
import base64
import copy
import json
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from tools import uploaded_l5x as reconstruction,rebuild_uploaded_acd as rebuild
import test_uploaded_rebuild as fixtures
import test_upload_tag_definitions as tag_fixtures


class UploadedL5xTests(unittest.TestCase):
    setUp=fixtures.UploadedRebuildTests.setUp
    plan=fixtures.UploadedRebuildTests.plan
    receipt=fixtures.UploadedRebuildTests.receipt
    program_receipt=fixtures.UploadedRebuildTests.program_receipt
    inputs=fixtures.UploadedRebuildTests.inputs

    def evidence(self):
        source,files=self.inputs();tag_receipt=tag_fixtures.UploadedTagDefinitionTests.artifact(self)
        files['request.json']['ExportUploadedTags']=True
        files['sdk-result.json']['uploadedContent']['controllerTags']=tag_receipt['controllerTags']
        self.store(files)
        return source,files

    def store(self,files):
        for name,value in files.items():(self.folder/name).write_text(json.dumps(value),encoding='utf8')

    def assemble(self,source):
        with patch.object(rebuild.NativeTypes,'from_acd',return_value=self.types):
            return reconstruction.assemble(source,self.project.path,self.folder)

    def test_complete_document_uses_actual_uploaded_values_and_program_documentation(self):
        source,files=self.evidence();original=self.project.path.read_bytes()
        # Current uploaded value differs from the original L5X/ACD context.
        for name in ('before-state.json','after-state.json'):
            next(t for t in files[name]['tags'] if t['name']=='SpeedSetpoint')['value']=87
        planned=files['request.json']['UploadContent']
        next(t for t in planned['tags'] if t['name']=='SpeedSetpoint')['expectedHex']='57000000'
        next(t for t in files['sdk-result.json']['uploadedContent']['tags'] if t['name']=='SpeedSetpoint')['actualHex']='57000000'
        tag_entry=files['sdk-result.json']['uploadedContent']['controllerTags'];path=self.folder/tag_entry['fileName']
        root=ET.fromstring(path.read_bytes());root.find(".//Tag[@Name='SpeedSetpoint']/Data/DataValue").set('Value','87')
        path.write_bytes(ET.tostring(root));tag_entry['sha256']=rebuild.digest(path)
        entry=files['sdk-result.json']['uploadedContent']['programs'][0];path=self.folder/entry['fileName']
        root=ET.fromstring(path.read_bytes());rung=root.find('.//Program/Routines/Routine/RLLContent/Rung')
        comment=rung.find('Comment')
        if comment is None:comment=ET.SubElement(rung,'Comment')
        comment.text='Actual uploaded documentation'
        path.write_bytes(ET.tostring(root));entry['sha256']=rebuild.digest(path);self.store(files)
        payload=self.assemble(source);root=ET.fromstring(payload);output=self.folder/'assembled.L5X';output.write_bytes(payload)
        self.assertEqual(root.get('TargetType'),'Controller');self.assertEqual(root.get('ContainsContext'),'false')
        self.assertEqual(root.find(".//Tag[@Name='SpeedSetpoint']/Data/DataValue").get('Value'),'87')
        self.assertEqual(root.find('.//Program/Routines/Routine/RLLContent/Rung/Comment').text,'Actual uploaded documentation')
        self.assertFalse(any(n.get('Use') is not None for n in root.findall('./Controller/Tags/Tag')+root.findall('./Controller/Programs/Program')))
        expected=dict(planned,rebuildSourceSchema=rebuild.source_schema(self.project))
        self.assertTrue(reconstruction.verify(output,expected,self.types)['verified'])
        self.assertEqual(self.project.path.read_bytes(),original)

    def test_absent_requested_controller_tag_export_cannot_substitute_source_tags(self):
        source,files=self.evidence();files['request.json']['ExportUploadedTags']=False;self.store(files)
        with self.assertRaisesRegex(ValueError,'actual requested controller-tag'):self.assemble(source)

    def test_corrupt_controller_export_rejects_instead_of_using_original_values(self):
        source,files=self.evidence();entry=files['sdk-result.json']['uploadedContent']['controllerTags']
        (self.folder/entry['fileName']).write_bytes(b'<changed')
        with self.assertRaises(ValueError):self.assemble(source)

    def test_unverified_alternative_value_representations_are_removed(self):
        source,files=self.evidence();entry=files['sdk-result.json']['uploadedContent']['controllerTags']
        path=self.folder/entry['fileName'];root=ET.fromstring(path.read_bytes())
        ET.SubElement(root.find(".//Tag[@Name='SpeedSetpoint']"),'Data',Format='L5K').text='999'
        path.write_bytes(ET.tostring(root));entry['sha256']=rebuild.digest(path);self.store(files)
        root=ET.fromstring(self.assemble(source));tag=root.find(".//Tag[@Name='SpeedSetpoint']")
        self.assertEqual([n.get('Format') for n in tag.findall('Data')],['Decorated'])
        self.assertEqual(tag.find('./Data/DataValue').get('Value'),'50')

    def test_full_source_program_order_and_distinct_task_schedule_are_preserved(self):
        tree=ET.fromstring(self.project.path.read_bytes());controller=tree.find('Controller');programs=controller.find('Programs')
        other=copy.deepcopy(programs[0]);other.set('Name','AuxProgram');programs.append(other)
        ET.SubElement(controller.find('./Tasks/Task/ScheduledPrograms'),'ScheduledProgram',Name='AuxProgram')
        path=self.folder/'two-programs.L5X';path.write_bytes(ET.tostring(tree))
        self.app.command('load',dict(name=path.name,content=base64.b64encode(path.read_bytes()).decode()))
        self.project=self.app.engine.project;self.state=self.app.state();self.state['connectivity']['source_l5x_sha256']=self.project.sha256
        self.types.source_l5x_sha256=self.project.sha256
        source,_=self.evidence();root=ET.fromstring(self.assemble(source))
        self.assertEqual([p.get('Name') for p in root.findall('./Controller/Programs/Program')],['MainProgram','AuxProgram'])
        self.assertEqual([p.get('Name') for p in root.findall('.//ScheduledProgram')],['MainProgram','AuxProgram'])

    def test_program_local_current_values_come_from_uploaded_package(self):
        tree=ET.fromstring(self.project.path.read_bytes());program=tree.find('./Controller/Programs/Program')
        tags=program.find('Tags')
        if tags is None:tags=ET.SubElement(program,'Tags')
        tag=ET.SubElement(tags,'Tag',Name='LocalValue',TagType='Base',DataType='DINT',Constant='false')
        ET.SubElement(ET.SubElement(tag,'Data',Format='Decorated'),'DataValue',DataType='DINT',Value='3')
        path=self.folder/'local-values.L5X';path.write_bytes(ET.tostring(tree))
        self.app.command('load',dict(name=path.name,content=base64.b64encode(path.read_bytes()).decode()))
        self.project=self.app.engine.project;self.state=self.app.state();self.state['connectivity']['source_l5x_sha256']=self.project.sha256
        self.types.source_l5x_sha256=self.project.sha256
        next(t for t in self.state['tags'] if t['name']=='Program:MainProgram.LocalValue')['value']=9
        source,files=self.evidence();entry=files['sdk-result.json']['uploadedContent']['programs'][0]
        exported=self.folder/entry['fileName'];tree=ET.fromstring(exported.read_bytes())
        tree.find(".//Program/Tags/Tag[@Name='LocalValue']/Data/DataValue").set('Value','9')
        exported.write_bytes(ET.tostring(tree));entry['sha256']=rebuild.digest(exported);self.store(files)
        root=ET.fromstring(self.assemble(source))
        self.assertEqual(root.find(".//Program/Tags/Tag[@Name='LocalValue']/Data/DataValue").get('Value'),'9')
        self.assertEqual(self.project.initial['program:mainprogram.localvalue'],3)

    def test_assembled_context_and_declarations_are_checked_before_native_import(self):
        source,files=self.evidence();payload=self.assemble(source);path=self.folder/'assembled.L5X'
        expected=dict(files['request.json']['UploadContent'],rebuildSourceSchema=rebuild.source_schema(self.project))
        for change in ('dimension','watchdog','logic','value'):
            tree=ET.fromstring(payload)
            if change=='dimension':tree.find(".//Tag[@Name='SpeedSetpoint']").set('Dimensions','2')
            elif change=='watchdog':tree.find('.//Tasks/Task').set('Watchdog','999')
            elif change=='logic':tree.find('.//Rung/Text').text='NOP();'
            else:tree.find(".//Tag[@Name='SpeedSetpoint']/Data/DataValue").set('Value','51')
            path.write_bytes(ET.tostring(tree))
            with self.subTest(change=change),self.assertRaises(ValueError):reconstruction.verify(path,expected,self.types)
