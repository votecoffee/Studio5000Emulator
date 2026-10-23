"""Keep timestamp versions valid in the Windows executable's 16-bit fields."""
import tempfile
from pathlib import Path
import unittest

from logixlab import __version__
from logixlab.versioning import windows_version, write_windows_resource


class VersioningTests(unittest.TestCase):
    def test_timestamp_seconds_do_not_overflow_windows_version_fields(self):
        self.assertEqual(windows_version('26.1011.172201'), (26, 1011, 1722, 1))
        self.assertEqual(windows_version('26.1231.235959'), (26, 1231, 2359, 59))
        self.assertEqual(windows_version('28.0229.000000'), (28, 229, 0, 0))

    def test_invalid_format_date_and_time_are_rejected(self):
        for version in ('0.6.0-connectivity.162', '26.1011.1722', '26.0229.120000',
                        '26.1331.120000', '26.1011.240000', '26.1011.172260'):
            with self.subTest(version=version), self.assertRaises(ValueError):
                windows_version(version)

    def test_resource_keeps_full_display_version_and_matching_numeric_tuple(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'version.txt'
            write_windows_resource(path)
            resource = path.read_text(encoding='utf-8')
        numeric = windows_version(__version__)
        self.assertIn(f'filevers={numeric!r}, prodvers={numeric!r}', resource)
        for field in ('FileVersion', 'ProductVersion'):
            self.assertIn(f'StringStruct({field!r}, {__version__!r})', resource)
