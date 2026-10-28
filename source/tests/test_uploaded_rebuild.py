"""Offline upload rebuilds must retain native evidence and revoke Online correlation."""
import copy
import json
import unittest
from unittest.mock import patch

from tools import rebuild_uploaded_acd as rebuild
import test_upload_content as content_tests
from test_native_project import container, FIELDS


class UploadedRebuildTests(unittest.TestCase):
    setUp = content_tests.UploadContentTests.setUp
    plan = content_tests.UploadContentTests.plan
    receipt = content_tests.UploadContentTests.receipt

    def program_receipt(self, expected):
        from xml.etree import ElementTree as ET
        receipt=content_tests.UploadContentTests.program_receipt(self,expected)
        for target, row in zip(expected['programs'],receipt['programs'],strict=True):
            path=self.folder/row['fileName'];tree=ET.fromstring(path.read_bytes())
            programs=tree.find('./Controller/Programs')
            for program in list(programs):
                if program.get('Name')!=target['name']: programs.remove(program)
            path.write_bytes(ET.tostring(tree));row['sha256']=rebuild.digest(path)
        return receipt

    def expected(self):
        return dict(self.plan(),rebuildSourceSchema=rebuild.source_schema(self.project))
    def inputs(self):
        source = self.folder / 'source.ACD'
        source.write_bytes(container(fields={**FIELDS,10:0,11:0}))
        expected = self.plan()
        state = copy.deepcopy(self.state)
        state['connectivity']['native_download'] = dict(installed=True,source_equivalent=True)
        receipt = self.receipt(expected)
        receipt['programs'] = self.program_receipt(expected)['programs']
        files = {
            'summary.json': dict(status='succeeded',native_sdk_offline_confirmed=True,cleanup_confirmed=True,
                                 sdk_server_faulted=False,source_unchanged=True,model_unchanged=True),
            'request.json': dict(Operation='upload',UploadNewProject=False,
                                 ControllerSourceSha256=rebuild.digest(source),UploadContent=expected),
            'sdk-result.json': dict(uploadedContent=receipt),
            'before-state.json': state, 'after-state.json': copy.deepcopy(state)}
        for name, value in files.items():
            (self.folder / name).write_text(json.dumps(value),encoding='utf8')
        return source, files

    def prepared(self, source):
        with patch.object(rebuild.NativeTypes,'from_acd',return_value=self.types):
            return rebuild.prepare(source,self.project.path,self.folder)

    def test_rebuild_accepts_original_source_without_a_saved_download_baseline(self):
        source, _ = self.inputs()
        manifest, expected, types = self.prepared(source)
        self.assertEqual(manifest['sourceSha256'],rebuild.digest(source))
        self.assertEqual(len(manifest['programs']),1)
        self.assertEqual(len(expected['tags']),14)
        self.assertIs(types,self.types)

    def test_requested_controller_tag_exports_are_revalidated_before_rebuild(self):
        from test_upload_tag_definitions import UploadedTagDefinitionTests
        source,files=self.inputs()
        files['request.json']['ExportUploadedTags']=True
        tag_receipt=UploadedTagDefinitionTests.artifact(self)
        files['sdk-result.json']['uploadedContent']['controllerTags']=tag_receipt['controllerTags']
        for name in ('request.json','sdk-result.json'):(self.folder/name).write_text(json.dumps(files[name]))
        self.prepared(source)
        path=self.folder/tag_receipt['controllerTags']['fileName']
        path.write_bytes(path.read_bytes().replace(b'Value="50"',b'Value="51"'))
        files['sdk-result.json']['uploadedContent']['controllerTags']['sha256']=rebuild.digest(path)
        (self.folder/'sdk-result.json').write_text(json.dumps(files['sdk-result.json']))
        with self.assertRaises(ValueError):self.prepared(source)

    def test_requested_missing_or_invalid_tag_export_cannot_fall_back_to_old_receipt(self):
        for flag in (True,'true',1):
            source,files=self.inputs();files['request.json']['ExportUploadedTags']=flag
            (self.folder/'request.json').write_text(json.dumps(files['request.json']))
            with self.subTest(flag=flag),self.assertRaises(ValueError):self.prepared(source)

    def test_failed_uncertain_faulted_or_unclean_upload_is_not_rebuilt(self):
        for change in (dict(status='unknown'),dict(status='failed'),dict(sdk_server_faulted=True),
                       dict(cleanup_confirmed=False),dict(native_sdk_offline_confirmed=False),dict(source_unchanged=False)):
            source, files = self.inputs()
            (self.folder/'summary.json').write_text(json.dumps(dict(files['summary.json'],**change)))
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prepared(source)

    def test_changed_source_model_or_recorded_plan_is_rejected(self):
        for change in ('source','model','plan','binding'):
            source, files = self.inputs()
            if change == 'source':
                source.write_bytes(source.read_bytes()+b'changed')
            elif change == 'model':
                files['after-state.json']['tags'][0]['value'] = 'changed'
                (self.folder/'after-state.json').write_text(json.dumps(files['after-state.json']))
            else:
                if change == 'plan': files['request.json']['UploadContent']['tags'][0]['expectedHex'] = 'ff'
                else: files['request.json']['ControllerSourceSha256'] = '0'*64
                (self.folder/'request.json').write_text(json.dumps(files['request.json']))
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prepared(source)

    def test_changed_native_package_or_value_receipt_cannot_hide_behind_success(self):
        for change in ('package','routine','value'):
            source, files = self.inputs()
            if change == 'value':
                files['sdk-result.json']['uploadedContent']['tags'][0]['actualHex'] = 'ff'
                (self.folder/'sdk-result.json').write_text(json.dumps(files['sdk-result.json']))
            else:
                entry = files['sdk-result.json']['uploadedContent']['programs' if change=='package' else 'routines'][0]
                path = self.folder/entry['fileName']
                path.write_bytes(path.read_bytes()+b'changed')
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.prepared(source)

    def artifacts(self):
        acd = self.folder/'rebuilt.ACD'; xml = self.folder/'rebuilt.L5X'
        acd.write_bytes(container(fields={**FIELDS,10:0,11:1}))
        xml.write_bytes(self.project.path.read_bytes())
        return dict(status='succeeded',offlineOnly=True,nativeAcdReopened=True,cleanupConfirmed=True,
                    directUploadedProjectSave=False,acdSha256=rebuild.digest(acd),l5xSha256=rebuild.digest(xml))

    def test_complete_reopened_content_is_verified_as_requiring_download(self):
        result = rebuild.verify(self.folder,self.expected(),self.types,self.artifacts())
        self.assertTrue(result['verified'])
        self.assertTrue(result['requires_download'])
        self.assertFalse(result['online_verified'])
        self.assertEqual(result['content']['rungs'],10)

    def test_complete_l5x_import_requires_actual_input_hash_and_native_import_step(self):
        receipt=self.artifacts();payload=self.project.path.read_bytes();path=self.folder/'input.L5X';path.write_bytes(payload)
        expected=dict(self.expected(),rebuildInputFormat='L5X',rebuildInputSha256=rebuild.digest(path))
        receipt.update(inputFormat='L5X',uploadedCompleteL5xImported=True,inputSha256=rebuild.digest(path),
            steps=[dict(method='Import assembled complete Controller L5X',status='succeeded')])
        result=rebuild.verify(self.folder,expected,self.types,receipt)
        self.assertTrue(result['verified']);self.assertTrue(result['uploaded_complete_l5x_imported'])
        self.assertFalse(result['original_acd_binary_used'])
        for field,value in (('inputFormat','ACD'),('inputSha256','0'*64),('uploadedCompleteL5xImported',False),('steps',[])):
            with self.subTest(field=field):
                self.assertFalse(rebuild.verify(self.folder,expected,self.types,dict(receipt,**{field:value}))['verified'])
        path.write_bytes(payload+b'changed')
        self.assertFalse(rebuild.verify(self.folder,expected,self.types,receipt)['verified'])

    def test_correlation_edited_logic_values_or_missing_cleanup_reject_saved_result(self):
        for change in ('correlation','logic','value','hash','cleanup','reopen','task','priority','watchdog','type','malformed'):
            receipt = self.artifacts()
            acd = self.folder/'rebuilt.ACD'; xml = self.folder/'rebuilt.L5X'
            if change == 'correlation':
                acd.write_bytes(container(fields=FIELDS));receipt['acdSha256']=rebuild.digest(acd)
            elif change in ('logic','value'):
                raw=xml.read_bytes().replace(b'XIC(StartPB)',b'XIO(StartPB)') if change=='logic' else xml.read_bytes().replace(b'Value="50"',b'Value="87"')
                xml.write_bytes(raw);receipt['l5xSha256']=rebuild.digest(xml)
            elif change in ('task','priority','watchdog','type'):
                from xml.etree import ElementTree as ET
                tree=ET.fromstring(xml.read_bytes())
                if change in ('task','priority','watchdog'):
                    field,value={'task':('Rate','99'),'priority':('Priority','15'),'watchdog':('Watchdog','999')}[change]
                    tree.find('.//Tasks/Task').set(field,value)
                else:
                    data_types=ET.SubElement(tree.find('Controller'),'DataTypes')
                    ET.SubElement(data_types,'DataType',Name='ExtraType')
                xml.write_bytes(ET.tostring(tree));receipt['l5xSha256']=rebuild.digest(xml)
            elif change=='malformed': acd.write_bytes(b'malformed acd bytes');receipt['acdSha256']=rebuild.digest(acd)
            elif change=='hash': receipt['acdSha256']='0'*64
            elif change=='cleanup': receipt['cleanupConfirmed']=False
            else: receipt['nativeAcdReopened']=False
            with self.subTest(change=change):
                self.assertFalse(rebuild.verify(self.folder,self.expected(),self.types,receipt)['verified'])

    def test_import_order_follows_task_schedule_instead_of_alphabetic_program_names(self):
        from xml.etree import ElementTree as ET
        tree=ET.fromstring(self.project.path.read_bytes())
        controller=tree.find('Controller'); programs=controller.find('Programs')
        auxiliary=copy.deepcopy(programs[0]);auxiliary.set('Name','AuxProgram');programs.append(auxiliary)
        ET.SubElement(controller.find('./Tasks/Task/ScheduledPrograms'),'ScheduledProgram',Name='AuxProgram')
        path=self.folder/'two-programs.L5X';path.write_bytes(ET.tostring(tree))
        import base64
        self.app.command('load',{'name':path.name,'content':base64.b64encode(path.read_bytes()).decode()})
        self.project=self.app.engine.project;self.state=self.app.state()
        self.state['connectivity']['source_l5x_sha256']=self.project.sha256
        source,_=self.inputs()
        self.types.source_l5x_sha256=self.project.sha256
        manifest,_,_=self.prepared(source)
        self.assertEqual([p['name'] for p in manifest['programs']],['MainProgram','AuxProgram'])
        self.assertEqual([p['fileName'] for p in manifest['programs']],['uploaded-program-0001.L5X','uploaded-program-0000.L5X'])
