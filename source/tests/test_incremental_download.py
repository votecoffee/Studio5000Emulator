"""A later download batch cannot replace the completed namespace or run code."""
import copy
import json
import unittest
from unittest.mock import patch
import zlib

from logixlab import device_payload
from logixlab.resilient_transport import ResilientTransport,TransportError,DEVICE_HEADER,ASSEMBLY_SECONDS
from test_download_namespace import NamespaceFixture,ENUM,STATUS
import test_device_payload as payloads
import test_resilient_transport as transport
import test_transport_fragments as fragments


class IncrementalModelTests(unittest.TestCase):
    def test_separate_cached_inspection_never_short_circuits_source_image_verification(self):
        stage=ResilientTransport();payloads.fill(stage)
        with patch('logixlab.resilient_transport.device_payload.decode',wraps=device_payload.decode) as decode:
            stage.inspect_incremental_payload();stage.inspect_incremental_payload()
            self.assertEqual(decode.call_count,1)
            self.assertEqual(stage.inspection['status'],'idle')
            stage.inspect_payload()
            self.assertEqual(decode.call_count,2)
        state=stage.description();summary=state['incremental_inspection']
        self.assertEqual((summary['status'],summary['record_count']),('decoded',2))
        summary['operations'][0]['count']=999
        self.assertNotEqual(stage.description()['incremental_inspection']['operations'][0]['count'],999)
        self.assertFalse(stage.execution_status_reported or stage.image_preparation_started)
        for private in ('PrivateDefinition','PrivateRoutine',payloads.ENCODED.hex()):
            self.assertNotIn(private,json.dumps(state))

    def test_missing_complete_bad_expansion_cached_failure_and_expiry(self):
        now=[100.];stage=ResilientTransport(lambda:now[0])
        with self.assertRaises(TransportError):stage.inspect_incremental_payload()
        payloads.fill(stage,expanded=payloads.EXPANDED+b'X')
        with patch('logixlab.resilient_transport.device_payload.decode',wraps=device_payload.decode) as decode:
            for _ in range(2):
                with self.assertRaises(TransportError) as error:stage.inspect_incremental_payload()
                self.assertEqual(error.exception.reason,'expanded_size_mismatch')
            self.assertEqual(decode.call_count,1)
        self.assertEqual(stage.inspection['status'],'idle')
        now[0]+=ASSEMBLY_SECONDS
        with self.assertRaises(TransportError):stage.inspect_incremental_payload()
        self.assertEqual(stage.description()['incremental_inspection']['status'],'idle')
        stage.clear();self.assertIsNone(stage.setup)


