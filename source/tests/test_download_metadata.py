"""Download metadata framing and isolated, source-checked later-batch effects."""
from dataclasses import replace
import json
import struct
import unittest
from unittest.mock import patch

from logixlab import device_payload as dp,metadata_query as wire
from logixlab.download_image import ImageError,Source
from logixlab.incremental_download import IncrementalDownload
from logixlab.ethernetip import logical
import test_native_metadata_values as original
import test_download_image as images
import test_object_staging as objects
import test_diagnostic_staging as diagnostics
from test_download_namespace import NamespaceFixture,STATUS,ENUM
import test_device_payload as payloads
import test_resilient_transport as transport


def packet(rows,definition=None):
    """Build the two packet shapes independently of the production decoder."""
    definition=rows[0].definition if definition is None else definition
    first=rows[0].target
    data=struct.pack('<HIIHH',first.class_id,first.instance_word,first.context_word,first.selector_word,len(first.qualifier))+first.qualifier
    if not definition:data+=struct.pack('<H',len(rows))
    for row in rows:
        data+=struct.pack('<H',row.locale_word)
        if not definition:data+=struct.pack('<H',row.definition)
        data+=bytes(12)+struct.pack('<H',row.kind)
        if row.kind==1:data+=struct.pack('<H',len(row.data))+row.data
        elif row.kind==2:data+=struct.pack('<HH',row.type_code,row.elements)+row.data
        elif row.kind==3:
            data+=struct.pack('<H',len(row.references))
            for ref in row.references:
                t=ref.target
                data+=struct.pack('<H',len(ref.name))+ref.name+struct.pack('<HIIHH',t.class_id,t.instance_word,t.context_word,t.selector_word,len(t.qualifier))+t.qualifier
    return struct.pack('<II',0x301,len(data))+data


