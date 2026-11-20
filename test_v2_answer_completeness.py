"""Source-bound completeness repairs; deterministic, no DB/provider I/O."""
import os
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from services.answer_service import generate_grounded_answer, classify_status
from services.context_assembly_service import assemble_context
from services.request_budget import RequestDeadlineExceeded, request_budget
from services.source_count_comparison import source_count_comparison


def bundle(*texts):
    return assemble_context([{'chunk': (i, 'owned-source', i, text, .5),
                              'rrf_score': .03, 'rerank_score': 1.0}
                             for i, text in enumerate(texts, 1)])


QUESTION = 'Give budget, team size and development duration.'
CONTEXT = bundle('Budget: 58 credits. Team size: 8 people. Development duration: 12 months.')
COMPLETE = '[DOCUMENT] The budget is 58 credits [S1]. The team size is 8 people [S1]. The development duration is 12 months [S1].'
OMITTED = '[DOCUMENT] The budget is 58 credits [S1]. The development duration is 12 months [S1].'


class AnswerCompletenessTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'RAG_V2': '1'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def answer(self, replies, question=QUESTION, context=CONTEXT, retries=1):
        generate = Mock(side_effect=replies)
        with patch('services.answer_service.cfg.ANSWER_MAX_RETRIES', retries):
            result = generate_grounded_answer(question, context, 'DOCUMENT', generate)
        return result, generate

    def test_complete_answer_uses_one_generation(self):
        result, generate = self.answer([COMPLETE])
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(generate.call_count, 1)
        self.assertFalse(result['coverage']['concrete_missing'])

    def test_concrete_omission_repairs_with_existing_retry_only(self):
        result, generate = self.answer([OMITTED, COMPLETE])
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(generate.call_count, 2)
        repair_prompt = generate.call_args_list[1].args[0]
        self.assertIn('CORRECTION REQUIRED', repair_prompt)
        self.assertIn('team', repair_prompt.lower())

    def test_exhausted_valid_omission_is_partial_not_complete(self):
        result, generate = self.answer([OMITTED, OMITTED])
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result['status'], 'partial')
        self.assertTrue(any(x.startswith('missing_requested_item:') for x in result['issues']))
        self.assertNotIn('8 people', result['answer'])
        self.assertTrue(result['citations'])

    def test_supported_evidence_refusal_gets_one_bounded_repair(self):
        refusal = '[DOCUMENT] I couldn\'t find sufficient information in the provided documents.'
        result, generate = self.answer([refusal, COMPLETE])
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result['status'], 'answered')

    def test_exhausted_false_refusal_is_unverified_not_absence(self):
        refusal = '[DOCUMENT] I couldn\'t find sufficient information in the provided documents.'
        result, generate = self.answer([refusal], retries=0)
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result['status'], 'unverified')
        self.assertNotEqual(result['answer'], refusal.removeprefix('[DOCUMENT] '))

    def test_absent_information_does_not_require_fabrication_or_extra_call(self):
        result, generate = self.answer(
            ["[DOCUMENT] I couldn't find sufficient information in the provided documents."],
            question='What signed customer contract number is listed?')
        self.assertEqual(result['status'], 'abstained')
        self.assertEqual(generate.call_count, 1)
        self.assertFalse(result['citations'])

    def test_saved_prefaced_phone_gap_is_partial(self):
        # Exact answer wording transcribed from the preserved manual screenshot.
        body = ('According to the resume, the Atlas project reduced report preparation time '
                'from 40 minutes to 12 minutes [S1]. Regarding the second part of your '
                'question, the provided documents do not contain any information about '
                'a telephone number for Morgan [S1].')
        result, generate = self.answer(['[DOCUMENT] ' + body],
            question='How did Atlas change report time? Also, what telephone number is listed?',
            context=bundle('Atlas reduced report preparation time from 40 minutes to 12 minutes.'))
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['answer'], body)
        self.assertEqual(generate.call_count, 1)

    def test_exact_live_uncited_listed_phone_gap_is_preserved_as_partial(self):
        body = ('- The Atlas project reduced report preparation time from 40 minutes to 12 minutes [S1].\n'
                '- The provided documents do not contain a telephone number listed for Morgan.')
        result, generate = self.answer(['[DOCUMENT] ' + body],
            question='According to Morgan Vale’s resume, how did the Atlas project change report preparation time? Also, what telephone number is listed for Morgan?',
            context=bundle('Atlas reduced report preparation time from 40 minutes to 12 minutes.'))
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['answer'], body)
        self.assertEqual(generate.call_count, 1)
        self.assertTrue(result['citations'])

    def test_reporting_participle_does_not_turn_excluded_service_into_gap(self):
        text='The policy does not provide a fax service listed for visitors [S1].'
        result,generate=self.answer(['[DOCUMENT] '+text],question='Is fax included?',
            context=bundle('The policy does not provide a fax service listed for visitors.'))
        self.assertEqual(result['status'],'answered')
        self.assertEqual(generate.call_count,1)

    def test_prefaced_explicit_negative_remains_answered(self):
        text = 'Regarding fax access, the observatory does not provide a fax service [S1].'
        result, generate = self.answer(['[DOCUMENT] ' + text], question='Is a fax service provided?',
            context=bundle('The observatory does not provide a fax service.'))
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(generate.call_count, 1)
        self.assertTrue(result['citations'])

    def test_same_document_source_disagreement_is_reported(self):
        result, _ = self.answer([
            '[DOCUMENT] The roadmap is inconsistent: its header says roughly three phases, '
            'but its list enumerates four phases [S1].'], question='Does the roadmap agree with itself?',
            context=bundle('The roadmap header says roughly three phases; its list enumerates four phases.'))
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(len(result['citations']), 1)

    def test_comparison_without_disagreement_is_not_conflict(self):
        self.assertEqual(classify_status('The roadmap sections do not conflict [S1].',
                                         {'owned-source'}, True), 'answered')

    def test_saved_live_phase_count_disagreement_keeps_failure_immutable(self):
        path = Path('v2_evidence/reliability-20261119/live-01/conflict.json')
        original = path.read_bytes()
        saved = json.loads(original)
        result = saved['result']
        self.assertEqual(result['status'], 'answered')
        self.assertIn('inconsistency between the stated phase count', result['answer'])
        self.assertEqual(classify_status(result['answer'],
            {c['document'] for c in result['citations']}, True), 'conflict')
        self.assertEqual(path.read_bytes(), original)

    def test_count_comparison_needs_disagreement_and_citation(self):
        text = ('There is an inconsistency between the stated phase count and '
                'the actual number of phases listed.')
        self.assertEqual(classify_status(text, set(), False), 'answered')
        self.assertEqual(classify_status('The stated phase count and the listed count agree [S1].',
                                         {'owned-source'}, True), 'answered')
        self.assertEqual(classify_status('The stated counts do not disagree [S1].',
                                         {'owned-source'}, True), 'answered')

    def test_saved_live_citation_failure_then_false_refusal_is_source_bound_conflict(self):
        path = Path('v2_evidence/reliability-20261119/live-02/conflict-trace.json')
        original = path.read_bytes()
        trace = json.loads(original)
        requests = [e for e in trace['events'] if e['stage'] == 'generation_request']
        responses = [e['raw']['answer'] for e in trace['events'] if e['stage'] == 'answer_generated']
        sources = requests[0]['raw']['sources']
        context = {'sources': sources, 'context_text': '\n'.join(s['content'] for s in sources)}
        question = 'Does the roadmap stated phase count agree with its listed phases? Report any inconsistency.'
        result, generate = self.answer(responses, question=question, context=context)
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result['status'], 'conflict')
        self.assertIn('roughly 3 phases', result['answer'])
        self.assertIn('Phase 1 through Phase 4', result['answer'])
        self.assertIn('inconsistency', result['answer'])
        self.assertEqual({c['page'] for c in result['citations']}, {15})
        self.assertTrue(result['validation']['valid'])
        self.assertEqual(result['coverage']['source_count_comparison']['observed_consecutive_headings'], [1, 2, 3, 4])
        self.assertEqual(path.read_bytes(), original)

    def phase_sources(self, declared='3 phases', headings=(1, 2, 3, 4)):
        text = 'The roadmap proposes ' + declared + '. '
        text += ' '.join(f'• Phase {i} – Work stage {i} (months):' for i in headings)
        return bundle(text)['sources']

    def test_source_count_proof_only_for_observed_excess_not_unseen_completion(self):
        question = 'Does the stated phase count agree with the listed phases?'
        proof = source_count_comparison(question, self.phase_sources())
        self.assertEqual(proof['stated_count'], 3)
        self.assertEqual(proof['observed_consecutive_headings'], [1, 2, 3, 4])
        for sources in (self.phase_sources('4 phases'), self.phase_sources('3 phases', (1, 2)),
                        self.phase_sources('3 phases', (1, 2, 4))):
            with self.subTest(sources=sources):
                self.assertIsNone(source_count_comparison(question, sources))

    def test_source_count_proof_refuses_negated_ranges_and_duplicate_ordinal_titles(self):
        question = 'Does the stated phase count agree with the listed phases?'
        for declared in ('not 3 phases', 'at least 3 phases', '2–3 phases', '2 or 3 phases'):
            with self.subTest(declared=declared):
                self.assertIsNone(source_count_comparison(question, self.phase_sources(declared)))
        sources = self.phase_sources()
        sources[0]['content'] += ' • Phase 2 – A different roadmap (months):'
        self.assertIsNone(source_count_comparison(question, sources))

    def test_source_count_proof_never_combines_documents_or_pages(self):
        question = 'Does the stated phase count agree with the listed phases?'
        a = self.phase_sources(headings=(1, 2))[0]
        b = self.phase_sources(headings=(3, 4))[0]
        b.update(ref='S2', document_name='different-owned-source')
        self.assertIsNone(source_count_comparison(question, [a, b]))
        b.update(document_name=a['document_name'], page_number=2)
        self.assertIsNone(source_count_comparison(question, [a, b]))

    def test_source_count_proof_does_not_change_unrelated_questions(self):
        self.assertIsNone(source_count_comparison('List all four phases', self.phase_sources()))
        self.assertIsNone(source_count_comparison('What is the budget?', self.phase_sources()))
        self.assertIsNone(source_count_comparison('Does the stated phase count agree with the listed phases? Also give the budget.', self.phase_sources()))

    def test_request_deadline_is_propagated_without_repair(self):
        generate = Mock(side_effect=RequestDeadlineExceeded())
        with self.assertRaises(RequestDeadlineExceeded):
            generate_grounded_answer(QUESTION, CONTEXT, 'DOCUMENT', generate)
        self.assertEqual(generate.call_count, 1)

    def test_answer_stage_does_not_start_repair_after_original_deadline(self):
        clock = [100.0]
        def late_reply(_prompt):
            clock[0] = 102.0
            return OMITTED
        generate = Mock(side_effect=late_reply)
        with patch('services.request_budget.time.monotonic', side_effect=lambda: clock[0]), \
                patch('services.answer_service.cfg.ANSWER_MAX_RETRIES', 1):
            with self.assertRaises(RequestDeadlineExceeded), request_budget(1):
                generate_grounded_answer(QUESTION, CONTEXT, 'DOCUMENT', generate)
        self.assertEqual(generate.call_count, 1)

    def test_legacy_contract_has_no_new_coverage_retry(self):
        with patch.dict(os.environ, {'RAG_V2': '0'}):
            result, generate = self.answer([OMITTED])
        self.assertEqual(result['status'], 'answered')
        self.assertEqual(generate.call_count, 1)
        self.assertNotIn('coverage', result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
