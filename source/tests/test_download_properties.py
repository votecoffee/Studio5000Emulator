"""Controller metadata uses original typed values and a private owning namespace."""
from dataclasses import replace
import unittest
from unittest.mock import patch
from logixlab.download_image import ImageError,Source
from logixlab.download_properties import DownloadProperties,CommittedProperties
from logixlab.incremental_download import value_identity
from logixlab.native_metadata_definitions import Definition
from logixlab.identity import Identity
from logixlab.metadata_query import records as metadata_records
from test_download_namespace import NamespaceFixture,ENUM
import test_native_metadata_values as original
import test_download_metadata as packets
import test_download_controller as controllers
import test_programming_preparation as prep


def catalog(source):
    values=original.catalog(acd=source.acd_sha256,l5x=source.l5x_sha256)
    number=values.rows[-1]
    text=replace(number,definition=1,record_word=len(values.rows)+1,kind=1,
        data='Original ÜTF-8 comment'.encode(),type_code=None,elements=0)
    definitions=replace(values.definitions,rows=(*values.definitions.rows,Definition(36,'SystemNumeric')))
    schema=replace(values.rows[2],record_word=len(values.rows)+2,
        target=replace(values.rows[2].target,instance_word=36))
    return replace(values,definitions=definitions,rows=(*values.rows,text,schema)),number,text


def request(rows,definition=None):
    definition=rows[0].definition if definition is None else definition
    return packets.request(0x349,definition,packets.packet(rows,definition)).request


class PropertyModelTests(unittest.TestCase):
    def setUp(self):
        self.source=Source('a'*64,'b'*64);self.values,self.number,self.text=catalog(self.source)
        self.stage=DownloadProperties()

    def test_numeric_text_and_multifield_packets_have_exact_private_readback_and_idempotent_replay(self):
        before=self.values.body('all-objects');body=packets.packet((self.number,))
        self.stage.stage(body,self.number.definition,self.source,self.values)
        self.assertEqual(value_identity(self.stage.read(0,self.source,self.values)),value_identity(self.number))
        self.stage.stage(body,self.number.definition,self.source,self.values)
        self.assertEqual(self.stage.description()['packets'],1)
        self.stage.stage(packets.packet((self.number,self.text),0),0,self.source,self.values)
        self.assertEqual(self.stage.description()['values'],2)
        self.assertEqual(self.stage.read(1,self.source,self.values).data,self.text.data)
        self.assertEqual(self.values.body('all-objects'),before)
        self.assertFalse(self.stage.description()['identity_changed'] or self.stage.description()['commit'])
        for index in (True,-1,2):
            with self.assertRaises(ImageError):self.stage.read(index,self.source,self.values)

    def test_truncation_unknown_targets_locales_and_values_never_publish_partial_properties(self):
        raw=packets.packet((self.number,))
        for n in range(len(raw)):
            with self.subTest(size=n),self.assertRaises(ImageError):self.stage.stage(raw[:n],self.number.definition,self.source,self.values)
        bad=(replace(self.number,data=bytes(4)),replace(self.number,locale_word=0x409),
            replace(self.number,target=replace(self.number.target,selector_word=1)),self.values.rows[0])
        for row in bad:
            with self.assertRaises(ImageError):self.stage.stage(packets.packet((row,)),row.definition,self.source,self.values)
        with self.assertRaises(ImageError):
            self.stage.stage(packets.packet((self.number,replace(self.text,data=b'Changed')),0),0,self.source,self.values)
        self.assertEqual(self.stage.description()['values'],0)
        for definition in (True,-1,65536):
            with self.assertRaises(ImageError):self.stage.stage(raw,definition,self.source,self.values)

    def test_catalog_source_property_and_packet_ledger_changes_revoke_readback(self):
        for case in ('source','catalog','properties','packets'):
            with self.subTest(case=case):
                self.setUp();self.stage.stage(packets.packet((self.number,)),self.number.definition,self.source,self.values)
                source=self.source;values=self.values
                if case=='source':source=Source('c'*64,'b'*64)
                elif case=='catalog':object.__setattr__(values,'rows',values.rows[:-1])
                elif case=='properties':self.stage._values={}
                else:self.stage._packets=()
                with self.assertRaises(ImageError):self.stage.read(0,source,values)

    def test_storage_limits_leave_existing_properties_intact(self):
        self.stage.stage(packets.packet((self.number,)),self.number.definition,self.source,self.values)
        for name,limit in (('MAX_VALUES',1),('MAX_VALUE_BYTES',1),('MAX_PACKETS',1),('MAX_PACKET_BYTES',1)):
            with patch('logixlab.download_properties.'+name,limit),self.assertRaises(ImageError):
                self.stage.stage(packets.packet((self.number,self.text),0),0,self.source,self.values)
            self.assertEqual(self.stage.description()['values'],1)


