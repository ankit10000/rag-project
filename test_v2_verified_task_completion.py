"""Fresh synthetic cases for task completion, source amounts and failure status."""
import os
import unittest
from unittest.mock import Mock, patch

from services.answer_service import BOUNDED_REFUSAL, generate_grounded_answer, with_source_locations
from services.context_assembly_service import assemble_context
from services.explicit_source_update import current_amount_answer


def bundle(*texts):
    return assemble_context([{'chunk': (i, 'synthetic', i, text, .5), 'rrf_score': .04}
                             for i, text in enumerate(texts, 1)])


class VerifiedTaskCompletionTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'RAG_V2': '1'})
        env.start()
        self.addCleanup(env.stop)

    def answer(self, question, passages, replies, retries=0):
        model = Mock(side_effect=replies)
        with patch('services.answer_service.cfg.ANSWER_MAX_RETRIES', retries):
            result = generate_grounded_answer(question, bundle(*passages), 'DOCUMENT', model)
        return result, model

    def test_silent_unobserved_field_is_disclosed_without_retry(self):
        r, model = self.answer('Give budget, team size and timeline.',
            ['Budget: 10 credits. Team size: 5 people.'],
            ['[DOCUMENT] The budget is 10 credits and team size is 5 people [S1].'])
        self.assertEqual(r['status'], 'partial')
        self.assertIn('timeline', r['answer'])
        self.assertIn('10 credits', r['answer'])
        self.assertEqual(model.call_count, 1)

    def test_supported_missing_value_gets_exactly_one_opportunity_for_repair(self):
        q = 'Give the budget and team size.'
        src = ['Budget: 10 credits. Team size: 5 people.']
        echo = '[DOCUMENT] The budget and team size were documented [S1].'
        corrected = '[DOCUMENT] The budget is 10 credits and team size is 5 people [S1].'
        r, model = self.answer(q, src, [echo, corrected], retries=7)
        self.assertEqual(r['status'], 'answered')
        self.assertEqual(model.call_count, 2)
        r, model = self.answer(q, src, [echo, echo], retries=7)
        self.assertNotEqual(r['status'], 'answered')
        self.assertEqual(model.call_count, 2)

    def test_wrong_source_field_values_are_removed_on_final_repair(self):
        r, _ = self.answer('Give the budget and team size.',
            ['Budget: 10 credits. Team size: 5 people.'],
            ['[DOCUMENT] The budget is 5 credits [S1]. The team size is 5 people [S1].'])
        self.assertEqual(r['status'], 'partial')
        self.assertNotIn('5 credits', r['answer'])
        self.assertIn('5 people', r['answer'])

    def test_question_allegation_is_not_evidence_for_duration(self):
        r, _ = self.answer('How long did Rey work at Linden? Was it 99 years?',
            ['Rey worked at Linden.'], ['[DOCUMENT] Rey worked there for 99 years [S1].'])
        self.assertNotIn('99 years', r['answer'])
        self.assertNotEqual(r['status'], 'answered')

    def test_only_a_joining_month_does_not_complete_a_duration(self):
        r, _ = self.answer('How long did Rey work at Linden?', ['Employee: Rey. Rey joined Linden in March 2020.'],
            ['[DOCUMENT] Rey joined Linden in March 2020 [S1].'])
        self.assertEqual(r['status'], 'abstained')
        self.assertEqual(r['answer'], BOUNDED_REFUSAL)

    def test_directly_sourced_work_duration_needs_no_date_calculation(self):
        r, _ = self.answer('How long did Rey work at Linden?', ['Employee: Rey. Rey worked at Linden for 8 months.'],
            ['[DOCUMENT] Rey worked at Linden for 8 months [S1].'])
        self.assertEqual(r['status'], 'answered')
        self.assertIn('8 months', r['answer'])

    def test_cannot_attach_wrong_persons_direct_duration(self):
        r, _ = self.answer('How long did Sam work at Linden?', ['Employee: Rey. Rey worked at Linden for 8 months.'],
            ['[DOCUMENT] Sam worked at Linden for 8 months [S1].'])
        self.assertNotIn('8 months', r['answer'])
        self.assertNotEqual(r['status'], 'answered')

    def test_application_duration_replaces_incidental_source_number(self):
        r, _ = self.answer('How long did Rey work at Linden, and what was his degree?',
            ['Employee: Rey. Employer: Linden: February 2022 to November 2025. He supervised 22 people. His degree is physics.'],
            ['[DOCUMENT] Rey worked at Linden for 22 years [S1]. His degree is physics [S1].'])
        self.assertIn('45 months', r['answer'])
        self.assertNotIn('22 years', r['answer'])
        self.assertIn('physics', r['answer'])
        self.assertEqual(r['calculation']['total_months'], 45)

    def test_failed_validation_repair_returns_system_error(self):
        r, model = self.answer('Give budget and team size.', ['Budget: 10 credits. Team size: 5 people.'],
            ['[DOCUMENT] The budget is 10 credits [S1].', TimeoutError()], retries=1)
        self.assertEqual((r['status'], model.call_count), ('error', 2))
        self.assertFalse(r['citations'])
        self.assertNotIn('10 credits', r['answer'])

    def test_bounded_abstention_wording(self):
        for passages in ([], ['An unrelated safe passage.']):
            r, model = self.answer('What was the recorded temperature?', passages,
                                   ['[DOCUMENT] ' + BOUNDED_REFUSAL])
            self.assertEqual(r['status'], 'abstained')
            self.assertEqual(r['answer'], BOUNDED_REFUSAL)
            self.assertEqual(model.call_count, len(passages))

    def test_comparing_entities_is_not_source_disagreement(self):
        from services.answer_service import classify_status
        self.assertEqual(classify_status('The companies have different budgets [S1][S2].',
                                         {'a', 'b'}, True), 'answered')
        self.assertEqual(classify_status('The two sources disagree on the budget [S1][S2].',
                                         {'a', 'b'}, True), 'conflict')

    def test_location_uses_current_result_ref_and_page_only(self):
        result = {'answer': 'The car is cerulean [S4].', 'status': 'answered',
                  'citations': [{'ref':'S4', 'page': 8, 'document': 'current'},
                                {'ref':'S7', 'page': 4, 'document': 'unrelated'}]}
        out = with_source_locations(result)
        self.assertIn('page 8 [S4]', out['answer'])
        self.assertNotIn('S7', out['answer'])
        for status in ('abstained', 'unverified', 'error'):
            item = {**result, 'status': status}
            self.assertIs(with_source_locations(item), item)

    def test_explicit_supersession_is_bound_to_named_original_amount_and_citation(self):
        q = 'What is the current Harbor travel allowance?'
        original = 'Original Harbor travel allowance: 14 credits.'
        revision = ('Official erratum to the Harbor travel allowance: the 19-credit allowance '
                    'supersedes the original 14-credit allowance.')
        r, model = self.answer(q, [original, revision], [])
        self.assertEqual((r['status'], model.call_count), ('answered', 0))
        self.assertIn('19 credits', r['answer'])
        self.assertEqual([(c['ref'], c['page']) for c in r['citations']], [('S2', 2)])
        for extra in (revision.replace('19-credit', '22-credit'), 'Harbor travel allowance: 25 credits.'):
            self.assertIsNone(current_amount_answer(q, bundle(original, revision, extra)['sources']))
        for wrong in (revision.replace('Harbor', 'Inlet'), revision.replace('14-credit', '10-credit'),
                      revision.replace('19-credit', '19-euro'), revision.replace('Official', 'Draft')):
            self.assertIsNone(current_amount_answer(q, bundle(original, wrong)['sources']))


if __name__ == '__main__':
    unittest.main()
