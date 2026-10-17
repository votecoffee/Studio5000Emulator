import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from logixlab.importers import convert_acd,default_converter
from logixlab.model import ModelError
from logixlab.server import Application


class ImportConfigurationTests(unittest.TestCase):
    def test_environment_configuration_precedes_path_discovery(self):
        with patch.dict(os.environ,{'LOGIXLAB_CONVERTER':'configured-converter.exe'}),patch('logixlab.importers.shutil.which') as lookup:
            self.assertEqual(default_converter(),'configured-converter.exe');lookup.assert_not_called()

    def test_path_discovery_without_machine_specific_defaults(self):
        with patch.dict(os.environ,{'LOGIXLAB_CONVERTER':''}),patch('logixlab.importers.shutil.which',return_value='path-converter.exe') as lookup:
            self.assertEqual(default_converter(),'path-converter.exe');lookup.assert_called_once_with('l5xgit')

    def test_missing_converter_leaves_original_and_output_directory_untouched(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.ACD';source.write_bytes(b'private test input');output=Path(folder)/'output/project.L5X'
            with patch.dict(os.environ,{'LOGIXLAB_CONVERTER':''}),patch('logixlab.importers.shutil.which',return_value=None):
                self.assertEqual(default_converter(),'')
                with self.assertRaisesRegex(ModelError,'Import settings'):convert_acd(source,output)
            self.assertEqual(source.read_bytes(),b'private test input');self.assertFalse(output.parent.exists())

    def test_saved_import_settings_override_environment_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'settings.json').write_text(json.dumps({'converter':'saved-converter.exe'}),encoding='utf-8')
            with patch.dict(os.environ,{'LOGIXLAB_CONVERTER':'environment-converter.exe'}):
                app=Application(folder)
                try:self.assertEqual(app.converter,'saved-converter.exe')
                finally:app.close()

    def test_explicit_converter_runs_on_a_private_copy_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.ACD';source.write_bytes(b'private input')
            converter=root/'converter.exe';converter.write_bytes(b'test double');output=root/'output/project.L5X'
            def run(command,**kwargs):
                self.assertEqual(command[0],str(converter.resolve()))
                copied=Path(command[command.index('--acd')+1]);self.assertNotEqual(copied,source)
                self.assertEqual(copied.read_bytes(),source.read_bytes())
                Path(command[command.index('--l5x')+1]).write_text('<RSLogix5000Content />',encoding='utf-8')
                return SimpleNamespace(stdout='ok',stderr='',returncode=0)
            with patch.dict(os.environ,{'LOGIXLAB_CONVERTER':'unused.exe'}),patch('logixlab.importers.subprocess.run',side_effect=run):
                receipt=convert_acd(source,output,converter)
            self.assertTrue(receipt['original_unchanged']);self.assertEqual(source.read_bytes(),b'private input')


if __name__=='__main__':unittest.main()
