"""Only proven label-free RLL routines expose an empty nested Label catalog."""
import base64
import copy
import hashlib
import struct
import unittest
from xml.etree import ElementTree as E

import test_routine_reference_symbols as fixtures
from logixlab.ethernetip import CIPError,decode_path
from tools.anonymous_client import AnonymousClient
from tools.upload_inventory import logical_path


def path(program=123,routine=40,label=0):
    return logical_path(0x6D,routine,program=program)+logical_path(0x8C,label)


class RoutineLabelTests(unittest.TestCase):
    tearDown=fixtures.RoutineReferenceTests.tearDown
    cip=fixtures.RoutineReferenceTests.cip

    def setUp(self):
        fixtures.RoutineReferenceTests.setUp(self);self.endpoint.native_read_only=True;self.endpoint.allow_writes=False

    def test_three_numeric_scopes_preserve_parent_ids_and_empty_replies_leave_model_intact(self):
        before=copy.deepcopy(self.app.state())
        for program in (123,124):
            for routine in (40,41):
                decoded=decode_path(path(program,routine))
                self.assertEqual((decoded.program_instance,decoded.routine_instance,decoded.class_id,decoded.instance),(program,routine,0x8C,0))
                self.assertEqual(self.cip(0x4B,path(program,routine)),b'\xcb\0\0\0')
        for key in ('tags','routines','scan','ms','controller'):self.assertEqual(self.app.state()[key],before[key])

    def test_global_class_revision_is_layout_metadata_without_a_global_label_inventory(self):
        target=logical_path(0x8C,0)
        self.assertEqual(self.cip(14,target+b'\x30\1'),b'\x8e\0\0\0\1\0')
        self.assertEqual(self.cip(3,target,struct.pack('<HH',1,1)),b'\x83\0\0\0'+struct.pack('<HHHH',1,1,0,1))
        self.assertEqual(self.cip(14,target+b'\x30\2')[2],0x14)
        self.assertEqual(self.cip(0x4B,target)[2],4)

    def test_nonempty_labels_are_not_hidden_and_other_routines_keep_their_own_empty_proof(self):
        data=copy.deepcopy(self.data);root=E.fromstring(base64.b64decode(data['content']))
        content=root.find("./Controller/Programs/Program[@Name='MainProgram']/Routines/Routine[@Name='MainRoutine']/RLLContent")
        content.clear();rung=E.SubElement(content,'Rung',Number='0',Type='N');E.SubElement(rung,'Text').text='LBL(Again)NOP();'
        raw=E.tostring(root);sha=hashlib.sha256(raw).hexdigest();data['content']=base64.b64encode(raw).decode()
        for key in ('native_project_identity','native_symbols','native_tasks','native_routines','native_auxiliary_symbols'):
            data[key]['source_l5x_sha256']=sha
        self.app.command('load',data);self.assertFalse(self.app.engine.blockers)
        self.assertEqual(self.app.engine.labels['mainprogram/mainroutine'],{'again':0})
        self.assertEqual(self.cip(0x4B,path())[2],0x0C)
        self.assertEqual(self.cip(0x4B,path(124)),b'\xcb\0\0\0')

    def test_unknown_parents_legacy_mode_payloads_and_other_services_do_not_invent_labels(self):
        for target in (path(999),path(routine=999),path(label=1)):
            self.assertEqual(self.cip(0x4B,target)[2],5)
        self.assertEqual(self.cip(0x4B,path(),b'x')[2],0x15)
        for service in (1,3,14,4,0x10,0x4C,0x5C):self.assertEqual(self.cip(service,path())[2],8)
        self.assertEqual(self.cip(0x4B,path()+b'\x30\1')[2],4)
        self.endpoint.native_read_only=False
        self.assertEqual(self.cip(0x4B,path())[2],4)

    def test_missing_source_dirty_logic_and_uncertain_runtime_never_become_empty_catalogs(self):
        engine=self.app.engine;target=engine.project.routines['mainprogram/mainroutine'];target.kind='ST'
        self.assertEqual(self.cip(0x4B,path())[2],0x0C);target.kind='RLL'
        engine.project.runtime_revision=1
        self.assertEqual(self.cip(0x4B,path())[2],0x0C);engine.project.runtime_revision=0
        engine._native_fault_history_uncertain=True
        self.assertEqual(self.cip(0x4B,path())[2],0x0C);engine._native_fault_history_uncertain=False
        self.app.native_routines=None
        self.assertEqual(self.cip(0x4B,path())[2],0x0C)

    def test_malformed_or_foreign_scope_chains_cannot_flatten_into_a_program_routine(self):
        invalid=[logical_path(0x8C,0),logical_path(0x6D,40)+logical_path(0x8C,0),
            logical_path(0x68,123)+logical_path(0x8C,0),
            logical_path(0x6D,40,aoi=7)+logical_path(0x8C,0),path()+logical_path(0x8C,0),path()[:-2]]
        for target in invalid:
            with self.subTest(target=target.hex()):self.assertEqual(self.cip(0x4B,target)[2],4)
        with self.assertRaises(CIPError):decode_path(path()[:-2])

    def test_signed_tcp_upload_query_accepts_the_same_nested_scope(self):
        self.endpoint.start()
        with AnonymousClient(self.endpoint) as client:
            client.bind();target=path();raw=bytes((0x4B,len(target)//2))+target
            self.assertEqual(client.request(raw),b'\xcb\0\0\0')
        self.assertEqual(self.app.engine.scan_count,0)


if __name__=='__main__':unittest.main()
