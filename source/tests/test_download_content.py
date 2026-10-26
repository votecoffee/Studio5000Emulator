"""Native connection success cannot replace downloaded file content validation."""
import json
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET

import test_upload_content as content_tests
from test_native_project import container, FIELDS
from tools import download_content as content
from tools.probe_native_sdk import digest
from tools.rebuild_uploaded_acd import source_schema


class DownloadContentTests(unittest.TestCase):
    setUp = content_tests.UploadContentTests.setUp
    plan = content_tests.UploadContentTests.plan

    def expected(self):
        return dict(self.plan(),downloadSourceSchema=source_schema(self.project))

    def artifacts(self):
        (self.folder/'downloaded.ACD').write_bytes(container(fields=FIELDS))
        (self.folder/'downloaded.L5X').write_bytes(self.project.path.read_bytes())
        return dict(nativeAcdReopened=True,reopenedOnline=True,downloadResultSaved=True,offlineContentExported=True,
                    acdSha256=digest(self.folder/'downloaded.ACD'),reopenedL5xSha256=digest(self.folder/'downloaded.L5X'))

    def test_explicit_saved_download_and_source_bound_complete_plan_are_required(self):
        for operation in ('connection','upload','download','edits'):
            self.assertIsNone(content.prepare(operation,False,None,None,self.state))
            if operation != 'download':
                with self.assertRaises(ValueError):content.prepare(operation,True,self.project.path,None,self.state)
        for save in (False,None,1,'true'):
            with self.assertRaises(ValueError):content.prepare('download',save,self.project.path,None,self.state)
        with patch.object(content.upload_content.NativeTypes,'from_acd',return_value=self.types):
            result=content.prepare('download',True,self.project.path,'source.ACD',self.state)
        self.assertEqual(json.loads(json.dumps(result)),json.loads(json.dumps(self.expected())))

    def test_complete_saved_values_logic_and_task_schema_require_actual_native_receipt(self):
        receipt=self.artifacts();result=content.verify(self.folder,self.expected(),self.types,receipt)
        self.assertTrue(result['verified']);self.assertTrue(result['source_schema_preserved'])
        self.assertEqual(result['content']['tags'],14);self.assertEqual(result['content']['rungs'],10)
        for field in ('nativeAcdReopened','reopenedOnline','downloadResultSaved','offlineContentExported'):
            with self.subTest(field=field):
                self.assertFalse(content.verify(self.folder,self.expected(),self.types,dict(receipt,**{field:False}))['verified'])
        self.assertFalse(content.verify(self.folder,self.expected(),self.types,None)['verified'])

    def test_modified_files_or_receipt_hashes_do_not_pass(self):
        for change in ('acd','xml','acd-hash','xml-hash','missing'):
            receipt=self.artifacts()
            if change=='acd':(self.folder/'downloaded.ACD').write_bytes(b'changed acd bytes')
            elif change=='xml':(self.folder/'downloaded.L5X').write_bytes(b'<malformed>')
            elif change=='missing':(self.folder/'downloaded.L5X').unlink()
            else:receipt['acdSha256' if change=='acd-hash' else 'reopenedL5xSha256']='0'*64
            with self.subTest(change=change):
                self.assertFalse(content.verify(self.folder,self.expected(),self.types,receipt)['verified'])

    def test_valid_hash_and_online_receipt_cannot_hide_changed_values_logic_or_partial_export(self):
        for change in ('value','logic','partial','missing-root'):
            receipt=self.artifacts();path=self.folder/'downloaded.L5X';root=ET.fromstring(path.read_bytes())
            if change=='value':root.find('.//Tag[@Name="SpeedSetpoint"]/Data[@Format="Decorated"]/DataValue').set('Value','87')
            elif change=='logic':root.find('.//Routine/RLLContent/Rung/Text').text='NOP();'
            elif change=='partial':root.set('TargetType','Program')
            else:
                tags=root.find('./Controller/Tags');tags.remove(tags[0])
            path.write_bytes(ET.tostring(root));receipt['reopenedL5xSha256']=digest(path)
            with self.subTest(change=change):
                self.assertFalse(content.verify(self.folder,self.expected(),self.types,receipt)['verified'])

    def test_unchanged_value_bytes_do_not_hide_changed_task_settings_or_types(self):
        for field,value in (('Priority','15'),('Watchdog','999'),('DisableUpdateOutputs','true'),('ExtraType',None)):
            receipt=self.artifacts();path=self.folder/'downloaded.L5X';root=ET.fromstring(path.read_bytes())
            if value is not None:root.find('.//Tasks/Task').set(field,value)
            else:ET.SubElement(ET.SubElement(root.find('Controller'),'DataTypes'),'DataType',Name=field)
            path.write_bytes(ET.tostring(root));receipt['reopenedL5xSha256']=digest(path)
            with self.subTest(field=field):
                self.assertFalse(content.verify(self.folder,self.expected(),self.types,receipt)['verified'])
