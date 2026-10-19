"""Message discovery cannot conceal unsupported or incomplete source objects."""
import copy
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.message_catalog import MessageCatalog
from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.model import Project
from logixlab.server import Application


class MessageCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample':'ConveyorDemo'})
        self.endpoint = Endpoint(self.app, 0, False, 'logix-v35-l85e')
        self.root = E.parse(self.app.engine.project.path).getroot()

    def tearDown(self):
        self.app.close();self.tmp.cleanup()

    def catalog(self, root):
        return MessageCatalog.from_source(root, root.find('Controller'))

    def call(self, path, data=b'', service=0x4B):
        return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data, Session())

    def test_message_free_source_has_empty_global_catalogs_with_any_cursor(self):
        self.assertTrue(self.catalog(self.root).empty)
        for class_id in (0x8D,):
            for cursor in (0,1,0xFFFFFFFF):
                path=b'\x21\0'+class_id.to_bytes(2,'little')+b'\x26\0'+cursor.to_bytes(4,'little')
                self.assertEqual(self.call(path),b'\xCB\0\0\0')
        self.assertEqual(self.app.engine.project.message_catalog.description()['instance_count'],0)

    def test_controller_program_and_aoi_message_declarations_prevent_empty(self):
        for dtype in ('MESSAGE',):
            for scope in ('controller','program','aoi'):
                with self.subTest(dtype=dtype,scope=scope):
                    root=copy.deepcopy(self.root);controller=root.find('Controller')
                    if scope=='controller':parent=controller.find('Tags');name='Tag'
                    elif scope=='program':parent=controller.find('./Programs/Program/Tags');name='Tag'
                    else:
                        aoi=E.SubElement(controller.find('AddOnInstructionDefinitions'),'AddOnInstructionDefinition',Name='MessageAOI')
                        parent=E.SubElement(aoi,'LocalTags');name='LocalTag'
                    E.SubElement(parent,name,Name='Button',DataType=dtype,TagType='Base')
                    self.assertFalse(self.catalog(root).empty)

    def test_message_data_and_parameters_are_detected_before_runtime_filtering(self):
        for mode in ('format','parameters','namespaced'):
            root=copy.deepcopy(self.root);tag=root.find('./Controller/Tags/Tag')
            if mode=='format':E.SubElement(tag,'Data',Format='MESSAGE')
            else:E.SubElement(tag,{'parameters':'MessageParameters','namespaced':'{urn:extra}MessageParameters'}[mode])
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
        tag=self.root.find('./Controller/Tags/Tag');tag.set('DataType','MESSAGE')
        path=Path(self.tmp.name)/'button.L5X';E.ElementTree(self.root).write(path)
        self.app.engine.project=Project(path)
        for target in ('21008d002400',):
            self.assertEqual(self.call(bytes.fromhex(target))[2],0x0C)
        self.assertIsNone(self.app.engine.project.message_catalog.description()['instance_count'])
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.call(bytes.fromhex('21008d002400')),b'\xCB\0\0\0')

    def test_scoped_paths_payloads_and_mutations_are_rejected_without_state_changes(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        for class_id in ('8d00',):
            path=bytes.fromhex('2100'+class_id+'2400')
            for target,data,service,status in ((path[:-2],b'',0x4B,4),(path+b'\x30\1',b'',0x4B,4),
                    (path,b'\0',0x4B,0x15),(symbol_path('Program:MainProgram')+path,b'',0x4B,4),
                    (path,b'',0x0E,8),(path,b'\0',0x10,8)):
                self.assertEqual(self.call(target,data,service)[2],status)
        self.assertEqual(self.app.engine.memory.values,before)


    def test_alarm_and_message_presence_are_independent(self):
        from logixlab.alarm_catalog import AlarmCatalog
        for dtype, alarm_empty, message_empty in (('MESSAGE', True, False), ('ALARM_DIGITAL', False, True)):
            root=copy.deepcopy(self.root);controller=root.find('Controller')
            controller.find('./Tags/Tag').set('DataType',dtype)
            self.assertEqual(AlarmCatalog.from_source(root,controller).empty,alarm_empty)
            self.assertEqual(self.catalog(root).empty,message_empty)

    def test_other_export_roots_are_not_complete_controller_tag_sources(self):
        root=copy.deepcopy(self.root);root.set('TargetType','Tag')
        self.assertFalse(self.catalog(root).empty)
        root=copy.deepcopy(self.root);root.tag='OtherContent'
        self.assertFalse(self.catalog(root).empty)

    def test_alarm_text_messages_are_not_message_objects(self):
        controller=self.root.find('Controller')
        E.SubElement(controller.find('./Tags/Tag'),'Message').text='An alarm text message'
        self.assertTrue(self.catalog(self.root).empty)

if __name__=='__main__':unittest.main()
