"""Native definition discovery must not hide unsupported source AOIs."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E

from logixlab.aoi_catalog import AOICatalog
from logixlab.ethernetip import Endpoint, Session, symbol_path
from logixlab.model import Project
from logixlab.server import Application


class AOICatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Application(self.tmp.name)
        self.app.command('demo', {'sample':'ConveyorDemo'})
        self.endpoint = Endpoint(self.app, 0, True)
        self.root = E.parse(self.app.engine.project.path).getroot()

    def tearDown(self):
        self.app.close(); self.tmp.cleanup()

    def call(self, path, service=0x4B, data=b''):
        return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data, Session())

    def test_empty_definition_section_allows_global_cursors_and_exposes_its_limits(self):
        for cursor in (0, 1, 0xFFFFFFFF):
            path=bytes.fromhex('210038032600')+struct.pack('<I',cursor)
            self.assertEqual(self.call(path), bytes.fromhex('cb000000'))
        info=self.app.engine.project.aoi_catalog.description()
        self.assertEqual(info['instance_count'],0)
        self.assertFalse(info['definition_upload'])
        ids=self.call(bytes.fromhex('20022401'),1)[4:]
        self.assertIn(0x338,struct.unpack('<'+'H'*(len(ids)//2),ids)[1:])

    def test_nonempty_ambiguous_partial_and_protected_sources_cannot_claim_empty(self):
        for kind in ('definition','unknown','missing','duplicate','nested','namespace','case',
                     'context','section-context','text','extra-attribute','protected','encoded','encoded-format'):
            with self.subTest(kind=kind):
                root=copy.deepcopy(self.root);controller=root.find('Controller')
                section=controller.find('AddOnInstructionDefinitions')
                if kind=='definition':E.SubElement(section,'AddOnInstructionDefinition',Name='Example')
                elif kind=='unknown':E.SubElement(section,'VendorDefinition')
                elif kind=='missing':controller.remove(section)
                elif kind=='duplicate':E.SubElement(controller,'AddOnInstructionDefinitions')
                elif kind=='nested':E.SubElement(controller.find('Tags'),'AddOnInstructionDefinitions')
                elif kind=='namespace':section.tag='{urn:extra}AddOnInstructionDefinitions'
                elif kind=='case':section.tag='addoninstructiondefinitions'
                elif kind=='context':root.set('ContainsContext','true')
                elif kind=='section-context':section.set('Use','Context')
                elif kind=='text':section.text='unparsed definitions'
                elif kind=='extra-attribute':section.set('EncodedData','hidden')
                elif kind=='protected':E.SubElement(controller,'ProtectedContent')
                elif kind=='encoded-format':E.SubElement(controller.find('./Tags/Tag'),'Data',Format='Encoded')
                else:controller.set('EncodedDefinitions','hidden')
                self.assertFalse(AOICatalog.from_source(root,controller).empty)

    def test_reload_removes_empty_claim_and_paths_or_writes_never_change_model(self):
        before=copy.deepcopy(self.app.engine.memory.values)
        path=bytes.fromhex('210038032400')
        for target,service,data,status in ((path[:-2],0x4B,b'',4),(path+b'\x30\1',0x4B,b'',4),
                (symbol_path('Program:MainProgram')+path,0x4B,b'',4),
                (bytes.fromhex('20682401')+path,0x4B,b'',4),
                (path,0x4B,b'\0',0x15),(path,0x10,b'\0',8),(path,1,b'',8)):
            self.assertEqual(self.call(target,service,data)[2],status)
        self.assertEqual(self.app.engine.memory.values,before)
        section=self.root.find('./Controller/AddOnInstructionDefinitions')
        E.SubElement(section,'UnrecognizedDefinition')
        source=Path(self.tmp.name)/'unknown.L5X';E.ElementTree(self.root).write(source)
        self.app.engine.project=Project(source)
        self.assertEqual(self.call(path)[2],0x0C)
        self.assertIsNone(self.app.engine.project.aoi_catalog.description()['instance_count'])
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.call(path),bytes.fromhex('cb000000'))


if __name__=='__main__':unittest.main()
