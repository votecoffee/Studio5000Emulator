"""Source identity checks cannot grant installation or name unknown Symbols."""
import copy
from dataclasses import replace
import json
import unittest
import zlib
from logixlab import source_object_verification as check
from logixlab.download_image import Source
from logixlab.native_symbols import NativeSymbols,Symbol
from logixlab.native_routines import NativeRoutines
from logixlab.native_auxiliary_symbols import NativeAuxiliarySymbols
from logixlab.native_tables import NativeTables
from logixlab.object_staging import ObjectStaging,NULL_REFERENCE
from logixlab.resilient_transport import ResilientTransport,TransportError
import test_object_staging as objects
import test_download_image as images
import test_device_payload as payloads
from test_native_types import catalog,source_types


def bindings(acd='a'*64,l5x='b'*64):
    symbols=NativeSymbols(acd,l5x,[Symbol('',0,'PublicTag',1),Symbol('ProgramA',2,'ScopedTag',1)],
                          programs=[dict(name='ProgramA',instance=2)])
    routines=NativeRoutines(acd,l5x,[dict(program='ProgramA',name='Logic',program_instance=2,instance=1)])
    return symbols,routines


class SourceObjectTests(unittest.TestCase):
    def test_table_id_sets_require_original_source_and_do_not_verify_addresses_or_storage(self):
        symbols,routines=bindings();stage=ObjectStaging.from_batch(objects.batch());source=Source('a'*64,'b'*64)
        tables=NativeTables('a'*64,'b'*64,[dict(instance=1,name='$Original$',body_bytes=420)])
        result=check.verify(stage,source,symbols,routines,tables=tables)
        self.assertEqual((result['status'],result['tables_matched'],result['tables_unresolved']),('matched',1,0))
        self.assertTrue(result['table_identities_verified']);self.assertFalse(result['addresses_verified'])
        self.assertFalse(result['compiled_code_verified']);self.assertFalse(result['install_authority'])
        for binding in (NativeTables('a'*64,'b'*64,[]),NativeTables('a'*64,'b'*64,[dict(instance=2,name='$Other$',body_bytes=420)])):
            result=check.verify(stage,source,symbols,routines,tables=binding)
            self.assertEqual(result['status'],'mismatch');self.assertIn('native_table_identity_mismatch',result['errors'])
            self.assertFalse(result['table_identities_verified'])
        for binding in (NativeTables('c'*64,'b'*64,[]),NativeTables('a'*64,'c'*64,[])):
            self.assertEqual(check.verify(stage,source,symbols,routines,tables=binding)['status'],'mismatch')
        self.assertFalse(check.verify(stage,source,symbols,routines)['table_identities_verified'])
        self.assertEqual(check.verify(stage,source,symbols,routines)['tables_unresolved'],1)
        wrong=NativeTables('a'*64,'b'*64,[])
        self.assertEqual(check.verify(stage,source,None,None,tables=wrong)['status'],'mismatch')
        symbols.program_inventory_error='Unavailable Program inventory'
        self.assertEqual(check.verify(stage,source,symbols,routines,tables=wrong)['status'],'mismatch')

    def test_auxiliary_identities_complete_both_scopes_but_unknown_and_missing_ids_stay_explicit(self):
        symbols,routines=bindings();source=Source('a'*64,'b'*64)
        rows=objects.batch()[:-1]+(objects.symbol(instance=9,table=NULL_REFERENCE,program=2),)+objects.batch()[-1:]
        rows+=(objects.symbol(instance=9,table=NULL_REFERENCE),)
        stage=ObjectStaging.from_batch(rows)
        auxiliary=NativeAuxiliarySymbols('a'*64,'b'*64,[dict(program_instance=p,instance=9,name='__Aux',component_type=256) for p in (0,2)])
        result=check.verify(stage,source,symbols,routines,auxiliary)
        self.assertEqual((result['status'],result['symbols_matched'],result['auxiliary_symbols_matched'],result['symbols_unresolved']),('matched',4,2,0))
        extra=ObjectStaging.from_batch(rows+(objects.symbol(instance=10,table=NULL_REFERENCE),))
        self.assertEqual(check.verify(extra,source,symbols,routines,auxiliary)['status'],'partial')
        missing=ObjectStaging.from_batch(objects.batch())
        self.assertIn('native_auxiliary_symbol_identity_missing',check.verify(missing,source,symbols,routines,auxiliary)['errors'])
        for value in (NativeAuxiliarySymbols('c'*64,'b'*64,auxiliary.manifest()['symbols']),
                      NativeAuxiliarySymbols('a'*64,'b'*64,[dict(program_instance=0,instance=1,name='__Bad',component_type=256)])):
            self.assertEqual(check.verify(stage,source,symbols,routines,value)['status'],'mismatch')

    def test_original_scoped_id_sets_match_without_claiming_table_or_compiled_equivalence(self):
        symbols,routines=bindings();stage=ObjectStaging.from_batch(objects.batch())
        result=check.verify(stage,Source('a'*64,'b'*64),symbols,routines)
        self.assertEqual(result['status'],'matched')
        self.assertEqual([result[k] for k in ('programs_matched','routines_matched','symbols_matched','symbols_unresolved')],[1,1,2,0])
        for key in ('table_identities_verified','compiled_code_verified','addresses_verified','install_authority','active_catalog_replaced','commit'):
            self.assertFalse(result[key])
        for text in ('ProgramA','PublicTag','ScopedTag','Logic','instance','source_acd_sha256'):
            self.assertNotIn(text,json.dumps(result))

    def test_unknown_internal_symbols_remain_partial_and_missing_known_symbols_are_mismatches(self):
        symbols,routines=bindings();source=Source('a'*64,'b'*64)
        stage=ObjectStaging.from_batch(objects.batch()+(objects.symbol(instance=9,table=NULL_REFERENCE),))
        result=check.verify(stage,source,symbols,routines)
        self.assertEqual((result['status'],result['symbols_matched'],result['symbols_unresolved']),('partial',2,1))
        symbols.by_key['missing']=Symbol('',0,'MissingTag',10)
        result=check.verify(stage,source,symbols,routines)
        self.assertEqual(result['status'],'mismatch');self.assertEqual(result['errors'],['native_symbol_identity_missing'])

    def test_program_and_routine_ids_cannot_be_numbered_or_resolved_in_another_parent(self):
        symbols,routines=bindings();stage=ObjectStaging.from_batch(objects.batch());source=Source('a'*64,'b'*64)
        changed=copy.copy(stage);changed.programs=(3,)
        self.assertIn('native_program_identity_mismatch',check.verify(changed,source,symbols,routines)['errors'])
        for parent,child in ((2,2),(3,1)):
            changed=copy.copy(stage);changed.routines=(replace(stage.routines[0],program=parent,instance=child),)
            self.assertIn('native_routine_identity_mismatch',check.verify(changed,source,symbols,routines)['errors'])

    def test_missing_incomplete_cross_source_and_inconsistent_parent_catalogs_fail_closed(self):
        stage=ObjectStaging.from_batch(objects.batch());source=Source('a'*64,'b'*64);symbols,routines=bindings()
        for s,r,expected in ((None,None,'unavailable'),(symbols,None,'unavailable'),
                (bindings(acd='c'*64)[0],routines,'mismatch'),(symbols,bindings(l5x='c'*64)[1],'mismatch')):
            self.assertEqual(check.verify(stage,source,s,r)['status'],expected)
        symbols.program_inventory_error='Unavailable original Program inventory'
        self.assertEqual(check.verify(stage,source,symbols,routines)['status'],'unavailable')
        symbols,routines=bindings();symbols.programs['programa']=3
        self.assertEqual(check.verify(stage,source,symbols,routines)['errors'],['native_object_parent_mismatch'])

    def test_binding_stamp_covers_derived_parent_maps_and_same_content_replacements(self):
        symbols,routines=bindings();stamp=check.binding_stamp(symbols,routines)
        self.assertEqual(stamp,check.binding_stamp(*bindings()))
        symbols.program_ids[3]='Other';self.assertNotEqual(stamp,check.binding_stamp(symbols,routines))
        self.assertEqual(check.binding_stamp(None,None),(None,None,None,None))


