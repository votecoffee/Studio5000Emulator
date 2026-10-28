"""Serial native upload and checked Offline ACD rebuild on a bound v35 source.

This saves uploaded Program packages and current values using the original
Controller metadata. It does not save the SDK's reconstructed upload object.
The resulting ACD requires a download; inputs and all stage evidence survive.
"""
import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

SOURCE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SOURCE))
from logixlab.model import ModelError
from tools import probe_native_sdk as probe, rebuild_uploaded_acd as rebuild, upload_content, upload_snapshot

MODEL_FIELDS=('instance_id','tags','scan','ms','mode','selected','changes','controller','routines','tasks','entry_routines','routine_edits')


def admit(args):
    """Check source, endpoint and the supported rebuild profile before any SDK call."""
    if sys.platform!='win32':raise ValueError('Native upload-to-ACD requires Windows and the Logix Designer SDK')
    url=probe.validate_url(args.url)
    paths=[]
    for name,suffix,bound in ((args.project,'.acd',100_000_000),(args.source,'.l5x',upload_content.MAX_XML)):
        p=Path(name).absolute()
        if p.is_symlink() or not p.is_file() or p.suffix.lower()!=suffix or not 8<=p.stat().st_size<=bound:
            raise ValueError('Select bounded regular source ACD and complete Controller L5X files')
        paths.append(p.resolve(strict=True))
    source,l5x=paths
    baseline=probe.upload_input(source,'upload',args.upload_target)
    before=probe.api(url,'state')
    probe.validate_target(before,args.path,probe.digest(source))
    probe.validate_idle(before)
    installed=before['connectivity'].get('native_download') or {}
    if installed.get('installed') is not True or installed.get('source_equivalent') is not True:
        raise ValueError('Upload-to-ACD requires an unchanged source-equivalent installed download')
    plan=upload_content.prepare('upload',False,l5x,source,before)
    if not plan['programs'] or not upload_content.Project(l5x).task_configuration.source_complete:
        raise ValueError('Upload-to-ACD requires complete ordinary Programs and Task schedules')
    if not any(not t['name'].casefold().startswith('program:') for t in plan['tags']):
        raise ValueError('Upload-to-ACD requires controller roots for complete tag-definition verification')
    if args.upload_target is not None:upload_snapshot.prepare(source,baseline,before)
    pins={p:probe.digest(p) for p in (source,l5x,baseline)}
    return url,source,l5x,baseline,before,pins


def stage_unknown(summary):
    return summary.get('status')=='unknown' or summary.get('native_call_outcome')=='unknown'


