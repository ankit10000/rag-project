"""Focused deterministic guards for the new synthetic development run only."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import ai_development_evaluation as dev


class DevelopmentEvaluationGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.out = Path(self.temporary.name)
        self.patch = patch.object(dev, 'OUT', self.out)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        dev.prepare()
        self.dataset = json.loads((self.out / 'dataset.json').read_text())
        self.policy = json.loads((self.out / 'policy.json').read_text())

    def test_four_new_cases_have_no_original_ids_or_questions(self):
        self.assertEqual(len(dev.validate_inputs(self.dataset, self.policy)), 4)

    def test_original_id_collision_rejected(self):
        from eval.phase35 import validate
        _, original = validate.load(['data_A', 'data_B', 'data_C', 'data_D'])
        self.dataset['cases'][0]['id'] = original[0]['id']
        with self.assertRaisesRegex(ValueError, 'collision'):
            dev.validate_inputs(self.dataset, self.policy)

    def test_original_question_collision_rejected(self):
        from eval.phase35 import validate
        _, original = validate.load(['data_A', 'data_B', 'data_C', 'data_D'])
        self.dataset['cases'][0]['question'] = original[0]['question']
        with self.assertRaisesRegex(ValueError, 'collision'):
            dev.validate_inputs(self.dataset, self.policy)

    def test_duplicate_ids_rejected(self):
        self.dataset['cases'][1]['id'] = self.dataset['cases'][0]['id']
        with self.assertRaisesRegex(ValueError, 'unique'):
            dev.validate_inputs(self.dataset, self.policy)

    def test_incomplete_policy_and_changed_digest_rejected(self):
        incomplete = copy.deepcopy(self.policy)
        del incomplete['criteria']['proper_abstention']
        with self.assertRaisesRegex(ValueError, 'criteria'):
            dev.validate_inputs(self.dataset, incomplete)
        self.policy['dataset_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'digest'):
            dev.validate_inputs(self.dataset, self.policy)

    def test_exclusive_preparation_and_run_no_overwrite(self):
        with self.assertRaises(FileExistsError):
            dev.prepare()
        (self.out / 'results.jsonl').write_text('immutable\n')
        with self.assertRaisesRegex(ValueError, 'rerun refused'):
            dev.run()
        self.assertEqual((self.out / 'results.jsonl').read_text(), 'immutable\n')


if __name__ == '__main__':
    unittest.main()
