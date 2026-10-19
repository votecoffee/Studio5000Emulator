"""Conversion comparison must detect lost logic, data and metadata."""
import hashlib
import contextlib
import io
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from tools.compare_imports import compare_exports, main


class ImportComparisonTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.reference = Path(__file__).resolve().parents[1] / 'samples/ConveyorDemo.L5X'
        self.candidate = Path(self.folder.name) / 'candidate.L5X'

    def tearDown(self):
        self.folder.cleanup()

    def changed(self, mutate):
        tree = ET.parse(self.reference)
        mutate(tree.getroot())
        tree.write(self.candidate, encoding='utf-8', xml_declaration=True)
        return compare_exports(self.reference, self.candidate)

    def test_formatting_only_changes_pass_and_preserve_input_bytes(self):
        before = hashlib.sha256(self.reference.read_bytes()).hexdigest()
        result = self.changed(lambda root: ET.indent(root, space='    '))
        self.assertTrue(result['modeled_content_matches'], result['different_groups'])
        self.assertTrue(result['inputs_unchanged'])
        self.assertEqual(hashlib.sha256(self.reference.read_bytes()).hexdigest(), before)
        self.assertEqual(result['native_runtime_equivalence'], 'NOT VERIFIED')

    def test_missing_rung_is_a_failure_even_when_tags_and_controller_match(self):
        def remove(root):
            routine = root.find('.//RLLContent')
            routine.remove(routine.findall('Rung')[3])
        result = self.changed(remove)
        self.assertFalse(result['modeled_content_matches'])
        self.assertIn('routines', result['different_groups'])
        self.assertEqual(result['candidate_counts']['rungs'], result['reference_counts']['rungs'] - 1)

    def test_lost_preset_is_a_failure(self):
        result = self.changed(lambda root: root.find(".//Tag[@Name='StartDelay']//DataValueMember[@Name='PRE']").set('Value', '0'))
        self.assertFalse(result['modeled_content_matches'])
        self.assertIn('initial_values', result['different_groups'])

    def test_lost_decorated_values_cannot_pass_as_default_zeroes(self):
        def remove(root):
            tag = root.find(".//Tag[@Name='SpeedSetpoint']")
            for data in tag.findall('Data'):
                tag.remove(data)
        result = self.changed(remove)
        self.assertFalse(result['modeled_content_matches'])
        self.assertTrue(result['candidate_blockers'])

    def test_task_and_external_access_changes_are_failures(self):
        result = self.changed(lambda root: root.find('.//Task').set('InhibitTask', 'true'))
        self.assertIn('tasks', result['different_groups'])
        result = self.changed(lambda root: root.find(".//Tag[@Name='StartPB']").set('ExternalAccess', 'None'))
        self.assertIn('tags', result['different_groups'])

    def test_unsupported_logic_never_passes_even_against_itself(self):
        def unsupported(root):
            root.find('.//RLLContent/Rung/Text').text = 'UNSUPPORTED();'
        self.changed(unsupported)
        result = compare_exports(self.candidate, self.candidate)
        self.assertFalse(result['modeled_content_matches'])
        self.assertTrue(result['candidate_blockers'])

    def test_cli_refuses_an_output_alias_of_either_input(self):
        self.changed(lambda root: None)
        alias = Path(self.folder.name) / 'receipt.json'
        alias.hardlink_to(self.candidate)
        before = self.candidate.read_bytes()
        for output in (self.reference, self.candidate, alias):
            args = ['compare_imports', '--reference', str(self.reference), '--candidate', str(self.candidate), '--out', str(output)]
            with self.subTest(output=output), patch('sys.argv', args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main()
                self.assertEqual(error.exception.code, 2)
        self.assertEqual(self.candidate.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
