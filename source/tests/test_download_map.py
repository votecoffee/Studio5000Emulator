"""A late Map flag has owned, source-bound private effects and no I/O commit."""
import copy
from dataclasses import replace
import struct
import unittest
from unittest.mock import patch

from logixlab.download_image import ImageError
from logixlab.download_map import DownloadMap
import test_download_routines as routines
import test_download_setup as setup
import test_device_payload as payloads
import test_resilient_transport as transport
import test_programming_preparation as prep
from test_download_namespace import NamespaceFixture,STATUS,ENUM


WRITE=bytes.fromhex('040220692401010007000100')
READ=bytes.fromhex('0e03206924013007')
LIST=bytes.fromhex('030220692401020002000700')
PAYLOAD=struct.pack('<HHH',1,7,1)


def map_route(self):
    result=routines.nop_route(self);result[2].attrib.update(ProductCode='168',Major='35',Minor='11')
    return result


class MapSignedTests(NamespaceFixture,unittest.TestCase):
    complete_tasks=setup.SetupSignedTests.complete_tasks
    configure=setup.SetupSignedTests.configure
    ready_setup=setup.SetupSignedTests.ready_setup
    ready_routines=routines.RoutineSignedTests.ready_routines
    next_routines=routines.RoutineSignedTests.next_routines

    def setUp(self):
        with patch.object(routines.headers.io_tests.IOMapTests,'local_route',map_route):setup.SetupSignedTests.setUp(self)

    def bindings(self):return self.endpoint.router.download_map_bindings(self.endpoint.programming_lease)

    def ready_map(self):
        self.ready_routines();self.next_routines()
        self.assertEqual(self.send(payloads.INSPECT)[2],0);self.assertEqual(self.send(STATUS)[2],0)
        self.assertEqual(self.send(transport.DELETE)[2],0)

    def test_owned_flag_has_exact_private_readback_and_preserves_all_earlier_effects(self):
        self.ready_map();ns=self.namespace;image=ns._image;updates=ns._incremental;code=ns._routine_batch
        before=copy.deepcopy(self.app.engine.memory.values);identity=self.endpoint.identity
        for _ in range(2):self.assertEqual(self.send(WRITE),bytes.fromhex('84000000010007000000'))
        self.assertEqual(ns.local_map.read(self.bindings()),b'\1\0')
        self.assertEqual(self.send(READ),bytes.fromhex('8e0000000100'))
        expected_key=b''.join(identity.attributes()[n] for n in (1,2,3,4))
        self.assertEqual(self.send(LIST),bytes.fromhex('83000000020002000000')+expected_key+bytes.fromhex('070000000100'))
        self.assertNotEqual(self.cip(READ)[2],0)
        self.assertIs(ns._image,image);self.assertIs(ns._incremental,updates);self.assertIs(ns._routine_batch,code)
        self.assertEqual(updates.read_attribute(0x69,0,1,7,image,ns._source,None,self.hb),b'\5\0')
        state=ns.local_map.description();self.assertTrue(state['configured'] and state['private_header_only'])
        for field in ('active_io_changed','active_project_changed','compiled_code_executed','commit','flag_bits_interpreted'):
            self.assertFalse(state[field])
        self.assertEqual(self.app.engine.memory.values,before);self.assertEqual(self.app.engine.scan_count,0)
        self.assertEqual(self.send(ENUM)[2],0);self.assertEqual(self.send(prep.END)[2],0)
        self.assertIsNone(self.endpoint.programming_lease.download_namespace);self.assertNotEqual(self.send(READ)[2],0)

    def test_setup_and_completed_routine_result_are_required_before_the_flag(self):
        self.assertEqual(self.send(WRITE)[2],12);self.ready_routines()
        self.assertEqual(self.send(WRITE)[2],12);self.next_routines();self.send(payloads.INSPECT)
        self.assertEqual(self.send(WRITE)[2],12);self.send(STATUS);self.send(transport.DELETE)
        self.assertEqual(self.send(WRITE)[2],0)

    def test_foreign_unsigned_run_and_wrong_scope_cannot_modify_the_flag(self):
        self.ready_map();self.assertNotEqual(self.cip(WRITE)[2],0)
        first=self.client;second=self.second_client()
        try:
            self.client=second;self.assertEqual(self.signed(4,WRITE)[2],15)
        finally:self.client=first;second.close()
        with patch.object(self.app,'controller_state',return_value={'mode':'Run'}):self.assertEqual(self.send(WRITE)[2],12)
        for raw in (bytes.fromhex('04042068240220692401')+PAYLOAD,bytes.fromhex('0403206924013007')+PAYLOAD):
            self.assertNotEqual(self.send(raw)[2],0)
        self.assertFalse(self.namespace.local_map.description()['configured'])

    def test_malformed_unknown_flag_and_reply_budget_failure_publish_nothing(self):
        self.ready_map();stage=DownloadMap();bindings=self.bindings()
        for raw in (PAYLOAD[:-1],PAYLOAD+b'X',struct.pack('<HHH',1,7,0),struct.pack('<HHH',1,7,5),struct.pack('<HHH',1,8,1),bytearray(PAYLOAD)):
            with self.subTest(raw=raw),self.assertRaises(ImageError):stage.configure(raw,bindings)
            self.assertFalse(stage.description()['configured'])
        changed=DownloadMap()
        with patch.object(bindings,'stamp',side_effect=('first','second')),self.assertRaises(ImageError):changed.configure(PAYLOAD,bindings)
        self.assertFalse(changed.description()['configured'])
        original=self.endpoint.router.native_read
        def limited(inner,session,native,depth,limit,budget,**kwargs):return original(inner,session,native,depth,9,budget,**kwargs)
        with patch.object(self.endpoint.router,'native_read',side_effect=limited):self.assertEqual(self.send(WRITE)[2],0x1B)
        self.assertFalse(self.namespace.local_map.description()['configured'])

    def test_current_identity_source_and_any_earlier_effect_changes_revoke_readback(self):
        self.ready_map();self.assertEqual(self.send(WRITE)[2],0);stage=self.namespace.local_map
        saved=self.endpoint.identity
        self.endpoint.identity=replace(saved,product_code=212);self.assertEqual(self.send(READ)[2],12)
        self.endpoint.identity=saved;self.assertEqual(self.send(READ)[2],0)
        stage._value=b'\5\0';self.assertEqual(self.send(READ)[2],12)
        stage._value=b'\1\0';self.assertEqual(self.send(READ)[2],0)
        self.namespace._routine_batch._values={};self.assertEqual(self.send(ENUM)[2],12)
        self.assertEqual(self.send(prep.END)[2],0)


if __name__=='__main__':unittest.main()
