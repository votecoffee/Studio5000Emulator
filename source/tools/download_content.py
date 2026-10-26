"""Independent full-content checks after a native downloaded ACD save/reopen."""
from pathlib import Path

from logixlab.model import ModelError, Project
from tools import upload_content


def prepare(operation, save, l5x, acd, state):
    if l5x is None:
        return None
    if operation != 'download' or save is not True:
        raise ValueError('--verify-downloaded-content requires download with --save-downloaded-acd')
    from tools.rebuild_uploaded_acd import source_schema
    expected = upload_content.prepare('upload', False, l5x, acd, state)
    expected['downloadSourceSchema'] = source_schema(Project(l5x))
    return expected


def verify(folder, expected, types, receipt):
    """Content checks supplement the probe's separate saved-correlation check."""
    from tools.probe_native_sdk import digest
    from tools.rebuild_uploaded_acd import source_schema
    result = dict(verified=False, serialized_content_verified=False)
    try:
        if not isinstance(receipt, dict) or any(receipt.get(key) is not True for key in
                ('nativeAcdReopened', 'reopenedOnline', 'downloadResultSaved', 'offlineContentExported')):
            return result
        folder = Path(folder)
        for name, key, maximum in [('downloaded.ACD','acdSha256',100_000_000),
                                   ('downloaded.L5X','reopenedL5xSha256',16_000_000)]:
            path = folder / name
            if (path.is_symlink() or not path.is_file() or not 8 <= path.stat().st_size <= maximum
                    or digest(path) != receipt.get(key)):
                return result
        content = upload_content.verify_serialized(folder/'downloaded.L5X', expected, types)
        result['content'] = content
        schema = source_schema(Project(folder/'downloaded.L5X')) == expected['downloadSourceSchema']
        result['source_schema_preserved'] = schema
        if content['verified'] and schema:
            result.update(verified=True, serialized_content_verified=True, native_acd_reopened=True,
                          reopened_online=True)
        return result
    except (OSError, ValueError, ModelError, TypeError, KeyError, AttributeError):
        return result
