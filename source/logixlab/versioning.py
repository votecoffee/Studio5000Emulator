"""Generate Windows build metadata from the application's single version value."""
import re
from pathlib import Path

from . import __version__


def write_windows_resource(path):
    match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:-connectivity\.(\d+))?', __version__)
    if not match:
        raise ValueError('Update the Windows version mapping for this version format')
    numeric = tuple(int(value or 0) for value in match.groups())
    if any(value > 65535 for value in numeric):
        raise ValueError('Windows version components must fit in 16 bits')
    values = {'CompanyName': 'Studio5000Emulator contributors',
              'FileDescription': 'LogixLab experimental offline Logix emulator',
              'FileVersion': __version__, 'InternalName': 'LogixLab',
              'LegalCopyright': 'MIT License', 'OriginalFilename': 'LogixLab.exe',
              'ProductName': 'LogixLab', 'ProductVersion': __version__}
    strings = ',\n'.join(f'StringStruct({key!r}, {value!r})' for key, value in values.items())
    resource = f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={numeric!r}, prodvers={numeric!r},
    mask=0x3f, flags=0, OS=0x40004, fileType=0x1, subtype=0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [{strings}])]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])])
'''
    Path(path).write_text(resource, encoding='utf-8')
