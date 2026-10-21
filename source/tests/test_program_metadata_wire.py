"""Captured edit Program Disable request against the source-bound wire path."""
import copy
import base64
import struct
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as E

from logixlab.native_symbols import NativeSymbols
from logixlab.native_tasks import NativeTasks
from logixlab.native_routines import NativeRoutines
from test_ethernetip import Client
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

    def test_emulator_program_and_main_addresses_require_bound_ordinary_idle_rll_objects(self):
        root=E.parse(self.app.engine.project.path).getroot();root.find('./Controller/Programs/Program').set('TestEdits','false')
        self.app.command('load',{'name':'references.L5X','content':base64.b64encode(E.tostring(root)).decode()})
        self.client.close();self.client=Client(self.endpoint.port);self.client.register();self.prepare()
        project=self.app.engine.project;digest=project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        names=project.executable_configuration.routine_names('MainProgram',source_sha256=digest)
        self.app.native_routines=NativeRoutines('a'*64,digest,[dict(program='MainProgram',name=name,program_instance=26038,instance=i+70) for i,name in enumerate(names)])
        before=copy.deepcopy(self.app.state())
        reply=self.signed(4,bytes.fromhex('030320682500b665020005001000'))
        self.assertEqual(reply[:10],bytes.fromhex('83000000020005000000'))
        self.assertEqual(reply[14:18],bytes.fromhex('10000000'))
        values={5:reply[10:14],16:reply[18:22]};space=self.app.engine.runtime_references
        self.assertNotEqual(values[5],values[16])
        for seq,number,kind in ((5,5,'routine'),(6,16,'program')):
            response=self.signed(seq,bytes.fromhex('0e0420682500b66530')+bytes((number,)))
            self.assertEqual(response,b'\x8e\0\0\0'+values[number])
            self.assertIsNotNone(space.resolve(project,int.from_bytes(values[number],'little'),kind))
        self.assertEqual(self.signed(7,bytes.fromhex('100420682500b665301000000000'))[2],15)
        self.app.native_routines=None
        self.assertEqual(self.signed(8,bytes.fromhex('0e0420682500b6653005'))[2],20)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_program_addresses_withhold_foreign_acd_and_unfinished_native_edits(self):
        import test_program_reservations as reservations
        root=E.parse(self.app.engine.project.path).getroot();root.find('./Controller/Programs/Program').set('TestEdits','false')
        self.app.command('load',{'name':'references.L5X','content':base64.b64encode(E.tostring(root)).decode()})
        self.client.close();self.client=Client(self.endpoint.port);self.client.register();self.prepare()
        project=self.app.engine.project;digest=project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        names=project.executable_configuration.routine_names('MainProgram',source_sha256=digest)
        rows=[dict(program='MainProgram',name=name,program_instance=26038,instance=i+70) for i,name in enumerate(names)]
        self.app.native_routines=NativeRoutines('b'*64,digest,rows)
        self.assertEqual(self.signed(4,bytes.fromhex('0e0420682500b6653010'))[2],20)
        self.app.native_routines=NativeRoutines('a'*64,digest,rows)
        self.assertEqual(self.signed(5,reservations.CONTROLLER_ACQUIRE)[2],0)
        self.assertEqual(self.signed(6,reservations.message(program=26038))[2],0)
        self.assertEqual(self.signed(7,bytes.fromhex('0e0420682500b6653010'))[2],20)
        self.assertEqual(self.signed(8,reservations.message(0x4C,program=26038,payload=b''))[2],0)
        self.assertEqual(self.signed(9,reservations.CONTROLLER_RELEASE)[2],0)
        self.assertEqual(self.signed(10,bytes.fromhex('0e0420682500b6653010'))[2],0)

    def test_normal_status_and_standard_memory_require_source_kind_owner_and_clean_idle_state(self):
        root=E.parse(self.app.engine.project.path).getroot();root.find('./Controller/Programs/Program').set('TestEdits','false')
        self.app.command('load',{'name':'status.L5X','content':base64.b64encode(E.tostring(root)).decode()})
        self.client.close();self.client=Client(self.endpoint.port);self.client.register();self.prepare()
        digest=self.app.engine.project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':77}])
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.signed(4,bytes.fromhex('030320682500b665020001001a00')),bytes.fromhex('8300000002000100000000001a0000000000'))
        self.assertEqual(self.signed(5,bytes.fromhex('0e0420682500b6653001')),bytes.fromhex('8e0000000000'))
        self.assertEqual(self.signed(6,bytes.fromhex('0e0420682500b665301a')),bytes.fromhex('8e0000000000'))
        self.assertEqual(self.signed(7,bytes.fromhex('100420682500b66530010000'))[2],15)
        self.app.native_tasks=None
        self.assertEqual(self.signed(8,bytes.fromhex('0e0420682500b6653001'))[2],20)
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':77}])
        self.app.engine.fault='unknown';self.app.engine.fault=''
        self.assertEqual(self.signed(9,bytes.fromhex('0e0420682500b6653001'))[2],20)
        self.assertEqual(self.signed(10,bytes.fromhex('0e0420682500b665301a')),bytes.fromhex('8e0000000000'))
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_idle_edit_mode_null_output_and_clean_faults_withhold_during_changes_and_faults(self):
        import test_program_reservations as reservations
        root=E.parse(self.app.engine.project.path).getroot();root.find('./Controller/Programs/Program').set('TestEdits','false')
        self.app.command('load',{'name':'diagnostics.L5X','content':base64.b64encode(E.tostring(root)).decode()})
        self.client.close();self.client=Client(self.endpoint.port);self.client.register();self.prepare()
        digest=self.app.engine.project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        before=copy.deepcopy(self.app.state())
        expected=bytes.fromhex('83000000040007000000')+bytes(4)+bytes.fromhex('0b000000')+bytes(2)+bytes.fromhex('14000000')+bytes(44)+bytes.fromhex('15000000')+bytes(44)
        self.assertEqual(self.signed(4,bytes.fromhex('030320682500b665040007000b0014001500')),expected)
        self.assertEqual(self.signed(5,reservations.CONTROLLER_ACQUIRE)[2],0)
        self.assertEqual(self.signed(6,reservations.message(program=26038))[2],0)
        self.assertEqual(self.signed(7,bytes.fromhex('0e0420682500b665300b'))[2],20)
        self.assertEqual(self.signed(8,reservations.message(0x4C,program=26038,payload=b''))[2],0)
        self.assertEqual(self.signed(9,bytes.fromhex('0e0420682500b665300b')),bytes.fromhex('8e0000000000'))
        self.assertEqual(self.signed(10,reservations.CONTROLLER_RELEASE)[2],0)
        self.assertEqual(self.signed(11,bytes.fromhex('100420682500b66530140000'))[2],15)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])
        self.app.engine.fault='unclassified';self.app.engine.fault=''
        self.assertEqual(self.signed(12,bytes.fromhex('0e0420682500b6653014'))[2],20)
        self.assertEqual(self.signed(13,bytes.fromhex('0e0420682500b6653015'))[2],20)
        self.assertEqual(self.signed(14,bytes.fromhex('0e0420682500b6653007')),bytes.fromhex('8e00000000000000'))

    def test_measured_timing_and_source_flags_list_single_and_denied_writes(self):
        root=E.parse(self.app.engine.project.path).getroot();program=root.find('./Controller/Programs/Program')
        program.set('UseAsFolder','false');program.set('SynchronizeRedundancyDataAfterExecution','true')
        self.app.command('load',{'name':'flags.L5X','content':base64.b64encode(E.tostring(root)).decode()})
        self.client.close();self.client=Client(self.endpoint.port);self.client.register();self.prepare()
        digest=self.app.engine.project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        with patch('logixlab.runtime.perf_counter_ns',side_effect=(0,123456)):self.app.engine.step()
        before=copy.deepcopy(self.app.state())
        expected=bytes.fromhex('830000000400020000007b000000030000007b0000001d000000011f00000001')
        self.assertEqual(self.signed(4,bytes.fromhex('030320682500b6650400020003001d001f00')),expected)
        for seq,number,value in ((5,2,struct.pack('<I',123)),(6,3,struct.pack('<I',123)),(7,29,b'\1'),(8,31,b'\1')):
            path=bytes.fromhex('20682500b66530')+bytes((number,))
            self.assertEqual(self.signed(seq,bytes((14,len(path)//2))+path),bytes.fromhex('8e000000')+value)
        self.assertEqual(self.signed(9,bytes.fromhex('100420682500b665301f00'))[2],15)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_nonempty_child_list_uses_source_order_and_original_bound_ids(self):
        root=E.parse(self.app.engine.project.path).getroot();programs=root.find('./Controller/Programs')
        for name in ('Second','Third'):
            node=copy.deepcopy(programs[0]);node.set('Name',name);programs.append(node)
        group=E.SubElement(programs[0],'ChildPrograms')
        for name in ('Third','Second'):E.SubElement(group,'ChildProgram',Name=name)
        self.app.command('load',{'name':'children.L5X','content':base64.b64encode(E.tostring(root)).decode()})
        self.client.close();self.client=Client(self.endpoint.port);self.client.register()
        self.prepare();digest=self.app.engine.project.sha256
        bindings=[{'name':'MainProgram','instance':26038},{'name':'Second','instance':40},{'name':'Third','instance':12}]
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],bindings)
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.signed(4,bytes.fromhex('0e0420682500b6653020')),bytes.fromhex('8e000000')+struct.pack('<HII',2,12,40))
        self.app.native_symbols=NativeSymbols('b'*64,digest,[],bindings)
        self.assertEqual(self.signed(5,bytes.fromhex('0e0420682500b6653020'))[2],20)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_owner_children_and_null_fault_reads_are_bound_and_preserve_the_active_program(self):
        self.prepare();digest=self.app.engine.project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,digest,[],[{'name':'MainProgram','instance':26038}])
        self.app.native_tasks=NativeTasks('a'*64,digest,[{'name':'MainTask','instance':77}])
        before=copy.deepcopy(self.app.state())
        self.assertEqual(self.signed(4,bytes.fromhex('030320682500b665030009000d002000')),
            bytes.fromhex('83000000030009000000000000000d0000004d000000200000000000'))
        for sequence,number,value in ((5,9,bytes(4)),(6,13,b'\x4d\0\0\0'),(7,32,bytes(2))):
            self.assertEqual(self.signed(sequence,bytes.fromhex('0e0420682500b66530')+bytes((number,))),b'\x8e\0\0\0'+value)
        self.assertEqual(self.signed(8,bytes.fromhex('100420682500b66530200000'))[2],15)
        self.app.native_tasks=NativeTasks('b'*64,digest,[{'name':'MainTask','instance':77}])
        self.assertEqual(self.signed(9,bytes.fromhex('0e0420682500b665300d'))[2],20)
        self.app.native_project_identity=None
        self.assertEqual(self.signed(10,bytes.fromhex('0e0420682500b6653020'))[2],20)
        for key in ('tags','routines','tasks','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

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
