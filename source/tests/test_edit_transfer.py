"""Temporary Routine bytes never become accepted or executable controller edits."""
import copy
import hashlib
import json
import struct
import unittest

from logixlab.edit_transfer import EditTransfer,EditTransferError,MAX_BYTES,MAX_FRAGMENTS,ASSEMBLY_SECONDS
from logixlab.ethernetip import logical
from logixlab.native_routines import NativeRoutines
from logixlab import signed_messages as sm
from test_signed_messages import KEY
import test_edit_preparation as edits
import test_program_reservations as reservations
from test_transport_fragments import message,part
from test_ethernetip import Client
from test_routine_source import container as source_container,xml_source


def container(size=52):
    elf=b'\x7fELF\x01\x01\x01'+bytes(size-7)
    return struct.pack('<5I',9,0,0,0,size)+elf


def prefix(program=300,routine=700):
    path=logical(0x20,0x68)+logical(0x24,program)+logical(0x20,0x6D)+logical(0x24,routine)
    return bytes((0x5C,len(path)//2))+path+struct.pack('<4I',3,1,123,0)


def source_prefix(routine=700):return prefix(routine=routine)[:-16]+struct.pack('<II',1,3)


class EditTransferModelTests(unittest.TestCase):
    def validated_source(self):
        self.complete_code();source=source_container()
        self.stage.accept(part(0x101,len(source),source_prefix()+source[:48]),target=(300,700),prefix=source_prefix(),kind='source')
        self.stage.accept(part(0x201,48,source[48:]),target=(300,700),kind='source')
        self.stage.translated_rungs=('NOP();',);self.stage.plan_validated=True

    def test_post_source_record_requires_validated_target_is_immutable_bounded_and_expires_with_source(self):
        data=struct.pack('<5I',2,5,0,1,123)
        with self.assertRaises(EditTransferError):self.stage.attach(data,target=(300,700))
        self.validated_source();self.stage.attach(data,target=(300,700));self.stage.attach(data,target=(300,700))
        state=self.stage.description();record=state['post_source_record']
        self.assertTrue(record['staged']);self.assertEqual(record['bytes'],20)
        self.assertEqual(record['sha256'],hashlib.sha256(data).hexdigest())
        self.assertEqual(state['retained_bytes'],len(self.body)+len(self.stage._data)+20)
        self.assertFalse(record['interpreted'] or record['payload_exposed'] or state['accepted_edits'])
        for bad,target in ((data,(300,701)),(data[:-1],(300,700)),(data+b'X',(300,700)),
                (bytearray(data),(300,700)),(struct.pack('<5I',2,5,0,1,0),(300,700)),
                (struct.pack('<5I',2,5,0,1,124),(300,700))):
            with self.assertRaises(EditTransferError):self.stage.attach(bad,target=target)
            self.assertEqual(self.stage.description(),state)
        self.stage._code=bytes(MAX_BYTES-len(self.stage._data))
        with self.assertRaises(EditTransferError):self.stage.attach(data,target=(300,700))
        self.now+=ASSEMBLY_SECONDS
        self.assertFalse(self.stage.description()['post_source_record']['staged'])
        self.assertEqual(self.stage.description()['retained_bytes'],0)

    def complete_code(self):
        self.start();self.stage.accept(part(0x201,32,self.body[32:]),target=(300,700))

    def test_source_requires_matching_complete_code_and_both_buffers_share_deadline_and_capacity(self):
        source=source_container()
        with self.assertRaises(EditTransferError):self.stage.accept(part(0x101,len(source),source_prefix()+source[:48]),
            target=(300,700),prefix=source_prefix(),kind='source')
        self.complete_code();self.now+=ASSEMBLY_SECONDS-1
        self.stage.accept(part(0x101,len(source),source_prefix()+source[:48]),target=(300,700),prefix=source_prefix(),kind='source')
        self.stage.accept(part(0x201,48,source[48:]),target=(300,700),kind='source')
        state=self.stage.description()
        self.assertEqual(state['component_kind'],'source');self.assertEqual(state['code_bytes'],72)
        self.assertEqual(state['retained_bytes'],72+len(source));self.assertTrue(state['source_description']['decoded'])
        self.assertEqual(self.stage._code,self.body);self.assertEqual(self.stage.source.name,'MainRoutine')
        self.now+=1;self.assertEqual(self.stage.description()['retained_bytes'],0)
        self.complete_code()
        with self.assertRaises(EditTransferError):self.stage.accept(part(0x101,len(source),source_prefix()+source[:48]),
            target=(300,701),prefix=source_prefix(),kind='source')
        self.assertEqual(self.stage.description()['code_bytes'],0)
        self.complete_code();self.stage.accept(part(0x101,len(source),source_prefix()+source[:48]),
            target=(300,700),prefix=source_prefix(),kind='source')
        with self.assertRaises(EditTransferError):self.stage.accept(part(0x201,48,source[48:-1]+b'X'),target=(300,700),kind='source')
        self.assertEqual(self.stage.description()['retained_bytes'],0)

    def setUp(self):self.now=100.;self.stage=EditTransfer(lambda:self.now);self.body=container()

    def start(self,body=None,count=32):
        body=self.body if body is None else body
        self.stage.accept(part(0x101,len(body),prefix()+body[:count]),target=(300,700),prefix=prefix())

    def test_contiguous_bytes_hash_and_aggregate_description_without_execution_or_payloads(self):
        self.start();self.stage.accept(part(1,32,self.body[32:40]),target=(300,700))
        self.stage.accept(part(0x201,40,self.body[40:]),target=(300,700))
        state=self.stage.description()
        self.assertEqual((state['status'],state['received_bytes'],state['fragments']),('complete',72,3))
        self.assertEqual(state['container_sha256'],hashlib.sha256(self.body).hexdigest())
        self.assertNotIn('ELF',json.dumps(state));self.assertEqual(self.stage._data,self.body)
        for field in ('elf_structural_validation','relocations_resolved','payloads_exposed','routine_installed','accepted_edits','commit'):
            self.assertFalse(state[field])
        self.assertEqual(state['instructions_executed'],0)

    def test_offsets_changed_target_conflicts_and_incorrect_final_sizes_discard_buffer(self):
        for envelope,target in ((part(1,31,b'X'),(300,700)),(part(1,33,b'X'),(300,700)),
                (part(0x201,32,b'X'),(300,700)),(part(1,32,self.body[32:]),(300,700)),
                (part(0x201,32,self.body[32:]+b'X'),(300,700)),(part(1,32,b'X'),(300,701)),
                (part(0x101,72,prefix()+self.body[:32]),(300,700))):
            self.start()
            with self.subTest(envelope=envelope),self.assertRaises(EditTransferError):self.stage.accept(envelope,target=target)
            self.assertEqual(self.stage.description()['status'],'idle')

    def test_first_fragment_requires_known_container_and_bound_limits_before_allocation(self):
        for body,total in ((container(),MAX_BYTES+1),(container(),71),(b'\0'*24,72),
                (container()[:16]+struct.pack('<I',53)+container()[20:],72),
                (container()[:20]+b'NOPE'+container()[24:],72)):
            with self.subTest(total=total),self.assertRaises(EditTransferError):
                self.stage.accept(part(0x101,total,prefix()+body[:32]),target=(300,700),prefix=prefix())
            self.assertFalse(self.stage.description()['buffer_allocated'])
        for target in ((True,700),(0,700),(300,1<<32),[300,700],None):
            with self.assertRaises(EditTransferError):self.stage.accept(part(0x101,72,prefix()+self.body[:32]),target=target,prefix=prefix())
        for bad in (None,b'',b'wrong'*5,bytearray(prefix())):
            with self.assertRaises(EditTransferError):self.stage.accept(part(0x101,72,prefix()+self.body[:32]),target=(300,700),prefix=bad)

    def test_exact_capacity_and_fragment_count_are_bounded(self):
        body=container(MAX_BYTES-20);self.start(body)
        for offset in range(32,len(body),60000):
            data=body[offset:offset+60000];last=offset+len(data)==len(body)
            self.stage.accept(part(0x201 if last else 1,offset,data),target=(300,700))
        self.assertEqual(self.stage.description()['received_bytes'],MAX_BYTES)
        source=source_container()
        with self.assertRaises(EditTransferError):self.stage.accept(part(0x101,len(source),source_prefix()+source[:48]),
            target=(300,700),prefix=source_prefix(),kind='source')
        self.assertEqual(self.stage.description()['retained_bytes'],0)
        self.stage.clear();body=container(200);self.start(body,24)
        for offset in range(24,24+MAX_FRAGMENTS-1):self.stage.accept(part(1,offset,b'X'),target=(300,700))
        with self.assertRaises(EditTransferError) as error:self.stage.accept(part(1,151,b'X'),target=(300,700))
        self.assertEqual(error.exception.status,2);self.assertEqual(self.stage.description()['status'],'idle')

    def test_absolute_deadline_clears_partial_and_complete_without_renewal(self):
        self.start();self.now+=ASSEMBLY_SECONDS-1;self.stage.accept(part(1,32,self.body[32:40]),target=(300,700))
        self.now+=1;self.assertEqual(self.stage.description()['status'],'idle')
        self.start();self.stage.accept(part(0x201,32,self.body[32:]),target=(300,700))
        self.now+=ASSEMBLY_SECONDS;self.assertFalse(self.stage.description()['buffer_allocated'])
        with self.assertRaises(EditTransferError):self.stage.accept(part(0x201,32,self.body[32:]),target=(300,700))


class EditTransferSignedTests(unittest.TestCase):
    setUp=edits.EditPreparationWireTests.setUp
    tearDown=edits.EditPreparationWireTests.tearDown
    cip=edits.EditPreparationWireTests.cip
    begin=edits.EditPreparationWireTests.begin
    signed=edits.EditPreparationWireTests.signed
    bind=edits.EditPreparationWireTests.bind
    prepare=edits.EditPreparationWireTests.prepare
    send=edits.EditPreparationWireTests.send

    def ready(self):
        self.prepare();project=self.app.engine.project
        names=project.executable_configuration.routine_names('MainProgram',source_sha256=project.sha256)
        self.app.native_routines=NativeRoutines('a'*64,project.sha256,[dict(program='MainProgram',name=name,
            program_instance=300,instance=700+index) for index,name in enumerate(names)])
        self.routine=self.app.native_routines.lookup('MainProgram','MainRoutine').instance
        self.send(reservations.CONTROLLER_ACQUIRE);self.send(edits.OPEN);self.send(reservations.message())

    def fragment(self,word,position,data,status=0):
        raw=message(word,position,data,self.sequence);self.sequence+=1;result=self.cip(raw)
        self.assertEqual(result[2],status,result.hex())
        if status==0:self.assertEqual(sm.verify_response(result,KEY,request=sm.parse_request(raw)).sequence,self.sequence-1)
        return result

    def first(self):return self.fragment(0x101,72,prefix(routine=self.routine)+container()[:32])

    def test_signed_complete_code_and_source_are_retained_but_source_installation_is_denied(self):
        self.ready();before=copy.deepcopy(self.app.state());self.first()
        self.fragment(0x201,32,container()[32:])
        stage=self.endpoint.state()['native_programming_lease']['edit_transfer']
        self.assertEqual((stage['status'],stage['received_bytes']),('complete',72))
        self.assertEqual(stage['container_sha256'],hashlib.sha256(container()).hexdigest())
        source=source_container();self.fragment(0x101,len(source),source_prefix(self.routine)+source[:48])
        self.assertEqual(self.fragment(0x201,48,source[48:],15),bytes.fromhex('b9000f00'))
        stage=self.endpoint.state()['native_programming_lease']['edit_transfer']
        self.assertEqual(stage['source_description']['rungs'],1)
        self.assertFalse(stage['source_description']['source_applied'])
        self.assertEqual(stage['retained_bytes'],len(source)+72)
        self.assertFalse(stage['routine_installed'] or stage['accepted_edits'])
        self.assertFalse(self.endpoint.programming_lease.transport.description()['open'])
        for key in ('tags','routines','tasks','controller','scan','ms'):self.assertEqual(self.app.state()[key],before[key])
        # Our independent client advances after an outer error; the live context
        # can still read and clean up without accepting the embedded operation.
        self.assertEqual(self.send(bytes.fromhex('0e03200124013001'))[2],0)
        self.send(reservations.message(0x4C,payload=b''));self.send(edits.CLOSE);self.send(reservations.CONTROLLER_RELEASE)
        self.assertEqual(self.endpoint.state()['native_programming_lease']['edit_transfer']['status'],'idle')

    def test_source_name_must_match_reserved_routine_and_bad_source_discards_both_components(self):
        from xml.etree import ElementTree as ET
        self.ready();self.first();self.fragment(0x201,32,container()[32:])
        source=source_container(ET.tostring(xml_source(name='OtherRoutine')))
        self.fragment(0x101,len(source),source_prefix(self.routine)+source[:48])
        self.fragment(0x201,48,source[48:],12)
        self.assertEqual(self.endpoint.programming_lease.edit_transfer.description()['retained_bytes'],0)

    def test_signed_source_translation_and_detached_plan_do_not_change_active_logic(self):
        from xml.etree import ElementTree as ET
        from logixlab.native_symbols import NativeSymbols,Symbol
        from logixlab.native_types import NativeTypes
        self.ready();sha=self.app.engine.project.sha256
        self.app.native_symbols=NativeSymbols('a'*64,sha,[Symbol('',0,'RunLatch',5)],
            programs=[{'name':'MainProgram','instance':300}])
        self.app.native_types=NativeTypes('a'*64,sha,[])
        before=copy.deepcopy(self.app.state())
        self.first();self.fragment(0x201,32,container()[32:])
        source=source_container(ET.tostring(xml_source(text='XIC(@107 5 0 0 0 0@)OTE(@107 5 0 0 0 0@);')))
        self.fragment(0x101,len(source),source_prefix(self.routine)+source[:48]);self.fragment(0x201,48,source[48:])
        description=self.endpoint.state()['native_programming_lease']['edit_transfer']['source_description']
        self.assertTrue(description['operand_bindings_verified'] and description['execution_plan_validated'])
        self.assertFalse(description['source_applied'])
        self.assertEqual(self.endpoint.programming_lease.edit_transfer.translated_rungs,('XIC(RunLatch)OTE(RunLatch);',))
        for key in ('tags','routines','tasks','controller','scan','ms'):self.assertEqual(self.app.state()[key],before[key])

        from test_signed_transfer import controlled_request
        path=prefix(routine=self.routine)[:14]
        record=path+struct.pack('<5I',2,5,0,1,123)
        # The identical inner write in another wrapper cannot stage data.
        self.assertEqual(self.send(record)[2],15)
        raw=controlled_request(record,self.sequence);self.sequence+=1
        response=sm.verify_response(self.cip(raw),KEY,request=sm.parse_request(raw))
        self.assertEqual(response.inner,b'\xDC\0\0\0');self.assertEqual(response.container_control,8)
        state=self.endpoint.state()['native_programming_lease']['edit_transfer']
        self.assertTrue(state['post_source_record']['staged'])
        self.assertFalse(state['routine_installed'] or state['accepted_edits'])
        for key in ('tags','routines','tasks','controller','scan','ms'):self.assertEqual(self.app.state()[key],before[key])
        self.send(reservations.message(0x4C,payload=b''))
        self.assertTrue(self.endpoint.programming_lease.edit_transfer.description()['program_released'])
        self.send(edits.CLOSE)
        self.assertFalse(self.endpoint.programming_lease.edit_transfer.description()['post_source_record']['staged'])

    def test_owner_phase_program_hold_and_matching_routine_binding_are_required(self):
        self.ready();self.send(reservations.message(0x4C,payload=b''))
        self.fragment(0x101,72,prefix(routine=self.routine)+container()[:32],15)
        self.send(reservations.message());self.app.native_routines=None
        self.fragment(0x101,72,prefix(routine=self.routine)+container()[:32],12)
        self.assertEqual(self.endpoint.programming_lease.edit_transfer.description()['status'],'idle')

    def test_unknown_scope_malformed_prefix_or_offset_never_leaves_stale_owned_bytes(self):
        self.ready()
        for start,status in ((prefix(program=301),5),(prefix(routine=999),5),
                (bytes((0x5D,))+prefix(routine=self.routine)[1:],15),
                (prefix(routine=self.routine)[:-16]+struct.pack('<4I',3,2,123,0),3)):
            self.first();self.fragment(0x101,72,start+container()[:32],status)
            self.assertEqual(self.endpoint.programming_lease.edit_transfer.description()['status'],'idle')
        self.first();self.fragment(1,33,b'wrong offset',3)
        self.assertEqual(self.endpoint.programming_lease.edit_transfer.description()['status'],'idle')

    def test_foreign_context_cannot_append_or_clear_owners_partial_routine(self):
        self.ready();self.first();first=self.client;sequence=self.sequence;second=Client(self.endpoint.port);second.register()
        try:
            self.client=second;self.bind();self.sequence=4
            self.fragment(1,32,b'x',15)
            self.assertEqual(self.endpoint.programming_lease.edit_transfer.description()['received_bytes'],32)
        finally:self.client=first;self.sequence=sequence;second.close()

    def test_release_phase_source_and_endpoint_cleanup_clear_all_compiled_bytes(self):
        for action in ('program','controller','source','stop'):
            self.ready();self.first()
            self.fragment(0x201,32,container()[32:]);source=source_container()
            self.fragment(0x101,len(source),source_prefix(self.routine)+source[:48])
            if action=='program':
                self.send(reservations.message(0x4C,payload=b''));self.send(edits.CLOSE);self.send(reservations.CONTROLLER_RELEASE)
            elif action=='controller':self.send(reservations.CONTROLLER_RELEASE)
            elif action=='source':self.app.command('demo',{'sample':'ConveyorDemo'})
            else:self.endpoint.stop()
            self.assertEqual(self.endpoint.programming_lease.edit_transfer.description()['status'],'idle')
            if action!='stop':
                self.client.close();self.client=Client(self.endpoint.port);self.client.register()


if __name__=='__main__':unittest.main()
