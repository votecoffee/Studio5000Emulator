"""Signed empty-log lookups preserve source cursors and programming authority."""
import copy
from dataclasses import replace
import struct
import unittest

from logixlab.native_project import NativeProjectIdentity
import test_programming_lease as leases


class EmptyChangeLogWireTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind

    def source(self):
        self.app.native_project_identity=NativeProjectIdentity('a'*64,self.app.engine.project.sha256,
            0,3,1,1,1,1,empty_change_log=True)
        self.bind()

    def query(self,index,generation):return bytes.fromhex('4f0220ac2401')+struct.pack('<HH',index,generation)

    def test_signed_empty_current_initial_and_end_lookups_echo_without_changes_or_write_authority(self):
        self.source();before=copy.deepcopy(self.app.state())
        for sequence,(index,generation) in enumerate(((0,3),(0,4),(1,3)),4):
            raw=self.query(index,generation)
            self.assertEqual(self.signed(sequence,raw),bytes.fromhex('cf000000')+raw[-4:])
        self.assertEqual(self.signed(7,self.query(2,3))[2],12)
        self.assertEqual(self.signed(8,bytes.fromhex('500220ac2401')+bytes(4))[2],15)
        after=self.app.state()
        for key in ('tags','routines','tasks','scan','ms','controller','routine_edits'):
            self.assertEqual(before[key],after[key])
        self.assertFalse(self.endpoint.state()['native_programming_lease']['owned'])

    def test_extra_lookups_require_evidence_unedited_model_and_matching_source(self):
        self.source();identity=self.app.native_project_identity
        self.app.native_project_identity=replace(identity,empty_change_log=False)
        self.assertEqual(self.signed(4,self.query(0,4))[2],12)
        self.assertEqual(self.signed(5,self.query(1,3))[2],12)
        self.assertEqual(self.signed(6,self.query(0,3))[2],0)
        self.app.native_project_identity=identity;self.app.engine.project.runtime_revision=1
        self.assertEqual(self.signed(7,self.query(0,4))[2],12)
        self.assertEqual(self.signed(8,self.query(1,3))[2],12)
        self.app.engine.project.runtime_revision=0
        self.app.native_project_identity=replace(identity,source_l5x_sha256='b'*64)
        self.assertEqual(self.signed(9,self.query(0,4))[2],12)


if __name__=='__main__':unittest.main()