class IncrementalSignedTests(NamespaceFixture,unittest.TestCase):
    def next_batch(self,expanded=payloads.EXPANDED,encoded=None):
        encoded=payloads.container(zlib.compress(expanded)) if encoded is None else encoded
        self.assertEqual(self.send(transport.SETUP[:8]+transport.payload(opaque=len(expanded)))[2],0)
        cut=len(encoded)//2
        self.fragment(0x101,len(encoded),DEVICE_HEADER+encoded[:cut])
        self.fragment(0x201,cut,encoded[cut:])

    def test_complete_second_batch_is_inspected_but_neither_started_nor_completed(self):
        self.retain();lease=self.endpoint.programming_lease;namespace=lease.download_namespace
        before=copy.deepcopy(self.app.state());catalog=self.send(ENUM)
        self.next_batch()
        for query in (payloads.INSPECT,STATUS,payloads.INSPECT):self.assertEqual(self.send(query)[2],15)
        stage=self.description();summary=stage['incremental_inspection']
        self.assertEqual((summary['status'],summary['expanded_bytes'],summary['record_count']),('decoded',len(payloads.EXPANDED),2))
        self.assertEqual(stage['inspection']['status'],'idle')
        self.assertFalse(stage['download_image']['preparation_started'] or lease.transport.execution_status_reported)
        self.assertEqual(summary['records_executed'],0);self.assertFalse(summary['execution_supported'])
        self.assertEqual(self.send(ENUM),catalog);self.assertIs(lease.download_namespace,namespace)
        for private in ('PrivateDefinition','PrivateRoutine'):
            self.assertNotIn(private,json.dumps(self.endpoint.state(True)['events']))
        self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertIs(lease.download_namespace,namespace);self.assertEqual(self.send(ENUM),catalog)
        self.assertEqual(self.description()['incremental_inspection']['status'],'idle')
        self.assertTrue(any(row['reason']=='incremental_download_processing_unimplemented'
                            for row in self.endpoint.state()['native_rejections']))
        for field in ('tags','scan','ms','mode','changes'):self.assertEqual(self.app.state()[field],before[field])

    def test_other_client_cannot_open_or_append_owners_next_buffer(self):
        self.retain();self.next_batch();before=self.description();namespace=self.endpoint.programming_lease.download_namespace
        first=self.client;second=self.second_client()
        try:
            self.client=second
            self.assertEqual(self.signed(4,transport.SETUP)[2],15)
            self.assertEqual(self.cip(fragments.message(0x101,5,DEVICE_HEADER+b'AB',5))[2],15)
        finally:self.client=first;second.close()
        self.assertEqual(self.description(),before);self.assertIs(self.endpoint.programming_lease.download_namespace,namespace)

    def test_source_catalog_change_denies_next_setup_fragment_start_and_status(self):
        self.retain();self.app.native_routines=None
        self.assertEqual(self.send(transport.SETUP)[2],12);self.assertFalse(self.description()['open'])
        # Restore an equivalent catalog and open; later source mutation still denies writes.
        from test_source_object_verification import bindings
        identity=self.app.native_project_identity
        _,self.app.native_routines=bindings(acd=identity.source_acd_sha256,l5x=self.app.engine.project.sha256)
        self.assertEqual(self.send(transport.SETUP)[2],0)
        self.app.native_routines=None
        self.fragment(0x101,5,DEVICE_HEADER+b'AB',expect=12)
        self.assertEqual(self.description()['received_bytes'],0)
        for query in (payloads.INSPECT,STATUS):self.assertEqual(self.send(query)[2],12)

    def test_conflict_malformed_fragment_invalid_container_and_expiry_preserve_namespace(self):
        self.retain();namespace=self.endpoint.programming_lease.download_namespace;catalog=self.send(ENUM)
        self.assertEqual(self.send(transport.SETUP)[2],0)
        self.assertEqual(self.send(transport.SETUP[:8]+transport.payload(opaque=18))[2],12)
        self.fragment(0x101,5,DEVICE_HEADER+b'AB')
        self.fragment(0x201,1,b'CDE',expect=3)
        self.assertEqual(self.description()['received_bytes'],0)
        self.assertIs(self.endpoint.programming_lease.download_namespace,namespace)
        self.send(transport.DELETE)
        self.next_batch(encoded=b'BadContainer')
        self.assertEqual(self.send(payloads.INSPECT)[2],3)
        self.assertEqual(self.send(STATUS)[2],3)
        self.assertEqual(self.description()['incremental_inspection']['status'],'invalid')
        self.endpoint.programming_lease.transport.deadline=0
        self.assertEqual(self.send(payloads.INSPECT)[2],12)
        self.assertEqual(self.description()['received_bytes'],0)
        self.assertIs(self.endpoint.programming_lease.download_namespace,namespace)
        self.assertEqual(self.send(ENUM),catalog)

    def test_incomplete_and_nonempty_commands_do_not_claim_completion_or_erase_namespace(self):
        self.retain();namespace=self.endpoint.programming_lease.download_namespace
        self.assertEqual(self.send(transport.SETUP)[2],0)
        self.fragment(0x101,5,DEVICE_HEADER+b'AB')
        for query in (payloads.INSPECT,STATUS):
            self.assertEqual(self.send(query)[2],12)
            self.assertEqual(self.send(query+b'X')[2],0x15)
        self.assertFalse(self.endpoint.programming_lease.transport.execution_status_reported)
        self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertIs(self.endpoint.programming_lease.download_namespace,namespace)
