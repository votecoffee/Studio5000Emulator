"""Native SDK acceptance against an already running LogixLab research endpoint.

The optional installed SDK runs on a private ACD copy. Download attempts require
disabled project transfer; temporary programming coordination is permitted.
Reports contain private project metadata and default to ignored .local storage.
Only explicit --operation modes changes Run/Program and executes scans. It
restores Program; resulting tag values and scan history are retained. Other
operations never request mode changes. The edits diagnostic imports a generated
NOP rung on a private copy with LeaveEdits or AcceptEdits. It requires advertised
online-edit authority to be disabled and never finalizes or assembles edits.
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


def edit_request(state, program, routine, option):
    """Create one NOP insert for a loaded, ordinary RLL routine, never arbitrary XML."""
    if option not in ('LeaveEdits', 'AcceptEdits'):
        raise ValueError('Edit diagnostics allow LeaveEdits or AcceptEdits; never FinalizeEdits')
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
    if state.get('connectivity', {}).get('native_programming_lease', {}).get('online_edits') is not False:
        raise ValueError('Edit diagnostic requires disabled controller online-edit authority')
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
    ET.SubElement(rung, 'Text').text = 'NOP();'
    payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    return payload, dict(XPath=f"Controller/Programs/Program[@Name='{program}']/Routines/Routine[@Name='{routine}']",
                         InsertPosition=0, ReplaceCount=0, ImportOption=option)


def rejection_delta(before, after):
    """Report newly rejected structural requests without mistaking earlier probes for this one."""
    fields = ('generation', 'service', 'class_id', 'instance', 'attribute', 'program_instance',
              'io_map_instance', 'controller_instance', 'symbolic', 'status', 'reason')
    previous = {tuple(row.get(field) for field in fields): row.get('count', 0)
                for row in before.get('native_rejections', [])}
    rows = []
    for row in after.get('native_rejections', []):
        count = row.get('count', 0) - previous.get(tuple(row.get(field) for field in fields), 0)
        if count > 0:
            rows.append({**row, 'probe_count': count})
    return sorted(rows, key=lambda row: row.get('last_seen', 0))


def edit_trace_evidence(trace, report, *, before_edit=None, after_edit=None):
    """Use emulator trace checkpoints around import; SDK and guest clocks may differ."""
    steps = [item for item in report.get('steps', [])
             if item.get('method', '').startswith('PartialImportRungsFromXmlFileAsync:')]
    if len(steps) != 1:return {'status':'import_not_reached', 'failed_requests':[], 'first_failed_request':None}
    step = steps[0]
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
                    io_map_instance=path.io_map_instance, controller_instance=path.controller_instance,
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
                    any(type(check.get(f)) is not int or check[f]!=0 for f in
                        ('types_matched','members_matched','types_unavailable')) or
                    any(check.get(f) is not False for f in ('member_locations_verified','storage_mapping_supported',
                        'signature_verified','definitions_exposed','execution_supported'))):
                raise ValueError('Probe requires empty source type verification')
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


def validate_idle(state):
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
            lease.get('controller_mode_changes') is not False or lease.get('online_edits') is not False or
            lease.get('tag_write_authority') is not False):
        raise ValueError('Probe requires an idle endpoint, free uninhibited lease and disabled programming authority')


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


def wait_for_cleanup(url, path, source_hash, *, instance, l5x_hash, timeout=40):
    """Allow the endpoint's 30-second idle transport close after SDK Dispose.

    Every poll still requires the same bound source/instance; success requires
    zero clients and a free, uninhibited lease with empty temporary state.
    """
    deadline = time.monotonic() + timeout
    while True:
        state = api(url, 'state')
        validate_target(state, path, source_hash, instance=instance, l5x_hash=l5x_hash)
        try:
            validate_idle(state)
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
    tag_read_type=validate_tag_read_type(args.operation,args.tag,getattr(args,'tag_read_type','BYTE_ARRAY'))
    edit_options = tuple(getattr(args, name, None) for name in ('edit_program', 'edit_routine', 'edit_import_option'))
    if args.operation != 'edits' and any(value is not None for value in edit_options):
        raise ValueError('Edit options belong to an edits diagnostic')
    source_hash = digest(source)
    initial = api(url, 'state')
    instance = validate_target(initial, args.path, source_hash)
    validate_idle(initial)
    if args.operation=='modes':validate_mode_probe(initial)
    edit_payload = edit_config = None
    if args.operation == 'edits':
        edit_payload, edit_config = edit_request(initial, edit_options[0] or 'MainProgram',
                                                edit_options[1] or 'MainRoutine', edit_options[2] or 'AcceptEdits')
    require_sdk_service()
    l5x_hash = initial['connectivity']['source_l5x_sha256']
    output = Path(args.output).resolve() if args.output else SOURCE.parent / '.local/native-probes' / (
        time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    copied = output / 'input.ACD'
    shutil.copyfile(source, copied)
    if digest(copied) != source_hash:
        raise ValueError('Source changed while creating the private copy')
    config = dict(Project=str(copied), SourceSha256=source_hash, CommunicationsPath=args.path,
                  Operation=args.operation, Tags=args.tag, TagReadType=tag_read_type)
    if args.operation in ('modes', 'edits'):config.update(BackendUrl=url,InstanceId=instance)
    if edit_payload is not None:
        edit_file = output / 'nop-rung.L5X'
        edit_file.write_bytes(edit_payload)
        config['Edit'] = dict(edit_config, File=str(edit_file), Sha256=digest(edit_file))
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
    validate_idle(state)
    if args.operation=='modes':validate_mode_probe(state)
    if args.operation == 'edits':
        payload, details = edit_request(state, edit_options[0] or 'MainProgram',
                                        edit_options[1] or 'MainRoutine', edit_options[2] or 'AcceptEdits')
        if (payload != edit_payload or details != edit_config or digest(edit_file) != config['Edit']['Sha256'] or
                any(state.get(key) != initial.get(key) for key in ('routines', 'tasks', 'entry_routines'))):
            raise ValueError('Edit target or generated rung changed before the native call')
    if digest(source) != source_hash or digest(copied) != source_hash:
        raise ValueError('Source changed before the native call')
    before = api(url, 'connectivity-trace', {})
    (output / 'before-state.json').write_text(json.dumps(state, indent=2), encoding='utf-8')
    (output / 'before-trace.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    executable = output / 'bin/NativeSdkProbe.exe'
    summary = dict(operation=args.operation, version=state['app_version'], instance_id=instance,
                   source_sha256=source_hash, harness_sha256=digest(executable),
                   harness_runtime_sha256=runtime_hashes(output / 'bin'),
                   harness_source_sha256={name: digest(SOURCE / 'tools/native_sdk_probe' / name)
                                          for name in ('Program.cs', 'NativeSdkProbe.csproj')},
                   status='incomplete', cleanup_confirmed=False,
                   native_controller_equivalence='NOT ASSESSED')
    if args.operation == 'edits':
        summary['edit_diagnostic'] = dict(import_option=config['Edit']['ImportOption'],
            xpath=config['Edit']['XPath'], insert_position=0, replace_count=0,
            rung_sha256=config['Edit']['Sha256'], code='NOP();', active_edits_authorized=False,
            finalize_edits=False, assembly=False)
    model_fields = ('tags', 'scan', 'ms', 'changes', 'mode')
    if args.operation == 'edits':model_fields += ('routines', 'tasks', 'entry_routines', 'controller')
    report = None
    try:
        with (output / 'sdk.log').open('wb') as log:
            result = subprocess.run([str(executable), str(output / 'request.json'), str(output / 'sdk-result.json')],
                                    stdout=log, stderr=subprocess.STDOUT, timeout=120, **background_options())
        report = json.loads((output / 'sdk-result.json').read_text(encoding='utf-8'))
        summary.update(status=report['status'], process_exit_code=result.returncode)
        summary['tag_read_type']=tag_read_type
        summary.update(sdk_server_faulted=report.get('serverFaulted'),
                       native_sdk_offline_confirmed=report.get('sdkOfflineConfirmed'),
                       native_sdk_diagnostic_codes=sdk_diagnostic_codes(report))
    finally:
        summary['source_unchanged'] = digest(source) == source_hash and digest(copied) == source_hash
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
            if args.operation == 'edits' and report is not None:
                edit_traces = {name:json.loads((output / (name + '-edit-trace.json')).read_text(encoding='utf-8'))
                               for name in ('before', 'after') if (output / (name + '-edit-trace.json')).is_file()}
                summary['edit_trace'] = edit_trace_evidence(trace, report,
                    before_edit=edit_traces.get('before'), after_edit=edit_traces.get('after'))
            summary['target_rechecked'] = True
            final = wait_for_cleanup(url, args.path, source_hash, instance=instance, l5x_hash=l5x_hash)
            summary['cleanup_confirmed'] = True
            (output / 'after-state.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
            summary['model_unchanged'] = all(state[key] == final[key] for key in model_fields)
            if args.operation == 'edits':summary['edit_payload_unchanged'] = digest(edit_file) == config['Edit']['Sha256']
        except Exception as error:
            summary.update(status='incomplete', target_rechecked=False, final_check_error=str(error))
        model_ok=(summary.get('mode_restored') and summary.get('scans_advanced')) if args.operation=='modes' else summary.get('model_unchanged') is not False
        if not summary['source_unchanged'] or not model_ok or summary.get('edit_payload_unchanged') is False:
            summary['status'] = 'failed'
        (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps({'report': str(output / 'summary.json'), **summary}, indent=2))
    return 0 if summary['status'] == 'succeeded' and summary.get('process_exit_code') == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Original ACD, preserved and checked by SHA-256')
    parser.add_argument('--url', required=True, help='Running local LogixLab HTTP URL')
    parser.add_argument('--path', required=True, help=r'Linx driver\IPv4\Backplane\0, matching the emulator')
    parser.add_argument('--operation', choices=('connection', 'upload', 'download', 'modes', 'edits'), default='connection',
                        help='modes runs logic then restores Program; edits diagnoses a generated NOP import with editing disabled')
    parser.add_argument('--edit-program', help='edits only: loaded program; default MainProgram')
    parser.add_argument('--edit-routine', help='edits only: loaded RLL routine; default MainRoutine')
    parser.add_argument('--edit-import-option', choices=('LeaveEdits', 'AcceptEdits'),
                        help='edits only: defaults to AcceptEdits to test the controller request; LeaveEdits is a local pending-edit comparison')
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