def request(cls,instance,payload,service=0x4F,path=None):
    path=logical(0x20,cls)+logical(0x24,instance) if path is None else path
    raw=bytes((service,len(path)//2))+path+payload
    return dp.records(struct.pack('<I',len(raw))+raw)[0]


def metadata(row):return request(0x349,row.definition,packet((row,)))
def table(data=b'\x32\0\0\0',**changes):
    header=dict(offset=0,selector=0,size=len(data));header.update(changes)
    return request(0x6A,1,struct.pack('<IBH',*header.values())+data,0x50)


class DownloadMetadataCodecTests(unittest.TestCase):
    def test_single_multilocale_and_typed_values_preserve_all_fields_except_local_ordinals(self):
        source=original.catalog()
        for row in source.rows:
            parsed=wire.download_records(packet((row,)),row.definition)
            self.assertEqual(parsed,(replace(row,record_word=1),))
        rows=source.rows[3:5]
        parsed=wire.download_records(packet(rows,0),0)
        self.assertEqual(parsed,tuple(replace(row,record_word=i) for i,row in enumerate(rows,1)))
        self.assertEqual(parsed[1].data,'Übersicht'.encode())

    def test_truncated_trailing_counts_duplicate_fields_unknown_kinds_and_reserved_words_reject(self):
        row=original.catalog().rows[3];raw=packet((row,))
        for n in range(len(raw)):
            with self.subTest(size=n),self.assertRaises(ValueError):wire.download_records(raw[:n],row.definition)
        for data,definition in ((raw+b'X',1),(packet((row,row),0),0),(raw,True),(raw,0x10000),(bytearray(raw),1),
                (raw[:24]+b'\1'+raw[25:],1),(raw[:36]+b'\x09\0'+raw[38:],1)):
            with self.subTest(definition=definition),self.assertRaises(ValueError):wire.download_records(data,definition)
        for count in (0,65):
            body=packet((row,),0);body=body[:22]+struct.pack('<H',count)+body[24:]
            with self.assertRaises(ValueError):wire.download_records(body,0)


class IncrementalEffectsTests(unittest.TestCase):
    def setUp(self):
        self.image=images.prepare();self.source=self.image.source;self.values=original.catalog()

    def prepare(self,rows):return IncrementalDownload.prepare(rows,self.image,self.source,self.values)

    def test_private_table_bytes_metadata_diagnostic_noop_and_coordination_have_readback(self):
        value=self.values.rows[3];rows=(metadata(value),table(),diagnostics.request(b'\0\0',service=4),
            objects.coordinate(),objects.coordinate(acquire=False))
        stage=self.prepare(rows);state=stage.description()
        self.assertEqual((state['records_modeled'],state['metadata_values'],state['table_bytes'],state['diagnostic_empty_updates'],state['coordination_records']),(5,1,4,1,2))
        self.assertEqual(state['status'],'modeled');self.assertTrue(state['source_metadata_verified'])
        self.assertEqual(stage.read_table(1,self.image,self.source,self.values),b'\x32\0\0\0')
        self.assertEqual(stage.read_metadata(0,self.image,self.source,self.values),replace(value,record_word=1))
        self.assertEqual(self.image.read_table(1,0,4,self.source),bytes(4))
        for name in ('base_image_modified','active_catalog_replaced','execution_supported','completion_supported','commit','payloads_exposed','metadata_targets_resolved'):self.assertFalse(state[name])
        for text in ('Private text','Member',value.data.hex()):self.assertNotIn(text,json.dumps(state))

    def test_unknown_operations_leave_partial_known_effects_and_redacted_counts(self):
        unknown=objects.request(0x68,2,b'Private data',4)
        stage=self.prepare((table(),unknown));state=stage.description()
        self.assertEqual((state['status'],state['records_modeled'],state['unsupported_records']),('partial',1,1))
        self.assertEqual(state['unsupported_operations'],[dict(service=4,class_id=0x68,count=1)])
        state['unsupported_operations'][0]['count']=99
        self.assertEqual(stage.description()['unsupported_records'],1)

    def test_changed_metadata_target_locale_definition_and_value_never_stage_a_prefix(self):
        row=self.values.rows[3]
        for bad in (replace(row,data=b'Changed'),replace(row,locale_word=0x409),replace(row,definition=4),
                replace(row,target=replace(row.target,instance_word=123))):
            with self.subTest(bad=bad.definition),self.assertRaises(ImageError) as error:self.prepare((table(),metadata(bad)))
            self.assertEqual(error.exception.reason,'incremental_metadata_value_mismatch')
            self.assertEqual(self.image.read_table(1,0,4,self.source),bytes(4))
        with self.assertRaises(ImageError):self.prepare((metadata(row),metadata(row)))
        for values in (None,original.catalog(acd='c'*64)):
            with self.assertRaises(ImageError):IncrementalDownload.prepare((metadata(row),),self.image,self.source,values)

    def test_table_writes_are_whole_exact_nonrepeated_and_globally_scoped(self):
        bad=(table(b'A'),table(offset=1),table(selector=1),table(size=3),table(size=5),table(b''),
            request(0x6A,2,b'\0'*11,0x50),request(0x6A,1,b'\0'*6,0x50),
            objects.request(0x6A,1,b'\0'*11,0x50,program=2))
        for row in bad:
            with self.subTest(row=row.request.hex()),self.assertRaises(ImageError):self.prepare((row,))
        with self.assertRaises(ImageError):self.prepare((table(),table()))
        self.assertEqual(self.image.read_table(1,0,4,self.source),bytes(4))

    def test_diagnostic_and_coordination_targets_must_exist_and_release(self):
        for rows in ((diagnostics.request(b'\0\0',99,4),),(diagnostics.request(b'\1\0',service=4),),
                (objects.coordinate(program=3),),(objects.coordinate(),),
                (objects.coordinate(acquire=False),),(objects.coordinate(),objects.coordinate())):
            with self.subTest(records=len(rows)),self.assertRaises(ImageError):self.prepare(rows)

    def test_readback_rechecks_base_source_and_metadata_catalog_and_never_accepts_boolean_indices(self):
        stage=self.prepare((metadata(self.values.rows[3]),table()))
        for values in (None,original.catalog(acd='c'*64)):
            with self.assertRaises(ImageError):stage.read_table(1,self.image,self.source,values)
        for ordinal in (-1,True,1):
            with self.assertRaises(ImageError):stage.read_metadata(ordinal,self.image,self.source,self.values)
        for instance in (True,0,2):
            with self.assertRaises(ImageError):stage.read_table(instance,self.image,self.source,self.values)
        with self.assertRaises(ImageError):stage.validate(images.prepare(),self.source,self.values)
        with self.assertRaises(ImageError):stage.validate(self.image,Source('c'*64,'b'*64),self.values)
        old=self.image._regions;self.image._regions={1:replace(old[1],data=b'evil')}
        with self.assertRaises(ImageError):stage.validate(self.image,self.source,self.values)
        self.image._regions=old
        changed=original.catalog();object.__setattr__(changed,'rows',changed.rows[:-1])
        with self.assertRaises(ImageError):stage.validate(self.image,self.source,changed)
        with patch('logixlab.incremental_download.MAX_METADATA_VALUES',0),self.assertRaises(ImageError):self.prepare((metadata(self.values.rows[3]),))


class IncrementalEffectsSignedTests(NamespaceFixture,unittest.TestCase):
    def next_batch(self,rows):
        from test_incremental_download import IncrementalSignedTests
        expanded=b''.join(payloads.record(row.request) for row in rows)
        IncrementalSignedTests.next_batch(self,expanded)

    def test_owning_client_stages_and_processes_known_effects_and_cleanup_retains_private_updates(self):
        self.retain();namespace=self.endpoint.programming_lease.download_namespace
        identity=self.app.native_project_identity
        self.app.native_metadata_values=original.catalog(acd=identity.source_acd_sha256,l5x=self.app.engine.project.sha256)
        row=self.app.native_metadata_values.rows[3]
        self.next_batch((metadata(row),table(),diagnostics.request(b'\0\0',service=4)))
        for query in (payloads.INSPECT,STATUS):self.assertEqual(self.send(query)[2],0)
        state=self.description()['incremental_staging']
        self.assertEqual((state['records_modeled'],state['metadata_packets'],state['table_writes']),(3,1,1))
        self.assertEqual(namespace._image.read_table(1,0,4,namespace._source),bytes(4))
        self.assertEqual(self.app.engine.scan_count,0)
        self.assertTrue(self.send(ENUM)[2]==0)
        self.send(transport.DELETE)
        self.assertEqual(self.description()['incremental_staging']['status'],'idle')
        self.assertIs(self.endpoint.programming_lease.download_namespace,namespace)
        self.assertEqual(namespace.description()['incremental_records'],3)

    def test_late_invalid_known_operation_publishes_no_partial_proposal(self):
        self.retain();identity=self.app.native_project_identity
        self.app.native_metadata_values=original.catalog(acd=identity.source_acd_sha256,l5x=self.app.engine.project.sha256)
        self.next_batch((table(),metadata(replace(self.app.native_metadata_values.rows[3],data=b'Wrong'))))
        self.assertEqual(self.send(payloads.INSPECT)[2],12)
        state=self.description()['incremental_staging']
        self.assertEqual((state['status'],state['table_writes']),('invalid',0))
        self.assertFalse(self.endpoint.programming_lease.transport.execution_status_reported)

    def test_current_metadata_source_is_rechecked_after_successful_staging(self):
        self.retain();identity=self.app.native_project_identity
        self.app.native_metadata_values=original.catalog(acd=identity.source_acd_sha256,l5x=self.app.engine.project.sha256)
        self.next_batch((metadata(self.app.native_metadata_values.rows[3]),table()))
        self.assertEqual(self.send(payloads.INSPECT)[2],0)
        self.assertEqual(self.description()['incremental_staging']['table_writes'],1)
        self.app.native_metadata_values=original.catalog(acd='c'*64,l5x=self.app.engine.project.sha256)
        self.assertEqual(self.send(STATUS)[2],12)
        state=self.description()['incremental_staging']
        self.assertEqual((state['status'],state['table_writes']),('invalid',0))
        self.assertFalse(self.endpoint.programming_lease.transport.execution_status_reported)

    def test_expiry_end_release_and_reset_clear_all_new_proposals(self):
        import test_programming_preparation as prep
        import test_programming_lease as leases
        for action in ('expiry','end','release','reset'):
            with self.subTest(action=action):
                self.retain();self.next_batch((table(),))
                self.assertEqual(self.send(payloads.INSPECT)[2],0)
                self.assertEqual(self.description()['incremental_staging']['table_writes'],1)
                if action=='expiry':self.endpoint.programming_lease.transport.deadline=0
                elif action=='end':self.send(prep.END)
                elif action=='release':self.send(leases.RELEASE)
                else:self.app.command('reset',{})
                self.assertEqual(self.description()['incremental_staging']['status'],'idle')
