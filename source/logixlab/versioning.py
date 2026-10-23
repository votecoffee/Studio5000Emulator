"""Stamp release versions and generate matching Windows build metadata."""
from datetime import datetime
import re
from pathlib import Path

from . import __version__


def windows_version(version):
    """Split YY.MMDD.HHmmss into four Windows WORDs: YY, MMDD, HHmm, ss."""
    match = re.fullmatch(r'([0-9]{2})\.([0-9]{4})\.([0-9]{4})([0-9]{2})', version)
    if not match:
        raise ValueError('App version must use YY.MMDD.HHmmss')
    datetime.strptime('20'+version, '%Y.%m%d.%H%M%S')
    return tuple(int(value) for value in match.groups())


def stamp_version():
    """Save one workstation-local release timestamp; never change it at startup."""
    version = datetime.now().strftime('%y.%m%d.%H%M%S')
    path = Path(__file__).with_name('__init__.py')
    content, count = re.subn(r'^__version__ = "[^"\r\n]+"$',
                             f'__version__ = "{version}"', path.read_text(encoding='utf-8'),
                             flags=re.MULTILINE)
    if count != 1:
        raise ValueError('Expected exactly one application version declaration')
    path.write_text(content, encoding='utf-8')
    return version


def write_windows_resource(path):
    numeric = windows_version(__version__)
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


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stamp', action='store_true', help='Stamp a new revision before building all delivery targets')
    args = parser.parse_args()
    print(stamp_version() if args.stamp else __version__)