class SourceObjectTransportTests(unittest.TestCase):
    def test_table_bindings_are_pinned_and_cleared_with_the_prepared_image(self):
        tables=NativeTables('a'*64,'b'*64,[dict(instance=1,name='$Original$',body_bytes=420)])
        self.stage.inspect_payload(self.native,native_symbols=self.symbols,native_routines=self.routines,native_tables=tables)
        self.stage.start_prepared_image()
        self.assertTrue(self.stage.description()['source_object_verification']['table_identities_verified'])
        for value in (None,NativeTables('a'*64,'b'*64,[])):
            with self.assertRaises(TransportError):self.stage.prepared_result_state(self.native,
                native_symbols=self.symbols,native_routines=self.routines,native_tables=value)
        self.stage.prepared_result_state(self.native,native_symbols=self.symbols,native_routines=self.routines,native_tables=tables)
        self.stage.clear();result=self.stage.description()['source_object_verification']
        self.assertFalse(result['table_identities_verified']);self.assertEqual(result['tables_matched'],0)

    def test_auxiliary_source_is_pinned_through_processing_and_result_queries(self):
        self.stage.clear()
        rows=images.batch()+(objects.symbol(instance=9,table=NULL_REFERENCE),)
        raw=b''.join(payloads.record(row.request) for row in rows)
        payloads.fill(self.stage,payloads.container(zlib.compress(raw)),raw)
        auxiliary=NativeAuxiliarySymbols('a'*64,'b'*64,[dict(program_instance=0,instance=9,name='__Aux',component_type=256)])
        self.stage.inspect_payload(self.native,native_symbols=self.symbols,native_routines=self.routines,native_auxiliary_symbols=auxiliary)
        self.assertEqual(self.stage.description()['source_object_verification']['auxiliary_symbols_matched'],1)
        self.stage.start_prepared_image()
        for binding in (None,NativeAuxiliarySymbols('a'*64,'b'*64,[])):
            with self.assertRaises(TransportError):self.stage.prepared_result_state(self.native,
                native_symbols=self.symbols,native_routines=self.routines,native_auxiliary_symbols=binding)
        self.stage.prepared_result_state(self.native,native_symbols=self.symbols,native_routines=self.routines,native_auxiliary_symbols=auxiliary)
        self.stage.clear();self.assertEqual(self.stage.description()['source_object_verification']['auxiliary_symbols_matched'],0)

    def setUp(self):
        self.now=100;self.stage=ResilientTransport(lambda:self.now);self.native=catalog(types=source_types()[:1])
        self.symbols,self.routines=bindings();self.fill()

    def fill(self):
        raw=b''.join(payloads.record(row.request) for row in images.batch())
        payloads.fill(self.stage,payloads.container(zlib.compress(raw)),raw)

    def inspect(self):
        return self.stage.inspect_payload(self.native,native_symbols=self.symbols,native_routines=self.routines)

    def test_success_is_cached_but_replaced_or_mutated_bindings_cannot_start_or_read_results(self):
        self.inspect();self.stage.start_prepared_image();image=self.stage.download_image
        self.inspect();self.assertIs(image,self.stage.download_image)
        self.assertEqual(self.stage.description()['source_object_verification']['status'],'matched')
        self.stage.prepared_result_state(self.native,native_symbols=self.symbols,native_routines=self.routines)
        for s,r in ((None,None),(self.symbols,None)):
            with self.assertRaises(TransportError):self.stage.prepared_result_state(self.native,native_symbols=s,native_routines=r)
        self.symbols.program_ids[3]='Other'
        for action in (self.inspect,self.stage.start_prepared_image):
            with self.assertRaises(TransportError) as error:action()
            self.assertEqual(error.exception.reason,'native_object_binding_changed')

    def test_mismatch_discards_all_models_caches_fixed_error_and_clears_with_transport(self):
        self.routines=NativeRoutines('a'*64,'b'*64,[dict(program='ProgramA',name='Logic',program_instance=2,instance=9)])
        for _ in range(2):
            with self.assertRaises(TransportError) as error:self.inspect()
            self.assertEqual(error.exception.reason,'source_object_verification_failed')
        result=self.stage.description();self.assertEqual(result['source_object_verification']['status'],'mismatch')
        self.assertEqual(result['template_staging']['templates'],0);self.assertEqual(result['object_staging']['records_modeled'],0)
        self.assertEqual(result['download_image']['storage_bytes'],0)
        result['source_object_verification']['errors'].append('mutated')
        self.assertNotIn('mutated',self.stage.description()['source_object_verification']['errors'])
        self.stage.clear();self.assertEqual(self.stage.description()['source_object_verification']['status'],'idle')

    def test_expiry_and_missing_optional_catalogs_do_not_claim_identity_matches(self):
        self.inspect();self.now+=31
        self.assertEqual(self.stage.description()['source_object_verification']['status'],'idle')
        self.fill();self.stage.inspect_payload(self.native)
        result=self.stage.description()['source_object_verification']
        self.assertEqual((result['status'],result['symbols_matched'],result['symbols_unresolved']),('unavailable',0,2))
        self.stage.start_prepared_image();self.assertFalse(self.stage.download_image.description()['commit'])


if __name__=='__main__':unittest.main()
