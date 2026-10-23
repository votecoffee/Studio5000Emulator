"""Bounded Controller download properties and signed owner/source isolation."""
import copy
from dataclasses import replace
import struct
import tempfile
import unittest
from unittest.mock import patch
from logixlab.download_controller import ControllerBindings,DownloadController,WIDTHS,attributes
from logixlab.download_image import ImageError
from test_download_namespace import NamespaceFixture,ENUM
import test_download_tasks as task_tests
import test_download_headers as headers
import test_programming_preparation as prep


def source_configuration(app):
    app.engine.project.controller_configuration=replace(app.engine.project.controller_configuration,
        security_code=0,empty_power_loss_handler=True,empty_fault_handler=True,
        time_slice=20,share_unused_time_slice=1,time_slice_defaulted=True,share_unused_defaulted=True,
        pass_through_configuration='EnabledWithAppend',match_project_to_controller=False,
        automatic_firmware_update_inhibit=0,can_use_rpi_from_producer=False,
        report_minor_overflow=False,automatic_diagnostics_enabled=True,changes_to_detect=2**64-1,
        continue_test_edits=False,io_memory_pad_percentage=0,data_table_pad_percentage=0)


def payload(values=None):
    values=values or {1:bytes(4),6:bytes(4),3:bytes(2),13:bytes(4),15:b'\0',16:bytes(2),17:b'\0',
        23:b'\0',28:b'\xff'*8,25:struct.pack('<I',3),31:b'\0',35:b'\1',33:bytes(32),34:bytes(32)}
    return struct.pack('<H',len(values))+b''.join(struct.pack('<H',n)+value for n,value in values.items())


class ControllerModelTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.app=headers.Application(folder.name);self.namespace,_=headers.fixture(self.app);task_tests.task_catalog(self.app)
        source_configuration(self.app)
        self.bindings=ControllerBindings(self.app.engine,self.namespace,self.app.native_project_identity)
        self.stage=DownloadController()

    def test_private_readback_retains_each_source_setting_and_zero_signature_operands(self):
        config=self.app.engine.project.controller_configuration;memory=copy.deepcopy(self.app.engine.memory.values)
        result=self.stage.configure(payload(),self.bindings)
        self.assertEqual(result,struct.pack('<H',14)+b''.join(struct.pack('<HH',n,0) for n in WIDTHS))
        self.assertEqual(dict(self.stage._values),attributes(payload()));self.stage.validate(self.bindings)
        self.assertIs(self.app.engine.project.controller_configuration,config)
        self.assertEqual(config.compatibility_attributes()[3],struct.pack('<H',20))
        self.assertEqual(self.app.engine.memory.values,memory)
        state=self.stage.description();self.assertEqual(state['attributes'],14)
        self.assertTrue(state['signature_reset_operands']);self.assertFalse(state['signature_verified'] or state['commit'])

    def test_malformed_and_wrong_field_values_reject_without_partial_properties(self):
        raw=payload()
        for length in range(len(raw)):
            with self.subTest(length=length),self.assertRaises(ImageError):self.stage.configure(raw[:length],self.bindings)
        for bad in (raw+b'X',raw[:2]+b'\2\0'+raw[4:],raw[:8]+b'\1\0'+raw[10:]):
            with self.assertRaises(ImageError):self.stage.configure(bad,self.bindings)
        for n in WIDTHS:
            values=attributes(raw);value=values[n];values[n]=bytes((value[0]^1,))+value[1:]
            with self.subTest(attribute=n),self.assertRaises(ImageError):self.stage.configure(payload(values),self.bindings)
        self.assertEqual(self.stage.description()['attributes'],0)
        values=dict(reversed(list(attributes(raw).items())))
        result=self.stage.configure(payload(values),self.bindings)
        self.assertEqual(result,struct.pack('<H',14)+b''.join(struct.pack('<HH',n,0) for n in values))

    def test_explicit_legacy_settings_cannot_be_replaced_with_omission_defaults(self):
        project=self.app.engine.project
        project.controller_configuration=replace(project.controller_configuration,time_slice=30,
            share_unused_time_slice=1,time_slice_defaulted=False,share_unused_defaulted=False)
        with self.assertRaises(ImageError):self.stage.configure(payload(),self.bindings)
        values=attributes(payload());values.update({3:struct.pack('<H',30),16:b'\1\0'})
        self.stage.configure(payload(values),self.bindings);self.stage.validate(self.bindings)

    def test_single_settings_require_base_and_source_values_then_preserve_all_prior_fields(self):
        with self.assertRaises(ImageError):self.stage.configure(payload({10:b'\0'}),self.bindings)
        self.stage.configure(payload(),self.bindings)
        for number,width in ((10,1),(11,2),(12,2)):
            self.assertEqual(self.stage.configure(payload({number:bytes(width)}),self.bindings),struct.pack('<HHH',1,number,0))
            before=dict(self.stage._values)
            with self.assertRaises(ImageError):self.stage.configure(payload({number:b'\1'+bytes(width-1)}),self.bindings)
            self.assertEqual(dict(self.stage._values),before)
        self.stage.configure(payload(),self.bindings)
        self.assertEqual(len(self.stage._values),17);self.stage.validate(self.bindings)

    def test_missing_configuration_changed_source_runtime_and_effects_revoke_authority(self):
        for case in ('missing','identity','processor','runtime','configuration','effect'):
            with self.subTest(case=case):
                self.setUp()
                if case=='missing':
                    self.app.engine.project.controller_configuration=replace(self.app.engine.project.controller_configuration,automatic_diagnostics_enabled=None)
                    with self.assertRaises(ImageError):self.stage.configure(payload(),self.bindings)
                    continue
                self.stage.configure(payload(),self.bindings)
                if case=='identity':self.bindings.identity=None
                elif case=='processor':self.app.engine.project.processor='1756-L85ES'
                elif case=='runtime':self.app.engine.project.runtime_revision=1
                elif case=='configuration':self.app.engine.project.controller_configuration=replace(self.app.engine.project.controller_configuration,security_code=1)
                else:self.stage._values={}
                with self.assertRaises(ImageError):self.stage.validate(self.bindings)