class PropertySignedTests(NamespaceFixture,unittest.TestCase):
    def setUp(self):
        controllers.ControllerSignedTests.setUp(self)
        self.values,self.number,self.text=catalog(self.namespace._source)
        self.app.native_metadata_definitions=self.values.definitions;self.app.native_metadata_values=self.values
    complete_tasks=controllers.ControllerSignedTests.complete_tasks

    def configure(self):
        self.complete_tasks()
        self.assertEqual(self.send(bytes.fromhex('0402208e2401')+controllers.payload())[2],0)

    def test_prepared_owner_retains_property_without_changing_source_identity_or_active_values(self):
        raw=request((self.number,));before=self.values.body('all-objects')
        self.assertNotEqual(self.send(raw)[2],0);self.configure()
        self.assertEqual(self.send(raw),bytes.fromhex('cf000000'))
        self.assertEqual(self.send(request((self.number,self.text),0))[2],0)
        self.assertEqual(self.send(ENUM)[2],0)
        self.assertEqual(self.namespace.properties.description()['values'],2)
        self.assertIs(self.app.native_metadata_values,self.values);self.assertEqual(self.values.body('all-objects'),before)
        self.assertEqual(self.app.engine.scan_count,0)
        self.assertEqual(self.send(prep.END)[2],0);self.assertIsNone(self.endpoint.programming_lease.download_namespace)

    def test_unsigned_foreign_run_mode_and_stale_source_cannot_write_properties(self):
        self.configure();raw=request((self.number,))
        self.assertNotEqual(self.cip(raw)[2],0)
        first=self.client;second=self.second_client()
        try:
            self.client=second;self.assertEqual(self.signed(4,raw)[2],15)
        finally:self.client=first;second.close()
        with patch.object(self.app,'controller_state',return_value={'mode':'Run'}):self.assertEqual(self.send(raw)[2],12)
        self.assertEqual(self.namespace.properties.description()['values'],0)
        self.assertEqual(self.send(raw)[2],0)
        self.app.native_metadata_values=original.catalog(acd='c'*64,l5x=self.app.engine.project.sha256)
        self.assertEqual(self.send(ENUM)[2],12)

    def test_unstored_logix_marker_uses_matching_complete_project_and_rechecks_its_profile(self):
        self.configure();project=self.app.engine.project
        marker=replace(self.number,definition=36,target=replace(self.number.target,qualifier=b'ProjectType'),data=b'L\0\0\0')
        self.assertEqual(self.send(request((marker,)))[2],0)
        self.assertTrue(self.namespace.properties.description()['controller_profile_marker'])
        self.assertEqual(self.send(ENUM)[2],0)
        self.assertEqual(self.namespace.properties.read(0,self.namespace._source,self.values,project).data,b'L\0\0\0')
        with self.assertRaises(ImageError):self.namespace.properties.read(0,self.namespace._source,self.values)
        project.version='34';self.assertEqual(self.send(ENUM)[2],12)

    def test_wrong_profile_marker_or_an_existing_conflicting_source_value_cannot_use_fallback(self):
        self.configure();project=self.app.engine.project
        marker=replace(self.number,definition=36,target=replace(self.number.target,qualifier=b'ProjectType'),data=b'L\0\0\0')
        wrong=replace(marker,data=b'X\0\0\0',record_word=len(self.values.rows)+1)
        self.assertEqual(self.send(request((wrong,)))[2],12)
        project.version='34';self.assertEqual(self.send(request((marker,)))[2],12);project.version='35'
        self.app.native_metadata_values=replace(self.values,rows=(*self.values.rows,wrong))
        self.assertEqual(self.send(request((marker,)))[2],12)
        self.assertEqual(self.namespace.properties.description()['values'],0)
        self.assertEqual(self.send(request((wrong,)))[2],0)
        self.assertFalse(self.namespace.properties.description()['controller_profile_marker'])

    def serial_source(self):
        row=replace(self.number,definition=36,record_word=len(self.values.rows)+1,data=bytes(4))
        self.values=replace(self.values,rows=(*self.values.rows,row))
        self.app.native_metadata_values=self.values
        return row

    def test_download_serial_tracks_actual_endpoint_identity_without_changing_original_catalog(self):
        self.configure();stored=self.serial_source();original=self.values.body('all-objects')
        identity=self.endpoint.identity
        row=replace(stored,data=identity.serial.to_bytes(4,'little'))
        self.assertEqual(self.send(request((row,)))[2],0)
        stage=self.namespace.properties
        self.assertTrue(stage.description()['controller_serial_bound'])
        self.assertEqual(stage.read(0,self.namespace._source,self.values,self.app.engine.project).data,row.data)
        self.assertEqual(self.values.body('all-objects'),original)
        self.assertEqual(self.values.rows[-1].data,bytes(4))
        committed=CommittedProperties.prepare(stage,self.namespace._source,self.values,self.app.engine.project)
        self.assertEqual(metadata_records(committed.body(self.values,'controller-all'))[-1].data,row.data)
        self.assertEqual(self.values.body('all-objects'),original)
        self.assertEqual(committed.additions,0)
        self.assertEqual(self.send(request((row,)))[2],0)
        self.assertEqual(self.send(ENUM)[2],0)
        stage._serial_identity=replace(identity,serial=identity.serial+1)
        self.assertEqual(self.send(ENUM)[2],12)

    def test_serial_requires_stored_key_correct_profile_scope_type_and_exact_endpoint_value(self):
        self.configure();stored=self.serial_source();identity=self.endpoint.identity
        row=replace(stored,data=identity.serial.to_bytes(4,'little'))
        for value in (replace(row,data=(identity.serial+1).to_bytes(4,'little')),replace(row,definition=17),
                replace(row,target=replace(row.target,qualifier=b'OtherSerialNumber')),replace(row,locale_word=0x409)):
            with self.subTest(value=value):self.assertEqual(self.send(request((value,)))[2],12)
        stage=self.namespace.properties;payload=packets.packet((row,));source=self.namespace._source;project=self.app.engine.project
        for wrong in (None,replace(identity,profile='research'),replace(identity,product_code=1),replace(identity,serial=True)):
            with self.subTest(identity=wrong),self.assertRaises(ImageError):
                stage.stage(payload,row.definition,source,self.values,project,identity=wrong)
        self.assertEqual(stage.description()['values'],0)
        self.app.native_metadata_values=replace(self.values,rows=self.values.rows[:-1])
        self.assertEqual(self.send(request((row,)))[2],12)
