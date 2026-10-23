"""Completed temporary Symbols remain separate from runtime discovery."""
import copy
from dataclasses import replace
import struct
import time
import unittest
import zlib

from logixlab.download_image import ImageError,Source
from logixlab.download_namespace import DownloadNamespace,SYMBOL_BASE,SYMBOL_STRIDE
from logixlab.resilient_transport import ResilientTransport
from test_native_types import catalog,source_types
from test_source_object_verification import bindings
import test_device_payload as payloads
import test_download_image as images
import test_programming_preparation as prep
import test_programming_lease as leases
import test_resilient_transport as transport

ENUM=bytes.fromhex('5502206b240001000500')
STATUS=bytes.fromhex('4d03210012042400')


class NamespaceTests(unittest.TestCase):
    def setUp(self):
        self.stage=ResilientTransport()
        expanded=b''.join(payloads.record(r.request) for r in images.batch())
        payloads.fill(self.stage,payloads.container(zlib.compress(expanded)),expanded)
        self.native=catalog(types=source_types()[:1]);symbols,routines=bindings()
        self.catalogs=dict(native_symbols=symbols,native_routines=routines)
        self.stage.inspect_payload(self.native,**self.catalogs);self.stage.start_prepared_image()
        self.namespace=DownloadNamespace(self.stage,self.native,**self.catalogs)
        self.source=Source('a'*64,'b'*64)

    def test_deleting_transport_keeps_exact_source_objects_and_bounded_scoped_pages(self):
        self.stage.clear()
        self.namespace.validate(self.source,self.native,**self.catalogs)
        self.assertEqual(self.namespace.symbol_page(0,0,8),(False,struct.pack('<II',1,SYMBOL_BASE)))
        self.assertEqual(self.namespace.symbol_page(2,0,8),(False,struct.pack('<II',1,SYMBOL_BASE+SYMBOL_STRIDE)))
        self.assertEqual(self.namespace.symbol_page(0,2,8),(False,b''))
        row=self.namespace.resolve_symbol(SYMBOL_BASE)
        self.assertEqual((row.program,row.instance,row.table),(0,1,1))
        for address in (SYMBOL_BASE+1,SYMBOL_BASE-1,True,0):
            with self.assertRaises(ImageError):self.namespace.resolve_symbol(address)
        for args in ((0,0,7),(3,0,8),(True,0,8),(0,-1,8),(0,0,-1)):
            with self.assertRaises(ImageError):self.namespace.symbol_page(*args)
        state=self.namespace.description()
        self.assertTrue(state['owner_only']);self.assertFalse(state['commit'] or state['physical_addresses'])

    def test_catalog_source_effect_and_record_changes_invalidate_retained_image(self):
        for case in ('source','types','type-mutation','objects','effect','digest'):
            self.setUp();native=self.native;catalogs=self.catalogs;source=self.source
            if case=='source':source=Source('c'*64,'b'*64)
            elif case=='types':native=catalog(types=source_types()[:1])
            elif case=='type-mutation':native.type_ids['inner']=0x301
            elif case=='objects':catalogs={**catalogs,'native_routines':None}
            elif case=='effect':
                image=self.namespace._image;image._regions={1:replace(image._regions[1],data=b'evil')}
            else:self.namespace._image.record_sha256='c'*64
            with self.subTest(case=case),self.assertRaises(ImageError):self.namespace.validate(source,native,**catalogs)

    def test_handle_pagination_preserves_sorted_ids_and_duplicate_ids_in_other_scopes(self):
        self.namespace._symbols=self.namespace._symbols+(replace(self.namespace._symbols[0],instance=3,address=SYMBOL_BASE+64),)
        self.assertEqual(self.namespace.symbol_page(0,0,8),(True,struct.pack('<II',1,SYMBOL_BASE)))
        self.assertEqual(self.namespace.symbol_page(0,2,8),(False,struct.pack('<II',3,SYMBOL_BASE+64)))


