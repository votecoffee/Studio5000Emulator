"""Additional empty Program inventories use independent source absence checks."""
import copy
import unittest
from xml.etree import ElementTree as E

from logixlab.ethernetip import Endpoint,symbol_path
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import logical_path
import test_alarm_catalog as alarm


class ProgramInventoryScopesTests(unittest.TestCase):
    def setUp(self):
        self.fixture=alarm.AlarmCatalogTests();self.fixture.setUp()
        self.app=self.fixture.app

    def tearDown(self):self.fixture.tearDown()

    def test_hmi_and_message_lists_preserve_sparse_parent_ids_cursor_widths_and_model(self):
        for parent in (7,472,70000):
            self.fixture.bind_program(instance=parent);before=copy.deepcopy(self.app.state())
            for cls in (0x36E,0x8D):
                for cursor in (0,1,0xffffffff):
                    self.assertEqual(self.fixture.call(logical_path(cls,cursor,program=parent)),b'\xcb\0\0\0')
                self.assertEqual(self.fixture.call(logical_path(cls,0,program=parent+1))[2],5)
            for key in ('tags','controller','scan','ms','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])

    def test_alarm_hmi_and_message_absence_are_independent_and_nonempty_objects_stay_unavailable(self):
        for dtype,unavailable in (('ALARM_DIGITAL',0x331),('HMIBC',0x36E),('MESSAGE',0x8D)):
            root=copy.deepcopy(self.fixture.root)
            E.SubElement(root.find('./Controller/Programs/Program/Tags'),'Tag',Name='Configured',DataType=dtype,TagType='Base')
            self.fixture.bind_program(root)
            for cls in (0x331,0x36E,0x8D):
                self.assertEqual(self.fixture.call(logical_path(cls,0,program=472))[2],0x0c if cls==unavailable else 0,(dtype,cls))

    def test_hmi_and_message_configuration_and_opaque_source_never_prove_empty(self):
        for name,cls in (('HMIBCParameters',0x36E),('MessageParameters',0x8D)):
            for mode in ('parameters','context','missing_tags','folder','safety'):
                root=copy.deepcopy(self.fixture.root);program=root.find('./Controller/Programs/Program')
                if mode=='parameters':E.SubElement(program.find('Tags/Tag') if program.find('Tags/Tag') is not None else program.find('Tags'),name)
                elif mode=='context':root.set('ContainsContext','true')
                elif mode=='missing_tags':program.remove(program.find('Tags'))
                elif mode=='folder':program.set('UseAsFolder','true')
                else:program.set('Class','Safety')
                self.fixture.bind_program(root)
                self.assertEqual(self.fixture.call(logical_path(cls,0,program=472))[2],5 if mode=='safety' else 0x0c,(name,mode))

    def test_hmi_and_message_scoped_reads_require_native_binding_and_exact_paths(self):
        self.fixture.bind_program();symbols=self.app.native_symbols
        for cls in (0x36E,0x8D):
            path=logical_path(cls,0,program=472)
            self.app.native_symbols=None;self.assertEqual(self.fixture.call(path)[2],0x0c)
            self.app.native_symbols=symbols
            for target,data,service,status in ((path,b'\0',0x4b,0x15),(path+b'\x30\1',b'',0x4b,4),
                    (path[:-2],b'',0x4b,4),(symbol_path('Program:MainProgram')+path,b'',0x4b,4),
                    (path,b'',0x0e,8),(path,b'\0',0x10,8)):
                self.assertEqual(self.fixture.call(target,data,service)[2],status)
        self.app.command('demo',{'sample':'ConveyorDemo'})
        self.assertEqual(self.fixture.call(logical_path(0x36E,0,program=472))[2],0x0c)

    def test_signed_tcp_hmi_and_message_reads_do_not_enable_configuration_or_execution(self):
        self.fixture.bind_program();before=copy.deepcopy(self.app.state())
        self.app.endpoint=Endpoint(self.app,0,False,'logix-v35-l85e',native_read_only=True)
        self.app.endpoint.start()
        with AnonymousClient(self.app.endpoint) as client:
            client.bind()
            for cls in (0x36E,0x8D):
                path=logical_path(cls,0,program=472)
                self.assertEqual(client.request(bytes((0x4b,len(path)//2))+path),b'\xcb\0\0\0')
        self.assertFalse(self.app.engine.project.hmi_button_catalog.description()['button_execution'])
        self.assertFalse(self.app.engine.project.message_catalog.description()['msg_execution'])
        for key in ('tags','controller','scan','ms','routines','tasks'):self.assertEqual(self.app.state()[key],before[key])


if __name__=='__main__':unittest.main()
