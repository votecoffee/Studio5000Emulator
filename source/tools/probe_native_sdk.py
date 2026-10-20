"""Native SDK acceptance against an already running LogixLab research endpoint.

The optional installed SDK runs on a private ACD copy. Download attempts require
disabled project transfer; temporary programming coordination is permitted.
Reports contain private project metadata and default to ignored .local storage.
This tool never edits, changes controller mode or manages Windows services.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit
import uuid

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from tools.vmware_appliance import api, background_options


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def runtime_hashes(folder):
    # A .NET apphost EXE can stay identical while its managed DLL changes.
    # Record the executable code and runtime configuration, not just the host.
    return {path.relative_to(folder).as_posix(): digest(path)
            for path in sorted(Path(folder).rglob('*'))
            if path.is_file() and path.suffix.lower() in ('.exe', '.dll', '.json')}


def validate_url(url):
    value = urlsplit(url)
    if (value.scheme != 'http' or value.hostname != '127.0.0.1' or
            value.username is not None or value.password is not None or
            value.path or value.query or value.fragment or not value.port):
        raise ValueError('Use the local LogixLab URL: http://127.0.0.1:<port>')
    return url


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
    if operation not in ('connection', 'upload', 'download'):
        raise ValueError('Expected connection, upload or download')
    if operation != 'connection' and tags:
        raise ValueError('Tag reads belong to a connection probe')
    if len(tags) > 32 or any(not tag or len(tag) > 1024 for tag in tags):
        raise ValueError('At most 32 nonempty tag XPaths of at most 1024 characters')


def validate_staging(lease):
    """Older endpoints may omit stages; advertised stages must be empty."""
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
    if ('preparation_state' in lease and lease['preparation_state']!='idle' or
            'preparation_status' in lease and (type(lease['preparation_status']) is not int or lease['preparation_status']!=0)):
        raise ValueError('Probe requires idle programming preparation')


def validate_idle(state):
    """Do not share a programming test with an existing native connection."""
    cip = state.get('connectivity', {})
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


def wait_for_cleanup(url, path, source_hash, *, instance, l5x_hash, timeout=8):
    """SDK Dispose may return before the TCP handler releases its lease."""
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
    source_hash = digest(source)
    initial = api(url, 'state')
    instance = validate_target(initial, args.path, source_hash)
    validate_idle(initial)
    l5x_hash = initial['connectivity']['source_l5x_sha256']
    output = Path(args.output).resolve() if args.output else SOURCE.parent / '.local/native-probes' / (
        time.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    copied = output / 'input.ACD'
    shutil.copyfile(source, copied)
    if digest(copied) != source_hash:
        raise ValueError('Source changed while creating the private copy')
    config = dict(Project=str(copied), SourceSha256=source_hash, CommunicationsPath=args.path,
                  Operation=args.operation, Tags=args.tag)
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
    try:
        with (output / 'sdk.log').open('wb') as log:
            result = subprocess.run([str(executable), str(output / 'request.json'), str(output / 'sdk-result.json')],
                                    stdout=log, stderr=subprocess.STDOUT, timeout=120, **background_options())
        report = json.loads((output / 'sdk-result.json').read_text(encoding='utf-8'))
        summary.update(status=report['status'], process_exit_code=result.returncode)
    finally:
        summary['source_unchanged'] = digest(source) == source_hash and digest(copied) == source_hash
        try:
            final = api(url, 'state')
            validate_target(final, args.path, source_hash, instance=instance, l5x_hash=l5x_hash)
            (output / 'after-state.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
            trace = api(url, 'connectivity-trace', {})
            (output / 'trace.json').write_text(json.dumps(trace, indent=2), encoding='utf-8')
            summary['model_unchanged'] = all(state[key] == final[key] for key in ('tags', 'scan', 'ms', 'changes', 'mode'))
            summary['native_verified_requests'] = (trace.get('counts', {}).get('native_verified', 0) -
                                                   before.get('counts', {}).get('native_verified', 0))
            summary['target_rechecked'] = True
            final = wait_for_cleanup(url, args.path, source_hash, instance=instance, l5x_hash=l5x_hash)
            summary['cleanup_confirmed'] = True
            (output / 'after-state.json').write_text(json.dumps(final, indent=2), encoding='utf-8')
            summary['model_unchanged'] = all(state[key] == final[key] for key in ('tags', 'scan', 'ms', 'changes', 'mode'))
        except Exception as error:
            summary.update(status='incomplete', target_rechecked=False, final_check_error=str(error))
        if not summary['source_unchanged'] or summary.get('model_unchanged') is False:
            summary['status'] = 'failed'
        (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps({'report': str(output / 'summary.json'), **summary}, indent=2))
    return 0 if summary['status'] == 'succeeded' and summary.get('process_exit_code') == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Original ACD, preserved and checked by SHA-256')
    parser.add_argument('--url', required=True, help='Running local LogixLab HTTP URL')
    parser.add_argument('--path', required=True, help=r'Linx driver\IPv4\Backplane\0, matching the emulator')
    parser.add_argument('--operation', choices=('connection', 'upload', 'download'), default='connection')
    parser.add_argument('--tag', action='append', default=[], help='Optional SDK tag XPath; may repeat')
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