class ControllerSignedTests(NamespaceFixture,unittest.TestCase):
    def setUp(self):
        task_tests.TaskLinkSignedTests.setUp(self);source_configuration(self.app)
    complete_tasks=task_tests.TaskLinkSignedTests.complete_tasks

    def test_configure_requires_complete_tasks_then_catalog_rechecks_and_end_discards(self):
        raw=bytes.fromhex('0402208e2401')+payload();memory=copy.deepcopy(self.app.engine.memory.values)
        self.assertEqual(self.send(raw)[2],12);self.complete_tasks()
        response=self.send(raw);self.assertEqual(response[2],0);self.assertEqual(len(response),62)
        self.assertEqual(self.send(ENUM)[2],0)
        self.assertEqual(self.namespace.controller.description()['attributes'],14)
        for number,width in ((10,1),(11,2),(12,2)):
            self.assertEqual(self.send(bytes.fromhex('0402208e2401')+payload({number:bytes(width)})),
                bytes.fromhex('84000000')+struct.pack('<HHH',1,number,0))
        self.assertEqual(self.namespace.controller.description()['attributes'],17)
        self.assertEqual(self.send(bytes.fromhex('0e03208e24013003'))[4:],struct.pack('<H',20))
        self.assertEqual(self.app.engine.memory.values,memory);self.assertEqual(self.app.engine.scan_count,0)
        self.assertEqual(self.send(prep.END)[2],0);self.assertIsNone(self.endpoint.programming_lease.download_namespace)
        self.assertEqual(self.send(raw)[2],12)

    def test_unsigned_foreign_wrong_scope_and_run_mode_cannot_configure(self):
        self.complete_tasks();raw=bytes.fromhex('0402208e2401')+payload()
        self.assertNotEqual(self.cip(raw)[2],0)
        first=self.client;second=self.second_client()
        try:
            self.client=second;self.assertEqual(self.signed(4,raw)[2],15)
        finally:self.client=first;second.close()
        with patch.object(self.app,'controller_state',return_value={'mode':'Run'}):self.assertEqual(self.send(raw)[2],12)
        for request in (bytes.fromhex('0402208e2400')+payload(),bytes.fromhex('0403208e24013001')+payload()):
            self.assertEqual(self.send(request)[2],4)
        self.assertFalse(self.namespace.controller.description()['configured'])
        self.assertEqual(self.send(raw)[2],0)
        self.app.engine.project.controller_configuration=replace(self.app.engine.project.controller_configuration,security_code=1)
        self.assertEqual(self.send(ENUM)[2],12)
