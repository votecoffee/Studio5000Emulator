"""Actual temporary effects and private ordered results, without vendor framing."""
from dataclasses import FrozenInstanceError,replace
import hashlib
import json
import struct
from types import MappingProxyType
import unittest
from unittest.mock import patch
import zlib

from logixlab import download_image as di,download_results as dr
from logixlab.resilient_transport import TransportError,ASSEMBLY_SECONDS
from test_download_image import batch,models,prepare
import test_download_image as images
from test_device_payload import fill,container,record
from test_native_types import catalog,source_types
import test_object_staging as objects
import test_template_staging as templates


class ExecutionStatusTests(unittest.TestCase):
    def test_busy_progress_and_exact_completed_byte_coverage_share_the_observed_layout(self):
        busy=dr.ExecutionStatus.decode(struct.pack('<BIH',6,17,0),37)
        self.assertFalse(busy.complete);self.assertEqual(busy.processed_bytes,17)
        complete=dr.ExecutionStatus(0,37)
        self.assertEqual(complete.encode(37),bytes.fromhex('00250000000000'))
        self.assertEqual(dr.ExecutionStatus.decode(complete.encode(37),37),complete)
        self.assertTrue(complete.complete)

    def test_unsupported_states_trailing_words_truncation_and_false_completion_remain_errors(self):
        for raw,expected in ((b'',37),(bytes(6),37),(bytes(8),37),(bytearray(7),37),
                             (struct.pack('<BIH',1,37,0),37),(struct.pack('<BIH',0,36,0),37),
                             (struct.pack('<BIH',6,38,0),37),(struct.pack('<BIH',0,37,1),37),
                             (struct.pack('<BIH',0,37,0),True),(struct.pack('<BIH',0,0,0),0)):
            with self.subTest(raw=raw,expected=expected),self.assertRaises(dr.ResultError):
                dr.ExecutionStatus.decode(raw,expected)
        for state,count in ((False,37),(6,True),(0,-1),(256,37),(0,2**32)):
            with self.assertRaises(dr.ResultError):dr.ExecutionStatus(state,count).encode(37)


