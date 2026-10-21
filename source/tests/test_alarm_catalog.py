"""Alarm discovery cannot conceal unsupported or incomplete source objects."""
import copy
import base64
from dataclasses import replace
import hashlib
import struct
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.alarm_catalog import AlarmCatalog, CLASSES, PROGRAM_CLASSES
from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.model import Project
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_symbols import NativeSymbols
from logixlab.server import Application
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import logical_path


class AlarmCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample':'ConveyorDemo'})
        self.endpoint = Endpoint(self.app, 0, False, 'logix-v35-l85e')
        self.root = E.parse(self.app.engine.project.path).getroot()

    def tearDown(self):
        self.app.close();self.tmp.cleanup()

    def catalog(self, root):
        return AlarmCatalog.from_source(root, root.find('Controller'))

    def call(self, path, data=b'', service=0x4B):
        return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data, Session())

    def bind_program(self,root=None,instance=472):
        root=copy.deepcopy(self.root if root is None else root)
        root.find('./Controller/Programs/Program').attrib.setdefault('UseAsFolder','false')
        content=E.tostring(root);source=hashlib.sha256(content).hexdigest()
        self.app.command('load',dict(name='alarms.L5X',content=base64.b64encode(content).decode(),
            native_project_identity=NativeProjectIdentity('a'*64,source,1,1,1,1,1,1).manifest(),
            native_symbols=NativeSymbols('a'*64,source,[],[dict(name='MainProgram',instance=instance)]).manifest()))

    def test_program_digital_and_analog_empty_lists_keep_original_parent_and_cursor_widths(self):
        for parent in (7,472,70000):
            self.bind_program(instance=parent);before=copy.deepcopy(self.app.state())
            for class_id in PROGRAM_CLASSES:
                for cursor in (0,1,0xffffffff):
                    self.assertEqual(self.call(logical_path(class_id,cursor,program=parent)),b'\xcb\0\0\0')
            for key in ('tags','controller','scan','ms','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])
        self.assertEqual(self.app.engine.project.alarm_catalog.description()['program_class_ids'],[0x331,0x332])

    def test_program_alarm_discovery_requires_current_original_identity_and_program_bindings(self):
        self.bind_program();path=logical_path(0x331,0,program=472)
        identity=self.app.native_project_identity;symbols=self.app.native_symbols
        for stale in (None,replace(identity,source_l5x_sha256='b'*64),replace(identity,source_acd_sha256='b'*64)):
            self.app.native_project_identity=stale;self.assertEqual(self.call(path)[2],0x0c)
        self.app.native_project_identity=identity
        for stale in (None,NativeSymbols('a'*64,'b'*64,[],[dict(name='MainProgram',instance=472)])):
            self.app.native_symbols=stale;self.assertEqual(self.call(path)[2],0x0c)
        self.app.native_symbols=symbols
        self.assertEqual(self.call(logical_path(0x331,0,program=473))[2],5)
        self.app.command('demo',{'sample':'ConveyorDemo'});self.assertEqual(self.call(path)[2],0x0c)

    def test_nonempty_or_incomplete_source_never_becomes_an_empty_program_alarm_catalog(self):
        for kind in ('alarm_tag','alarm_config','context','missing_tags','folder','opaque','safety'):
            root=copy.deepcopy(self.root);program=root.find('./Controller/Programs/Program')
            if kind=='alarm_tag':E.SubElement(program.find('Tags'),'Tag',Name='Alarm',DataType='ALARM_ANALOG',TagType='Base')
            elif kind=='alarm_config':E.SubElement(root.find('Controller'),'AlarmConfiguration')
            elif kind=='context':root.set('ContainsContext','true')
            elif kind=='missing_tags':program.remove(program.find('Tags'))
            elif kind=='folder':program.set('UseAsFolder','true')
            elif kind=='opaque':E.SubElement(program,'OpaqueProgramData')
            else:program.set('Class','Safety')
            self.bind_program(root)
            for class_id in PROGRAM_CLASSES:
                self.assertEqual(self.call(logical_path(class_id,0,program=472))[2],5 if kind=='safety' else 0x0c,kind)

    def test_program_alarm_paths_reject_other_scopes_payloads_attributes_and_mutations(self):
        self.bind_program();before=copy.deepcopy(self.app.state())
        for class_id in PROGRAM_CLASSES:
            path=logical_path(class_id,0,program=472)
            for target,data,service,status in ((path[:-2],b'',0x4b,4),(path+b'\x30\1',b'',0x4b,4),
                    (path,b'\0',0x4b,0x15),(symbol_path('Program:MainProgram')+path,b'',0x4b,4),
                    (path,b'',0x0e,8),(path,b'\0',0x10,8)):
                self.assertEqual(self.call(target,data,service)[2],status)
        for class_id in set(CLASSES)-set(PROGRAM_CLASSES):
            self.assertEqual(self.call(logical_path(class_id,0,program=472))[2],4)
        for parent in (0x338,0x8e):
            self.assertEqual(self.call(logical_path(parent,1)+logical_path(0x331,0))[2],4)
        for key in ('tags','controller','scan','ms','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])

    def test_program_alarm_reads_use_real_anonymous_signed_tcp_and_cleanup(self):
        self.bind_program();before=copy.deepcopy(self.app.state())
        self.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True);self.app.endpoint=self.endpoint
        self.endpoint.start()
        with AnonymousClient(self.endpoint) as client:
            client.bind()
            for class_id in PROGRAM_CLASSES:
                path=logical_path(class_id,0,program=472)
                self.assertEqual(client.request(bytes((0x4b,len(path)//2))+path),b'\xcb\0\0\0')
                self.assertNotEqual(client.request(bytes((0x10,len(path)//2))+path+b'\0')[2],0)
        for key in ('tags','controller','scan','ms','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])

    def test_alarm_free_source_has_empty_global_catalogs_with_any_cursor(self):
        self.assertTrue(self.catalog(self.root).empty)
        for class_id in CLASSES:
            for cursor in (0,1,0xFFFFFFFF):
                path=b'\x21\0'+class_id.to_bytes(2,'little')+b'\x26\0'+cursor.to_bytes(4,'little')
                self.assertEqual(self.call(path),b'\xCB\0\0\0')
        self.assertEqual(self.app.engine.project.alarm_catalog.description()['instance_count'],0)

    def test_controller_program_and_aoi_alarm_declarations_prevent_empty(self):
        for dtype in ('ALARM_DIGITAL','ALARM_ANALOG'):
            for scope in ('controller','program','aoi'):
                with self.subTest(dtype=dtype,scope=scope):
                    root=copy.deepcopy(self.root);controller=root.find('Controller')
                    if scope=='controller':parent=controller.find('Tags');name='Tag'
                    elif scope=='program':parent=controller.find('./Programs/Program/Tags');name='Tag'
                    else:
                        aoi=E.SubElement(controller.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='AlarmAOI')
                        parent=E.SubElement(aoi,'LocalTags');name='LocalTag'
                    E.SubElement(parent,name,Name='Alarm',DataType=dtype,TagType='Base')
                    self.assertFalse(self.catalog(root).empty)

    def test_alarm_data_and_parameters_are_detected_before_runtime_filtering(self):
        for mode in ('format','digital','analog','config','namespaced', 'definition', 'set', 'condition',
                     'tag-based', 'protected', 'encoded-format', 'encoded-attribute'):
            root=copy.deepcopy(self.root);tag=root.find('./Controller/Tags/Tag')
            if mode=='format':E.SubElement(tag,'Data',Format='Alarm')
            elif mode=='encoded-format':E.SubElement(tag,'Data',Format='Encoded')
            elif mode=='encoded-attribute':tag.set('ProtectedData','hidden')
            else:E.SubElement(tag,{'digital':'AlarmDigitalParameters','analog':'AlarmAnalogParameters','config':'AlarmConfig','namespaced':'{urn:extra}AlarmConfig',
                                  'definition':'AlarmDefinitions','set':'AlarmSet','condition':'AlarmConditionDefinition','tag-based':'TagBasedAlarm',
                                  'protected':'ProtectedContent'}[mode])
            self.assertFalse(self.catalog(root).empty)

    def test_incomplete_or_ambiguous_source_does_not_prove_empty(self):
        for mode in ('context','unknown_context','duplicate_controller','missing_tags','duplicate_tags',
                     'unknown_tag','unknown_type','tag_context','program_context','missing_program_tags',
                     'unknown_program','duplicate_programs','namespace'):
            with self.subTest(mode=mode):
                root=copy.deepcopy(self.root);controller=root.find('Controller');tags=controller.find('Tags')
                if mode=='context':root.set('ContainsContext','true')
                elif mode=='unknown_context':root.attrib.pop('ContainsContext')
                elif mode=='duplicate_controller':E.SubElement(root,'Controller')
                elif mode=='missing_tags':controller.remove(tags)
                elif mode=='duplicate_tags':E.SubElement(controller,'Tags')
                elif mode=='unknown_tag':E.SubElement(tags,'EncryptedTags')
                elif mode=='unknown_type':tags[0].attrib.pop('DataType')
                elif mode=='tag_context':tags[0].set('Use','Context')
                elif mode=='program_context':controller.find('./Programs/Program').set('Use','Context')
                elif mode=='missing_program_tags':
                    program=controller.find('./Programs/Program');program.remove(program.find('Tags'))
                elif mode=='unknown_program':E.SubElement(controller.find('Programs'),'EncryptedProgram')
                elif mode=='duplicate_programs':E.SubElement(controller,'Programs')
                else:E.SubElement(controller,'{urn:extra}Tags')
                self.assertFalse(self.catalog(root).empty)

    def test_nonempty_source_is_unavailable_until_project_replaced(self):
        tag=self.root.find('./Controller/Tags/Tag');tag.set('DataType','ALARM_DIGITAL')
        path=Path(self.tmp.name)/'alarm.L5X';E.ElementTree(self.root).write(path)
        self.app.engine.project=Project(path)
        for class_id in CLASSES:
            self.assertEqual(self.call(bytes.fromhex('2100')+struct.pack('<H',class_id)+bytes.fromhex('2400'))[2],0x0C)
        self.assertIsNone(self.app.engine.project.alarm_catalog.description()['instance_count'])
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.call(bytes.fromhex('210031032400')),b'\xCB\0\0\0')

    def test_scoped_paths_payloads_and_mutations_are_rejected_without_state_changes(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        for class_id in CLASSES:
            path=bytes.fromhex('2100')+struct.pack('<H',class_id)+bytes.fromhex('2400')
            for target,data,service,status in ((path[:-2],b'',0x4B,4),(path+b'\x30\1',b'',0x4B,4),
                    (path,b'\0',0x4B,0x15),(symbol_path('Program:MainProgram')+path,b'',0x4B,4),
                    (path,b'',0x0E,8),(path,b'\0',0x10,8)):
                self.assertEqual(self.call(target,data,service)[2],status)
        self.assertEqual(self.app.engine.memory.values,before)


if __name__=='__main__':unittest.main()