class NamespaceSignedTests(unittest.TestCase):
    setUp=payloads.InspectionSignedTests.setUp
    tearDown=payloads.InspectionSignedTests.tearDown
    cip=payloads.InspectionSignedTests.cip
    begin=payloads.InspectionSignedTests.begin
    signed=payloads.InspectionSignedTests.signed
    bind=payloads.InspectionSignedTests.bind
    prepare=payloads.InspectionSignedTests.prepare
    second_client=payloads.InspectionSignedTests.second_client
    send=payloads.InspectionSignedTests.send
    acquire=payloads.InspectionSignedTests.acquire
    ready=payloads.InspectionSignedTests.ready
    description=payloads.InspectionSignedTests.description
    fragment=payloads.InspectionSignedTests.fragment
    stage=payloads.InspectionSignedTests.stage
    object_source_fixture=payloads.InspectionSignedTests.object_source_fixture

    def retain(self):
        self.object_source_fixture();self.assertEqual(self.send(payloads.INSPECT)[2],0)
        self.assertEqual(self.send(STATUS)[2],0);self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertIsNotNone(self.endpoint.programming_lease.download_namespace)

    def test_completed_namespace_survives_delete_only_for_owner_and_does_not_change_model(self):
        self.retain();before=copy.deepcopy(self.app.state())
        self.assertEqual(self.send(ENUM),bytes.fromhex('d5000000')+struct.pack('<II',1,SYMBOL_BASE))
        first=self.client;second=self.second_client()
        try:
            self.client=second
            result=self.signed(4,ENUM)
            self.assertNotEqual(result[4:],struct.pack('<II',1,SYMBOL_BASE))
        finally:self.client=first;second.close()
        self.assertEqual(self.send(transport.SETUP)[2],15)
        self.assertEqual(self.send(ENUM[:-2]+b'\x0c\0')[2],0x14)
        for field in ('tags','scan','ms','mode','changes'):self.assertEqual(self.app.state()[field],before[field])

    def test_source_changes_reject_owner_readback(self):
        self.retain();self.app.native_routines=None
        self.assertEqual(self.send(ENUM)[2],12)

    def test_delete_before_result_query_does_not_retain_namespace(self):
        self.object_source_fixture();self.assertEqual(self.send(payloads.INSPECT)[2],0)
        self.assertEqual(self.send(transport.DELETE)[2],0)
        self.assertIsNone(self.endpoint.programming_lease.download_namespace)

    def test_stale_completed_catalog_rejects_retention_and_still_deletes_transport(self):
        self.object_source_fixture();self.assertEqual(self.send(payloads.INSPECT)[2],0)
        self.assertEqual(self.send(STATUS)[2],0);self.app.native_routines=None
        self.assertEqual(self.send(transport.DELETE)[2],12)
        self.assertFalse(self.description()['open'])
        self.assertIsNone(self.endpoint.programming_lease.download_namespace)

    def test_cleanup_end_release_reset_expiry_disconnect_and_bad_mac_drop_namespace(self):
        for action in ('end','release','reset','expiry','disconnect','bad-mac'):
            with self.subTest(action=action):
                self.retain();lease=self.endpoint.programming_lease
                if action=='end':self.send(prep.END)
                elif action=='release':self.send(leases.RELEASE)
                elif action=='reset':self.app.command('reset',{})
                elif action=='expiry':lease.owner.deadline=time.monotonic()-1;lease.live(self.app.generation,self.app.engine.project.sha256)
                elif action=='bad-mac':
                    from test_signed_messages import request
                    raw=request(0x36,inner=ENUM,sequence=self.sequence)
                    self.assertEqual(self.cip(raw[:-1]+bytes((raw[-1]^1,)))[2],15)
                else:
                    self.client.close();deadline=time.monotonic()+2
                    while lease.download_namespace is not None and time.monotonic()<deadline:time.sleep(.01)
                self.assertIsNone(lease.download_namespace)
                self.client.close();self.client=leases.Client(self.endpoint.port);self.client.register()