class DownloadResultTests(unittest.TestCase):
    def test_every_ordered_record_has_exact_request_digest_scope_and_typed_actual_effect(self):
        rows=batch();image=prepare(rows);results=image.preparation_results(0,64,image.source)
        self.assertEqual(len(results),len(rows))
        for ordinal,(row,result) in enumerate(zip(rows,results)):
            self.assertEqual((result.ordinal,result.service,result.request_bytes),(ordinal,row.service,len(row.request)))
            self.assertEqual(result.scopes,tuple((s.class_id,s.instance) for s in row.scopes))
            self.assertEqual(result.request_sha256,hashlib.sha256(row.request).hexdigest())
            readback=image.read_preparation_effect(ordinal,image.source)
            self.assertEqual(readback.result,result);self.assertTrue(readback.matches)
        self.assertEqual([type(r.effect) for r in results],
                         [dr.TemplateCreate,dr.TemplateAttributes,dr.TemplateWrite,dr.SymbolCreate,dr.TableCreate,
                          dr.ProgramCreate,dr.CoordinationChange,dr.SymbolCreate,dr.RoutineCreate,
                          dr.CoordinationChange,dr.DiagnosticCreate])
        self.assertEqual(results[7].scopes,((0x68,2),(0x6B,1)))
        self.assertEqual(results[6].effect,dr.CoordinationChange(False,True))
        self.assertEqual(results[9].effect,dr.CoordinationChange(True,False))
        self.assertTrue(image.read_preparation_effect(6,image.source).historical_transition)
        self.assertFalse(image.read_preparation_effect(4,image.source).historical_transition)

    def test_each_template_write_fragment_has_independent_slice_digest_and_readback(self):
        rows=list(batch());raw=models(rows)[0].templates[0].definition
        rows[2:3]=[templates.request(0x4D,templates.write(raw[:4],0),0x101),
                   templates.request(0x4D,templates.write(raw[4:],4),0x101)]
        image=prepare(tuple(rows));results=image.preparation_results(2,2,image.source)
        self.assertEqual([(r.effect.offset,r.effect.count) for r in results],[(0,4),(4,len(raw)-4)])
        for result in results:
            data=image.read_template(0x101,result.effect.offset,result.effect.count,image.source)
            self.assertEqual(hashlib.sha256(data).hexdigest(),result.effect.data_sha256)
            self.assertTrue(image.read_preparation_effect(result.ordinal,image.source).matches)
        for args in ((True,0,1),(0x101,-1,1),(0x101,0,0),(0x101,0,di.MAX_READ_BYTES+1),
                     (0x101,len(raw)-1,2),(0x101,True,1)):
            with self.assertRaises(di.ImageError):image.read_template(*args,image.source)

    def test_results_counts_and_pages_are_immutable_bounded_and_complete(self):
        rows=batch()[:3]+tuple(objects.symbol(i,0xFFFF) for i in range(1,101))
        image=prepare(rows);one=image.preparation_results(0,64,image.source);two=image.preparation_results(64,64,image.source)
        self.assertEqual((len(one),len(two)),(64,39));self.assertEqual([r.ordinal for r in one+two],list(range(103)))
        self.assertEqual(image.preparation_results(103,1,image.source),())
        for start,count in ((-1,1),(104,1),(True,1),(0,0),(0,True),(0,65)):
            with self.assertRaises(di.ImageError):image.preparation_results(start,count,image.source)
        with self.assertRaises(FrozenInstanceError):one[0].request_sha256='f'*64
        with self.assertRaises(FrozenInstanceError):one[0].effect.words=0
        with self.assertRaises(FrozenInstanceError):image._results.counts[0].count=0
        with self.assertRaises(FrozenInstanceError):image._results.results=()
        state=image.description()['preparation_results'];self.assertEqual(sum(r['count'] for r in state['operations']),103)
        state['operations'][0]['count']=0
        self.assertEqual(sum(r['count'] for r in image.description()['preparation_results']['operations']),103)

    def test_source_and_record_binding_are_required_for_every_page_and_effect_read(self):
        image=prepare()
        for source in (None,di.Source('c'*64,'b'*64),di.Source('a'*64,'c'*64)):
            for read in (lambda:image.preparation_results(0,1,source),lambda:image.read_preparation_effect(0,source),
                         lambda:image.read_template(0x101,0,1,source)):
                with self.assertRaises(di.ImageError):read()
        image.record_sha256='f'*64
        for read in (lambda:image.preparation_results(0,1,image.source),lambda:image.read_preparation_effect(0,image.source)):
            with self.assertRaises(di.ImageError) as error:read()
            self.assertEqual(error.exception.reason,'download_result_binding_changed')

    def test_changed_actual_template_storage_reports_the_specific_failed_write_effect(self):
        image=prepare();template=image.templates[0]
        image.templates=(replace(template,definition=template.definition[:-1]+b'X'),)
        self.assertTrue(image.read_preparation_effect(0,image.source).matches)
        self.assertTrue(image.read_preparation_effect(1,image.source).matches)
        self.assertFalse(image.read_preparation_effect(2,image.source).matches)
        image.templates=(replace(template,attributes=replace(template.attributes,handle=99)),)
        self.assertFalse(image.read_preparation_effect(1,image.source).matches)

    def test_actual_table_symbol_program_routine_and_diagnostic_resources_are_read_back(self):
        image=prepare();region=image._regions[1]
        image._regions=MappingProxyType({1:replace(region,data=b'\1'+region.data[1:])})
        self.assertFalse(image.read_preparation_effect(4,image.source).matches)
        image._symbols=MappingProxyType({**image._symbols,(0,1):0xFFFF})
        self.assertFalse(image.read_preparation_effect(3,image.source).matches)
        image.programs=();self.assertFalse(image.read_preparation_effect(5,image.source).matches)
        image.routines=(replace(image.routines[0],create_word=1),)
        self.assertFalse(image.read_preparation_effect(8,image.source).matches)
        image.diagnostics=(replace(image.diagnostics[0],code=b'Changed'),)
        self.assertFalse(image.read_preparation_effect(10,image.source).matches)
        image.routines=()
        with self.assertRaises(di.ImageError):image.read_preparation_effect(8,image.source)
        for ordinal in (-1,True,11):
            with self.assertRaises(di.ImageError):image.read_preparation_effect(ordinal,image.source)

    def test_ledger_build_verifies_retained_model_against_each_original_operation(self):
        rows=batch();t,d,o=models(rows);native=catalog(types=source_types()[:1]);verified=native.verify(t.templates)
        original=t.templates[0]
        for changed in (replace(original,words=original.words+1),
                        replace(original,definition=original.definition[:-1]+b'X'),
                        replace(original,attributes=replace(original.attributes,handle=99))):
            t.templates=(changed,)
            with self.assertRaises(di.ImageError) as error:di.DownloadImage.prepare(rows,t,d,o,native,verified)
            self.assertEqual(error.exception.reason,'download_result_effect_mismatch')

    def test_summary_exposes_aggregate_counts_without_request_digests_or_vendor_status_codes(self):
        image=prepare();state=image.description()['preparation_results'];encoded=json.dumps(state)
        self.assertEqual(state['records'],11);self.assertTrue(state['immutable']);self.assertTrue(state['private_internal_only'])
        self.assertFalse(state['wire_encoding_supported']);self.assertFalse(state['vendor_status_exposed'])
        self.assertFalse(state['request_bytes_exposed']);self.assertFalse(state['object_identifiers_exposed'])
        for result in image.preparation_results(0,64,image.source):self.assertNotIn(result.request_sha256,encoded)
        for secret in ('Inner','Private','Value','a'*64,'b'*64):self.assertNotIn(secret,encoded)


