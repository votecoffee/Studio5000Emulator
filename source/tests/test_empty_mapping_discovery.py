"""Native PLC file-mapping discovery never hides configured or unknown maps."""
import copy
from dataclasses import replace
import struct
import unittest

from logixlab.ethernetip import Session,symbol_path
from logixlab.native_project import NativeProjectIdentity
from logixlab.pccc_mapping import PcccMapping
import test_native_session as sessions


class EmptyMappingDiscoveryTests(unittest.TestCase):
    setUp=sessions.NativeSessionTests.setUp
    tearDown=sessions.NativeSessionTests.tearDown
    cip=sessions.NativeSessionTests.cip
    begin=sessions.NativeSessionTests.begin
    signed=sessions.NativeSessionTests.signed
    bind=sessions.NativeSessionTests.bind

    def identity(self):
        return NativeProjectIdentity('1'*64,self.app.engine.project.sha256,2,3,4,5,6,0xffffffff)

    def test_bound_empty_source_returns_no_ids_and_leaves_values_and_audit_unchanged(self):
        self.app.native_project_identity=self.identity();self.bind()
        before=copy.deepcopy(self.app.state());source=self.app.engine.project.path.read_bytes()
        self.assertEqual(self.signed(4,bytes.fromhex('4b02206e2400')),bytes.fromhex('cb000000'))
        self.assertEqual(self.app.engine.project.pccc_mapping.discovery_body(),b'')
        after=self.app.state()
        for key in ('tags','controller','scan','ms','routines','tasks','routine_edits'):
            self.assertEqual(before[key],after[key])
        self.assertEqual(before['connectivity']['controller_change_detection'],after['connectivity']['controller_change_detection'])
        self.assertEqual(source,self.app.engine.project.path.read_bytes())

    def test_missing_mismatched_or_configured_source_never_becomes_empty(self):
        identity=self.identity();self.bind();sequence=4
        for value in (None,replace(identity,source_l5x_sha256='2'*64)):
            self.app.native_project_identity=value
            self.assertEqual(self.signed(sequence,bytes.fromhex('4b02206e2400'))[2],0x0c);sequence+=1
        self.app.native_project_identity=identity
        for empty in (False,None,0,'true'):
            self.app.engine.project.pccc_mapping=PcccMapping(empty)
            self.assertIsNone(self.app.engine.project.pccc_mapping.discovery_body())
            self.assertEqual(self.signed(sequence,bytes.fromhex('4b02206e2400'))[2],0x0c);sequence+=1

    def test_global_cursor_and_exact_empty_payload_are_required(self):
        self.app.native_project_identity=self.identity();self.bind()
        cases=((bytes.fromhex('4b02206e2401'),5),
               (bytes.fromhex('4b02206e2400')+b'\0',0x15),
               (bytes.fromhex('4b03206e24003001'),4),
               (bytes.fromhex('4b01206e'),4))
        for sequence,(raw,status) in enumerate(cases,4):self.assertEqual(self.signed(sequence,raw)[2],status)

    def test_deeper_symbolic_and_program_scopes_are_rejected(self):
        self.app.native_project_identity=self.identity();self.bind()
        paths=(symbol_path('Program:MainProgram')+bytes.fromhex('206e2400'),
               bytes.fromhex('20682401')+bytes.fromhex('206e2400'),
               bytes.fromhex('20692401')+bytes.fromhex('206e2400'))
        for sequence,path in enumerate(paths,4):
            self.assertEqual(self.signed(sequence,bytes((0x4b,len(path)//2))+path)[2],4)

    def test_attribute_file_and_write_services_are_not_enabled(self):
        self.app.native_project_identity=self.identity();self.bind()
        self.assertEqual(self.signed(4,bytes.fromhex('0e03206e24003001'))[2],4)
        self.assertEqual(self.signed(5,bytes.fromhex('0302206e240001000100'))[2],8)
        self.assertEqual(self.signed(6,bytes.fromhex('0102206e2400'))[2],8)
        for sequence,service in enumerate((0x10,4,8,9,0x4c,0x4d),7):
            self.assertEqual(self.signed(sequence,bytes((service,2))+bytes.fromhex('206e2400'))[2],15)

    def test_only_native_profile_advertises_the_discovery_class_once(self):
        self.app.native_project_identity=self.identity();self.bind()
        reply=self.signed(4,bytes.fromhex('010220022401'))
        count=struct.unpack_from('<H',reply,4)[0];classes=struct.unpack_from('<'+'H'*count,reply,6)
        self.assertEqual(classes.count(0x6e),1)
        self.endpoint.native_read_only=False
        raw=self.endpoint.router.handle(bytes.fromhex('4b02206e2400'),Session())
        self.assertEqual(raw[2],8)
        reply=self.endpoint.router.handle(bytes.fromhex('010220022401'),Session())
        count=struct.unpack_from('<H',reply,4)[0];classes=struct.unpack_from('<'+'H'*count,reply,6)
        self.assertNotIn(0x6e,classes)


if __name__=='__main__':unittest.main()
