import base64
import copy
import struct
import tempfile
import unittest
from pathlib import Path
from xml.etree import ElementTree as E
from logixlab.server import Application
from logixlab.model import ModelError
from logixlab.identity import Identity
from logixlab.ethernetip import Endpoint
from test_ethernetip import Client


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.app=Application(self.tmp.name)
        self.app.command('demo',{'sample':'TextLab'});self.endpoint=None;self.clients=[]

    def tearDown(self):
        for client in self.clients:client.close()
        if self.endpoint:self.endpoint.stop()
        self.app.close();self.tmp.cleanup()

    def endpoint_for(self,profile='research'):
        self.endpoint=Endpoint(self.app,0,False,profile).start()
        c=Client(self.endpoint.port);c.register();self.clients.append(c);return c

    def cip(self,c,raw):
        status,data=c.cip(raw);self.assertEqual(status,0);return data

    def test_research_identity_remains_default(self):
        c=self.endpoint_for();result=self.cip(c,b'\x01\x02\x20\1\x24\1')
        self.assertEqual(result[2],0);self.assertEqual(result[4:6],b'\xFF\xFF');self.assertIn(b'LogixLab',result)
        self.assertEqual(self.endpoint.state()['profile'],'research')

    def test_compatibility_identity_is_explicit_and_uses_source_revision(self):
        c=self.endpoint_for('logix-v35-l85e');result=self.cip(c,b'\x01\x02\x20\1\x24\1')
        self.assertEqual(result[4:10],struct.pack('<HHH',1,14,168));self.assertEqual(result[10:12],b'\x23\x0B')
        self.assertIn(b'1756-L85E/B',result);state=self.endpoint.state()
        self.assertTrue(state['identity']['experimental']);self.assertEqual(state['source_l5x_sha256'],self.app.engine.project.sha256)
        self.assertEqual(state['studio_go_online'],'NOT IMPLEMENTED OR VERIFIED')

    def test_discovery_and_cip_identity_are_consistent(self):
        c=self.endpoint_for('logix-v35-l85e');_,discovery=c.packet(0x63)
        identity=self.cip(c,b'\x01\x02\x20\1\x24\1')[4:]
        self.assertEqual(discovery[24:-1],identity);self.assertEqual(discovery[-1],3)

    def test_identity_get_attribute_list_has_per_attribute_status(self):
        c=self.endpoint_for('logix-v35-l85e')
        result=self.cip(c,b'\x03\x02\x20\1\x24\1'+struct.pack('<HHHH',3,1,4,0xFF))
        self.assertEqual(result[:4],b'\x83\0\x0A\0')
        self.assertEqual(result[4:],struct.pack('<HHHHHH',3,1,0,1,4,0)+b'\x23\x0B'+struct.pack('<HH',0xFF,0x14))

    def test_unsupported_native_symbol_attributes_are_reported_and_counted(self):
        c=self.endpoint_for()
        result=self.cip(c,b'\x55\x02\x20\x6B\x24\0'+struct.pack('<HHHH',3,1,4,5))
        self.assertEqual(result[2],0x14)
        trace=self.endpoint.state(True)
        self.assertEqual(trace['unsupported'][0]['count'],1)
        self.assertIn('Unsupported Symbol attribute',trace['events'][-2]['detail'])

    def test_identity_state_and_class_attributes(self):
        c=self.endpoint_for()
        self.assertEqual(self.cip(c,b'\x0E\3\x20\1\x24\1\x30\x08')[4:],b'\3')
        self.assertEqual(self.cip(c,b'\x0E\3\x20\1\x24\0\x30\7')[4:],b'\x66\x00')
        self.assertEqual(self.cip(c,b'\x0E\2\x20\1\x30\1')[4:],b'\1\0')

    def test_extended_revision_list_matches_single_reads_and_virtual_metadata(self):
        c=self.endpoint_for('logix-v35-l85e')
        result=self.cip(c,b'\x03\2\x20\1\x24\1'+struct.pack('<3H',2,101,102))
        self.assertEqual(result,b'\x83\0\0\0'+struct.pack('<3H',2,101,0)+b'\1\0'+struct.pack('<HHI',102,0,0))
        for number,expected in ((101,b'\1\0'),(102,b'\0'*4)):
            path=b'\x20\1\x24\1'+bytes((0x30,number))
            self.assertEqual(self.cip(c,bytes((0x0E,3))+path),b'\x8E\0\0\0'+expected)
        metadata=self.endpoint.state()['identity']
        self.assertEqual(metadata['hardware_revision'],{'major':1,'minor':0})
        self.assertEqual(metadata['firmware_build'],0)
        self.assertIn('not physical-controller provenance',metadata['revision_metadata_policy'])

    def test_extended_revision_unknown_attributes_and_write_attempts_preserve_memory(self):
        c=self.endpoint_for();before=copy.deepcopy(self.app.engine.memory.values)
        result=self.cip(c,b'\x03\2\x20\1\x24\1'+struct.pack('<4H',3,101,103,102))
        self.assertEqual(result,b'\x83\0\x0A\0'+struct.pack('<3H',3,101,0)+b'\1\0'+
                         struct.pack('<HHHHI',103,0x14,102,0,0))
        identity_before=self.endpoint.identity.description()
        for number,value in ((101,b'\xFF\xFF'),(102,b'\xFF'*4)):
            raw=b'\x10\3\x20\1\x24\1'+bytes((0x30,number))+value
            self.assertEqual(self.cip(c,raw)[2],8)
        self.assertEqual(self.cip(c,b'\x04\2\x20\1\x24\1'+struct.pack('<HHI',1,102,99))[2],8)
        self.assertEqual(self.endpoint.identity.description(),identity_before)
        self.assertEqual(self.app.engine.memory.values,before)

    def test_extended_revision_defaults_do_not_change_standard_identity_wire_layout(self):
        for profile in ('research','logix-v35-l85e'):
            identity=Identity.from_project(profile,self.app.engine.project)
            standard=identity.all_attributes()
            name_length=standard[14]
            self.assertEqual(len(standard),15+name_length)
            self.assertEqual(standard[8:10],b'\0\0')
            self.assertEqual(standard[10:14],struct.pack('<I',identity.serial))
            self.assertEqual(identity.attributes()[101],b'\1\0')
            self.assertEqual(identity.attributes()[102],b'\0'*4)

    def test_attribute_errors_do_not_change_memory(self):
        c=self.endpoint_for();before=copy.deepcopy(self.app.engine.memory.values)
        for data in (b'\0\0',b'\x02\0\x01\0',struct.pack('<H',33)+b'\1\0'*33):
            self.assertNotEqual(self.cip(c,b'\x03\x02\x20\1\x24\1'+data)[2],0)
        self.assertEqual(before,self.app.engine.memory.values)

    def test_controller_name_service_returns_source_name(self):
        c=self.endpoint_for();result=self.cip(c,b'\x01\x02\x20\x64\x24\1')
        self.assertEqual(result,b'\x81\0\0\0\7\0TextLab')

    def test_message_router_lists_only_implemented_object_classes(self):
        c=self.endpoint_for();result=self.cip(c,b'\x0E\3\x20\2\x24\1\x30\1')
        self.assertEqual(result[4:],struct.pack('<25H',24,1,2,6,0x4E,0x4F,0x50,0x64,0x6A,0x6B,0x6C,0x8D,0x8E,0xAC,0xB0,0xB1,0xF4,0xF5,0xF6,0x31A,0x32B,0x331,0x332,0x349,0x36E))

    def test_profile_rejects_other_controller_firmware_and_unknown_revision(self):
        p=self.app.engine.project
        for field,value in (('processor','1756-L85ES'),('version','34'),('minor_version','0'),('minor_version','256'),('minor_version','unknown')):
            with self.subTest(field=field,value=value):
                original=getattr(p,field);setattr(p,field,value)
                try:
                    with self.assertRaises(ModelError):Identity.from_project('logix-v35-l85e',p)
                finally:setattr(p,field,original)
        with self.assertRaises(ModelError):Identity.from_project('arbitrary',p)

    def test_import_of_incompatible_project_keeps_live_profile_and_project(self):
        self.app.command('connectivity-start',{'port':0,'profile':'logix-v35-l85e'})
        old=self.app.engine;source=E.parse(Path(__file__).resolve().parents[1]/'samples/TextLab.L5X')
        source.find('Controller').set('ProcessorType','1756-L83E')
        raw=E.tostring(source.getroot(),encoding='utf-8')
        with self.assertRaises(ModelError):self.app.command('load',{'name':'other.L5X','content':base64.b64encode(raw).decode()})
        self.assertIs(self.app.engine,old);self.assertFalse(self.app.busy)
        self.assertEqual(self.app.endpoint.state()['identity']['product_code'],168)

    def test_explicit_profile_is_exposed_in_application_state(self):
        state=self.app.command('connectivity-start',{'port':0,'profile':'logix-v35-l85e'})
        self.assertEqual(state['connectivity']['profile'],'logix-v35-l85e')
        self.assertEqual(state['connectivity']['identity']['revision'],{'major':35,'minor':11})

    def test_compatible_project_replacement_updates_identity_and_invalidates_sessions(self):
        c=self.endpoint_for('logix-v35-l85e')
        source=E.parse(Path(__file__).resolve().parents[1]/'samples/TextLab.L5X')
        source.find('Controller').set('MinorRev','12');source.find('Controller').set('Name','RenamedLab')
        raw=E.tostring(source.getroot(),encoding='utf-8')
        # Attach the isolated endpoint to the same application lifecycle.
        self.app.endpoint=self.endpoint
        state=self.app.command('load',{'name':'changed.L5X','content':base64.b64encode(raw).decode()})
        self.assertEqual(state['connectivity']['identity']['revision'],{'major':35,'minor':12})
        self.assertEqual(c.cip(b'\x01\x02\x20\1\x24\1')[0],0x64)
        self.assertEqual(self.endpoint.identity.major,35);self.assertEqual(self.endpoint.identity.minor,12)
        fresh=Client(self.endpoint.port);fresh.register();self.clients.append(fresh)
        self.assertEqual(self.cip(fresh,b'\x01\x02\x20\x64\x24\1')[4:],b'\x0A\0RenamedLab')


if __name__=='__main__':unittest.main()
