"""Verify an accepted native edit saved by its existing SDK project.

This does not upload, import neutral logic or provide Change Log history.
The native Save As may change Copy UID; the remaining correlation is pinned.
"""
import hashlib
from pathlib import Path

from logixlab.model import ModelError,Project
from logixlab.native_project import NativeProjectIdentity
from logixlab.native_types import NativeTypes
from tools import upload_content

METHODS=('SaveAsAsync:native-edited.ACD','Close native edited project before reopen',
         'OpenLogixProjectAsync:native-edited.ACD','Require native edited ACD Offline',
         'SaveAsAsync:native-edited.L5X','GoOnlineAsync:native-edited.ACD',
         'Verify native edited ACD Online','GoOfflineAsync:native-edited.ACD',
         'Require native edited ACD Offline after verification')
FIXED=('online_index','online_generation','download_uid','project_uid','timeline_uid','empty_change_log')


def validate_options(operation,enabled,*,apply,baseline,reconnect,second_code,import_option,neutral_save):
    if type(enabled) is not bool:raise ValueError('Native edit save must be an explicit boolean')
    if enabled and (operation!='edits' or apply is not True or not baseline or reconnect is not True
                    or second_code is not None or import_option!='AcceptEdits' or neutral_save):
        raise ValueError('Native edit save requires one accepted edit, --connection-target and --reconnect-edits without --save-edited-acd')


def prepare(source_l5x,source_acd,state):
    path=Path(source_l5x)
    if path.suffix.casefold()!='.l5x' or not path.is_file() or not 8<=path.stat().st_size<=upload_content.MAX_XML:
        raise ValueError('Native edit save requires the original matching L5X')
    project=Project(path);binding=state.get('connectivity',{}).get('source_l5x_sha256')
    if project.sha256!=binding or state.get('routine_edits',{}).get('revision')!=0:
        raise ValueError('Native edit save requires unchanged bound source before the edit')
    upload_content.plan(project,NativeTypes.from_acd(source_acd,binding),state)
    return project.sha256


def verify(folder,source_l5x,source_acd,baseline,state,report,source_hash):
    result=dict(verified=False,correlation_anchors_preserved=False,content_verified=False,reopened_online=False)
    try:
        if (not isinstance(report,dict) or report.get('status')!='succeeded'
                or report.get('serverFaulted') is not False or report.get('sdkOfflineConfirmed') is not True
                or report.get('workingProjectUnchanged') is not True):return result
        receipt=report.get('savedNativeEditedProject')
        if (not isinstance(receipt,dict) or any(receipt.get(key) is not True for key in
                ('directAcceptedEditSave','nativeAcdReopened','reopenedOnline','noUploadCalled','noL5xImportCalled'))
                or receipt.get('baselineSha256')!=hashlib.sha256(Path(baseline).read_bytes()).hexdigest()):return result
        steps=report.get('steps')
        if not isinstance(steps,list) or any(not isinstance(row,dict) for row in steps):return result
        selected=[row for row in steps if row.get('method') in METHODS]
        if tuple(row['method'] for row in selected)!=METHODS or any(row.get('status')!='succeeded' for row in selected):return result
        if state.get('routine_edits',{}).get('revision')!=1:return result
        folder=Path(folder)
        for name,key,maximum in (('native-edited.ACD','acdSha256',100_000_000),('native-edited.L5X','l5xSha256',upload_content.MAX_XML)):
            path=folder/name
            if (path.is_symlink() or not path.is_file() or not 8<=path.stat().st_size<=maximum
                    or hashlib.sha256(path.read_bytes()).hexdigest()!=receipt.get(key)):return result
        binding=state['connectivity']['source_l5x_sha256'];source=Project(source_l5x)
        if source.sha256!=binding or source.sha256!=source_hash:return result
        original=NativeProjectIdentity.from_acd(baseline,binding)
        saved=NativeProjectIdentity.from_acd(folder/'native-edited.ACD',binding)
        if (not original.download_uid or not saved.copy_uid or not original.empty_change_log
                or any(getattr(original,k)!=getattr(saved,k) for k in FIXED)):return result
        result['correlation_anchors_preserved']=True;result['copy_uid_changed']=original.copy_uid!=saved.copy_uid
        types=NativeTypes.from_acd(source_acd,binding)
        expected=upload_content.plan(source,types,state,allow_edited=True)
        content=upload_content.verify_serialized(folder/'native-edited.L5X',expected,types)
        result['content']=content
        if not content['verified']:return result
        result.update(verified=True,content_verified=True,reopened_online=True,
            profile='Accepted native edit saved by the existing SDK project; no controller upload',
            change_log_records_decoded=False,controller_upload_verified=False)
        return result
    except (OSError,ValueError,ModelError,TypeError,KeyError,AttributeError):return result
