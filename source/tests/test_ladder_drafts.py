
from types import SimpleNamespace
import unittest

from logixlab.ladder_drafts import reopen
from logixlab.model import ModelError, Routine, parse_rung


class LadderDraftTests(unittest.TestCase):
    def test_reopen_checks_runtime_digest_even_at_the_same_revision(self):
        routine = Routine('MainProgram', 'Main', 'RLL')
        routine.rungs = [{'number': '0', 'comment': '', 'text': 'NOP();', 'nodes': parse_rung('NOP();')}]
        project = SimpleNamespace(sha256='a' * 64, runtime_revision=1, runtime_logic_sha256='b' * 64,
                                  routines={routine.key.lower(): routine})
        draft = {'format': 'logixlab-rll-draft', 'version': 1, 'source_sha256': project.sha256,
                 'base_revision': 1, 'routine': routine.key,
                 'rungs': [{'number': '0', 'comment': '', 'text': 'XIC(?);'}]}
        for stale in (draft, {**draft, 'base_logic_sha256': 'c' * 64}):
            with self.assertRaisesRegex(ModelError, 'matching base logic revision'):
                reopen(project, stale)
        restored = reopen(project, {**draft, 'base_logic_sha256': project.runtime_logic_sha256})
        self.assertEqual(restored[0]['nodes'], parse_rung('XIC(?);'))
        self.assertEqual(routine.rungs[0]['text'], 'NOP();')
