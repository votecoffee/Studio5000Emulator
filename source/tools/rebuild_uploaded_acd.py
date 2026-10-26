"""Rebuild a verified native upload into an Offline ACD using bound source metadata.

This separate, offline-only step consumes retained successful upload evidence.
Program import invalidates download correlation: the result requires a download.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from logixlab.model import ModelError, Project
from logixlab.native_types import NativeTypes
from logixlab.native_project import NativeProjectIdentity
from tools import upload_content
from tools.probe_native_sdk import background_options, digest, require_sdk_service


def source_schema(project):
    """Preserve task order/settings and explicit UDT member semantics, not XML formatting."""
    from logixlab.model import dimensions
    types = {}
    for name, definition in project.udts.items():
        members = []
        for member in definition.findall('./Members/Member'):
            members.append(dict(name=member.get('Name'),dtype=member.get('DataType'),
                dimensions=dimensions(member.get('Dimension','0')),hidden=member.get('Hidden','false'),
                target=member.get('Target',''),bit=member.get('BitNumber',''),access=member.get('ExternalAccess','Read/Write')))
        types[name] = dict(family=definition.get('Family','NoFamily'),
                          tag_class=definition.get('Class','User'),members=members)
    return json.loads(json.dumps(dict(tasks=project.tasks,types=types)))


def read_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 2 <= path.stat().st_size <= 32_000_000:
        raise ValueError('A bounded regular evidence file is required')
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('An evidence object is required')
    return value


def prepare(source, l5x, upload):
    """Revalidate actual native artifacts and source; no live endpoint is contacted."""
    source, l5x, upload = Path(source), Path(l5x), Path(upload)
    if (source.is_symlink() or l5x.is_symlink() or source.suffix.lower() != '.acd'
            or l5x.suffix.lower() != '.l5x' or not 8 <= source.stat().st_size <= 100_000_000
            or not 8 <= l5x.stat().st_size <= upload_content.MAX_XML):
        raise ValueError('Select bounded original ACD and complete source L5X files')
    summary = read_json(upload / 'summary.json')
    request = read_json(upload / 'request.json')
    native = read_json(upload / 'sdk-result.json')
    before = read_json(upload / 'before-state.json')
    after = read_json(upload / 'after-state.json')
    installed = before.get('connectivity', {}).get('native_download') or {}
    if (summary.get('status') != 'succeeded' or summary.get('native_sdk_offline_confirmed') is not True
            or summary.get('cleanup_confirmed') is not True or summary.get('sdk_server_faulted') is not False
            or summary.get('source_unchanged') is not True or summary.get('model_unchanged') is not True
            or request.get('Operation') != 'upload' or request.get('UploadNewProject') is not False
            or request.get('ControllerSourceSha256') != digest(source)
            or installed.get('installed') is not True or installed.get('source_equivalent') is not True):
        raise ValueError('Rebuild requires a successful cleaned-up source-equivalent existing-project upload')
    for key in ('instance_id', 'tags', 'scan', 'ms', 'controller', 'routines', 'tasks', 'entry_routines', 'routine_edits'):
        if before.get(key) != after.get(key):
            raise ValueError('Upload did not preserve its pinned model')
    project = Project(l5x)
    types = NativeTypes.from_acd(source, project.sha256)
    expected = json.loads(json.dumps(upload_content.plan(project, types, before)))
    if request.get('UploadContent') != expected:
        raise ValueError('Recorded upload plan differs from the bound source and current-value evidence')
    receipt = native.get('uploadedContent')
    if (not upload_content.verify(upload, expected, receipt)['verified']
            or not upload_content.verify_programs(upload, expected, types, receipt)['verified']):
        raise ValueError('Native uploaded values, routines or Program packages failed independent validation')
    if not expected['programs']:
        raise ValueError('Program rebuild requires at least one complete ordinary Program')
    if not project.task_configuration.source_complete:
        raise ValueError('Program rebuild requires complete ordinary Task schedules')
    # Overwrite imports move each Program to the end of its Task schedule.
    # Import in original scheduled order, then the original unscheduled order.
    by_name = {p['name']:p for p in expected['programs']}
    order = [name for task in project.tasks for name in task['programs']]
    if len(set(order)) != len(order) or any(name not in by_name for name in order):
        raise ValueError('Program scheduling is ambiguous')
    order.extend(name for name in project.programs if name not in order)
    packages = [dict(name=p['name'], xpath=p['xpath'], fileName=p['fileName'],
                     sha256=digest(upload / p['fileName'])) for p in (by_name[name] for name in order)]
    expected['rebuildSourceSchema'] = source_schema(project)
    manifest = dict(sourceSha256=digest(source), sourceL5xSha256=project.sha256,
                    programs=packages, tags=expected['tags'])
    return manifest, expected, types


def verify(folder, expected, types, receipt):
    """Require actual native reopen, complete saved values/logic and revoked correlation."""
    result = dict(verified=False,online_verified=False,requires_download=True)
    try:
        if (not isinstance(receipt, dict) or receipt.get('status') != 'succeeded'
                or any(receipt.get(k) is not True for k in ('offlineOnly', 'nativeAcdReopened', 'cleanupConfirmed'))
                or receipt.get('directUploadedProjectSave') is not False):
            return result
        folder = Path(folder)
        for name, key, bound in [('rebuilt.ACD', 'acdSha256', 100_000_000), ('rebuilt.L5X', 'l5xSha256', 16_000_000)]:
            p = folder / name
            if p.is_symlink() or not p.is_file() or not 8 <= p.stat().st_size <= bound or digest(p) != receipt.get(key):
                return result
        if NativeProjectIdentity.from_acd(folder / 'rebuilt.ACD', expected['sourceL5xSha256']).download_uid != 0:
            return result
        content = upload_content.verify_serialized(folder / 'rebuilt.L5X', expected, types)
        result['content'] = content
        schema_matches = source_schema(Project(folder / 'rebuilt.L5X')) == expected['rebuildSourceSchema']
        result['source_schema_preserved'] = schema_matches
        if content['verified'] and schema_matches:
            result.update(verified=True,native_acd_reopened=True,download_correlation_cleared=True,
                          profile='Native uploaded Programs and current values with original Controller metadata')
        return result
    except (OSError, ValueError, ModelError, TypeError, KeyError, AttributeError):
        return result


def run(args):
    if sys.platform != 'win32':
        raise ValueError('The offline native rebuild requires Windows and the Logix Designer SDK')
    source, l5x, upload = Path(args.project).absolute(), Path(args.source).absolute(), Path(args.upload_result).absolute()
    manifest, expected, types = prepare(source, l5x, upload)
    output = Path(args.output).absolute()
    output.mkdir(parents=True, exist_ok=False)
    copied = output / 'input.ACD'
    shutil.copyfile(source, copied)
    for p in manifest['programs']:
        shutil.copyfile(upload / p['fileName'], output / p['fileName'])
    config = dict(manifest, project=str(copied))
    request = output / 'rebuild-request.json'
    request.write_text(json.dumps(config, indent=2), encoding='utf8')
    summary = dict(status='failed', offline_only=True, online_verified=False, requires_download=True,
                   physical_controller_contact_initiated=False)
    try:
        require_sdk_service()
        command = ['dotnet', 'build', str(SOURCE / 'tools/native_uploaded_rebuild/NativeUploadedRebuild.csproj'),
                   '-c', 'Release', '--nologo', '--output', str(output / 'bin'),
                   '-p:BaseIntermediateOutputPath=' + str(output / 'obj') + os.sep]
        feed = Path(args.sdk_feed) if args.sdk_feed else Path(os.environ.get('PUBLIC', r'C:\Users\Public')) / 'Documents/Studio 5000/Logix Designer SDK/dotnet'
        if args.sdk_feed and not feed.is_dir():
            raise ValueError('SDK feed directory does not exist')
        if feed.is_dir():
            command.append('-p:RestoreAdditionalProjectSources=' + str(feed.resolve()))
        with (output / 'build.log').open('xb') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120, **background_options())
        if prepare(source, l5x, upload)[0] != manifest or digest(copied) != manifest['sourceSha256']:
            raise ValueError('Source or uploaded artifacts changed while building')
        for p in manifest['programs']:
            if digest(output / p['fileName']) != p['sha256']:
                raise ValueError('Copied Program changed')
        executable = output / 'bin/NativeUploadedRebuild.exe'
        subprocess.run([str(executable), str(request), '--validate-request'], check=True,
                       capture_output=True, timeout=15, **background_options())
        require_sdk_service()
        with (output / 'sdk.log').open('xb') as log:
            subprocess.run([str(executable), str(request)], stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=300, **background_options())
        receipt = read_json(output / 'native-result.json')
        summary['verification'] = verify(output, expected, types, receipt)
        require_sdk_service()
        if not summary['verification']['verified']:
            raise ValueError('Saved rebuilt ACD failed independent validation')
        if prepare(source, l5x, upload)[0] != manifest or digest(copied) != manifest['sourceSha256']:
            raise ValueError('Original inputs changed during native rebuild')
        summary.update(status='succeeded', source_unchanged=True, native_offline_cleanup=True,
                       source_acd_sha256=manifest['sourceSha256'], rebuilt_acd_sha256=digest(output / 'rebuilt.ACD'))
    except subprocess.TimeoutExpired:
        summary.update(status='unknown', error='Native/build deadline expired; no automatic retry')
    except (OSError, ValueError, ModelError, subprocess.SubprocessError) as error:
        summary['error'] = str(error)
    finally:
        (output / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf8')
    print(json.dumps(summary, indent=2))
    return 0 if summary['status'] == 'succeeded' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Original bound source ACD; preserved')
    parser.add_argument('--source', required=True, help='Exact complete source Controller L5X')
    parser.add_argument('--upload-result', required=True, help='Successful probe folder with complete native upload content checks')
    parser.add_argument('--output', required=True, help='New private output directory')
    parser.add_argument('--sdk-feed')
    args = parser.parse_args()
    try:
        return run(args)
    except (OSError, ValueError, ModelError) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
