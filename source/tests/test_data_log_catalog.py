"""Data Logging discovery must not conceal trends or unparsed configuration."""
import copy
from pathlib import Path
import struct
import tempfile
import unittest
from xml.etree import ElementTree as E
from logixlab.data_log_catalog import DataLogCatalog
from logixlab.ethernetip import Endpoint,Session,symbol_path
from logixlab.model import Project
from logixlab.server import Application


class DataLogCatalogTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.endpoint=Endpoint(self.app,0,True)
        self.root=E.parse(self.app.engine.project.path).getroot()

    def tearDown(self):self.app.close();self.tmp.cleanup()

    def send(self,path=bytes.fromhex('20712400'),service=0x4B,data=b''):
        return self.endpoint.router.handle(bytes((service,len(path)//2))+path+data,Session())

    def test_optional_absent_or_explicit_empty_trends_prove_no_logs(self):
        self.assertTrue(self.app.engine.project.data_log_catalog.empty)
        controller=self.root.find('Controller')
        E.SubElement(controller,'Trends',Use='Target')
        E.SubElement(controller,'DataLogs')
        self.assertTrue(DataLogCatalog.from_source(self.root,controller).empty)
        for cursor in (0,100,101,0xFFFFFFFF):
            self.assertEqual(self.send(bytes.fromhex('20712600')+struct.pack('<I',cursor)),bytes.fromhex('cb000000'))
        info=self.app.engine.project.data_log_catalog.description()
        self.assertEqual((info['instance_count'],info['storage_bytes']),(0,0))
        self.assertFalse(info['native_logging_engine'])

    def test_configured_partial_nested_namespaced_and_protected_source_is_unavailable(self):
        for kind in ('trend','unknown','duplicate','context','section-context','namespace','nested','case',
                     'data-log','text','section-attribute','protected','format','type','reference',
                     'configured-data-log','duplicate-data-log','nested-data-log','data-log-namespace'):
            with self.subTest(kind=kind):
                root=copy.deepcopy(self.root);controller=root.find('Controller')
                section=E.SubElement(controller,'Trends')
                if kind=='trend':E.SubElement(section,'Trend',Name='Example')
                elif kind=='unknown':E.SubElement(section,'UnknownTrend')
                elif kind=='duplicate':E.SubElement(controller,'Trends')
                elif kind=='context':root.set('ContainsContext','true')
                elif kind=='section-context':section.set('Use','Context')
                elif kind=='namespace':section.tag='{urn:extra}Trends'
                elif kind=='nested':controller.remove(section);controller.find('Tags').append(section)
                elif kind=='case':section.tag='trends'
                elif kind=='data-log':E.SubElement(controller,'DataLogging')
                elif kind=='configured-data-log':E.SubElement(E.SubElement(controller,'DataLogs'),'DataLog',Name='Configured')
                elif kind=='duplicate-data-log':E.SubElement(controller,'DataLogs');E.SubElement(controller,'DataLogs')
                elif kind=='nested-data-log':E.SubElement(controller.find('Tags'),'DataLogs')
                elif kind=='data-log-namespace':E.SubElement(controller,'{urn:extra}DataLogs')
                elif kind=='text':section.text='unparsed logs'
                elif kind=='section-attribute':section.set('Count','0')
                elif kind=='protected':E.SubElement(controller,'ProtectedContent')
                elif kind=='format':E.SubElement(controller,'Data',Format='Encrypted')
                elif kind=='type':controller.find('./Tags/Tag').set('DataType','DATALOG_BUFFER')
                else:controller.set('TrendUId','1')
                self.assertFalse(DataLogCatalog.from_source(root,controller).empty)

    def test_class_fields_use_uint_revision_and_udint_counts_and_zero_storage(self):
        numbers=(1,2,3,10,11,12,13,14,15)
        data=struct.pack('<10H',9,*numbers)
        expected=bytes.fromhex('830000000900')
        for number in numbers:
            value=b'\1\0' if number==1 else bytes(4)
            expected+=struct.pack('<HH',number,0)+value
            self.assertEqual(self.send(bytes.fromhex('2071240030')+bytes((number,)),0x0E),b'\x8E\0\0\0'+value)
        self.assertEqual(self.send(service=3,data=data),expected)
        self.app.engine.project.data_log_catalog=DataLogCatalog(False)
        self.assertEqual(self.send()[2],0x0C)
        self.assertEqual(self.send(service=3,data=struct.pack('<3H',2,1,3)),bytes.fromhex('83000a00020001000000010003001400'))

    def test_bad_scopes_payloads_writes_and_reload_preserve_memory(self):
        before=copy.deepcopy(self.app.engine.memory.values);path=bytes.fromhex('20712400')
        for target,service,data,status in ((path[:-2],0x4B,b'',4),(path+b'\x30\1',0x4B,b'',4),
                (symbol_path('Program:MainProgram')+path,0x4B,b'',4),
                (bytes.fromhex('20682401')+path,0x4B,b'',4),(path,0x4B,b'x',0x15),
                (path,0x10,b'\0',8),(bytes.fromhex('20712401'),0x0E,b'',5)):
            self.assertEqual(self.send(target,service,data)[2],status)
        self.assertEqual(self.app.engine.memory.values,before)
        E.SubElement(self.root.find('Controller'),'Trends').append(E.Element('Trend',Name='NotImplemented'))
        source=Path(self.tmp.name)/'logs.L5X';E.ElementTree(self.root).write(source)
        self.app.engine.project=Project(source)
        self.assertEqual(self.send()[2],0x0C)
        self.assertIsNone(self.app.engine.project.data_log_catalog.description()['instance_count'])
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.send(),bytes.fromhex('cb000000'))


if __name__=='__main__':unittest.main()
