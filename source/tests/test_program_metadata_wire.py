"""Captured edit Program Disable request against the source-bound wire path."""
import copy
import unittest

from logixlab.native_symbols import NativeSymbols
import test_programming_lease as leases

READ=bytes.fromhex('030320682500b66501001300')


class ProgramMetadataWireTests(unittest.TestCase):
    setUp=leases.SemaphoreSignedTests.setUp
    tearDown=leases.SemaphoreSignedTests.tearDown
    cip=leases.SemaphoreSignedTests.cip
    begin=leases.SemaphoreSignedTests.begin
    signed=leases.SemaphoreSignedTests.signed
    bind=leases.SemaphoreSignedTests.bind
    prepare=leases.SemaphoreSignedTests.prepare

    def test_captured_edit_read_and_single_read_return_the_source_disable_byte(self):
        self.prepare()
        self.app.native_symbols=NativeSymbols('a'*64,self.app.engine.project.sha256,[],
                                              [{'name':'MainProgram','instance':26038}])
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.signed(4,READ),bytes.fromhex('8300000001001300000000'))
        self.assertEqual(self.signed(5,bytes.fromhex('0e0420682500b6653013')),bytes.fromhex('8e00000000'))
        self.assertEqual(self.signed(6,bytes.fromhex('100420682500b665301301'))[2],15)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_native_identity_and_exact_source_are_required_for_program_fields(self):
        self.prepare();self.assertEqual(self.signed(4,READ)[2],12)
        self.app.native_symbols=NativeSymbols('a'*64,'f'*64,[],[{'name':'MainProgram','instance':26038}])
        self.assertEqual(self.signed(5,READ)[2],12)
        self.app.native_symbols=NativeSymbols('a'*64,self.app.engine.project.sha256,[],
                                              [{'name':'MainProgram','instance':26039}])
        self.assertEqual(self.signed(6,READ)[2],5)

    def test_program_type_single_list_and_mixed_errors_preserve_model_and_deny_writes(self):
        self.prepare()
        self.app.native_symbols=NativeSymbols('a'*64,self.app.engine.project.sha256,[],
                                              [{'name':'MainProgram','instance':26038}])
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.signed(4,bytes.fromhex('030320682500b66501001e00')),
                         bytes.fromhex('8300000001001e00000001'))
        self.assertEqual(self.signed(5,bytes.fromhex('0e0420682500b665301e')),bytes.fromhex('8e00000001'))
        self.assertEqual(self.signed(6,bytes.fromhex('030320682500b66503001e0063001e00')),
                         bytes.fromhex('83000a0003001e00000001630014001e00000001'))
        self.assertEqual(self.signed(7,bytes.fromhex('100420682500b665301e00'))[2],15)
        self.assertEqual(self.signed(8,bytes.fromhex('030320682500b665020016001e00')),
                         bytes.fromhex('83000000020016000000b66500001e00000001'))
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])
        self.app.native_symbols=NativeSymbols('a'*64,'f'*64,[],[{'name':'MainProgram','instance':26038}])
        self.assertEqual(self.signed(9,bytes.fromhex('0e0420682500b665301e'))[2],12)

    def test_program_type_never_resolves_other_parent_scopes(self):
        self.prepare();self.app.native_symbols=NativeSymbols('a'*64,self.app.engine.project.sha256,[],
                                              [{'name':'MainProgram','instance':26038}])
        for seq,parent in enumerate(('208e2401','20692401','210038032401'),4):
            path=bytes.fromhex(parent+'20682500b665301e')
            self.assertEqual(self.signed(seq,bytes((0x0e,len(path)//2))+path)[2],4)


if __name__=='__main__':unittest.main()
