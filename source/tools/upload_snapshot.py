"""Bounded current-value ACD snapshots on an unchanged matching installation.

The native SDK upload supplies independently checked values and source. A
separate matching ACD copy retains Controller metadata and receives Offline
value updates only. No compiled logic, identity or journal bytes are patched.
"""
from pathlib import Path

from logixlab.model import ModelError
from logixlab.native_project import NativeProjectIdentity
from tools import upload_content


def validate_options(operation,enabled,content_source,target,save_uploaded=False,new_project=False,*,option='--snapshot-uploaded-acd'):
    if type(enabled) is not bool:raise ValueError('Upload snapshot must be an explicit boolean')
    if enabled and (operation!='upload' or content_source is None or target is None or save_uploaded or new_project):
        raise ValueError(option+' requires existing-project upload, --upload-target and --verify-uploaded-content without --save-uploaded-acd')


def prepare(source,baseline,state):
    installed=state.get('connectivity',{}).get('native_download') or {}
    if (installed.get('source_equivalent') is not True or installed.get('installed') is not True
            or state.get('routine_edits',{}).get('revision')!=0):
        raise ValueError('Upload snapshot requires an unchanged source-equivalent installation')
    binding=state['connectivity']['source_l5x_sha256']
    try:
        original=NativeProjectIdentity.from_acd(source,binding);saved=NativeProjectIdentity.from_acd(baseline,binding)
    except ModelError as error:raise ValueError('Snapshot source/baseline identity is unavailable: '+str(error)) from error
    fixed=('online_index','online_generation','copy_uid','project_uid','timeline_uid','empty_change_log')
    if (not original.empty_change_log or not saved.empty_change_log or not saved.download_uid
            or saved.download_uid==original.download_uid or any(getattr(saved,k)!=getattr(original,k) for k in fixed)):
        raise ValueError('Upload snapshot requires an unedited saved-download baseline from the bound source')
    return saved.manifest()


def baseline_online_verified(receipt):
    """Require actual ordered Online/Offline steps, not only a requested flag."""
    methods=('GoOnlineAsync:verify-upload-baseline','Verify upload baseline Online',
             'GoOfflineAsync:verify-upload-baseline','Require upload baseline Offline before upload')
    if not isinstance(receipt,dict) or receipt.get('uploadBaselineOnlineVerified') is not True:return False
    steps=receipt.get('steps')
    if not isinstance(steps,list) or any(not isinstance(row,dict) for row in steps):return False
    selected=[row for row in steps if row.get('method') in methods]
    return tuple(row['method'] for row in selected)==methods and all(row.get('status')=='succeeded' for row in selected)


def _online_typed(expected,receipt,types,key):
    """Require exact encoded bytes and complete typed Online scalar coverage."""
    result=dict(verified=False,tags=0)
    try:
        wanted={tag['xpath']:tag['expectedHex'] for tag in expected['tags']
            if tag['typeCode'] in types and tag['constant'] is False and len(tag['expectedHex'])==types[tag['typeCode']]
            and all(size==0 for size in tag['dimensions'])}
        rows=receipt.get(key,[])
        if type(rows) is not list or len(rows)!=len(wanted):return result
        seen=set()
        for row in rows:
            if (type(row) is not dict or set(row)!={'xpath','actualHex'} or type(row['xpath']) is not str
                    or row['xpath'] in seen or row['xpath'] not in wanted
                    or type(row['actualHex']) is not str or row['actualHex']!=wanted[row['xpath']]):return result
            seen.add(row['xpath'])
        return dict(verified=True,tags=len(wanted))
    except (ValueError,TypeError,KeyError,AttributeError):return result


def online_reals(expected,receipt):
    return _online_typed(expected,receipt,{0xCA:8},'onlineRealChecks')


def online_small_integers(expected,receipt):
    return _online_typed(expected,receipt,{0xC2:2,0xC3:4},'onlineIntegerChecks')


def verify(folder,expected,native_types,baseline,receipt):
    """Require native reopen/Online receipts, retained correlation and full content."""
    from tools.probe_native_sdk import digest
    result=dict(verified=False,correlation_preserved=False,serialized_content_verified=False)
    try:
        if (not isinstance(receipt,dict) or any(receipt.get(key) is not True for key in
                ('sourceEquivalentValueSnapshot','baselineLogicVerified','nativeAcdReopened','reopenedOnline'))
                or receipt.get('baselineSha256')!=digest(baseline)):return result
        online=online_reals(expected,receipt)
        result['online_real_checks']=online
        if not online['verified']:return result
        integers=online_small_integers(expected,receipt)
        result['online_integer_checks']=integers
        if not integers['verified']:return result
        folder=Path(folder)
        for filename,key,maximum in (('snapshot.ACD','acdSha256',100_000_000),('snapshot.L5X','reopenedL5xSha256',16_000_000)):
            path=folder/filename
            if (path.is_symlink() or not path.is_file() or not 8<=path.stat().st_size<=maximum
                    or digest(path)!=receipt.get(key)):return result
        binding=expected['sourceL5xSha256']
        before=NativeProjectIdentity.from_acd(baseline,binding)
        after=NativeProjectIdentity.from_acd(folder/'snapshot.ACD',binding)
        if (not before.empty_change_log or not before.download_uid or before.attributes()!=after.attributes()
                or before.empty_change_log!=after.empty_change_log):return result
        result['correlation_preserved']=True
        content=upload_content.verify_serialized(folder/'snapshot.L5X',expected,native_types)
        result['content']=content
        if not content['verified']:return result
        result.update(verified=True,serialized_content_verified=True,native_acd_reopened=True,reopened_online=True,
                      profile='Unchanged source with current uploaded values; baseline Controller metadata retained')
        return result
    except (OSError,ValueError,ModelError,TypeError,KeyError,AttributeError):return result