def run(args):
    url,source,l5x,baseline,before,pins=admit(args)
    output=Path(args.output).absolute()
    output.mkdir(parents=True,exist_ok=False)
    summary=dict(status='failed',phase='upload',native_upload_status='not_started',
        native_rebuild_status='not_started',online_verified=False,requires_download=True,
        original_controller_metadata_used=True,direct_uploaded_project_save=False,
        automatic_retry=False,physical_controller_contact_initiated=False)
    (output/'before-state.json').write_text(json.dumps(before,indent=2),encoding='utf8')
    try:
        print('Uploading and verifying native values, routines, Programs and controller tags...',flush=True)
        request=SimpleNamespace(project=str(source),url=url,path=args.path,operation='upload',tag=[],
            output=str(output/'upload'),sdk_feed=args.sdk_feed,upload_target=str(baseline) if args.upload_target is not None else None,
            verify_uploaded_content=str(l5x),verify_uploaded_tag_definitions=True,
            verify_upload_baseline_online=args.upload_target is not None,retain_transfer_trace=True)
        summary['native_upload_status']='started'
        with (output/'upload-stage.log').open('x',encoding='utf8') as log,redirect_stdout(log):
            code=probe.run(request)
        native=rebuild.read_json(output/'upload/summary.json')
        summary.update(native_upload_status=native.get('status'),
                       native_upload_offline_confirmed=native.get('native_sdk_offline_confirmed'),
                       upload_sdk_server_faulted=native.get('sdk_server_faulted'),
                       native_verified_requests=native.get('native_verified_requests'),
                       native_call_outcome=native.get('native_call_outcome'))
        if code!=0 or native.get('status')!='succeeded':
            summary['status']='unknown' if stage_unknown(native) else 'failed'
            raise ValueError('Native upload did not succeed; its outcome is retained and no rebuild was attempted')
        recorded=rebuild.read_json(output/'upload/request.json')
        if (recorded.get('ExportUploadedTags') is not True
                or recorded.get('VerifyUploadBaselineOnline') is not (args.upload_target is not None)):
            raise ValueError('Native upload omitted a requested controller-tag or baseline check')
        # Do not accept only the stage's success flag: independently reopen its
        # actual receipts and artifacts before initiating any native rebuild.
        _,expected,types=rebuild.prepare(source,l5x,output/'upload')
        summary['phase']='rebuild'
        print('Building a fresh Offline ACD from the verified upload...',flush=True)
        request=SimpleNamespace(project=str(source),source=str(l5x),upload_result=str(output/'upload'),
                                output=str(output/'rebuilt'),sdk_feed=args.sdk_feed)
        summary['native_rebuild_status']='started'
        with (output/'rebuild-stage.log').open('x',encoding='utf8') as log,redirect_stdout(log):
            code=rebuild.run(request)
        saved=rebuild.read_json(output/'rebuilt/summary.json')
        summary['native_rebuild_status']=saved.get('status')
        if code!=0 or saved.get('status')!='succeeded':
            summary['status']='unknown' if stage_unknown(saved) else 'failed'
            raise ValueError('Native ACD rebuild did not succeed; outputs are retained without retry')
        verification=rebuild.verify(output/'rebuilt',expected,types,rebuild.read_json(output/'rebuilt/native-result.json'))
        summary['verification']=verification
        if not verification['verified']:raise ValueError('Saved ACD failed independent reopen/content validation')
        # Recheck both the retained upload and running model after the entirely
        # Offline rebuild. Original inputs are checked on every exit below.
        rebuild.prepare(source,l5x,output/'upload')
        final=probe.api(url,'state')
        probe.validate_target(final,args.path,pins[source],instance=before['instance_id'],l5x_hash=pins[l5x])
        probe.validate_idle(final)
        (output/'after-state.json').write_text(json.dumps(final,indent=2),encoding='utf8')
        summary['model_unchanged']=all(before.get(k)==final.get(k) for k in MODEL_FIELDS)
        if not summary['model_unchanged']:raise ValueError('The pinned emulator model changed during the workflow')
        summary.update(status='succeeded',phase='complete',native_acd_reopened=True,
            acd_path='rebuilt/rebuilt.ACD',acd_sha256=probe.digest(output/'rebuilt/rebuilt.ACD'))
    except (OSError,ValueError,ModelError,subprocess.SubprocessError) as error:
        summary['error']=str(error)
    finally:
        try:preserved=all(p.is_file() and probe.digest(p)==digest for p,digest in pins.items())
        except OSError:preserved=False
        summary['inputs_preserved']=preserved
        if not preserved:
            summary['status']='failed';summary['input_error']='An original source or merge baseline changed'
        (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(dict(report=str(output/'summary.json'),**summary),indent=2))
    return 0 if summary['status']=='succeeded' else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True,help='Original bound source ACD; preserved')
    parser.add_argument('--source',required=True,help='Exact complete source Controller L5X; preserved')
    parser.add_argument('--upload-target',help='Optional matching saved-download baseline; checked Online/Offline before upload')
    parser.add_argument('--url',required=True,help='Owned emulator local HTTP URL')
    parser.add_argument('--path',required=True,help=r'Owned emulator Linx driver\IPv4\Backplane\0')
    parser.add_argument('--output',required=True,help='New private directory containing upload/, rebuilt/ and separate receipts')
    parser.add_argument('--sdk-feed')
    args=parser.parse_args()
    try:return run(args)
    except (OSError,ValueError,ModelError,subprocess.SubprocessError) as error:
        parser.exit(2,str(error)+'\n')


if __name__=='__main__':raise SystemExit(main())
