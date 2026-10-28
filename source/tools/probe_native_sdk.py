"""Native SDK acceptance against an already running LogixLab research endpoint.

The optional installed SDK runs on a private ACD copy. Download attempts use the
bounded source-equivalent installation profile; they can reset runtime values,
execution state and correlation while preserving the original ACD. General
project replacement remains disabled.
--save-downloaded-acd saves a successful source-equivalent download to a new
downloaded.ACD, reopens it and verifies Go Online. The emulator installation
remains memory-only; resetting or reloading it revokes that saved correlation.
Reports contain private project metadata and default to ignored .local storage.
An upload may select a separate preserved offline merge baseline with
--upload-target; the emulator remains pinned to --project. Only the new private
working copy may change during upload. Its final hash is checked independently.
--connection-target selects a separate saved ACD for a read-only connection
check, or an unchanged source-equivalent saved-download target for edits.
--project continues to pin the emulator's original source.
Only explicit --operation modes changes Run/Program and executes scans. It
restores Program; resulting tag values and scan history are retained. Other
operations never request mode changes. The edits diagnostic imports a generated
NOP rung on a private copy with LeaveEdits or AcceptEdits. The default requires
disabled online edits. --apply-supported-edits instead requires explicitly
enabled Program-mode RLL replacement and verifies the exact resulting insert.
An optional second insert and Offline/Online cycle use the same open SDK project;
each step must preserve the preceding edit and all non-logic model state.
Explicit FinalizeEdits imports are limited to stopped Program mode. Native Test,
Untest and Run-mode assembly are not requested.
Windows services are never managed.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid
import xml.etree.ElementTree as ET

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from tools.vmware_appliance import api, background_options
from logixlab import signed_messages
from logixlab.ethernetip import CIPError, decode_path


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def upload_input(source,operation,target=None):
    """Select a preserved merge baseline; controller binding still uses source."""
    if target is None:return source
    if operation!='upload':raise ValueError('--upload-target belongs only to an upload diagnostic')
    target=Path(target).resolve(strict=True)
    if not target.is_file() or target.suffix.lower()!='.acd' or not 8<=target.stat().st_size<=100_000_000:
        raise ValueError('Upload target must be an ACD file of 8..100000000 bytes')
    return target


def connection_input(source,operation,target=None):
    """A saved connection target is a copied SDK input, never a new source binding."""
    if target is None:return source
    if operation not in ('connection','edits'):raise ValueError('--connection-target requires a connection or edits diagnostic')
    path=Path(target).resolve(strict=True)
    if path.suffix.lower()!='.acd' or not path.is_file() or not 8<=path.stat().st_size<=100_000_000:
        raise ValueError('Connection target must be an ACD file of 8..100000000 bytes')
    return path


def validate_new_upload(operation, enabled, target=None, save_uploaded=False):
    if type(enabled) is not bool:
        raise ValueError('New-project upload must be an explicit boolean')
    if enabled and (operation!='upload' or target is not None or save_uploaded):
        raise ValueError('--upload-new-project requires upload without --upload-target or --save-uploaded-acd')


def new_upload_artifact(output, receipt):
    """Check retained factory output bytes, without asserting ACD validity."""
    if not isinstance(receipt,dict) or receipt.get('factoryCompleted') is not True or receipt.get('fileCreated') is not True:
        return False
    path=Path(output)/'uploaded.ACD'
    try:
        return path.is_file() and 8<=path.stat().st_size<=100_000_000 and digest(path)==receipt.get('acdSha256')
    except OSError:
        return False


def input_evidence(source,source_hash,baseline,baseline_hash,copied,operation):
    """Hash observations must not prevent native cleanup if a file disappears."""
    def observe(path):
        try:return digest(path) if path.is_file() and 8<=path.stat().st_size<=100_000_000 else None
        except OSError:return None
    original=observe(source)==source_hash;target=observe(baseline)==baseline_hash;working=observe(copied)
    return dict(source_unchanged=original and target and (operation=='upload' or working==baseline_hash),
                upload_target_original_unchanged=target,working_copy_sha256=working,
                working_copy_unchanged=working==baseline_hash,working_copy_present=working is not None,
                working_copy_changes_permitted=operation=='upload')


def runtime_hashes(folder):
    # A .NET apphost EXE can stay identical while its managed DLL changes.
    # Record the executable code and runtime configuration, not just the host.
    return {path.relative_to(folder).as_posix(): digest(path)
            for path in sorted(Path(folder).rglob('*'))
            if path.is_file() and path.suffix.lower() in ('.exe', '.dll', '.json')}


def sdk_diagnostic_codes(report):
    """Retain SDK codes from exceptions and the separately logged import XML.

    Import failures can wrap the useful mnemonic in ImportLog status events.
    Codes identify reported diagnostics, not the cause of a protocol failure.
    """
    messages=[]
    for step in report.get('steps',[]):
        messages.extend(item.get('message','') for item in step.get('errors',[]))
        messages.append(step.get('error',''))
    messages.extend(item.get('message','') for item in report.get('events',[]))
    pattern=r'\b(?:Rx[A-Za-z0-9]*(?:_E|E)|LgxSrv_E|XMLSrv_E)_[A-Z][A-Z0-9_]{0,127}\b'
    return sorted({code for message in messages if isinstance(message,str)
                   for code in re.findall(pattern,message)})


def validate_url(url):
    value = urlsplit(url)
    if (value.scheme != 'http' or value.hostname != '127.0.0.1' or
            value.username is not None or value.password is not None or
            value.path or value.query or value.fragment or not value.port):
        raise ValueError('Use the local LogixLab URL: http://127.0.0.1:<port>')
    return url


def require_sdk_service():
    """Read service status before any native build/project call; never control it."""
    result=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',
        '(Get-Service -Name LdSdkService -ErrorAction Stop).Status.ToString()'],
        capture_output=True,text=True,timeout=10,**background_options())
    if result.returncode or result.stdout.strip()!='Running':
        raise ValueError('Logix Designer SDK Service (LdSdkService) must be Running; this tool never starts or restarts it')


def validate_target(state, path, source_hash, *, instance=None, l5x_hash=None):
    """Require one source-bound anonymous endpoint; never retarget the app."""
    parts = path.split('\\')
    if len(parts) != 4 or not parts[0] or parts[2:] != ['Backplane', '0']:
        raise ValueError('Expected a Linx driver\\IPv4\\Backplane\\0 path')
    address = str(ipaddress.IPv4Address(parts[1]))
    cip = state.get('connectivity', {})
    identity = cip.get('native_correlation') or {}
    native = cip.get('native_session') or {}
    if (not state.get('instance_id') or instance is not None and state['instance_id'] != instance or
            cip.get('enabled') is not True or cip.get('profile') != 'logix-v35-l85e' or
            cip.get('address') != address + ':44818' or
            cip.get('allow_writes') is not False or native.get('enabled') is not True or
            native.get('read_only') is not True or
            state.get('device_io', {}).get('writes_enabled') is not False or
            identity.get('bound') is not True or identity.get('source_acd_sha256') != source_hash or
            not cip.get('source_l5x_sha256') or
            identity.get('source_l5x_sha256') != cip['source_l5x_sha256'] or
            l5x_hash is not None and cip['source_l5x_sha256'] != l5x_hash):
        raise ValueError('Running emulator, source binding or read-only policy does not match the probe')
    return state['instance_id']


def validate_operation(operation, tags):
    if operation not in ('connection', 'upload', 'download', 'modes', 'edits'):
        raise ValueError('Expected connection, upload, download, modes or edits')
    if operation != 'connection' and tags:
        raise ValueError('Tag reads belong to a connection probe')
    if len(tags) > 32 or any(not tag or len(tag) > 1024 for tag in tags):
        raise ValueError('At most 32 nonempty tag XPaths of at most 1024 characters')


def validate_tag_read_type(operation,tags,read_type):
    if read_type not in ('BYTE_ARRAY','BOOL','DINT','REAL'):
        raise ValueError('Supported SDK tag-read types are BYTE_ARRAY, BOOL, DINT and REAL')
    if read_type!='BYTE_ARRAY' and (operation!='connection' or not tags):
        raise ValueError('A typed SDK read requires a connection probe and at least one --tag')
    return read_type


def validate_edit_extensions(operation,apply,tags,save):
    if type(save) is not bool or not isinstance(tags,(list,tuple)) or len(tags)>8 or any(
            not isinstance(tag,str) or not 1<=len(tag)<=1024 or '\0' in tag for tag in tags):
        raise ValueError('At most eight bounded post-edit DINT tag XPaths and a boolean save option')
    if (save or tags) and (operation!='edits' or apply is not True):
        raise ValueError('Post-edit reads and ACD save require explicit supported-edit application')


def saved_acd_effect(state,folder,receipt):
    """Check native save/reopen evidence and the resulting neutral project source."""
    from logixlab.model import Project,Memory,ModelError
    from logixlab.runtime import Engine
    from logixlab.server import serialize_nodes
    try:
        if not isinstance(receipt,dict) or receipt.get('nativeAcdReopened') is not True or receipt.get('offlineOnly') is not True:return False
        for filename,key in (('emulator-edited.L5X','inputL5xSha256'),('edited.ACD','acdSha256'),('reopened.L5X','reopenedL5xSha256')):
            path=folder/filename
            if not path.is_file() or not 8<=path.stat().st_size<=150_000_000 or digest(path)!=receipt.get(key):return False
        original=Project(folder/'emulator-edited.L5X');reopened=Project(folder/'reopened.L5X')
        expected={r['key'].casefold():(r['kind'],[row['nodes'] for row in r['rungs']]) for r in state['routines']}
        for project in (original,reopened):
            actual={key:(r.kind,[serialize_nodes(row['nodes']) for row in r.rungs]) for key,r in project.routines.items()}
            engine=Engine(project,defer_prescan=True)
            if actual!=expected or engine.blockers or engine.entries!=state['entry_routines']:return False
        def leaves(project):
            return {row['name'].casefold():{k:row[k] for k in ('type','value','kind','constant','alias','unknown','problem')}
                    for row in Memory(project).leaves()}
        if leaves(original)!=leaves(reopened):return False
        if original.task_configuration.names!=reopened.task_configuration.names:return False
        if original.executable_configuration.program_names!=reopened.executable_configuration.program_names:return False
        return True
    except (OSError,ValueError,KeyError,TypeError,ModelError):return False


def validate_upload_save(operation,save):
    if type(save) is not bool or save and operation!='upload':
        raise ValueError('Saving an uploaded ACD requires an upload operation and a boolean option')


def validate_download_save(operation,save):
    if type(save) is not bool or save and operation!='download':
        raise ValueError('Saving a downloaded ACD requires a download operation and a boolean option')


def saved_downloaded_acd_effect(state,source,folder,receipt):
    """Check saved correlation and native reopen evidence, separately from upload."""
    from logixlab.native_project import NativeProjectIdentity
    from logixlab.model import ModelError
    try:
        if (not isinstance(receipt,dict) or any(receipt.get(key) is not True for key in
                ('nativeAcdReopened','reopenedOnline','downloadResultSaved'))
                or receipt.get('emulatorPersistence')!='memory_only'
                or (state['connectivity'].get('native_download') or {}).get('source_equivalent') is not True):return False
        path=Path(folder)/'downloaded.ACD'
        if path.is_symlink() or not path.is_file() or not 8<=path.stat().st_size<=100_000_000 or digest(path)!=receipt.get('acdSha256'):return False
        binding=state['connectivity']['source_l5x_sha256']
        original=NativeProjectIdentity.from_acd(source,binding);saved=NativeProjectIdentity.from_acd(path,binding)
        return (saved.download_uid!=original.download_uid and all(getattr(saved,key)==getattr(original,key) for key in
            ('online_index','online_generation','copy_uid','project_uid','timeline_uid','empty_change_log')))
    except (OSError,ValueError,KeyError,TypeError,ModelError):return False


def saved_uploaded_acd_effect(folder,receipt):
    """Verify new saved/reopened artifacts; source/logic equivalence is separate."""
    try:
        if not isinstance(receipt,dict) or any(receipt.get(key) is not True for key in
                ('nativeAcdReopened','offlineOnly','uploadResultSaved')):return False
        for filename,key,maximum in (('uploaded.ACD','acdSha256',100_000_000),
                                     ('uploaded.L5X','reopenedL5xSha256',16_000_000)):
            path=folder/filename
            if (path.is_symlink() or not path.is_file() or not 8<=path.stat().st_size<=maximum
                    or digest(path)!=receipt.get(key)):return False
        raw=(folder/'uploaded.L5X').read_bytes()
        text=raw.decode('utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'utf-8-sig')
        if '\0' in text or '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():return False
        root=ET.fromstring(text)
        return root.tag=='RSLogix5000Content' and root.get('TargetType')=='Controller' and len(root.findall('Controller'))==1
    except (OSError,ValueError,TypeError,ET.ParseError):return False


def edit_request(state, program, routine, option, *, code='NOP();',apply=False,position=0,replace=0):
    """Create one checked rung insert for an ordinary RLL routine, never arbitrary XML."""
    if option not in ('LeaveEdits', 'AcceptEdits', 'FinalizeEdits') or option=='FinalizeEdits' and not apply:
        raise ValueError('FinalizeEdits requires explicit supported Program-mode edit application')
    names = (state.get('name'), program, routine)
    if any(not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,39}', name)
           for name in names):
        raise ValueError('Edit controller, program and routine names must be ordinary Logix identifiers')
    if str(state.get('version')) not in ('35', '35.00'):
        raise ValueError('Edit diagnostic requires a source-bound Logix v35 project')
    candidates = [item for item in state.get('routines', []) if item.get('key') == program + '/' + routine]
    if (len(candidates) != 1 or candidates[0].get('kind') != 'RLL' or
            candidates[0].get('harness') is not True or not isinstance(candidates[0].get('rungs'), list)):
        raise ValueError('Edit diagnostic requires one loaded ordinary RLL routine')
    if state.get('controller', {}).get('mode') != 'Program' or state['controller'].get('running') is not False:
        raise ValueError('Edit diagnostic requires stopped Program mode')
    lease=state.get('connectivity', {}).get('native_programming_lease', {})
    if lease.get('online_edits') is not apply:
        raise ValueError('Edit access must match the explicit supported-edit option')
    if apply and (option not in ('AcceptEdits','FinalizeEdits') or lease.get('online_edit_scope')!='standard_rll_program_mode'
            or state.get('routine_edits',{}).get('enabled') is not True):
        raise ValueError('Active edit requires enabled supported Program-mode RLL replacement')
    count=len(candidates[0]['rungs'])
    if (type(position) is not int or type(replace) is not int or not 0<=position<=count
            or not 0<=replace<=count-position or not apply and (position or replace)):
        raise ValueError('Edit range must fit the loaded routine; custom ranges require supported-edit application')
    if not isinstance(code,str) or not 1<=len(code)<=4096 or '@' in code or not apply and code!='NOP();':
        raise ValueError('Custom rung text requires explicit supported-edit application')
    from logixlab.model import parse_rung,operations,ARITIES,operand_problem,ModelError
    try:
        nodes=parse_rung(code)
        if not list(operations(nodes)) or any(op.name not in ARITIES or operand_problem(op) for op in operations(nodes)):
            raise ValueError('Rung requires supported ordinary instructions')
    except ModelError as error:raise ValueError('Invalid rung syntax') from error
    root = ET.Element('RSLogix5000Content', SchemaRevision='1.0', SoftwareRevision='35.00',
                      TargetType='Rung', TargetCount='1', ContainsContext='true',
                      ExportOptions='References NoRawData L5KData DecoratedData Context Dependencies ForceProtectedEncoding AllProjDocTrans')
    controller = ET.SubElement(root, 'Controller', Use='Context', Name=names[0])
    programs = ET.SubElement(controller, 'Programs', Use='Context')
    parent = ET.SubElement(programs, 'Program', Use='Context', Name=program)
    routines = ET.SubElement(parent, 'Routines', Use='Context')
    target = ET.SubElement(routines, 'Routine', Use='Context', Name=routine, Type='RLL')
    content = ET.SubElement(target, 'RLLContent')
    rung = ET.SubElement(content, 'Rung', Number='0', Type='N')
    ET.SubElement(rung, 'Text').text = code
    payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return payload, dict(XPath=f"Controller/Programs/Program[@Name='{program}']/Routines/Routine[@Name='{routine}']",
                         InsertPosition=position, ReplaceCount=replace, ImportOption=option)


def rejection_delta(before, after):
    """Report newly rejected structural requests without mistaking earlier probes for this one."""
    fields = ('generation', 'service', 'class_id', 'instance', 'attribute', 'program_instance',
              'io_map_instance', 'controller_instance', 'aoi_instance', 'symbolic', 'status', 'reason')
    previous = {tuple(row.get(field) for field in fields): row.get('count', 0)
                for row in before.get('native_rejections', [])}
    rows = []
    for row in after.get('native_rejections', []):
        count = row.get('count', 0) - previous.get(tuple(row.get(field) for field in fields), 0)
        if count > 0:
            rows.append({**row, 'probe_count': count})
    return sorted(rows, key=lambda row: row.get('last_seen', 0))


def supported_edit_effect(before,after,config,code):
    """Verify the generated insert plus preserved model values/history/config."""
    from logixlab.model import parse_rung,ModelError
    from logixlab.server import serialize_nodes
    try:
        names=re.findall(r"@Name='([^']+)'",config['XPath']);key='/'.join(names[-2:])
        old={r['key']:r for r in before['routines']};new={r['key']:r for r in after['routines']}
        if set(old)!=set(new) or key not in old:return False
        if any(old[k]!=new[k] for k in old if k!=key):return False
        position=config['InsertPosition'];replace=config['ReplaceCount']
        nodes=[r['nodes'] for r in old[key]['rungs']]
        expected=nodes[:position]+[serialize_nodes(parse_rung(code))]+nodes[position+replace:]
        if [r['nodes'] for r in new[key]['rungs']]!=expected:return False
        if after['routine_edits']['revision']!=before['routine_edits']['revision']+1:return False
        if not re.fullmatch(r'[a-f0-9]{64}',after['routine_edits']['logic_sha256']):return False
        return all(before[k]==after[k] for k in ('instance_id','tags','scan','ms','changes','mode','tasks','entry_routines','controller'))
    except (KeyError,TypeError,IndexError,ModelError):return False


def edit_sequence(state, program, routine, option, codes, *, apply=False,second_target=None,ranges=None):
    """Bounded generated inserts with exact before/after expectations for native checks."""
    if not 1 <= len(codes) <= 2 or len(codes)>1 and not apply:
        raise ValueError('One diagnostic insert or at most two explicitly applied inserts')
    if apply and (type(state.get('routine_edits',{}).get('revision')) is not int or state['routine_edits']['revision']!=0):
        raise ValueError('A fresh ACD-copy probe requires unmodified runtime logic; keep sequential edits in the same SDK project')
    from logixlab.model import parse_rung
    from logixlab.server import serialize_nodes
    if ranges is None:ranges=[(0,0)]*len(codes)
    if len(ranges)!=len(codes) or second_target is not None and (len(codes)!=2 or not apply):
        raise ValueError('Second target and ranges must match the explicit edit sequence')
    result=[];by_target={}
    for index,code in enumerate(codes):
        target_program,target_routine=(second_target if index==1 and second_target is not None else (program,routine))
        key=target_program+'/'+target_routine
        # Ranges are checked against the predicted preceding edit, which can
        # alter the same routine's length. No active model object is mutated.
        import copy
        preview=copy.deepcopy(state)
        if key in by_target:
            next(r for r in preview['routines'] if r['key']==key)['rungs']=[{'nodes':n} for n in by_target[key]]
        position,replace=ranges[index]
        payload,config=edit_request(preview,target_program,target_routine,option,code=code,apply=apply,position=position,replace=replace)
        if apply:
            target=next(r for r in preview['routines'] if r['key']==key)
            nodes=[r['nodes'] for r in target['rungs']]
            revision=state['routine_edits']['revision']
            if type(revision) is not int or revision<0:raise ValueError('Invalid base logic revision')
            config.update(BaseRevision=revision+index,BeforeRungs=nodes)
            nodes=nodes[:position]+[serialize_nodes(parse_rung(code))]+nodes[position+replace:]
            config['ExpectedRungs']=nodes
            by_target[key]=nodes
        result.append((payload,config))
    return result


def supported_sequence_effect(before,after,edits,codes,output,*,reconnect=False):
    """Require every individual insert and reconnect, not merely the final routine."""
    stable=('instance_id','tags','scan','ms','changes','mode','tasks','entry_routines','controller','routines','routine_edits')
    if not 1<=len(edits)==len(codes)<=2:return False
    previous=before
    try:
        for index,((_,config),code) in enumerate(zip(edits,codes,strict=True)):
            suffix='edit' if index==0 else 'edit2'
            start=json.loads((output/f'before-{suffix}-state.json').read_text(encoding='utf-8'))
            end=json.loads((output/f'after-{suffix}-state.json').read_text(encoding='utf-8'))
            if any(previous[k]!=start[k] for k in stable) or not supported_edit_effect(start,end,config,code):return False
            if reconnect:
                connected=json.loads((output/f'after-reconnect-{index+1}-state.json').read_text(encoding='utf-8'))
                if any(end[k]!=connected[k] for k in stable):return False
                end=connected
            previous=end
        return all(previous[k]==after[k] for k in stable)
    except (OSError,ValueError,TypeError,KeyError):return False


def edit_trace_evidence(trace, report, *, before_edit=None, after_edit=None, import_index=0):
    """Use emulator trace checkpoints around import; SDK and guest clocks may differ."""
    steps = [item for item in report.get('steps', [])
             if item.get('method', '').startswith('PartialImportRungsFromXmlFileAsync:')]
    if not 0<=import_index<len(steps):return {'status':'import_not_reached', 'failed_requests':[], 'first_failed_request':None}
    step = steps[import_index]
    if before_edit is None or after_edit is None:
        return {'status':'checkpoints_unavailable', 'failed_requests':[], 'first_failed_request':None,
                'sdk_method':step['method'], 'sdk_status':step['status']}
    previous = before_edit.get('events', [])
    events = after_edit.get('events', [])
    if previous:
        positions = [index for index,event in enumerate(events) if event == previous[-1]]
        if not positions:
            return {'status':'checkpoint_events_not_retained', 'failed_requests':[], 'first_failed_request':None,
                    'sdk_method':step['method'], 'sdk_status':step['status']}
        events = events[positions[-1]+1:]
    failures = []; wrappers = []; matched = skipped = 0
    for event in events:
        if event.get('kind') != 'cip':continue
        if event.get('truncated'):skipped += 1;continue
        try:
            raw = bytes.fromhex(event.get('request_hex', ''))
            response = bytes.fromhex(event.get('response_hex', ''))
            if len(raw) < 2 or len(response) < 4:raise ValueError('Missing CIP header')
            children = ((raw, response),)
            sequence = None
            if raw[0] in (0x36, 0x37, 0x38, 0x39):
                request = signed_messages.parse_request(raw)
                # A policy rejection can be an ordinary outer CIP error, with
                # no signed response envelope. Keep it separate from inner
                # operation results and never label it MAC-authenticated.
                if (response[0]==(raw[0]|0x80) and response[1]==0 and response[2]!=0
                        and len(response)==4+2*response[3]):
                    row=dict(time=event['time'],service=raw[0],status=response[2],sequence=request.sequence,
                             response_authenticated=False,additional_status=response[4:].hex())
                    if isinstance(request,signed_messages.FragmentEnvelope):
                        row.update(container_format=request.container_format,position=request.position,
                                   fragment_bytes=len(request.fragment))
                    wrappers.append(row);matched+=1;continue
                reply = signed_messages.parse_response(response, request)
                sequence = request.sequence
                if isinstance(request, signed_messages.FragmentEnvelope):continue
                children = (tuple(zip(request.children, reply.children))
                            if isinstance(request, signed_messages.BatchEnvelope) else ((request.inner, reply.inner),))
            for child, result in children:
                matched += 1
                if not result[2]:continue
                path = decode_path(child[2:2 + child[1] * 2])
                failures.append(dict(time=event['time'], service=child[0], class_id=path.class_id,
                    instance=path.instance, attribute=path.attribute, program_instance=path.program_instance,
                    io_map_instance=path.io_map_instance, controller_instance=path.controller_instance,aoi_instance=path.aoi_instance,
                    symbolic=bool(path.symbols), status=result[2], sequence=sequence,
                    payload_bytes=len(child) - 2 - child[1]*2))
        except (ValueError, IndexError, CIPError):skipped += 1
    return dict(status='observed' if matched else 'no_complete_cip_during_import',
                sdk_method=step['method'], sdk_status=step['status'], started_at=step['startedAt'],
                finished_at=step['finishedAt'], requests_observed=matched, unparsed_events=skipped,
                correlation='emulator_trace_checkpoints',
                failed_requests=failures[:64], failures_truncated=len(failures)>64,
                wrapper_rejections=wrappers[:64], wrapper_rejections_truncated=len(wrappers)>64,
                first_wrapper_rejection=wrappers[0] if wrappers else None,
                first_failed_request=failures[0] if failures else None, mac_verification='not performed by report parser')


def validate_staging(lease):
    """Older endpoints may omit stages; advertised stages must be empty."""
    if 'request_selector' in lease and lease['request_selector'] is not None:
        raise ValueError('Probe requires no outstanding programming or edit reservation')
    if 'edit_preparation' in lease:
        edit = lease['edit_preparation']
        if (not isinstance(edit, dict) or edit.get('status') != 'idle' or
                type(edit.get('changes_staged')) is not int or edit['changes_staged'] != 0 or
                any(edit.get(field) is not False for field in ('reserved', 'source_bound', 'active_changes',
                    'accepted', 'testing', 'assembled', 'commit'))):
            raise ValueError('Probe requires an empty idle edit reservation without active edits')
        if 'program_reservations' in edit and (type(edit['program_reservations']) is not int or edit['program_reservations']!=0):
            raise ValueError('Probe requires empty Program reservations')
        for field in ('phase_open','active_stack_changed'):
            if field in edit and edit[field] is not False:raise ValueError('Probe requires closed edit preparation')
        for field in ('program_stack_preparations','stack_bytes_allocated'):
            if field in edit and (type(edit[field]) is not int or edit[field]!=0):
                raise ValueError('Probe requires empty Program stack preparation')
    if 'edit_transfer' in lease:
        transfer=lease['edit_transfer']
        if not isinstance(transfer,dict) or transfer.get('status')!='idle' or transfer.get('container_sha256') is not None:
            raise ValueError('Probe requires idle empty compiled edit storage')
        for field in ('source_bound','buffer_allocated','complete','container_length_verified','elf_structural_validation',
                      'relocations_resolved','payloads_exposed','routine_installed','accepted_edits','commit'):
            if transfer.get(field) is not False:raise ValueError('Probe requires disabled compiled edit installation')
        for field in ('received_bytes','total_bytes','fragments','instructions_executed'):
            if type(transfer.get(field)) is not int or transfer[field]!=0:
                raise ValueError('Probe requires empty compiled edit storage')
        for field in ('component_kind','code_sha256','source_description'):
            if transfer.get(field) is not None:raise ValueError('Probe requires no retained Routine source or code')
        for field in ('retained_bytes','code_bytes'):
            if field in transfer and (type(transfer[field]) is not int or transfer[field]!=0):
                raise ValueError('Probe requires empty paired Routine containers')
        if transfer.get('program_released',False) is not False or transfer.get('base_logic_revision') is not None:
            raise ValueError('Probe requires no released Routine candidate')
        if 'post_source_record' in transfer:
            record=transfer['post_source_record']
            if (not isinstance(record,dict) or any(record.get(field) is not False
                    for field in ('staged','interpreted','payload_exposed'))
                    or type(record.get('bytes')) is not int or record['bytes']!=0 or record.get('sha256') is not None):
                raise ValueError('Probe requires empty post-source edit storage')
        if 'routine_metadata' in transfer:
            record=transfer['routine_metadata']
            if (not isinstance(record,dict) or record.get('sha256') is not None
                    or any(record.get(k) is not False for k in ('active_metadata_written','region_semantics_verified','payload_exposed'))
                    or any(type(record.get(k)) is not int or record[k]!=0 for k in ('records','bytes'))):
                raise ValueError('Probe requires empty temporary routine metadata')
    if lease.get('applied_routine_edit') is not None:raise ValueError('Probe requires no active edit transaction receipt')
    for name in ('library_staging','metadata_staging'):
        if name not in lease:continue
        stage=lease[name]
        if not isinstance(stage,dict):raise ValueError('Probe requires empty temporary stages')
        for field in ('instances','name_bytes','value_targets','value_count','value_bytes'):
            value=stage.get(field) if field in ('instances','name_bytes') else stage.get(field,0)
            if type(value) is not int or value!=0:raise ValueError('Probe requires empty temporary stages')
        if (stage.get('commit') is not False or stage.get('data_transfer',False) is not False
                or stage.get('active_values_transfer',False) is not False):
            raise ValueError('Probe requires disabled commit and active data transfer')
        if stage.get('values_transfer',False) is not False and (
                name!='metadata_staging' or stage.get('values_transfer') is not True or
                stage.get('values_scope')!='staged_definitions' or stage.get('active_values_transfer') is not False):
            raise ValueError('Metadata values must remain scoped to temporary definitions')
    if 'resilient_transport' in lease:
        stage=lease['resilient_transport']
        if (not isinstance(stage,dict) or stage.get('open') is not False
                or type(stage.get('buffer_bytes')) is not int or stage['buffer_bytes']!=0
                or stage.get('buffer_allocated') is not False or stage.get('payload_transfer') is not False
                or stage.get('commit') is not False):
            raise ValueError('Probe requires closed Resilient Transport and disabled payload transfer')
        for field in ('received_bytes','total_bytes','fragments'):
            value=stage.get(field,0)
            if type(value) is not int or value!=0:raise ValueError('Probe requires empty transport fragment staging')
        if stage.get('complete',False) is not False:raise ValueError('Probe requires empty transport fragment staging')
        if 'template_staging' in stage:
            templates=stage['template_staging']
            if (not isinstance(templates,dict) or templates.get('status')!='idle'
                    or any(templates.get(field) is not False for field in ('definitions_exposed','active_catalog_replaced','commit'))):
                raise ValueError('Probe requires empty temporary templates and disabled installation')
            for field in ('templates','definition_bytes','write_fragments','records_modeled','unsupported_records'):
                if type(templates.get(field)) is not int or templates[field]!=0:raise ValueError('Probe requires empty temporary templates')
            if 'layout_inspection' in templates:
                layout=templates['layout_inspection']
                if (not isinstance(layout,dict) or layout.get('status')!='idle' or layout.get('errors')!=[] or
                        any(type(layout.get(f)) is not int or layout[f]!=0 for f in
                            ('templates_decoded','templates_unavailable','members_decoded','opaque_trailer_bytes','encoded_offset_members')) or
                        any(layout.get(f) is not False for f in
                            ('storage_mapping_supported','signature_verified','definitions_exposed','execution_supported'))):
                    raise ValueError('Probe requires empty temporary Template layout inspection')
        if 'source_type_verification' in stage:
            check=stage['source_type_verification']
            if (not isinstance(check,dict) or check.get('status')!='idle' or check.get('errors')!=[] or
                    any(f in check and (type(check[f]) is not int or check[f]!=0) for f in ('template_ids_matched','template_ids_unresolved')) or
                    ('template_identities_verified' in check and check['template_identities_verified'] is not False) or
                    any(type(check.get(f)) is not int or check[f]!=0 for f in
                        ('types_matched','members_matched','types_unavailable')) or
                    any(check.get(f) is not False for f in ('member_locations_verified','storage_mapping_supported',
                        'signature_verified','definitions_exposed','execution_supported'))):
                raise ValueError('Probe requires empty source type verification')
        if 'source_object_verification' in stage:
            check=stage['source_object_verification']
            if (not isinstance(check,dict) or check.get('status')!='idle' or check.get('errors')!=[]
                    or check.get('identity_checks_only') is not True
                    or any(f in check and (type(check[f]) is not int or check[f]!=0) for f in ('tables_matched','tables_unresolved'))
                    or 'auxiliary_symbols_matched' in check and (type(check['auxiliary_symbols_matched']) is not int or check['auxiliary_symbols_matched']!=0)
                    or any(type(check.get(f)) is not int or check[f]!=0 for f in
                        ('programs_matched','routines_matched','symbols_matched','symbols_unresolved'))
                    or any(check.get(f) is not False for f in ('table_identities_verified','compiled_code_verified',
                        'addresses_verified','install_authority','active_catalog_replaced','commit'))):
                raise ValueError('Probe requires empty source object identity verification')
        if 'download_image' in stage:
            image = stage['download_image']
            if (not isinstance(image, dict) or image.get('status') != 'idle' or
                    image.get('record_sha256') is not None or image.get('reason') is not None or
                    any(image.get(field) is not False for field in ('source_bound', 'temporary_readback',
                        'preparation_started', 'initial_values_applied', 'compiled_routines_installed', 'active_catalog_replaced',
                        'native_execution_supported', 'commit', 'values_exposed'))):
                raise ValueError('Probe requires an idle empty download image without readback or installation authority')
            for field in ('records_prepared', 'tables_allocated', 'templates_retained', 'diagnostics_retained',
                          'programs_retained', 'routines_retained', 'storage_bytes', 'symbols_linked', 'symbols_unresolved'):
                if type(image.get(field)) is not int or image[field] != 0:
                    raise ValueError('Probe requires an empty download image')
            if 'preparation_results' in image:
                results=image['preparation_results']
                if (not isinstance(results,dict) or results.get('status')!='idle' or
                        type(results.get('records')) is not int or results['records']!=0 or
                        results.get('operations')!=[] or
                        any(results.get(field) is not True for field in ('immutable','private_internal_only')) or
                        any(results.get(field) is not False for field in ('wire_encoding_supported','vendor_status_exposed',
                            'request_bytes_exposed','object_identifiers_exposed'))):
                    raise ValueError('Probe requires an empty immutable private preparation result ledger')
        if 'diagnostic_staging' in stage:
            diagnostics=stage['diagnostic_staging']
            if (not isinstance(diagnostics,dict) or diagnostics.get('status')!='idle'
                    or any(diagnostics.get(field) is not False for field in ('definitions_exposed','active_catalog_replaced','commit'))):
                raise ValueError('Probe requires empty temporary diagnostics and disabled installation')
            for field in ('messages','text_bytes','records_modeled'):
                if type(diagnostics.get(field)) is not int or diagnostics[field]!=0:raise ValueError('Probe requires empty temporary diagnostics')
        if 'object_staging' in stage:
            objects=stage['object_staging']
            if (not isinstance(objects,dict) or objects.get('status')!='idle'
                    or any(objects.get(field) is not False for field in ('definitions_exposed','active_catalog_replaced','commit','references_validated'))):
                raise ValueError('Probe requires empty temporary objects and disabled installation')
            for field in ('symbols','tables','programs','routines','coordination_records','records_modeled','storage_bytes','open_coordination'):
                if type(objects.get(field)) is not int or objects[field]!=0:raise ValueError('Probe requires empty temporary objects')
        if 'inspection' in stage:
            inspection=stage['inspection']
            if (not isinstance(inspection,dict) or inspection.get('status')!='idle' or inspection.get('operations')!=[]
                    or inspection.get('execution_supported') is not False or inspection.get('payloads_exposed') is not False
                    or inspection.get('signature_verified') is not False):
                raise ValueError('Probe requires empty structural inspection and disabled batch execution')
            for field in ('expanded_bytes','record_count','scoped_records','records_executed'):
                if type(inspection.get(field)) is not int or inspection[field]!=0:raise ValueError('Probe requires empty structural inspection')
    if ('preparation_state' in lease and lease['preparation_state']!='idle' or
            'preparation_status' in lease and (type(lease['preparation_status']) is not int or lease['preparation_status']!=0)):
        raise ValueError('Probe requires idle programming preparation')


def validate_idle(state, *, allow_supported_edits=False):
    """Do not share a programming test with an existing native connection."""
    cip = state.get('connectivity', {})
    if 'controller' in state and (state['controller'].get('running') is not False or state['controller'].get('mode')!='Program'):
        raise ValueError('Probe requires the emulator stopped in Program')
    lease = cip.get('native_programming_lease') or {}
    validate_staging(lease)
    clients = cip.get('active_tcp_clients')
    mask = lease.get('run_mode_inhibit')
    if (type(clients) is not int or clients != 0 or lease.get('available') is not True or
            lease.get('owned') is not False or type(mask) is not int or mask != 0 or
            lease.get('scan_inhibited') is not False or lease.get('project_transfer') is not False or
            lease.get('controller_mode_changes') is not False or lease.get('online_edits') is not allow_supported_edits or
            lease.get('tag_write_authority') is not False):
        raise ValueError('Probe requires an idle endpoint, free uninhibited lease and disabled programming authority')
    if allow_supported_edits and (lease.get('online_edit_scope')!='standard_rll_program_mode'
            or state.get('routine_edits',{}).get('enabled') is not True):
        raise ValueError('Only explicitly enabled Program-mode RLL edits are supported')


def validate_mode_probe(state):
    controller=state.get('controller') or {}
    interval=controller.get('scan_interval_ms')
    prescans=controller.get('prescan_count')
    if (controller.get('running') is not False or controller.get('mode')!='Program' or
            controller.get('keyswitch')!='Remote' or type(interval) is not int or not 1<=interval<=100 or
            type(prescans) is not int or prescans<0 or type(controller.get('first_scan_pending')) is not bool or
            state.get('blockers')!=[] or state.get('fault') or
            state.get('connectivity',{}).get('native_session',{}).get('controller_mode_requests') is not True):
        raise ValueError('Mode probe requires executable Remote Program, Run-entry status and a 1..100 ms interval')


def wait_for_cleanup(url, path, source_hash, *, instance, l5x_hash, timeout=40,allow_supported_edits=False):
    """Allow the endpoint's 30-second idle transport close after SDK Dispose.

    Every poll still requires the same bound source/instance; success requires
    zero clients and a free, uninhibited lease with empty temporary state.
    """
    deadline = time.monotonic() + timeout
    while True:
        state = api(url, 'state')
        validate_target(state, path, source_hash, instance=instance, l5x_hash=l5x_hash)
        try:
            validate_idle(state,allow_supported_edits=allow_supported_edits)
            return state
        except ValueError as error:
            if time.monotonic() >= deadline:
                raise ValueError('SDK cleanup did not close clients and clear the lease/inhibit/staging') from error
            time.sleep(.2)


def run(args):
    if sys.platform != 'win32':
        raise ValueError('The optional native SDK probe requires Windows')
    url = validate_url(args.url)
    source = Path(args.project).resolve(strict=True)
    if source.suffix.lower() != '.acd' or not 8 <= source.stat().st_size <= 100_000_000:
        raise ValueError('Select an ACD file of 8..100000000 bytes')
    validate_operation(args.operation, args.tag)
    retain_trace=getattr(args,'retain_transfer_trace',False)
    if type(retain_trace) is not bool or retain_trace and args.operation not in ('upload','download'):
        raise ValueError('--retain-transfer-trace requires upload or download')
    save_upload=getattr(args,'save_uploaded_acd',False);validate_upload_save(args.operation,save_upload)
    save_download=getattr(args,'save_downloaded_acd',False);validate_download_save(args.operation,save_download)
    download_content_source=getattr(args,'verify_downloaded_content',None)
    upload_new=getattr(args,'upload_new_project',False)
    validate_new_upload(args.operation,upload_new,getattr(args,'upload_target',None),save_upload)
    content_source=getattr(args,'verify_uploaded_content',None)
    edited_content=getattr(args,'allow_edited_upload_content',False)
    export_uploaded_tags=getattr(args,'verify_uploaded_tag_definitions',False)
    from tools import upload_tag_definitions
    upload_tag_definitions.validate_options(args.operation,export_uploaded_tags,content_source,upload_new)
    snapshot_upload=getattr(args,'snapshot_uploaded_acd',False)
    from tools import upload_snapshot
    upload_snapshot.validate_options(args.operation,snapshot_upload,content_source,getattr(args,'upload_target',None),save_upload,upload_new)
    verify_upload_baseline=getattr(args,'verify_upload_baseline_online',False)
    if edited_content and (content_source is None or args.operation!='upload' or upload_new
            or snapshot_upload or verify_upload_baseline or save_upload):
        raise ValueError('--allow-edited-upload-content requires a content-checked existing upload without save or baseline snapshot options')
    upload_snapshot.validate_options(args.operation,verify_upload_baseline,content_source,getattr(args,'upload_target',None),save_upload,upload_new,
                                     option='--verify-upload-baseline-online')
    if content_source is not None and (args.operation!='upload' or upload_new):
        raise ValueError('--verify-uploaded-content requires an existing-project upload')
    connection_target=getattr(args,'connection_target',None)
    if connection_target is not None and getattr(args,'upload_target',None) is not None:
        raise ValueError('Select one SDK input target')
    baseline=(connection_input(source,args.operation,connection_target) if connection_target is not None
              else upload_input(source,args.operation,getattr(args,'upload_target',None)))
    baseline_hash=digest(baseline)
    tag_read_type=validate_tag_read_type(args.operation,args.tag,getattr(args,'tag_read_type','BYTE_ARRAY'))
    apply_edits=getattr(args,'apply_supported_edits',False)
    edit_tags=getattr(args,'post_edit_tag',[]);save_acd=getattr(args,'save_edited_acd',False)
    validate_edit_extensions(args.operation,apply_edits,edit_tags,save_acd)
    edit_code=getattr(args,'edit_code',None)
    if edit_code is None:edit_code='NOP();'
    second_code=getattr(args,'second_edit_code',None)
    reconnect=getattr(args,'reconnect_edits',False)
    second_program=getattr(args,'second_edit_program',None);second_routine=getattr(args,'second_edit_routine',None)
    ranges=[(getattr(args,'edit_insert_position',0),getattr(args,'edit_replace_count',0)),
            (getattr(args,'second_edit_insert_position',0),getattr(args,'second_edit_replace_count',0))]
    if (second_program is not None or second_routine is not None or any(ranges[1])) and second_code is None:
        raise ValueError('Second edit target/range requires --second-edit-code')
    if any(ranges[0]) and (args.operation!='edits' or not apply_edits):raise ValueError('Custom ranges require supported-edit application')
    if (second_code is not None or reconnect) and (args.operation!='edits' or not apply_edits):
        raise ValueError('Sequential edits and reconnect require explicit supported-edit application')
    edit_codes=[edit_code]+([second_code] if second_code is not None else [])
    if (apply_edits or edit_code!='NOP();') and args.operation!='edits':raise ValueError('Supported edits belong to an edits case')
    edit_options = tuple(getattr(args, name, None) for name in ('edit_program', 'edit_routine', 'edit_import_option'))
    second_target=(second_program or edit_options[0] or 'MainProgram',second_routine or edit_options[1] or 'MainRoutine') if second_code is not None else None
    ranges=ranges[:len(edit_codes)]
    if args.operation != 'edits' and any(value is not None for value in edit_options):
        raise ValueError('Edit options belong to an edits diagnostic')
    source_hash = digest(source)
    initial = api(url, 'state')
    instance = validate_target(initial, args.path, source_hash)
    validate_idle(initial,allow_supported_edits=apply_edits)
    from tools import upload_content
    content_plan=upload_content.prepare(args.operation,upload_new,content_source,source,initial,allow_edited=edited_content)
    if export_uploaded_tags and not any(not t['name'].casefold().startswith('program:') for t in content_plan['tags']):
        raise ValueError('Uploaded controller-tag export requires at least one controller root')
    from tools import download_content
    download_content_plan=download_content.prepare(args.operation,save_download,download_content_source,source,initial)
    snapshot_baseline=upload_snapshot.prepare(source,baseline,initial) if snapshot_upload or verify_upload_baseline else None
    edit_baseline=upload_snapshot.prepare(source,baseline,initial) if args.operation=='edits' and connection_target is not None else None
    if args.operation=='modes':validate_mode_probe(initial)
    edits=[]
    if args.operation == 'edits':
        edits=edit_sequence(initial,edit_options[0] or 'MainProgram',edit_options[1] or 'MainRoutine',
                            edit_options[2] or 'AcceptEdits',edit_codes,apply=apply_edits,second_target=second_target,ranges=ranges)
    require_sdk_service()
    l5x_hash = initial['connectivity']['source_l5x_sha256']
    output = Path(args.output).resolve() if args.output else SOURCE.parent / '.local/native-probes' / (
        time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    copied = output / 'input.ACD'
    shutil.copyfile(baseline, copied)
    if digest(copied) != baseline_hash:
        raise ValueError('Source changed while creating the private copy')
    config = dict(Project=str(copied), SourceSha256=baseline_hash, CommunicationsPath=args.path,
                  Operation=args.operation, Tags=args.tag, TagReadType=tag_read_type)
    if args.operation in ('upload','edits'):config['ControllerSourceSha256']=source_hash
    if args.operation in ('modes','edits','upload','download'):config.update(BackendUrl=url,InstanceId=instance)
    config['ApplySupportedEdits']=apply_edits
    config['ReconnectEdits']=reconnect
    config.update(SaveEditedAcd=save_acd,PostEditTags=edit_tags)
    config['SaveUploadedAcd']=save_upload
    config['SaveDownloadedAcd']=save_download
    config['ExportDownloadedL5x']=download_content_plan is not None
    config['UploadNewProject']=upload_new
    config['ExportUploadedTags']=export_uploaded_tags
    config['VerifyUploadBaselineOnline']=verify_upload_baseline
    config['SnapshotUploadedAcd']=snapshot_upload
    if snapshot_upload:
        snapshot_input=output/'snapshot-input.ACD';shutil.copyfile(baseline,snapshot_input)
        if digest(snapshot_input)!=baseline_hash:raise ValueError('Snapshot baseline changed while copying')
        config['SnapshotBaseline']=str(snapshot_input)
    if content_plan is not None:config['UploadContent']=content_plan
    edit_files=[]
    for index,(payload,details) in enumerate(edits):
        edit_file=output/('nop-rung.L5X' if index==0 else 'second-rung.L5X')
        edit_file.write_bytes(payload);edit_files.append(edit_file)
        config['Edit' if index==0 else 'SecondEdit']=dict(details,File=str(edit_file),Sha256=digest(edit_file))
    (output / 'request.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    command = ['dotnet', 'build', str(SOURCE / 'tools/native_sdk_probe/NativeSdkProbe.csproj'),
               '-c', 'Release', '--nologo', '--output', str(output / 'bin'),
               '-p:BaseIntermediateOutputPath=' + str(output / 'obj') + os.sep]
    feed = args.sdk_feed or Path(os.environ.get('PUBLIC', r'C:\Users\Public')) / 'Documents/Studio 5000/Logix Designer SDK/dotnet'
    if args.sdk_feed and not Path(feed).is_dir():
        raise ValueError('SDK feed directory does not exist')
    if Path(feed).is_dir():
        command.append('-p:RestoreAdditionalProjectSources=' + str(Path(feed).resolve()))
    with (output / 'build.log').open('wb') as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120,
                       **background_options())
    # Build can take time: recheck identity, policies and both source hashes now.
    state = api(url, 'state')
    validate_target(state, args.path, source_hash, instance=instance, l5x_hash=l5x_hash)
    validate_idle(state,allow_supported_edits=apply_edits)
    if content_plan is not None and upload_content.prepare(args.operation,upload_new,content_source,source,state,allow_edited=edited_content)!=content_plan:
        raise ValueError('Uploaded-content source or current values changed before the native call')
    if snapshot_upload and (upload_snapshot.prepare(source,baseline,state)!=snapshot_baseline or digest(snapshot_input)!=baseline_hash):
        raise ValueError('Snapshot baseline or installation changed before the native call')
    if verify_upload_baseline and upload_snapshot.prepare(source,baseline,state)!=snapshot_baseline:
        raise ValueError('Upload baseline admission changed before the native call')
    if download_content_plan!=download_content.prepare(args.operation,save_download,download_content_source,source,state):
        raise ValueError('Downloaded-content source or current-value plan changed before the native call')
    if edit_baseline is not None and upload_snapshot.prepare(source,baseline,state)!=edit_baseline:
        raise ValueError('Saved edit baseline changed before the native call')
    if args.operation=='modes':validate_mode_probe(state)
    if args.operation == 'edits':
        current_edits=edit_sequence(state,edit_options[0] or 'MainProgram',edit_options[1] or 'MainRoutine',
                                   edit_options[2] or 'AcceptEdits',edit_codes,apply=apply_edits,second_target=second_target,ranges=ranges)
        if (current_edits!=edits or any(digest(file)!=config[key]['Sha256'] for file,key in zip(edit_files,('Edit','SecondEdit'))) or
                any(state.get(key) != initial.get(key) for key in ('routines', 'tasks', 'entry_routines','routine_edits'))):
            raise ValueError('Edit target or generated rung changed before the native call')
    if digest(source) != source_hash or digest(baseline)!=baseline_hash or digest(copied) != baseline_hash:
        raise ValueError('Source changed before the native call')
    if content_plan is not None:
        # Check the actual managed request decoder without opening an SDK
        # project. Python-only receipt tests cannot prove cross-language DTOs.
        check=subprocess.run([str(output/'bin/NativeSdkProbe.exe'),str(output/'request.json'),
            str(output/'unused-validation-report.json'),'--validate-request'],capture_output=True,text=True,
            check=True,timeout=15,**background_options())
        decoded=json.loads(check.stdout)
        if decoded!=dict(requestValidated=True,nativeProjectCalls=0,uploadTags=len(content_plan['tags']),uploadRoutines=len(content_plan['routines']),
                         uploadPrograms=len(content_plan['programs']),exportUploadedTags=export_uploaded_tags,verifyUploadBaselineOnline=verify_upload_baseline):
            raise ValueError('Managed uploaded-content request differs from the generated plan')
        (output/'request-validation.json').write_text(json.dumps(decoded,indent=2),encoding='utf8')
    before = api(url, 'connectivity-trace', {})
    (output / 'before-state.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    (output / 'before-trace.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    executable = output / 'bin/NativeSdkProbe.exe'
    summary = dict(operation=args.operation, version=state['app_version'], instance_id=instance,
                   source_sha256=source_hash, harness_sha256=digest(executable),
                   sdk_input_sha256=baseline_hash,separate_upload_target=args.operation=='upload' and baseline!=source,
                   separate_connection_target=args.operation=='connection' and baseline!=source,
                   separate_edit_target=args.operation=='edits' and baseline!=source,
                   harness_runtime_sha256=runtime_hashes(output / 'bin'),
                   harness_source_sha256={name: digest(SOURCE / 'tools/native_sdk_probe' / name)
                                          for name in ('Program.cs', 'NativeSdkProbe.csproj')},
                   status='incomplete', cleanup_confirmed=False,
                   native_controller_equivalence='NOT ASSESSED')
    if upload_new:summary.update(upload_new_project_requested=True,new_project_native_reopen_verified=False)
    if args.operation == 'edits':
        summary['edit_diagnostic'] = dict(import_option=config['Edit']['ImportOption'],
            xpath=config['Edit']['XPath'], insert_position=config['Edit']['InsertPosition'], replace_count=config['Edit']['ReplaceCount'],
            rung_sha256=config['Edit']['Sha256'], code=edit_code, active_edits_authorized=apply_edits,
            second_code=second_code,second_xpath=config.get('SecondEdit',{}).get('XPath'),
            second_range=ranges[1] if len(ranges)>1 else None,reconnect_after_each=reconnect,
            finalize_edits=config['Edit']['ImportOption']=='FinalizeEdits', assembly=False)
        summary['post_edit_tag_reads']=dict(type='DINT',tags=edit_tags)
        summary['save_edited_acd_requested']=save_acd
    model_fields = ('tags', 'scan', 'ms', 'changes', 'mode')
    if args.operation == 'edits':model_fields += ('routines', 'tasks', 'entry_routines', 'controller')
    elif args.operation in ('upload','download'):
        model_fields+=tuple(key for key in ('routines','tasks','entry_routines','controller') if key in state)
    summary['model_fields_checked']=list(model_fields)
    report = None;final=None;journal=None;journal_path=None
    try:
        if retain_trace:
            from tools.trace_journal import TraceJournal
            journal_path=output/'transfer-events.jsonl.gz'
            journal=TraceJournal(journal_path,lambda body:api(url,'connectivity-trace-read',body),instance,l5x_hash)
        with (output / 'sdk.log').open('wb') as log:
            command=[str(executable),str(output/'request.json'),str(output/'sdk-result.json')]
            timeout=300 if save_acd or save_upload or save_download or snapshot_upload else 120
            if journal is None:
                result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,**background_options())
            else:
                from tools.trace_journal import run_recorded
                result=run_recorded(command,journal=journal,stdout=log,timeout=timeout,background=background_options())
        report = json.loads((output / 'sdk-result.json').read_text(encoding='utf-8'))
        summary.update(status=report['status'], process_exit_code=result.returncode)
        summary['tag_read_type']=tag_read_type
        summary.update(sdk_server_faulted=report.get('serverFaulted'),
                       native_sdk_offline_confirmed=report.get('sdkOfflineConfirmed'),
                       native_sdk_diagnostic_codes=sdk_diagnostic_codes(report))
    except subprocess.TimeoutExpired:
        summary.update(status='incomplete',native_process_timed_out=True,
                       native_call_outcome='unknown',native_sdk_offline_confirmed=None,
                       sdk_server_faulted=None)
    finally:
        if journal is not None:
            try:summary['trace_recording']=journal.close()
            except Exception:summary['trace_recording']={'complete':False,'error':'trace_close_failed'}
        summary.update(input_evidence(source,source_hash,baseline,baseline_hash,copied,args.operation))
        if upload_new:summary['working_copy_changes_permitted']=False
        summary['sdk_working_copy_sha256']=(report or {}).get('workingProjectSha256')
        summary['working_copy_matches_sdk']=(summary['working_copy_sha256']==summary['sdk_working_copy_sha256']
                                            if summary['sdk_working_copy_sha256'] is not None else None)
        summary['sdk_controller_source_matches']=((report or {}).get('controllerSourceSha256')==source_hash
                                                if 'controllerSourceSha256' in (report or {}) else None)
        try:
            final = api(url, 'state')
            validate_target(final, args.path, source_hash, instance=instance, l5x_hash=l5x_hash)
            if args.operation=='modes':
                final=api(url,'controller-mode',{'mode':'Program'})
                validate_target(final,args.path,source_hash,instance=instance,l5x_hash=l5x_hash)
            (output / 'after-state.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
            trace = api(url, 'connectivity-trace', {})
            (output / 'trace.json').write_text(json.dumps(trace, indent=2), encoding='utf-8')
            summary['model_unchanged'] = all(state[key] == final[key] for key in model_fields)
            if args.operation=='modes':
                summary['mode_restored']=final.get('controller',{}).get('mode')=='Program' and not final['controller']['running']
                summary['scans_advanced']=final['scan']>state['scan']
            summary['native_verified_requests'] = (trace.get('counts', {}).get('native_verified', 0) -
                                                   before.get('counts', {}).get('native_verified', 0))
            summary['native_rejections'] = rejection_delta(before, trace)
            if args.operation in ('upload','download'):
                try:
                    from tools.analyze_native_transfer import analyze,read_json
                    checkpoints={name:read_json(output/(name+'-transfer-trace.json'))
                                 for name in ('before','after') if (output/(name+'-transfer-trace.json')).is_file()}
                    if len(checkpoints)==2:
                        summary['transfer_trace']=analyze(checkpoints['before'],checkpoints['after'],args.operation,report,journal=journal_path)
                    else:summary['transfer_trace']={'status':'checkpoints_unavailable','analysis_complete':False}
                except (OSError,ValueError,TypeError,KeyError):
                    # Diagnostic decoding must never suppress endpoint cleanup.
                    summary['transfer_trace']={'status':'analysis_failed','analysis_complete':False}
            if args.operation == 'edits' and report is not None:
                edit_traces = {name:json.loads((output / (name + '-edit-trace.json')).read_text(encoding='utf-8'))
                               for name in ('before', 'after') if (output / (name + '-edit-trace.json')).is_file()}
                summary['edit_trace'] = edit_trace_evidence(trace, report,
                    before_edit=edit_traces.get('before'), after_edit=edit_traces.get('after'))
                if second_code is not None:
                    second_traces={name:json.loads((output/(name+'-edit2-trace.json')).read_text(encoding='utf-8'))
                                   for name in ('before','after') if (output/(name+'-edit2-trace.json')).is_file()}
                    summary['second_edit_trace']=edit_trace_evidence(trace,report,before_edit=second_traces.get('before'),
                        after_edit=second_traces.get('after'),import_index=1)
            summary['target_rechecked'] = True
            final = wait_for_cleanup(url, args.path, source_hash, instance=instance, l5x_hash=l5x_hash,allow_supported_edits=apply_edits)
            summary['cleanup_confirmed'] = True
            (output / 'after-state.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
            summary['model_unchanged'] = all(state[key] == final[key] for key in model_fields)
            if args.operation == 'edits':summary['edit_payload_unchanged'] = all(digest(file)==config[key]['Sha256'] for file,key in zip(edit_files,('Edit','SecondEdit')))
        except Exception as error:
            summary.update(status='incomplete', target_rechecked=False, final_check_error=str(error))
        if apply_edits:summary['supported_edit_applied']=supported_sequence_effect(state,final,edits,edit_codes,output,reconnect=reconnect)
        if save_acd:
            summary['saved_edited_acd_verified']=saved_acd_effect(final,output,report.get('savedEditedProject') if report else None)
            summary['saved_edited_project']=report.get('savedEditedProject') if report else None
        if save_upload:
            summary['save_uploaded_acd_requested']=True
            summary['saved_uploaded_acd_verified']=saved_uploaded_acd_effect(output,report.get('savedUploadedProject') if report else None)
            summary['saved_uploaded_project']=report.get('savedUploadedProject') if report else None
            summary['uploaded_logic_equivalence']='NOT ASSESSED'
            summary['upload_result_persistence']='saved_and_reopened' if summary['saved_uploaded_acd_verified'] else 'failed'
        if content_plan is not None:
            summary['uploaded_content_requested']=True
            if verify_upload_baseline:
                summary['upload_baseline_online_requested']=True
                summary['upload_baseline_online_verified']=upload_snapshot.baseline_online_verified(report)
            summary['uploaded_content_verification']=upload_content.verify(output,content_plan,(report or {}).get('uploadedContent'))
            from logixlab.native_types import NativeTypes
            summary['uploaded_program_verification']=upload_content.verify_programs(output,content_plan,
                NativeTypes.from_acd(source,l5x_hash),(report or {}).get('uploadedContent'))
            if export_uploaded_tags:
                summary['uploaded_tag_definitions_requested']=True
                summary['uploaded_tag_definitions_verification']=upload_tag_definitions.verify(output,content_plan,
                    NativeTypes.from_acd(source,l5x_hash),(report or {}).get('uploadedContent'),upload_content.Project(content_source))
            if save_upload:
                from logixlab.native_types import NativeTypes
                try:verification=upload_content.verify_saved(output,content_plan,NativeTypes.from_acd(source,l5x_hash),(report or {}).get('savedUploadedProject'))
                except Exception:verification={'verified':False,'serialized_values_verified':False,'serialized_logic_verified':False}
                summary['serialized_uploaded_content_verification']=verification
                summary['uploaded_logic_equivalence']='verified' if verification['verified'] else 'failed'
        if save_download:
            summary['save_downloaded_acd_requested']=True
            summary['saved_downloaded_acd_verified']=saved_downloaded_acd_effect(final,source,output,(report or {}).get('savedDownloadedProject'))
            summary['saved_downloaded_project']=(report or {}).get('savedDownloadedProject')
            summary['download_result_persistence']='saved_and_reopened_online' if summary['saved_downloaded_acd_verified'] else 'failed'
            summary['emulator_installation_persistence']='memory_only'
            if download_content_plan is not None:
                from logixlab.native_types import NativeTypes
                summary['downloaded_content_verification']=download_content.verify(output,download_content_plan,
                    NativeTypes.from_acd(source,l5x_hash),(report or {}).get('savedDownloadedProject'))
        if snapshot_upload:
            from logixlab.native_types import NativeTypes
            summary['snapshot_uploaded_acd_requested']=True
            summary['uploaded_snapshot_verification']=upload_snapshot.verify(output,content_plan,
                NativeTypes.from_acd(source,l5x_hash),baseline,(report or {}).get('savedUploadedSnapshot'))
            try:summary['snapshot_baseline_preserved']=digest(snapshot_input)==baseline_hash
            except OSError:summary['snapshot_baseline_preserved']=False
            summary['upload_result_persistence']='source_equivalent_value_snapshot' if summary['uploaded_snapshot_verification']['verified'] else 'failed'
        model_ok=(summary.get('mode_restored') and summary.get('scans_advanced')) if args.operation=='modes' else summary.get('supported_edit_applied') if apply_edits else summary.get('model_unchanged') is not False
        if upload_new:
            summary['new_project_artifact_matches_receipt']=new_upload_artifact(output,(report or {}).get('newProjectUpload'))
        if (not summary['source_unchanged'] or not summary['working_copy_present'] or not model_ok or summary.get('edit_payload_unchanged') is False
                or upload_new and summary.get('working_copy_unchanged') is not True
                or upload_new and report is not None and not summary.get('new_project_artifact_matches_receipt')
                or save_acd and not summary.get('saved_edited_acd_verified')
                or save_download and not summary.get('saved_downloaded_acd_verified')
                or content_plan is not None and not summary['uploaded_content_verification']['verified']
                or content_plan is not None and not summary['uploaded_program_verification']['verified']
                or export_uploaded_tags and not summary['uploaded_tag_definitions_verification']['verified']
                or verify_upload_baseline and not summary['upload_baseline_online_verified']
                or content_plan is not None and save_upload and not summary['serialized_uploaded_content_verification']['verified']
                or save_upload and not summary.get('saved_uploaded_acd_verified')):
            summary['status'] = 'failed'
        if snapshot_upload and (not summary['uploaded_snapshot_verification']['verified'] or not summary['snapshot_baseline_preserved']):
            summary['status']='failed'
        if download_content_plan is not None and not summary['downloaded_content_verification']['verified']:
            summary['status']='failed'
        if args.operation=='upload' and summary['status']=='succeeded' and (
                summary['working_copy_matches_sdk'] is not True or summary['sdk_controller_source_matches'] is not True):
            summary['status']='failed'
        (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps({'report': str(output / 'summary.json'), **summary}, indent=2))
    return 0 if summary['status'] == 'succeeded' and summary.get('process_exit_code') == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Original ACD, preserved and checked by SHA-256')
    parser.add_argument('--upload-target',help='Upload only: preserved offline merge baseline, copied into the new private output directory; --project still pins the emulator source')
    parser.add_argument('--connection-target',help='Connection or edits: preserved saved ACD copy; edits require an unchanged source-equivalent saved-download identity; --project still pins the emulator source')
    parser.add_argument('--snapshot-uploaded-acd',action='store_true',help='Upload only: save current verified values into a fresh matching-baseline ACD, requiring unchanged source, --upload-target and --verify-uploaded-content; reopen and verify Online')
    parser.add_argument('--verify-uploaded-tag-definitions',action='store_true',help='With --verify-uploaded-content: independently export and verify every controller tag definition/current value after native upload')
    parser.add_argument('--verify-upload-baseline-online',action='store_true',help='Matching source-equivalent saved-download target only: verify Online/Offline before upload; requires upload-target and verify-uploaded-content; does not save or extend the ordinary timeout')
    parser.add_argument('--retain-transfer-trace',action='store_true',help='Upload/download only: record bounded compressed cursor pages privately while the single native call runs')
    parser.add_argument('--upload-new-project',action='store_true',help='Upload only: use UploadToNewProjectAsync to create uploaded.ACD without opening a merge baseline; cannot combine with upload-target or save-uploaded-acd')
    parser.add_argument('--url', required=True, help='Running local LogixLab HTTP URL')
    parser.add_argument('--path', required=True, help=r'Linx driver\IPv4\Backplane\0, matching the emulator')
    parser.add_argument('--operation', choices=('connection', 'upload', 'download', 'modes', 'edits'), default='connection',
                        help='modes cycles Run/Program; edits defaults to a NOP diagnostic with editing disabled')
    parser.add_argument('--edit-program', help='edits only: loaded program; default MainProgram')
    parser.add_argument('--edit-routine', help='edits only: loaded RLL routine; default MainRoutine')
    parser.add_argument('--edit-import-option', choices=('LeaveEdits', 'AcceptEdits', 'FinalizeEdits'),
                        help='edits only: defaults to AcceptEdits; LeaveEdits is a local pending-edit comparison; FinalizeEdits requires explicit supported Program-mode application')
    parser.add_argument('--apply-supported-edits',action='store_true',help='Require enabled Program-mode RLL replacement and verify the applied routine')
    parser.add_argument('--edit-code',help='One neutral-text rung for an explicit supported-edit case; default NOP();')
    parser.add_argument('--second-edit-code',help='Explicit supported edits only: insert a second rung using the same SDK project')
    parser.add_argument('--edit-insert-position',type=int,default=0,help='Zero-based insert position; explicit supported edits only')
    parser.add_argument('--edit-replace-count',type=int,default=0,help='Existing rungs replaced by the generated rung; explicit supported edits only')
    parser.add_argument('--second-edit-program',help='Second edit program; defaults to the first edit target')
    parser.add_argument('--second-edit-routine',help='Second edit routine; defaults to the first edit target')
    parser.add_argument('--second-edit-insert-position',type=int,default=0)
    parser.add_argument('--second-edit-replace-count',type=int,default=0)
    parser.add_argument('--reconnect-edits',action='store_true',help='Explicit supported edits only: go Offline/Online after each checked insert')
    parser.add_argument('--post-edit-tag',action='append',default=[],help='Explicit supported edits only: diagnose a DINT SDK read after the imports, before Offline; may repeat up to eight times')
    parser.add_argument('--save-edited-acd',action='store_true',help='Explicit supported edits only: import exported L5X through the SDK, save a new edited.ACD and reopen it offline')
    parser.add_argument('--save-uploaded-acd',action='store_true',help='Successful upload only: save a new uploaded.ACD, reopen it offline and export uploaded.L5X for separate content comparison')
    parser.add_argument('--verify-uploaded-content',metavar='SOURCE.L5X',help='Existing-project upload only: compare native offline tag bytes and independently exported routines with this exact source and current emulator values')
    parser.add_argument('--allow-edited-upload-content',action='store_true',help='With verify-uploaded-content: use complete retained native RLL edits as expected logic; pin runtime revision/hash; no upload save/snapshot')
    parser.add_argument('--save-downloaded-acd',action='store_true',help='Successful source-equivalent download only: save a new downloaded.ACD, reopen it and verify Go Online; emulator installation remains memory-only')
    parser.add_argument('--verify-downloaded-content',metavar='SOURCE.L5X',help='Download with --save-downloaded-acd only: independently verify the reopened full Controller values, logic, Programs, types and Task settings')
    parser.add_argument('--tag', action='append', default=[], help='Optional SDK tag XPath; may repeat')
    parser.add_argument('--tag-read-type',choices=('BYTE_ARRAY','BOOL','DINT','REAL'),default='BYTE_ARRAY',
                        help='Use the generic byte-array API or a typed SDK getter for every selected tag')
    parser.add_argument('--output', help='New private output directory; default .local/native-probes/<unique run>')
    parser.add_argument('--sdk-feed', help='Optional installed SDK NuGet feed directory')
    args = parser.parse_args()
    try:
        return run(args)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
