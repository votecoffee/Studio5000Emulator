"""Temporary image readback and lifetime, distinct from native download success."""
from dataclasses import FrozenInstanceError,replace
import hashlib
import json
import struct
import unittest
from unittest.mock import patch
import zlib

from logixlab import download_image as di
from logixlab.resilient_transport import ResilientTransport,TransportError,ASSEMBLY_SECONDS
from logixlab import template_staging as ts,diagnostic_staging as ds,object_staging as os
from test_native_types import catalog,source_types
from test_template_layout import definition
import test_template_staging as templates
import test_diagnostic_staging as diagnostics
import test_object_staging as objects
from test_device_payload import fill,container,record


def batch():
    raw=definition(header=b'Inner;n');raw+=b'\0'*(-len(raw)%4)
    return templates.batch(0x101,raw)+objects.batch()+(diagnostics.request(),)


def models(rows):
    t=ts.TemplateStaging.from_batch(rows);d=ds.DiagnosticStaging.from_batch(rows)
    return t,d,os.ObjectStaging.from_batch(rows,t.templates)


def prepare(rows=None,native=None):
    rows=batch() if rows is None else rows
    native=catalog(types=source_types()[:1]) if native is None else native
    t,d,o=models(rows)
    return di.DownloadImage.prepare(rows,t,d,o,native,native.verify(t.templates))


class DownloadImageTests(unittest.TestCase):
    def test_complete_source_verified_graph_allocates_independent_temporary_tables(self):
        image=prepare();source=di.Source('a'*64,'b'*64);state=image.description()
        self.assertEqual(state['status'],'prepared');self.assertEqual(state['records_prepared'],11)
        self.assertEqual((state['tables_allocated'],state['storage_bytes'],state['symbols_linked'],
                          state['symbols_unresolved']),(1,4,1,1))
        self.assertEqual((state['templates_retained'],state['diagnostics_retained'],state['programs_retained'],
                          state['routines_retained']),(1,1,1,1))
        self.assertEqual(image.read_table(1,0,4,source),bytes(4))
        self.assertEqual(image.read_symbol(0,1,1,2,source),bytes(2))
        for field in ('initial_values_applied','compiled_routines_installed','active_catalog_replaced',
                      'native_execution_supported','commit','values_exposed'):self.assertFalse(state[field])
        self.assertTrue(state['temporary_readback']);self.assertTrue(state['source_bound'])

    def test_record_digest_is_bound_to_exact_order_and_bytes(self):
        rows=batch();image=prepare(rows)
        expected=hashlib.sha256(b''.join(record(r.request) for r in rows)).hexdigest()
        self.assertEqual(image.record_sha256,expected)
        other=prepare(rows[-1:]+rows[:-1]);self.assertNotEqual(image.record_sha256,other.record_sha256)
        self.assertEqual(image.description()['storage_bytes'],other.description()['storage_bytes'])

    def test_source_hashes_are_strict_and_both_are_required_for_every_read(self):
        image=prepare()
        for first,second in (('bad','b'*64),('A'*64,'b'*64),('a'*64,1),(None,'b'*64)):
            with self.assertRaises(di.ImageError):di.Source(first,second)
        for source in (None,('a'*64,'b'*64),di.Source('c'*64,'b'*64),di.Source('a'*64,'c'*64)):
            for read in (lambda:image.read_table(1,0,1,source),lambda:image.read_symbol(0,1,0,1,source),
                         lambda:image.attribute(0x6A,1,2,source)):
                with self.assertRaises(di.ImageError):read()
        with self.assertRaises(FrozenInstanceError):image.source.acd_sha256='f'*64

    def test_readback_cannot_cross_table_or_allocation_bounds_or_accept_boolean_ids(self):
        image=prepare();source=image.source
        for values in ((2,0,1),(True,0,1),(1,-1,1),(1,4,1),(1,3,2),(1,0,0),
                       (1,0,di.MAX_READ_BYTES+1),(1,False,1),(1,0,True)):
            with self.subTest(values=values),self.assertRaises(di.ImageError):image.read_table(*values,source)
        for values in ((2,1),(0,2),(True,1),(0,True)):
            with self.assertRaises(di.ImageError):image.read_symbol(*values,0,1,source)
        with self.assertRaises(di.ImageError) as error:image.read_symbol(2,1,0,1,source)
        self.assertEqual(error.exception.reason,'download_symbol_storage_unresolved')

    def test_attributes_have_exact_widths_and_no_invented_name_or_address(self):
        image=prepare();source=image.source
        self.assertEqual(image.attribute(0x6A,1,1,source),bytes(12))
        self.assertEqual(image.attribute(0x6A,1,2,source),b'\xc4\0')
        self.assertEqual(image.attribute(0x6A,1,6,source),b'\x6a\0')
        self.assertEqual(image.attribute(0x6A,1,8,source),b'\1\0\0\0')
        self.assertEqual(image.attribute(0x6B,1,12,source),b'\1\0\0\0')
        self.assertEqual(image.attribute(0x6B,1,12,source,program=2),b'\xff\xff\0\0')
        self.assertEqual(image.attribute(0x6C,0x101,5,source),b'\4\0\0\0')
        for args in ((0x6B,1,1),(0x6B,1,5),(0x6A,1,3),(0x6A,1,7),(0x6C,0x101,3),
                     (0x68,2,1),(0x6C,1,1),(0x6A,True,1)):
            with self.assertRaises(di.ImageError):image.attribute(*args,source)
        with self.assertRaises(di.ImageError):image.attribute(0x6A,1,1,source,program=2)

    def test_unhandled_service_on_known_class_and_unknown_class_block_allocation(self):
        for extra in (objects.request(0x6A,service=3),objects.request(0x7F)):
            rows=batch()+(extra,);native=catalog(types=source_types()[:1]);t,d,o=models(rows)
            image=di.DownloadImage.prepare(rows,t,d,o,native,native.verify(t.templates))
            self.assertEqual(image.description()['reason'],'unmodeled_device_record')
            self.assertEqual(image.description()['storage_bytes'],0)

    def test_absent_source_failed_verification_or_coverage_cannot_publish_an_image(self):
        rows=batch();native=catalog(types=source_types()[:1]);t,d,o=models(rows);verification=native.verify(t.templates)
        for source,result,reason in ((None,verification,'native_type_source_required'),
                (native,{**verification,'status':'mismatch'},'source_verified_types_required'),
                (native,{**verification,'types_matched':0},'source_verified_types_required'),
                (native,{**verification,'types_unavailable':1},'source_verified_types_required')):
            image=di.DownloadImage.prepare(rows,t,d,o,source,result)
            self.assertEqual(image.description()['reason'],reason);self.assertEqual(image.description()['tables_allocated'],0)
        o.records-=1
        self.assertEqual(di.DownloadImage.prepare(rows,t,d,o,native,verification).description()['reason'],
                         'device_record_coverage_mismatch')
        self.assertEqual(di.DownloadImage.prepare((),t,d,o,native,verification).description()['reason'],'empty_device_batch')

    def test_large_array_reads_are_bounded_and_storage_capacity_precedes_allocation(self):
        rows=batch()+(objects.table(2,os.NULL_REFERENCE,0x20C2,(32768,0,0),use=4),)
        image=prepare(rows);self.assertEqual(len(image.read_table(2,0,di.MAX_READ_BYTES,image.source)),di.MAX_READ_BYTES)
        self.assertEqual(image.description()['storage_bytes'],32772)
        native=catalog(types=source_types()[:1]);t,d,o=models(rows)
        with patch.object(di,'MAX_STORAGE_BYTES',32771),self.assertRaises(di.ImageError):
            di.DownloadImage.prepare(rows,t,d,o,native,native.verify(t.templates))

    def test_summary_is_defensive_and_never_exposes_definitions_ids_values_or_source_hashes(self):
        image=prepare();report=image.description();report['records_prepared']=999
        self.assertEqual(image.description()['records_prepared'],11)
        encoded=json.dumps(report)
        for text in ('Inner','Private','Value','a'*64,'b'*64):self.assertNotIn(text,encoded)
        with self.assertRaises(TypeError):image._regions[1]=None
        with self.assertRaises(FrozenInstanceError):image._regions[1].data=b'evil'