class DownloadResultLifetimeTests(unittest.TestCase):
    setUp=images.TransportDownloadImageTests.setUp
    stage_image=images.TransportDownloadImageTests.stage_image

    def test_completed_wire_status_requires_start_full_coverage_and_unchanged_actual_effects(self):
        self.stage_image()
        with self.assertRaises(TransportError):self.stage.execution_status(self.native)
        self.stage.start_prepared_image()
        raw,state=self.stage.execution_status(self.native)
        expected=self.stage.inspection['expanded_bytes']
        self.assertEqual(dr.ExecutionStatus.decode(raw,expected),dr.ExecutionStatus(0,expected))
        self.assertFalse(state['commit']);self.assertEqual(state['records_prepared'],11)
        self.assertEqual(self.stage.execution_status(self.native)[0],raw)
        image=self.stage.download_image
        region=image._regions[1]
        image._regions=MappingProxyType({**image._regions,1:replace(region,data=b'\1'+region.data[1:])})
        with self.assertRaises(TransportError) as error:self.stage.execution_status(self.native)
        self.assertEqual(error.exception.reason,'device_image_result_effect_changed')

    def test_completed_status_never_reuses_foreign_unstarted_expired_or_incomplete_byte_coverage(self):
        self.stage_image();self.stage.start_prepared_image()
        self.stage.inspection['expanded_bytes']+=1
        with self.assertRaises(TransportError) as error:self.stage.execution_status(self.native)
        self.assertEqual(error.exception.reason,'device_image_result_byte_coverage_mismatch')
        self.stage.clear();self.stage_image();self.stage.start_prepared_image()
        with self.assertRaises(TransportError):self.stage.execution_status(catalog(types=source_types()[:1]))
        self.now+=ASSEMBLY_SECONDS
        with self.assertRaises(TransportError):self.stage.execution_status(self.native)

    def test_start_repeat_and_cached_inspection_reuse_identical_results(self):
        self.stage_image();ledger=self.stage.download_image._results
        self.stage.start_prepared_image();self.stage.inspect_payload(self.native);self.stage.start_prepared_image()
        self.assertIs(self.stage.download_image._results,ledger)
        self.assertEqual(len(ledger.results),11)

    def test_start_rejects_missing_or_unbound_result_ledger(self):
        for field in ('empty','acd','l5x'):
            self.stage_image();image=self.stage.download_image
            image._results=(dr.ResultLedger() if field=='empty' else replace(image._results,
                **{'source_acd_sha256' if field=='acd' else 'source_l5x_sha256':'c'*64}))
            with self.assertRaises(TransportError) as error:self.stage.start_prepared_image()
            self.assertEqual(error.exception.reason,'device_image_result_binding_mismatch')
            self.assertFalse(self.stage.image_preparation_started)
            self.stage.clear_fragments()

    def test_delete_fragment_reset_and_expiry_remove_all_ledger_results(self):
        for action in ('delete','clear','expiry'):
            self.stage_image();self.stage.start_prepared_image()
            if action=='delete':self.stage.clear()
            elif action=='clear':self.stage.clear_fragments()
            else:self.now+=ASSEMBLY_SECONDS
            ledger=self.stage.description()['download_image']['preparation_results']
            self.assertEqual(ledger['status'],'idle');self.assertEqual(ledger['records'],0);self.assertEqual(ledger['operations'],[])
            with self.assertRaises(di.ImageError):self.stage.download_image.preparation_results(0,1,di.Source('a'*64,'b'*64))

    def test_late_result_build_failure_is_atomic_cached_and_reset_discards_it(self):
        expanded=b''.join(record(r.request) for r in batch());fill(self.stage,container(zlib.compress(expanded)),expanded)
        native=catalog(types=source_types()[:1])
        with patch('logixlab.download_image.ResultLedger.from_image',side_effect=dr.ResultError('download_result_effect_mismatch')) as builder:
            for _ in range(2):
                with self.assertRaises(TransportError):self.stage.inspect_payload(native)
            self.assertEqual(builder.call_count,1)
        self.assertEqual(self.stage.templates.templates,());self.assertEqual(self.stage.objects.records,0)
        self.assertEqual(self.stage.description()['download_image']['preparation_results']['records'],0)
        self.stage.clear_fragments();self.assertIsNone(self.stage.image_error)


if __name__=='__main__':unittest.main()
