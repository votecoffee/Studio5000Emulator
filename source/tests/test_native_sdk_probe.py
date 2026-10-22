"""The optional native probe cannot silently select another target or source."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from tools.probe_native_sdk import (runtime_hashes, validate_target, validate_url,
                                    validate_operation, validate_idle, validate_mode_probe, wait_for_cleanup, run,
                                    edit_request, rejection_delta, edit_trace_evidence, sdk_diagnostic_codes, validate_tag_read_type)


class NativeSdkProbeTests(unittest.TestCase):
    def test_saving_uploaded_results_is_explicit_and_upload_only(self):
        from tools.probe_native_sdk import validate_upload_save
        validate_upload_save('upload',True);validate_upload_save('upload',False)
        for operation in ('connection','download','modes','edits'):
            validate_upload_save(operation,False)
            with self.assertRaises(ValueError):validate_upload_save(operation,True)
        for value in (1,None,'true',[]):
            with self.assertRaises(ValueError):validate_upload_save('upload',value)

    def test_uploaded_save_receipt_checks_artifact_hashes_flags_and_xml_not_logic_equivalence(self):
        from tools.probe_native_sdk import saved_uploaded_acd_effect,digest
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);acd=root/'uploaded.ACD';xml=root/'uploaded.L5X'
            acd.write_bytes(b'\r\nsynthetic-native-save-evidence')
            content='<RSLogix5000Content TargetType="Controller"><Controller Name="Test"/></RSLogix5000Content>'
            xml.write_text(content,encoding='utf-8')
            receipt=dict(nativeAcdReopened=True,offlineOnly=True,uploadResultSaved=True,
                acdSha256=digest(acd),reopenedL5xSha256=digest(xml))
            self.assertTrue(saved_uploaded_acd_effect(root,receipt))
            self.assertFalse(saved_uploaded_acd_effect(root,None))
            for key in ('nativeAcdReopened','offlineOnly','uploadResultSaved','acdSha256','reopenedL5xSha256'):
                self.assertFalse(saved_uploaded_acd_effect(root,{**receipt,key:False}))
            for bad in ('<broken',content.replace('Controller"','Routine"'),
                        content.replace('</RSLogix5000Content>','<Controller/></RSLogix5000Content>'),
                        '<!DOCTYPE source [<!ENTITY value "text">]>'+content):
                xml.write_text(bad,encoding='utf-8')
                self.assertFalse(saved_uploaded_acd_effect(root,{**receipt,'reopenedL5xSha256':digest(xml)}))
            xml.write_text(content,encoding='utf-16')
            self.assertTrue(saved_uploaded_acd_effect(root,{**receipt,'reopenedL5xSha256':digest(xml)}))
            acd.write_bytes(b'changed artifact')
            self.assertFalse(saved_uploaded_acd_effect(root,receipt))
            acd.unlink();self.assertFalse(saved_uploaded_acd_effect(root,receipt))

    def test_post_edit_read_and_native_save_options_require_explicit_edit_application(self):
        from tools.probe_native_sdk import validate_edit_extensions
        validate_edit_extensions('connection',False,[],False)
        validate_edit_extensions('edits',True,['Controller/Tags/Tag[@Name=\'Value\']'],True)
        for operation,apply,tags,save in [('connection',True,[],True),('edits',False,[],True),
                ('download',True,['Value'],False),('edits',True,['x']*9,False),('edits',True,[''],False),
                ('edits',True,['x\0y'],False),('edits',True,[None],False),('edits',True,[],1)]:
            with self.subTest(operation=operation,apply=apply,tags=tags,save=save),self.assertRaises(ValueError):
                validate_edit_extensions(operation,apply,tags,save)

    def test_saved_acd_validation_requires_reopen_receipt_matching_logic_values_and_hashes(self):
        from tools.probe_native_sdk import saved_acd_effect,digest
        from logixlab.server import Application
        from logixlab.routine_edits import prepare
        from logixlab.routine_source import decode
        from test_routine_source import xml_source,container
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);app=Application(root/'app')
            try:
                app.command('demo',{'sample':'ConveyorDemo'})
                code='MOV(123,SpeedSetpoint);'
                source=decode(container(ET.tostring(xml_source(text=code))))
                app.engine,_=prepare(app.engine,source,(code,),'MainProgram',0)
                export=app.command('export-edited-l5x',{})
                for name in ('emulator-edited.L5X','reopened.L5X'):(root/name).write_text(export['content'],encoding='utf-8')
                (root/'edited.ACD').write_bytes(b'synthetic-native-evidence-fixture')
                receipt={'nativeAcdReopened':True,'offlineOnly':True,'inputL5xSha256':digest(root/'emulator-edited.L5X'),
                    'acdSha256':digest(root/'edited.ACD'),'reopenedL5xSha256':digest(root/'reopened.L5X')}
                self.assertTrue(saved_acd_effect(app.state(),root,receipt))
                self.assertFalse(saved_acd_effect(app.state(),root,None))
                for field in ('nativeAcdReopened','offlineOnly','acdSha256'):
                    wrong=dict(receipt);wrong[field]=False
                    self.assertFalse(saved_acd_effect(app.state(),root,wrong))
                for text in (export['content'].replace('MOV(123,','MOV(124,'),
                        export['content'].replace('Value="50"','Value="51"')):
                    self.assertNotEqual(text,export['content'])
                    (root/'reopened.L5X').write_text(text,encoding='utf-8')
                    wrong=dict(receipt,reopenedL5xSha256=digest(root/'reopened.L5X'))
                    self.assertFalse(saved_acd_effect(app.state(),root,wrong))
                (root/'reopened.L5X').write_text(export['content'],encoding='utf-8')
                (root/'edited.ACD').unlink();self.assertFalse(saved_acd_effect(app.state(),root,receipt))
            finally:app.close()

    def test_temporary_routine_metadata_must_be_empty_and_without_active_write_authority(self):
        from logixlab.edit_transfer import EditTransfer
        state=self.state();transfer=EditTransfer().description()
        state['connectivity']['native_programming_lease']['edit_transfer']=transfer
        validate_idle(state)
        for field,value in (('records',1),('bytes',38),('sha256','a'*64),('active_metadata_written',True),
                ('region_semantics_verified',True),('payload_exposed',True)):
            changed=copy.deepcopy(state);changed['connectivity']['native_programming_lease']['edit_transfer']['routine_metadata'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_idle(changed)

    def test_compiled_edit_storage_must_be_idle_empty_and_without_installation_authority(self):
        from logixlab.edit_transfer import EditTransfer
        state=self.state();lease=state['connectivity']['native_programming_lease'];lease['edit_transfer']=EditTransfer().description()
        validate_idle(state)
        for field,value in (('status','receiving'),('container_sha256','a'*64),('source_bound',True),
                ('buffer_allocated',True),('complete',True),('container_length_verified',True),
                ('elf_structural_validation',True),('relocations_resolved',True),('payloads_exposed',True),
                ('routine_installed',True),('accepted_edits',True),('commit',True),('received_bytes',1),
                ('total_bytes',1),('fragments',1),('instructions_executed',1),('received_bytes',False)):
            other=copy.deepcopy(state);other['connectivity']['native_programming_lease']['edit_transfer'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_idle(other)
        for field,value in (('component_kind','source'),('code_sha256','a'*64),('source_description',{}),
                            ('retained_bytes',1),('code_bytes',72),('code_bytes',False)):
            other=copy.deepcopy(state);other['connectivity']['native_programming_lease']['edit_transfer'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_idle(other)
        for value in (None,[],{}):
            other=copy.deepcopy(state);other['connectivity']['native_programming_lease']['edit_transfer']=value
            with self.assertRaises(ValueError):validate_idle(other)
        for field,value in (('staged',True),('bytes',20),('bytes',False),('sha256','a'*64),
                            ('interpreted',True),('payload_exposed',True)):
            other=copy.deepcopy(state)
            other['connectivity']['native_programming_lease']['edit_transfer']['post_source_record'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_idle(other)
        legacy=copy.deepcopy(state);del legacy['connectivity']['native_programming_lease']['edit_transfer']['post_source_record']
        validate_idle(legacy)

    def test_typed_tag_getters_are_explicit_and_require_a_tag_connection_case(self):
        for kind in ('BYTE_ARRAY','BOOL','DINT','REAL'):
            self.assertEqual(validate_tag_read_type('connection',['tag'],kind),kind)
        for kind in ('BOOL','DINT','REAL'):
            for operation,tags in (('connection',[]),('upload',[]),('download',[]),('edits',[])):
                with self.assertRaises(ValueError):validate_tag_read_type(operation,tags,kind)
        for kind in ('bool','STRING','',None):
            with self.assertRaises(ValueError):validate_tag_read_type('connection',['tag'],kind)

    def test_diagnostic_codes_include_import_log_mnemonic_and_wrapped_sdk_errors(self):
        report={'steps':[{'status':'failed','errors':[
            {'message':'XMLSrv_E_IMPORT_ABORTED_NO_CHANGES - See import log'},
            {'message':'RxDA_E_NO_ONLINE_ADDRESS - Tag unavailable'}]},
            {'method':'Dispose','status':'failed','error':'LgxSrv_E_SERVER_FAULTED'}],
            'events':[{'kind':'status','message':"ImportLog <Exception Severity='Error' Mnemonic='RxCsE_ASA_ATTRIBUTE_LIST_ERROR'>"},
                {'kind':'error','message':'XMLSrv_E_IMPORT_ABORTED_NO_CHANGES'},
                {'kind':'status','message':'Open project succeeded'},
                {'kind':'status','message':'user.RxSomething and a lowercase_value'}]}
        self.assertEqual(sdk_diagnostic_codes(report),['LgxSrv_E_SERVER_FAULTED',
            'RxCsE_ASA_ATTRIBUTE_LIST_ERROR','RxDA_E_NO_ONLINE_ADDRESS','XMLSrv_E_IMPORT_ABORTED_NO_CHANGES'])
        self.assertEqual(sdk_diagnostic_codes({'steps':[],'events':[]}),[])

    def test_native_server_fault_and_sdk_offline_remain_distinct_from_endpoint_cleanup(self):
        from tools.probe_native_sdk import digest
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.ACD';source.write_bytes(b'owned-acd-source')
            output=root/'report';state=self.state()
            state.update(app_version='test',tags=[],scan=0,ms=0,changes=[],mode='test')
            state['connectivity']['native_correlation']['source_acd_sha256']=digest(source)
            args=SimpleNamespace(project=str(source),url='http://127.0.0.1:8786',
                path=r'TestDriver\192.0.2.8\Backplane\0',operation='connection',tag=[],output=str(output),sdk_feed=None)
            trace={'events':[],'counts':{'native_verified':0}}
            def process(command,**kwargs):
                if command[0]=='dotnet':
                    (output/'bin').mkdir();(output/'bin/NativeSdkProbe.exe').write_bytes(b'fake-apphost')
                    (output/'bin/NativeSdkProbe.dll').write_bytes(b'fake-code')
                    return subprocess.CompletedProcess(command,0)
                Path(command[2]).write_text(json.dumps({'status':'failed','steps':[],
                    'serverFaulted':True,'sdkOfflineConfirmed':False}))
                return subprocess.CompletedProcess(command,1)
            with patch('tools.probe_native_sdk.sys.platform','win32'), \
                    patch('tools.probe_native_sdk.require_sdk_service'), \
                    patch('tools.probe_native_sdk.background_options',return_value={}), \
                    patch('tools.probe_native_sdk.subprocess.run',side_effect=process), \
                    patch('tools.probe_native_sdk.api',side_effect=(state,state,trace,state,trace)), \
                    patch('tools.probe_native_sdk.wait_for_cleanup',return_value=state),patch('builtins.print'):
                self.assertEqual(run(args),1)
            report=json.loads((output/'summary.json').read_text())
            self.assertEqual(report['status'],'failed')
            self.assertTrue(report['cleanup_confirmed'])
            self.assertTrue(report['sdk_server_faulted'])
            self.assertIs(report['native_sdk_offline_confirmed'],False)

    def test_upload_save_fault_does_not_claim_persistence_or_retry_the_native_operation(self):
        from tools.probe_native_sdk import digest
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.ACD';source.write_bytes(b'owned-acd-source')
            output=root/'report';state=self.state()
            state.update(app_version='test',tags=[],scan=0,ms=0,changes=[],mode='test')
            state['connectivity']['native_correlation']['source_acd_sha256']=digest(source)
            args=SimpleNamespace(project=str(source),url='http://127.0.0.1:8786',
                path=r'TestDriver\192.0.2.8\Backplane\0',operation='upload',tag=[],
                output=str(output),sdk_feed=None,save_uploaded_acd=True)
            trace={'events':[],'counts':{'native_verified':0}};native_calls=[]
            def process(command,**kwargs):
                if command[0]=='dotnet':
                    (output/'bin').mkdir();(output/'bin/NativeSdkProbe.exe').write_bytes(b'fake-apphost')
                    (output/'bin/NativeSdkProbe.dll').write_bytes(b'fake-code')
                    return subprocess.CompletedProcess(command,0)
                native_calls.append(command)
                self.assertTrue(json.loads(Path(command[1]).read_text())['SaveUploadedAcd'])
                Path(command[2]).write_text(json.dumps({'status':'failed','steps':[
                    {'method':'UploadAsync','status':'succeeded'},
                    {'method':'SaveAsAsync:uploaded.ACD','status':'failed',
                     'errors':[{'message':'LgxSrv_E_UNHANDLED_EXCEPTION'}]}],
                    'serverFaulted':True,'sdkOfflineConfirmed':False,'savedUploadedProject':None}))
                return subprocess.CompletedProcess(command,1)
            with patch('tools.probe_native_sdk.sys.platform','win32'), \
                    patch('tools.probe_native_sdk.require_sdk_service'), \
                    patch('tools.probe_native_sdk.background_options',return_value={}), \
                    patch('tools.probe_native_sdk.subprocess.run',side_effect=process), \
                    patch('tools.probe_native_sdk.api',side_effect=(state,state,trace,state,trace)), \
                    patch('tools.probe_native_sdk.wait_for_cleanup',return_value=state),patch('builtins.print'):
                self.assertEqual(run(args),1)
            report=json.loads((output/'summary.json').read_text())
            self.assertEqual(len(native_calls),1)
            self.assertEqual(report['status'],'failed')
            self.assertEqual(report['upload_result_persistence'],'failed')
            self.assertEqual(report['uploaded_logic_equivalence'],'NOT ASSESSED')
            self.assertFalse(report['saved_uploaded_acd_verified'])
            self.assertTrue(report['source_unchanged'] and report['model_unchanged'] and report['cleanup_confirmed'])
            self.assertTrue(report['sdk_server_faulted'])
            self.assertIs(report['native_sdk_offline_confirmed'],False)
            self.assertFalse((output/'uploaded.ACD').exists())

    def test_edit_reservation_must_be_idle_empty_unbound_and_without_active_edit_authority(self):
        from logixlab.programming_lease import ProgrammingLease
        state=self.state();lease=ProgrammingLease().description(1,'a'*64);lease['available']=True
        state['connectivity']['native_programming_lease']=lease
        validate_idle(state)
        for field,value in (('status','reserved'),('reserved',True),('source_bound',True),('changes_staged',1),
                ('changes_staged',False),('active_changes',True),('accepted',True),('testing',True),('assembled',True),('commit',True)):
            other=copy.deepcopy(state);other['connectivity']['native_programming_lease']['edit_preparation'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_idle(other)
        for selector in (0,1,False):
            other=copy.deepcopy(state);other['connectivity']['native_programming_lease']['request_selector']=selector
            with self.assertRaises(ValueError):validate_idle(other)
        for value in (None,{},[]):
            other=copy.deepcopy(state);other['connectivity']['native_programming_lease']['edit_preparation']=value
            with self.assertRaises(ValueError):validate_idle(other)
        for value in (1,-1,True,False,None,'0'):
            other=copy.deepcopy(state);other['connectivity']['native_programming_lease']['edit_preparation']['program_reservations']=value
            with self.assertRaises(ValueError):validate_idle(other)
        for field in ('phase_open','active_stack_changed','program_stack_preparations','stack_bytes_allocated'):
            for value in ((True,0,None) if field in ('phase_open','active_stack_changed') else (1,True,False,None)):
                other=copy.deepcopy(state);other['connectivity']['native_programming_lease']['edit_preparation'][field]=value
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):validate_idle(other)
            legacy=copy.deepcopy(state);del legacy['connectivity']['native_programming_lease']['edit_preparation'][field]
            validate_idle(legacy)

    def test_download_image_requires_empty_unbound_idle_storage_with_all_authority_disabled(self):
        from logixlab.resilient_transport import ResilientTransport
        state=self.state();state['connectivity']['native_programming_lease']['resilient_transport']=ResilientTransport().description()
        validate_idle(state)
        for field,value in (('status','prepared'),('source_bound',True),('temporary_readback',True),
                ('preparation_started',True),
                ('record_sha256','a'*64),('reason','blocked'),('initial_values_applied',True),
                ('compiled_routines_installed',True),('active_catalog_replaced',True),('native_execution_supported',True),
                ('commit',True),('values_exposed',True),('records_prepared',False),('tables_allocated',1),
                ('templates_retained',1),('diagnostics_retained',1),('programs_retained',1),('routines_retained',1),
                ('storage_bytes',1),('symbols_linked',1),('symbols_unresolved',1)):
            other=copy.deepcopy(state)
            other['connectivity']['native_programming_lease']['resilient_transport']['download_image'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_idle(other)
        for value in (None,{},[]):
            other=copy.deepcopy(state);other['connectivity']['native_programming_lease']['resilient_transport']['download_image']=value
            with self.assertRaises(ValueError):validate_idle(other)

    def test_source_object_verification_must_be_idle_empty_and_without_install_authority(self):
        from logixlab.resilient_transport import ResilientTransport
        state=self.state();lease=state['connectivity']['native_programming_lease']
        lease['resilient_transport']=ResilientTransport().description();validate_idle(state)
        for field,value in (('status','matched'),('programs_matched',1),('routines_matched',1),
                ('symbols_matched',1),('tables_matched',1),('tables_unresolved',1),('tables_matched',True),('auxiliary_symbols_matched',1),('auxiliary_symbols_matched',True),('symbols_unresolved',1),('symbols_matched',False),
                ('errors',['native_object_source_mismatch']),('identity_checks_only',False),
                ('table_identities_verified',True),('compiled_code_verified',True),('addresses_verified',True),
                ('install_authority',True),('active_catalog_replaced',True),('commit',True)):
            other=copy.deepcopy(state)
            other['connectivity']['native_programming_lease']['resilient_transport']['source_object_verification'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_idle(other)
        for value in (None,{},[]):
            other=copy.deepcopy(state)
            other['connectivity']['native_programming_lease']['resilient_transport']['source_object_verification']=value
            with self.assertRaises(ValueError):validate_idle(other)

    def test_source_type_verification_must_be_idle_and_not_retain_prior_matches(self):
        from logixlab.resilient_transport import ResilientTransport
        state=self.state();lease=state['connectivity']['native_programming_lease']
        lease['resilient_transport']=ResilientTransport().description();validate_idle(state)
        older=copy.deepcopy(state)
        for field in ('template_ids_matched','template_ids_unresolved','template_identities_verified'):
            del older['connectivity']['native_programming_lease']['resilient_transport']['source_type_verification'][field]
        validate_idle(older)
        for field,value in (('status','matched'),('types_matched',1),('members_matched',1),('types_unavailable',1),
                ('template_ids_matched',1),('template_ids_unresolved',1),('template_ids_matched',False),
                ('template_ids_unresolved',True),('template_identities_verified',True),('template_identities_verified',0),
                ('types_matched',False),('errors',[{'reason':'source_member_type_mismatch','types':1}]),
                ('member_locations_verified',True),('storage_mapping_supported',True),
                ('signature_verified',True),('definitions_exposed',True),('execution_supported',True)):
            other=copy.deepcopy(state)
            other['connectivity']['native_programming_lease']['resilient_transport']['source_type_verification'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):validate_idle(other)
        for value in (None,{},[]):
            other=copy.deepcopy(state)
            other['connectivity']['native_programming_lease']['resilient_transport']['source_type_verification']=value
            with self.assertRaises(ValueError):validate_idle(other)

    def test_layout_inspection_must_be_idle_empty_and_without_execution_authority(self):
        from logixlab.resilient_transport import ResilientTransport
        state=self.state();lease=state['connectivity']['native_programming_lease']
        lease['resilient_transport']=ResilientTransport().description();validate_idle(state)
        for field,value in (('status','decoded'),('templates_decoded',1),('templates_unavailable',1),
                ('members_decoded',1),('opaque_trailer_bytes',1),('encoded_offset_members',1),
                ('templates_decoded',False),('errors',[{'reason':'invalid_member_name','templates':1}]),
                ('storage_mapping_supported',True),('signature_verified',True),
                ('definitions_exposed',True),('execution_supported',True)):
            other=copy.deepcopy(state)
            other['connectivity']['native_programming_lease']['resilient_transport']['template_staging']['layout_inspection'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):validate_idle(other)
        for value in (None,[],{}):
            other=copy.deepcopy(state)
            other['connectivity']['native_programming_lease']['resilient_transport']['template_staging']['layout_inspection']=value
            with self.assertRaises(ValueError):validate_idle(other)

    def test_runtime_evidence_changes_when_managed_code_changes_under_the_same_apphost(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'probe.exe').write_bytes(b'same-apphost')
            (root/'probe.dll').write_bytes(b'first managed implementation')
            (root/'probe.runtimeconfig.json').write_text('{}')
            (root/'private.pdb').write_bytes(b'debug paths')
            before=runtime_hashes(root)
            (root/'probe.dll').write_bytes(b'changed managed implementation')
            after=runtime_hashes(root)
            self.assertEqual(before['probe.exe'],after['probe.exe'])
            self.assertNotEqual(before['probe.dll'],after['probe.dll'])
            self.assertEqual(set(after),{'probe.exe','probe.dll','probe.runtimeconfig.json'})

    def state(self):
        return {'instance_id': 'one-session', 'device_io': {'writes_enabled': False},
                'connectivity': {'enabled': True, 'profile': 'logix-v35-l85e',
                    'address': '192.0.2.8:44818', 'allow_writes': False,
                    'source_l5x_sha256': '2'*64,
                    'native_session': {'enabled': True, 'read_only': True},
                    'active_tcp_clients':0,
                    'native_programming_lease':{'available':True,'owned':False,'run_mode_inhibit':0,
                        'scan_inhibited':False,'project_transfer':False,'controller_mode_changes':False,
                        'online_edits':False,'tag_write_authority':False},
                    'native_correlation': {'bound': True, 'source_acd_sha256': '1'*64,
                                           'source_l5x_sha256': '2'*64}}}

    def check(self, state, **kwargs):
        return validate_target(state, r'TestDriver\192.0.2.8\Backplane\0', '1'*64, **kwargs)

    def test_exact_bound_endpoint_is_accepted_without_mutating_state(self):
        state = self.state(); before = copy.deepcopy(state)
        self.assertEqual(self.check(state), 'one-session')
        self.assertEqual(self.check(state, instance='one-session'), 'one-session')
        self.assertEqual(state, before)

    def test_changed_instance_project_binding_and_writable_endpoint_are_rejected(self):
        for section, field, value in (('connectivity','enabled',False),
                ('connectivity','allow_writes',True), ('connectivity','profile','research'),
                ('connectivity','address','192.0.2.9:44818'),
                ('connectivity','address','192.0.2.8:44819'),
                ('connectivity','source_l5x_sha256','3'*64),
                ('device_io','writes_enabled',True)):
            state=self.state();state[section][field]=value
            with self.assertRaises(ValueError):self.check(state)
        for section, field, value in (('native_session','enabled',False),
                ('native_session','read_only',False), ('native_correlation','bound',False),
                ('native_correlation','source_acd_sha256','3'*64),
                ('native_correlation','source_l5x_sha256','3'*64)):
            state=self.state();state['connectivity'][section][field]=value
            with self.assertRaises(ValueError):self.check(state)
        with self.assertRaises(ValueError):self.check(self.state(),instance='replaced-session')
        with self.assertRaises(ValueError):self.check(self.state(),l5x_hash='3'*64)
        for state in ({}, {'instance_id':'other'}, {'connectivity':{}}):
            with self.assertRaises(ValueError):self.check(state)

    def test_wrong_slot_ipv4_driver_and_nested_path_do_not_reach_the_sdk(self):
        for path in (r'TestDriver\192.0.2.8\Backplane\1',r'TestDriver\192.0.2.8',
                     r'TestDriver\192.0.2.9\Backplane\0',r'\192.0.2.8\Backplane\0',
                     r'TestDriver\host.example\Backplane\0',r'TestDriver\192.0.2.8\Backplane\0\1'):
            with self.assertRaises(ValueError):validate_target(self.state(),path,'1'*64)

    def test_remote_urls_credentials_paths_and_token_queries_are_rejected(self):
        self.assertEqual(validate_url('http://127.0.0.1:8786'),'http://127.0.0.1:8786')
        for url in ('http://192.0.2.8:80','http://localhost:8786','https://127.0.0.1:8786',
                    'http://127.0.0.1','http://user@127.0.0.1:8786','http://127.0.0.1:8786/',
                    'http://127.0.0.1:8786?token=private','http://127.0.0.1:8786#fragment'):
            with self.assertRaises(ValueError):validate_url(url)

    def test_download_is_explicit_and_transfer_operations_cannot_include_tag_reads(self):
        for operation in ('connection','upload','download','modes','edits'):
            validate_operation(operation,[])
        validate_operation('connection',['Controller/Tags/Tag'])
        for operation,tags in (('download',['Controller/Tags/Tag']),('upload',['tag']),
                ('edit',[]),('connection',['']),('connection',['x'*1025]),('connection',['tag']*33)):
            with self.subTest(operation=operation,tags_count=len(tags)),self.assertRaises(ValueError):
                validate_operation(operation,tags)

    def edit_state(self):
        state = self.state()
        state.update(name='Controller_A', version='35', controller={'mode':'Program', 'running':False},
                     routines=[{'key':'MainProgram/MainRoutine','kind':'RLL','harness':True,'rungs':[]}])
        return state

    def test_edit_payload_is_one_nop_insert_bound_to_a_loaded_rll_routine(self):
        state = self.edit_state(); before = copy.deepcopy(state)
        for option in ('LeaveEdits', 'AcceptEdits'):
            payload, config = edit_request(state, 'MainProgram', 'MainRoutine', option)
            root = ET.fromstring(payload)
            self.assertEqual(root.attrib['TargetType'], 'Rung')
            self.assertEqual(root.attrib['TargetCount'], '1')
            self.assertEqual(root.find('Controller').attrib['Name'], 'Controller_A')
            self.assertEqual([node.text for node in root.findall('.//Text')], ['NOP();'])
            self.assertEqual(len(root.findall('.//Rung')), 1)
            self.assertEqual(config, dict(XPath="Controller/Programs/Program[@Name='MainProgram']/Routines/Routine[@Name='MainRoutine']",
                InsertPosition=0, ReplaceCount=0, ImportOption=option))
        self.assertEqual(state, before)

    def test_custom_rung_application_requires_explicit_enabled_supported_profile(self):
        state=self.edit_state()
        with self.assertRaises(ValueError):edit_request(state,'MainProgram','MainRoutine','AcceptEdits',code='MOV(123,Value);')
        state['connectivity']['native_programming_lease'].update(online_edits=True,online_edit_scope='standard_rll_program_mode')
        state['routine_edits']={'enabled':True,'revision':0}
        payload,_=edit_request(state,'MainProgram','MainRoutine','AcceptEdits',code='MOV(123,Value);',apply=True)
        self.assertEqual(ET.fromstring(payload).findtext('.//Text'),'MOV(123,Value);')
        for code in ('','MOV(1);','UNKNOWN();','MOV(1,@107 1 0 0 0 0@);'):
            with self.assertRaises(ValueError):edit_request(state,'MainProgram','MainRoutine','AcceptEdits',code=code,apply=True)
        with self.assertRaises(ValueError):edit_request(state,'MainProgram','MainRoutine','LeaveEdits',apply=True)
        with self.assertRaises(ValueError):validate_idle(state)
        validate_idle(state,allow_supported_edits=True)

    def test_applied_edit_verification_requires_exact_insert_and_unchanged_values_history_and_other_routines(self):
        from logixlab.server import Application
        from tools.probe_native_sdk import supported_edit_effect
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder);app.command('demo',{'sample':'ConveyorDemo'})
            before=app.state();_,config=edit_request({**before,'connectivity':self.state()['connectivity']},'MainProgram','MainRoutine','AcceptEdits')
            after=copy.deepcopy(before);routine=next(r for r in after['routines'] if r['key']=='MainProgram/MainRoutine')
            from logixlab.server import serialize_nodes
            from logixlab.model import parse_rung
            routine['rungs'].insert(0,{'nodes':serialize_nodes(parse_rung('MOV(123,SpeedSetpoint);'))})
            after['routine_edits'].update(revision=1,logic_sha256='a'*64)
            self.assertTrue(supported_edit_effect(before,after,config,'MOV(123,SpeedSetpoint);'))
            for field,value in (('scan',1),('tags',[]),('controller',{})):
                changed=copy.deepcopy(after);changed[field]=value
                self.assertFalse(supported_edit_effect(before,changed,config,'MOV(123,SpeedSetpoint);'))
            after['routine_edits']['revision']=0
            self.assertFalse(supported_edit_effect(before,after,config,'MOV(123,SpeedSetpoint);'))
            app.close()

    def test_sequential_edit_checks_retain_prior_logic_and_reject_missing_or_changed_reconnect_evidence(self):
        from logixlab.server import Application
        from tools.probe_native_sdk import edit_sequence,supported_sequence_effect
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);app=Application(root/'app')
            try:
                app.command('demo',{'sample':'ConveyorDemo'});app.allow_routine_edits=True
                initial=app.state();initial['connectivity']=self.state()['connectivity']
                initial['connectivity']['native_programming_lease'].update(online_edits=True,online_edit_scope='standard_rll_program_mode')
                codes=['MOV(123,SpeedSetpoint);','MOV(456,SpeedSetpoint);']
                edits=edit_sequence(initial,'MainProgram','MainRoutine','AcceptEdits',codes,apply=True)
                state=copy.deepcopy(initial);saved={}
                for index,(_,config) in enumerate(edits):
                    suffix='edit' if index==0 else 'edit2'
                    saved[f'before-{suffix}-state.json']=copy.deepcopy(state)
                    routine=next(r for r in state['routines'] if r['key']=='MainProgram/MainRoutine')
                    self.assertEqual([r['nodes'] for r in routine['rungs']],config['BeforeRungs'])
                    routine['rungs']=[{'nodes':n} for n in config['ExpectedRungs']]
                    state['routine_edits'].update(revision=index+1,logic_sha256=str(index+1)*64)
                    saved[f'after-{suffix}-state.json']=copy.deepcopy(state)
                    saved[f'after-reconnect-{index+1}-state.json']=copy.deepcopy(state)
                for name,value in saved.items():(root/name).write_text(json.dumps(value))
                self.assertTrue(supported_sequence_effect(initial,state,edits,codes,root,reconnect=True))
                # A final second insert is insufficient if the prior rung was lost.
                bad=copy.deepcopy(state)
                next(r for r in bad['routines'] if r['key']=='MainProgram/MainRoutine')['rungs'].pop(1)
                self.assertFalse(supported_sequence_effect(initial,bad,edits,codes,root,reconnect=True))
                for name,field,value in [('after-edit-state.json','scan',1),('before-edit2-state.json','tags',[]),
                        ('after-reconnect-1-state.json','routine_edits',{'revision':0})]:
                    changed=copy.deepcopy(saved[name]);changed[field]=value;(root/name).write_text(json.dumps(changed))
                    self.assertFalse(supported_sequence_effect(initial,state,edits,codes,root,reconnect=True))
                    (root/name).write_text(json.dumps(saved[name]))
                (root/'after-reconnect-2-state.json').unlink()
                self.assertFalse(supported_sequence_effect(initial,state,edits,codes,root,reconnect=True))
                for codes,apply in [([],True),(['NOP();']*3,True),(['NOP();']*2,False)]:
                    with self.assertRaises(ValueError):edit_sequence(initial,'MainProgram','MainRoutine','AcceptEdits',codes,apply=apply)
                for revision in (1,True,None,-1):
                    changed=copy.deepcopy(initial);changed['routine_edits']['revision']=revision
                    with self.assertRaises(ValueError):edit_sequence(changed,'MainProgram','MainRoutine','AcceptEdits',['NOP();'],apply=True)
                self.assertFalse(supported_sequence_effect(initial,initial,[],[],root))
            finally:app.close()

    def test_edit_diagnostic_rejects_unloaded_nonladder_aoi_ambiguous_or_writable_target(self):
        state = self.edit_state()
        for replacement in ([], [{'key':'MainProgram/MainRoutine','kind':'ST','harness':True,'rungs':[]}],
                [{'key':'MainProgram/MainRoutine','kind':'RLL','harness':False,'rungs':[]}],
                [{'key':'MainProgram/MainRoutine','kind':'RLL','harness':True}], state['routines'] * 2):
            other = copy.deepcopy(state); other['routines'] = replacement
            with self.assertRaises(ValueError):edit_request(other, 'MainProgram', 'MainRoutine', 'AcceptEdits')
        for change in ({'mode':'Run','running':True}, {'mode':'Faulted','running':False}, {'mode':'Program'}):
            other = copy.deepcopy(state); other['controller'] = change
            with self.assertRaises(ValueError):edit_request(other, 'MainProgram', 'MainRoutine', 'AcceptEdits')
        for value in (True, None, 0):
            other = copy.deepcopy(state);other['connectivity']['native_programming_lease']['online_edits'] = value
            with self.assertRaises(ValueError):edit_request(other, 'MainProgram', 'MainRoutine', 'AcceptEdits')

    def test_edit_ranges_and_second_routine_use_independent_predicted_bases(self):
        from logixlab.server import Application
        from tools.probe_native_sdk import edit_sequence,supported_edit_effect
        with tempfile.TemporaryDirectory() as folder:
            app=Application(folder)
            try:
                app.command('demo',{'sample':'ConveyorDemo'});app.allow_routine_edits=True
                state=app.state();state['connectivity']=self.state()['connectivity']
                state['connectivity']['native_programming_lease'].update(online_edits=True,online_edit_scope='standard_rll_program_mode')
                codes=['MOV(123,SpeedSetpoint);','MOV(456,Parts.PRE);']
                edits=edit_sequence(state,'MainProgram','MainRoutine','AcceptEdits',codes,apply=True,
                    second_target=('MainProgram','Reporting'),ranges=[(1,1),(0,1)])
                main=next(r for r in state['routines'] if r['key']=='MainProgram/MainRoutine')
                self.assertEqual(len(edits[0][1]['ExpectedRungs']),len(main['rungs']))
                self.assertEqual(edits[0][1]['BeforeRungs'][0],edits[0][1]['ExpectedRungs'][0])
                self.assertEqual(len(edits[1][1]['BeforeRungs']),1);self.assertEqual(len(edits[1][1]['ExpectedRungs']),1)
                changed=copy.deepcopy(state)
                next(r for r in changed['routines'] if r['key']==main['key'])['rungs']=[{'nodes':n} for n in edits[0][1]['ExpectedRungs']]
                changed['routine_edits'].update(revision=1,logic_sha256='a'*64)
                self.assertTrue(supported_edit_effect(state,changed,edits[0][1],codes[0]))
                changed['routines'][0]['rungs'].pop()
                self.assertFalse(supported_edit_effect(state,changed,edits[0][1],codes[0]))
                for position,replace in ((-1,0),(99,0),(0,-1),(0,99),(True,0),(0,True)):
                    with self.subTest(position=position,replace=replace),self.assertRaises(ValueError):
                        edit_request(state,'MainProgram','MainRoutine','AcceptEdits',apply=True,position=position,replace=replace)
                # A second insert may append after the first expanded the routine.
                count=len(main['rungs'])
                same=edit_sequence(state,'MainProgram','MainRoutine','AcceptEdits',codes,apply=True,ranges=[(count,0),(count+1,0)])
                self.assertEqual(same[1][1]['BeforeRungs'],same[0][1]['ExpectedRungs'])
                with self.assertRaises(ValueError):edit_sequence(state,'MainProgram','MainRoutine','AcceptEdits',codes,apply=True,
                    second_target=('MainProgram','missing'))
            finally:app.close()

    def test_edit_diagnostic_rejects_finalize_bad_names_and_wrong_project_version(self):
        state = self.edit_state()
        for name in ('', 'x'*41, "name']", 'AOI:one', '<other>', None):
            with self.subTest(name=name),self.assertRaises(ValueError):edit_request(state, name, 'MainRoutine', 'AcceptEdits')
            with self.assertRaises(ValueError):edit_request(state, 'MainProgram', name, 'AcceptEdits')
        for option in ('FinalizeEdits', '', None):
            with self.assertRaises(ValueError):edit_request(state, 'MainProgram', 'MainRoutine', option)
        for version in ('34','36', None):
            other = copy.deepcopy(state);other['version'] = version
            with self.assertRaises(ValueError):edit_request(other, 'MainProgram', 'MainRoutine', 'AcceptEdits')

    def test_rejection_delta_does_not_count_previous_native_failures_or_changed_status_as_the_same_request(self):
        old = dict(generation=2, service=6, class_id=1042, instance=0, status=15, reason='unsupported', count=4, last_seen=10)
        new = dict(old, count=5, last_seen=20)
        different = dict(old, status=8, count=2, last_seen=30)
        before = {'native_rejections':[old]}; after = {'native_rejections':[different, new]}
        result = rejection_delta(before, after)
        self.assertEqual([item['probe_count'] for item in result], [1,2])
        self.assertEqual([item['status'] for item in result], [15,8])
        self.assertEqual(rejection_delta(after, after), [])
        self.assertNotIn('probe_count', new)

    def test_edit_trace_retains_outer_fragment_rejections_separately_without_claiming_mac_authentication(self):
        import struct
        raw=bytes.fromhex('390220022401')+struct.pack('<II',0x101,123)+b'fragment'+struct.pack('<I',101)+b'x'*20
        marker={'kind':'marker','time':0}
        event=dict(kind='cip',time=1,request_hex=raw.hex(),response_hex='b9000f00')
        report={'steps':[dict(method='PartialImportRungsFromXmlFileAsync:AcceptEdits',status='failed',
                            startedAt='start',finishedAt='end')]}
        events=[marker,event,dict(event,time=2,response_hex='b9000c013412'),
                dict(event,time=3,response_hex='b9000f0100'),
                dict(event,time=4,response_hex='b6000f00'),dict(event,time=5,response_hex='b9000000')]
        result=edit_trace_evidence({},report,before_edit={'events':[marker]},after_edit={'events':events})
        self.assertEqual(result['requests_observed'],2);self.assertEqual(result['unparsed_events'],3)
        self.assertIsNone(result['first_failed_request'])
        self.assertEqual(result['first_wrapper_rejection'],dict(time=1,service=0x39,status=15,sequence=101,
            response_authenticated=False,additional_status='',container_format=0x101,position=123,fragment_bytes=8))
        self.assertEqual(result['wrapper_rejections'][1]['additional_status'],'3412')
        self.assertEqual(result['mac_verification'],'not performed by report parser')

    def test_edit_trace_pairs_signed_inner_failures_only_during_the_sdk_import_interval(self):
        import struct
        # Opaque synthetic MACs deliberately prove framing does not imply authentication.
        child = bytes.fromhex('0603210012042400')
        raw = bytes.fromhex('360220022401') + child + struct.pack('<I', 7) + b'x'*20
        reply = bytes.fromhex('b600000086000f00') + struct.pack('<I', 7) + b'y'*20
        event = dict(time=1.5, kind='cip', request_hex=raw.hex(), response_hex=reply.hex(), truncated=False)
        report = {'steps':[dict(method='PartialImportRungsFromXmlFileAsync:AcceptEdits', status='failed',
            startedAt='1970-01-01T00:00:01+00:00', finishedAt='1970-01-01T00:00:02+00:00')]}
        marker = dict(event,time=.5)
        trace = {'events':[marker,event,dict(event,time=2.5),dict(event,time=1.7,truncated=True)]}
        result = edit_trace_evidence(trace, report, before_edit={'events':[marker]},
            after_edit={'events':[marker,event,dict(event,time=1.7,truncated=True)]})
        self.assertEqual(result['requests_observed'],1)
        self.assertEqual(result['unparsed_events'],1)
        self.assertEqual(result['first_failed_request'],dict(time=1.5,service=6,class_id=0x412,instance=0,
        attribute=None,program_instance=None,io_map_instance=None,controller_instance=None,aoi_instance=None,symbolic=False,
            status=15,sequence=7,payload_bytes=0))
        self.assertEqual(result['mac_verification'],'not performed by report parser')
        self.assertEqual(edit_trace_evidence(trace, {'steps':[]})['status'],'import_not_reached')
        self.assertEqual(result['correlation'],'emulator_trace_checkpoints')

    def test_edit_trace_keeps_absent_or_incomplete_network_evidence_distinct_from_sdk_success(self):
        report = {'steps':[dict(method='PartialImportRungsFromXmlFileAsync:LeaveEdits', status='succeeded',
            startedAt='1970-01-01T00:00:01+00:00', finishedAt='1970-01-01T00:00:02+00:00')]}
        for events in ([], [dict(kind='cip',time=1.5,request_hex='bad hex',response_hex='00')]):
            result = edit_trace_evidence({'events':events}, report,
                before_edit={'events':[]},after_edit={'events':events})
            self.assertEqual(result['status'],'no_complete_cip_during_import')
            self.assertIsNone(result['first_failed_request'])
            self.assertEqual(result['sdk_status'],'succeeded')
        self.assertEqual(edit_trace_evidence({}, report)['status'],'checkpoints_unavailable')
        self.assertEqual(edit_trace_evidence({}, report,before_edit={'events':[{'time':1,'kind':'marker'}]},
            after_edit={'events':[]})['status'],'checkpoint_events_not_retained')

    def test_two_import_trace_intervals_select_the_corresponding_sdk_result(self):
        report={'steps':[dict(method='PartialImportRungsFromXmlFileAsync:AcceptEdits',status='succeeded',startedAt='start1',finishedAt='end1'),
                         dict(method='PartialImportRungsFromXmlFileAsync:AcceptEdits:2',status='failed',startedAt='start2',finishedAt='end2')]}
        events=[dict(kind='cip',time=1,request_hex='0e03200124013001',response_hex='8e0000000100')]
        for index,status in ((0,'succeeded'),(1,'failed')):
            result=edit_trace_evidence({},report,before_edit={'events':[]},after_edit={'events':events},import_index=index)
            self.assertEqual(result['sdk_status'],status);self.assertEqual(result['requests_observed'],1)
        self.assertEqual(edit_trace_evidence({},report,import_index=2)['status'],'import_not_reached')

    def test_edit_trace_uses_checkpoint_order_with_guest_clock_offset_and_backward_adjustment(self):
        first = dict(kind='cip',time=1_000,request_hex='4b04208e24012074240101',response_hex='cb000300')
        second = dict(first,time=100,response_hex='cb000f00')
        report = {'steps':[dict(method='PartialImportRungsFromXmlFileAsync:AcceptEdits',status='failed',
            startedAt='2026-10-20T15:56:12+00:00',finishedAt='2026-10-20T15:56:13+00:00')]}
        marker = {'kind':'native_verified','sequence':80,'time':123}
        result = edit_trace_evidence({},report,before_edit={'events':[marker]},after_edit={'events':[marker,first,second]})
        self.assertEqual(result['requests_observed'],2)
        self.assertEqual(result['first_failed_request']['status'],3)
        self.assertEqual(result['first_failed_request']['time'],1_000)

    def test_edit_probe_preserves_routine_model_and_reports_local_pending_success_without_native_acceptance(self):
        from tools.probe_native_sdk import digest
        for mutation in (None, 'routines', 'controller', 'input'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);source=root/'original.ACD';source.write_bytes(b'owned-acd-source')
                output=root/'report'
                args=SimpleNamespace(project=str(source),url='http://127.0.0.1:8786',
                    path=r'TestDriver\192.0.2.8\Backplane\0',operation='edits',tag=[],output=str(output),sdk_feed=None,
                    edit_program=None,edit_routine=None,edit_import_option='LeaveEdits')
                state=self.edit_state();state.update(app_version='test',tags=[],scan=0,ms=0,changes=[],mode='project',tasks=[],entry_routines=[])
                state['connectivity']['native_correlation']['source_acd_sha256']=digest(source)
                final=copy.deepcopy(state)
                if mutation=='routines':final['routines'][0]['rungs'].append({'text':'NOP();'})
                if mutation=='controller':final['controller']['prescan_count']=1
                trace={'events':[],'counts':{'native_verified':0}}
                def process(command,**kwargs):
                    if command[0]=='dotnet':
                        (output/'bin').mkdir();(output/'bin/NativeSdkProbe.exe').write_bytes(b'test-apphost')
                        (output/'bin/NativeSdkProbe.dll').write_bytes(b'test-managed-code')
                        return subprocess.CompletedProcess(command,0)
                    if mutation=='input':(output/'nop-rung.L5X').write_bytes(b'changed private input')
                    Path(command[2]).write_text(json.dumps({'status':'succeeded','steps':[]}))
                    return subprocess.CompletedProcess(command,0)
                with patch('tools.probe_native_sdk.sys.platform','win32'), \
                        patch('tools.probe_native_sdk.require_sdk_service'), \
                        patch('tools.probe_native_sdk.background_options',return_value={}), \
                        patch('tools.probe_native_sdk.subprocess.run',side_effect=process), \
                        patch('tools.probe_native_sdk.api',side_effect=(state,state,trace,final,trace)), \
                        patch('tools.probe_native_sdk.wait_for_cleanup',return_value=final),patch('builtins.print'):
                    self.assertEqual(run(args),0 if mutation is None else 1)
                report=json.loads((output/'summary.json').read_text())
                self.assertEqual(report['status'],'succeeded' if mutation is None else 'failed')
                self.assertTrue(report['source_unchanged'] and report['cleanup_confirmed'])
                self.assertEqual(report['edit_diagnostic']['import_option'],'LeaveEdits')
                self.assertFalse(report['edit_diagnostic']['active_edits_authorized'])
                self.assertEqual(report['edit_trace']['status'],'import_not_reached')

    def test_mode_probe_requires_executable_stopped_remote_controller(self):
        state=self.state()
        state.update(controller={'running':False,'mode':'Program','keyswitch':'Remote','scan_interval_ms':10,'prescan_count':0,'first_scan_pending':True},blockers=[],fault='')
        state['connectivity']['native_session']['controller_mode_requests']=True
        validate_mode_probe(state)
        for field,value in (('running',True),('mode','Faulted'),('keyswitch','Run'),('scan_interval_ms',101),('scan_interval_ms',True),
                            ('prescan_count',-1),('prescan_count',True),('prescan_count',None),('first_scan_pending',None)):
            other=copy.deepcopy(state);other['controller'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_mode_probe(other)
        for field,value in (('blockers',['unsupported']),('fault','scan failed')):
            other=copy.deepcopy(state);other[field]=value
            with self.assertRaises(ValueError):validate_mode_probe(other)

    def test_busy_inhibited_unknown_or_programmable_endpoints_are_not_admitted(self):
        state=self.state();before=copy.deepcopy(state);validate_idle(state)
        self.assertEqual(state,before)
        for field,value in (('active_tcp_clients',1),('active_tcp_clients',False),
                ('available',False),('owned',True),('run_mode_inhibit',1),('run_mode_inhibit',False),
                ('scan_inhibited',True),('project_transfer',True),('controller_mode_changes',True),
                ('online_edits',True),('tag_write_authority',True)):
            state=self.state()
            target=state['connectivity'] if field=='active_tcp_clients' else state['connectivity']['native_programming_lease']
            target[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):validate_idle(state)
        for field in self.state()['connectivity']['native_programming_lease']:
            state=self.state();del state['connectivity']['native_programming_lease'][field]
            with self.subTest(missing=field),self.assertRaises(ValueError):validate_idle(state)

    def test_transport_admission_and_cleanup_require_closed_empty_disabled_state(self):
        from logixlab.resilient_transport import ResilientTransport
        state=self.state();lease=state['connectivity']['native_programming_lease']
        lease['resilient_transport']=ResilientTransport().description();validate_idle(state)
        for field,value in (('open',True),('buffer_bytes',1),('buffer_bytes',False),
                ('buffer_allocated',True),('payload_transfer',True),('commit',True),
                ('received_bytes',1),('total_bytes',1),('fragments',1),('complete',True),('fragments',False)):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease']['resilient_transport'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):validate_idle(proposed)
        for value in (None,{},'unknown'):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease']['resilient_transport']=value
            with self.assertRaises(ValueError):validate_idle(proposed)

    def test_payload_inspection_must_be_empty_and_cannot_advertise_execution_or_signature_authority(self):
        from logixlab.resilient_transport import ResilientTransport
        state=self.state();state['connectivity']['native_programming_lease']['resilient_transport']=ResilientTransport().description()
        validate_idle(state)
        for field,value in (('status','decoded'),('operations',[{}]),('expanded_bytes',1),('record_count',1),
                ('scoped_records',1),('records_executed',1),('record_count',False),('execution_supported',True),
                ('signature_verified',True),('payloads_exposed',True)):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease']['resilient_transport']['inspection'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_idle(proposed)
        for value in (None,{},'unknown'):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease']['resilient_transport']['inspection']=value
            with self.assertRaises(ValueError):validate_idle(proposed)

    def test_async_tcp_close_and_lease_release_finish_before_cleanup_is_confirmed(self):
        connected=self.state();connected['connectivity']['active_tcp_clients']=1
        owned=self.state();owned['connectivity']['native_programming_lease'].update(owned=True,run_mode_inhibit=1,scan_inhibited=True)
        idle=self.state()
        with patch('tools.probe_native_sdk.api',side_effect=(connected,owned,idle)) as api, \
                patch('tools.probe_native_sdk.time.monotonic',return_value=0), \
                patch('tools.probe_native_sdk.time.sleep') as sleep:
            result=wait_for_cleanup('http://127.0.0.1:8786',r'TestDriver\192.0.2.8\Backplane\0','1'*64,
                                    instance='one-session',l5x_hash='2'*64)
        self.assertEqual(result,idle)
        self.assertEqual(sleep.call_count,2)
        self.assertEqual([call.args for call in api.call_args_list],[('http://127.0.0.1:8786','state')]*3)

    def test_temporary_template_models_must_be_empty_without_installation_authority(self):
        from logixlab.resilient_transport import ResilientTransport
        state=self.state();state['connectivity']['native_programming_lease']['resilient_transport']=ResilientTransport().description()
        validate_idle(state)
        for field,value in (('status','modeled'),('templates',1),('definition_bytes',1),('write_fragments',1),
                ('records_modeled',1),('unsupported_records',1),('templates',False),('commit',True),
                ('active_catalog_replaced',True),('definitions_exposed',True)):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease']['resilient_transport']['template_staging'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_idle(proposed)
        for value in (None,{},'unknown'):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease']['resilient_transport']['template_staging']=value
            with self.assertRaises(ValueError):validate_idle(proposed)

    def test_diagnostic_models_must_be_empty_without_installation_authority(self):
        from logixlab.resilient_transport import ResilientTransport
        state=self.state();state['connectivity']['native_programming_lease']['resilient_transport']=ResilientTransport().description()
        validate_idle(state)
        for field,value in (('status','modeled'),('messages',1),('text_bytes',1),('records_modeled',1),
                ('messages',False),('definitions_exposed',True),('active_catalog_replaced',True),('commit',True)):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease']['resilient_transport']['diagnostic_staging'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_idle(proposed)
        for value in (None,{},'unknown'):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease']['resilient_transport']['diagnostic_staging']=value
            with self.assertRaises(ValueError):validate_idle(proposed)

    def test_object_graph_models_must_be_empty_and_reference_checks_are_not_transfer_authority(self):
        from logixlab.resilient_transport import ResilientTransport
        state=self.state();state['connectivity']['native_programming_lease']['resilient_transport']=ResilientTransport().description()
        validate_idle(state)
        for field,value in tuple((f,1) for f in ('symbols','tables','programs','routines','coordination_records','records_modeled','storage_bytes','open_coordination'))+(
                ('symbols',False),('status','modeled'),('references_validated',True),('commit',True),('definitions_exposed',True),('active_catalog_replaced',True)):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease']['resilient_transport']['object_staging'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):validate_idle(proposed)
        for value in (None,{},'unknown'):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease']['resilient_transport']['object_staging']=value
            with self.assertRaises(ValueError):validate_idle(proposed)

    def test_staging_admission_requires_empty_counts_and_only_definition_value_capability(self):
        from logixlab.library_staging import LibraryStaging
        from logixlab.metadata_staging import MetadataStaging
        state=self.state();lease=state['connectivity']['native_programming_lease']
        lease.update(library_staging=LibraryStaging().description(),metadata_staging=MetadataStaging().description(),
                     preparation_state='idle',preparation_status=0)
        validate_idle(state)
        for section,field,value in (('metadata_staging','value_count',1),('metadata_staging','value_targets',1),
                ('metadata_staging','value_bytes',1),('library_staging','instances',1),
                ('metadata_staging','name_bytes',1),('metadata_staging','value_count',False),
                ('metadata_staging','commit',True),('metadata_staging','active_values_transfer',True),
                ('metadata_staging','values_scope','active_objects'),('library_staging','data_transfer',True)):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease'][section][field]=value
            with self.subTest(section=section,field=field),self.assertRaises(ValueError):validate_idle(proposed)
        for value in (None,{}, {'instances':0},'unknown'):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease']['metadata_staging']=value
            with self.assertRaises(ValueError):validate_idle(proposed)
        for field,value in (('preparation_state','ready'),('preparation_status',2)):
            proposed=copy.deepcopy(state);proposed['connectivity']['native_programming_lease'][field]=value
            with self.assertRaises(ValueError):validate_idle(proposed)

    def test_cleanup_waits_for_staged_values_and_does_not_confirm_persistent_values(self):
        from logixlab.metadata_staging import MetadataStaging
        idle=self.state();idle['connectivity']['native_programming_lease']['metadata_staging']=MetadataStaging().description()
        dirty=copy.deepcopy(idle);dirty['connectivity']['native_programming_lease']['metadata_staging']['value_count']=1
        with patch('tools.probe_native_sdk.api',side_effect=(dirty,idle)), \
                patch('tools.probe_native_sdk.time.monotonic',return_value=0), \
                patch('tools.probe_native_sdk.time.sleep') as sleep:
            result=wait_for_cleanup('http://127.0.0.1:8786',r'TestDriver\192.0.2.8\Backplane\0','1'*64,
                                    instance='one-session',l5x_hash='2'*64)
        self.assertEqual(result,idle);self.assertEqual(sleep.call_count,1)
        with patch('tools.probe_native_sdk.api',return_value=dirty), \
                patch('tools.probe_native_sdk.time.monotonic',side_effect=(0,41)):
            with self.assertRaisesRegex(ValueError,'staging'):
                wait_for_cleanup('http://127.0.0.1:8786',r'TestDriver\192.0.2.8\Backplane\0','1'*64,
                                 instance='one-session',l5x_hash='2'*64)

    def test_cleanup_timeout_and_target_replacement_remain_failures(self):
        for failure in ('busy','lease','source','instance'):
            state=self.state()
            if failure=='busy':state['connectivity']['active_tcp_clients']=1
            elif failure=='lease':state['connectivity']['native_programming_lease']['run_mode_inhibit']=1
            elif failure=='source':state['connectivity']['source_l5x_sha256']='3'*64
            else:state['instance_id']='replacement'
            with self.subTest(failure=failure),patch('tools.probe_native_sdk.api',return_value=state) as api, \
                    patch('tools.probe_native_sdk.time.monotonic',side_effect=(0,41)), \
                    patch('tools.probe_native_sdk.time.sleep') as sleep:
                with self.assertRaises(ValueError):
                    wait_for_cleanup('http://127.0.0.1:8786',r'TestDriver\192.0.2.8\Backplane\0','1'*64,
                                     instance='one-session',l5x_hash='2'*64)
                self.assertEqual(api.call_count,1);sleep.assert_not_called()

    def test_cleanup_allows_idle_transport_close_without_weakening_final_guards(self):
        busy=self.state();busy['connectivity']['active_tcp_clients']=1
        clean=self.state()
        with patch('tools.probe_native_sdk.api',side_effect=(busy,clean)), \
                patch('tools.probe_native_sdk.time.monotonic',side_effect=(0,31)), \
                patch('tools.probe_native_sdk.time.sleep') as sleep:
            result=wait_for_cleanup('http://127.0.0.1:8786',r'TestDriver\192.0.2.8\Backplane\0','1'*64,
                                    instance='one-session',l5x_hash='2'*64)
        self.assertEqual(result,clean);sleep.assert_called_once()

    def test_cleanup_failure_keeps_post_call_trace_and_reports_incomplete(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.ACD';source.write_bytes(b'owned-acd-source')
            output=root/'report'
            args=SimpleNamespace(project=str(source),url='http://127.0.0.1:8786',
                path=r'TestDriver\192.0.2.8\Backplane\0',operation='download',tag=[],output=str(output),sdk_feed=None)
            from tools.probe_native_sdk import digest
            state=self.state();state.update(app_version='test',tags=[],scan=0,ms=0,changes=[],mode='test')
            state['connectivity']['native_correlation']['source_acd_sha256']=digest(source)
            busy=copy.deepcopy(state);busy['connectivity']['active_tcp_clients']=1
            before={'events':[],'counts':{'native_verified':0}}
            after={'events':[{'kind':'test-retained-evidence'}],'counts':{'native_verified':3}}
            def process(command,**kwargs):
                if command[0]=='dotnet':
                    (output/'bin').mkdir()
                    (output/'bin/NativeSdkProbe.exe').write_bytes(b'test-apphost')
                    (output/'bin/NativeSdkProbe.dll').write_bytes(b'test-managed-code')
                    return subprocess.CompletedProcess(command,0)
                Path(command[2]).write_text(json.dumps({'status':'failed'}))
                return subprocess.CompletedProcess(command,1)
            with patch('tools.probe_native_sdk.sys.platform','win32'), \
                    patch('tools.probe_native_sdk.require_sdk_service'), \
                    patch('tools.probe_native_sdk.background_options',return_value={}), \
                    patch('tools.probe_native_sdk.subprocess.run',side_effect=process), \
                    patch('tools.probe_native_sdk.api',side_effect=(state,state,before,busy,after)), \
                    patch('tools.probe_native_sdk.wait_for_cleanup',side_effect=ValueError('still owned')), \
                    patch('builtins.print'):
                self.assertEqual(run(args),1)
            report=json.loads((output/'summary.json').read_text())
            self.assertEqual(report['status'],'incomplete')
            self.assertFalse(report['cleanup_confirmed'])
            self.assertTrue(report['source_unchanged'] and report['model_unchanged'])
            self.assertEqual(report['native_verified_requests'],3)
            self.assertEqual(json.loads((output/'trace.json').read_text()),after)
            self.assertEqual(json.loads((output/'after-state.json').read_text()),busy)

    def test_transfer_diagnostic_failure_still_checks_endpoint_cleanup_and_pins_backend(self):
        from tools.probe_native_sdk import digest
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original.ACD';source.write_bytes(b'owned-acd-source')
            output=root/'report';state=self.state()
            state.update(app_version='test',tags=[],scan=0,ms=0,changes=[],mode='test')
            state['connectivity']['native_correlation']['source_acd_sha256']=digest(source)
            args=SimpleNamespace(project=str(source),url='http://127.0.0.1:8786',
                path=r'TestDriver\192.0.2.8\Backplane\0',operation='upload',tag=[],output=str(output),sdk_feed=None)
            trace={'events':[],'counts':{'native_verified':0}}
            def process(command,**kwargs):
                if command[0]=='dotnet':
                    (output/'bin').mkdir();(output/'bin/NativeSdkProbe.exe').write_bytes(b'fake-apphost')
                    return subprocess.CompletedProcess(command,0)
                request=json.loads(Path(command[1]).read_text())
                self.assertEqual(request['BackendUrl'],args.url);self.assertEqual(request['InstanceId'],state['instance_id'])
                Path(command[2]).write_text(json.dumps({'status':'failed','steps':[],
                    'serverFaulted':False,'sdkOfflineConfirmed':True}))
                (output/'before-transfer-trace.json').write_text('invalid JSON')
                (output/'after-transfer-trace.json').write_text('{}')
                return subprocess.CompletedProcess(command,1)
            with patch('tools.probe_native_sdk.sys.platform','win32'), \
                    patch('tools.probe_native_sdk.require_sdk_service'), \
                    patch('tools.probe_native_sdk.background_options',return_value={}), \
                    patch('tools.probe_native_sdk.subprocess.run',side_effect=process), \
                    patch('tools.probe_native_sdk.api',side_effect=(state,state,trace,state,trace)), \
                    patch('tools.probe_native_sdk.wait_for_cleanup',return_value=state) as cleanup,patch('builtins.print'):
                self.assertEqual(run(args),1)
            cleanup.assert_called_once()
            report=json.loads((output/'summary.json').read_text())
            self.assertTrue(report['cleanup_confirmed']);self.assertTrue(report['target_rechecked'])
            self.assertEqual(report['transfer_trace'],dict(status='analysis_failed',analysis_complete=False))


if __name__=='__main__':unittest.main()