class TransportDownloadImageTests(unittest.TestCase):
    def setUp(self):self.now=100.;self.stage=ResilientTransport(lambda:self.now)

    def stage_image(self):
        expanded=b''.join(record(r.request) for r in batch())
        fill(self.stage,container(zlib.compress(expanded)),expanded)
        self.native=catalog(types=source_types()[:1]);self.stage.inspect_payload(self.native)

    def test_transport_inspection_publishes_cached_image_without_marking_native_execution(self):
        self.stage_image();image=self.stage.download_image;self.stage.inspect_payload(self.native)
        self.assertIs(self.stage.download_image,image)
        self.assertEqual(self.stage.description()['download_image']['status'],'prepared')
        self.assertEqual(self.stage.inspection['records_executed'],0)
        self.assertFalse(self.stage.inspection['execution_supported'])

    def test_delete_fragment_clear_and_expiry_discard_the_entire_image(self):
        for action in ('delete','clear','expiry'):
            self.stage_image()
            if action=='delete':self.stage.clear()
            elif action=='clear':self.stage.clear_fragments()
            else:self.now+=ASSEMBLY_SECONDS
            self.assertEqual(self.stage.description()['download_image']['status'],'idle')
            self.assertEqual(self.stage.download_image.description()['storage_bytes'],0)

    def test_source_change_cannot_reuse_the_image_and_late_errors_are_atomic(self):
        self.stage_image();image=self.stage.download_image
        with self.assertRaises(TransportError):self.stage.inspect_payload(catalog())
        self.assertIs(self.stage.download_image,image)
        self.stage.clear_fragments()
        expanded=b''.join(record(r.request) for r in batch())
        fill(self.stage,container(zlib.compress(expanded)),expanded)
        with patch('logixlab.resilient_transport.DownloadImage.prepare',side_effect=di.ImageError('download_image_storage_limit')):
            for _ in range(2):
                with self.assertRaises(TransportError) as error:self.stage.inspect_payload(self.native)
                self.assertEqual(error.exception.reason,'download_image_storage_limit')
        self.assertEqual(self.stage.templates.templates,());self.assertEqual(self.stage.objects.records,0)
        self.assertEqual(self.stage.description()['download_image']['status'],'invalid')
        self.stage.clear_fragments();self.assertIsNone(self.stage.image_error)


if __name__=='__main__':unittest.main()
