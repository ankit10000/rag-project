"""Deterministic missing-evidence contract tests; no database/provider calls."""
import os
os.environ.setdefault('DATABASE_URL', 'postgresql://nobody@127.0.0.1:1/rag_test_scratch')
os.environ.setdefault('TESTSAFE_BLOCK_NETWORK', '1')
import testsafe
testsafe.require_scratch_db()

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from services.answer_service import classify_status, generate_grounded_answer
from services.citation_service import count_uncited_sentences
from services.context_assembly_service import assemble_context


def bundle(*contents):
    return assemble_context([{'chunk': (i, 'synthetic.txt', i, text, 1.),
                             'rrf_score': 1., 'rerank_score': 1.}
                            for i, text in enumerate(contents, 1)])


class AbstentionContractTests(unittest.TestCase):
    def answer(self, text, context, question='What is the requested information?'):
        with patch('services.answer_service.cfg.ANSWER_MAX_RETRIES', 0):
            return generate_grounded_answer(question, context, 'DOCUMENT', lambda _: '[DOCUMENT] '+text)

    def test_saved_fax_response_is_cited_abstention_without_rewriting_history(self):
        original = Path('ai_review/development/results.jsonl').read_bytes()
        rows = [json.loads(line) for line in original.splitlines()]
        old = rows[-1]['result']
        self.assertEqual(old['status'], 'answered')
        dataset = json.loads(Path('ai_review/development/dataset.json').read_text())
        case = dataset['cases'][-1]
        context = bundle(case['tier1_chunks'][0]['content'])
        out = self.answer(old['answer'], context, case['question'])
        self.assertEqual(out['status'], 'abstained')
        self.assertEqual([c['ref'] for c in out['citations']], ['S1'])
        self.assertEqual(out['answer'], old['answer'])
        self.assertEqual(Path('ai_review/development/results.jsonl').read_bytes(), original)

    def test_explicit_negative_service_fact_stays_answered_and_cited(self):
        text = 'The observatory does not provide a fax service.'
        out = self.answer(text+' [S1]', bundle(text))
        self.assertEqual(out['status'], 'answered')
        self.assertEqual(len(out['citations']), 1)

    def test_singular_address_and_saved_postfix_partial(self):
        original = Path('ai_review/postfix_development/results.jsonl').read_bytes()
        rows = [json.loads(line) for line in original.splitlines()]
        saved = next(row for row in rows if row['expected_kind'] == 'partial_information')
        dataset = json.loads(Path('ai_review/postfix_development/dataset.json').read_text())
        case = next(case for case in dataset['cases'] if case['id'] == saved['id'])
        context = bundle(case['tier1_chunks'][0]['content'])
        for text in ('The policy does not provide a mailing address [S1].',
                     'Regarding the mailing address, the policy does not provide a mailing address [S1].',
                     'The policy does not provide mailing addresses [S1].'):
            with self.subTest(text=text):
                self.assertEqual(self.answer(text, context)['status'], 'abstained')
        out = self.answer(saved['result']['answer'], context, case['question'])
        self.assertEqual(out['status'], 'partial')
        self.assertEqual(out['answer'], saved['result']['answer'])
        self.assertEqual([citation['ref'] for citation in out['citations']], ['S1'])
        self.assertEqual(saved['result']['status'], 'answered')
        self.assertFalse(saved['technical']['policy_pass'])
        self.assertEqual(Path('ai_review/postfix_development/results.jsonl').read_bytes(), original)

    def test_document_information_omission_can_retain_a_valid_citation(self):
        text = 'The policy does not provide a telephone number.'
        out = self.answer(text+' [S1]', bundle(text))
        self.assertEqual(out['status'], 'abstained')
        self.assertEqual(len(out['citations']), 1)

    def test_same_phrase_with_real_world_subject_is_not_a_blanket_abstention(self):
        text = 'The company does not provide a telephone number.'
        out = self.answer(text+' [S1]', bundle(text))
        self.assertEqual(out['status'], 'answered')

    def test_cited_source_alignment_does_not_use_other_passages(self):
        context = bundle('The company provides emergency care.',
                         'The policy does not provide emergency care information.')
        text = 'The company does not provide emergency care [S1].'
        # This is a factual assertion, not an abstention. Status classification
        # does not claim to prove its entailment or approve the contradiction.
        self.assertEqual(classify_status(text, {'synthetic.txt'}, True, context['sources']), 'answered')
        other = bundle('The policy does not provide a telephone number.')
        self.assertEqual(classify_status('The clinic does not provide emergency care [S1].',
                         {'synthetic.txt'}, True, other['sources']), 'answered')

    def test_negative_containment_and_availability_are_not_missing_evidence(self):
        for text in ('The product does not contain latex.',
                     'Wheelchair access is not available.',
                     'The policy does not provide emergency care.'):
            with self.subTest(text=text):
                out = self.answer(text+' [S1]', bundle(text))
                self.assertEqual(out['status'], 'answered')
                self.assertEqual(len(out['citations']), 1)

    def test_incidental_information_words_in_excluded_benefits_are_not_gaps(self):
        for text in ('The policy does not provide refunds of tuition fees.',
                     'The policy does not provide fixed-rate coverage.'):
            with self.subTest(text=text):
                out = self.answer(text+' [S1]', bundle(text))
                self.assertEqual(out['status'], 'answered')
                self.assertEqual(len(out['citations']), 1)

    def test_polite_prefaces_are_not_an_answered_part(self):
        for text in ("Sorry, I couldn't find the requested information in the documents.",
                     "I'm sorry, but the documents do not state a fax number.",
                     'Unfortunately, the documents do not state a fax number.'):
            with self.subTest(text=text):
                out = self.answer(text, bundle('Only the visitor fee is listed.'))
                self.assertEqual(out['status'], 'abstained')
                self.assertEqual(out['citations'], [])

    def test_uncited_negative_facts_still_need_evidence(self):
        for text in ('The product does not contain any latex.',
                     'The clinic does not provide emergency care.'):
            with self.subTest(text=text):
                out = self.answer(text, bundle(text))
                self.assertEqual(out['status'], 'unverified')
                self.assertGreater(count_uncited_sentences(text), 0)

    def test_mixed_facts_and_document_gaps_are_partial(self):
        context = bundle('The fee is 83 credits. The policy does not provide a fax number.')
        for text in ('The fee is 83 credits [S1]. The policy does not provide a fax number [S1].',
                     'The fee is 83 credits [S1], but the fax number is not stated.'):
            with self.subTest(text=text):
                out = self.answer(text, context)
                self.assertEqual(out['status'], 'partial')
                self.assertEqual(len(out['citations']), 1)

    def test_real_uncited_abstentions_remain_accepted(self):
        for text in ("I couldn't find the requested information in the documents.",
                     'The documents do not state the fax number.',
                     'No information about the fax number is provided.',
                     'Not enough information to answer the question.',
                     'Insufficient information about the requested number.'):
            with self.subTest(text=text):
                out = self.answer(text, bundle('Only the visitor permit fee is listed.'))
                self.assertEqual(out['status'], 'abstained')
                self.assertEqual(out['citations'], [])

    def test_passive_document_gaps_do_not_become_negative_service_facts(self):
        for text in ('The fax number is not provided.',
                     'Accepted cards are not specified.'):
            with self.subTest(text=text):
                out = self.answer(text+' [S1]', bundle(text))
                self.assertEqual(out['status'], 'abstained')
                self.assertEqual(len(out['citations']), 1)

    def test_missing_information_clause_does_not_exempt_an_uncited_fact(self):
        text = 'The document does not state a fax number, but assistance is free.'
        self.assertGreater(count_uncited_sentences(text), 0)
        out = self.answer(text, bundle('The document does not state a fax number.'))
        self.assertEqual(out['status'], 'unverified')

    def test_unknown_citations_do_not_turn_into_valid_abstentions(self):
        out = self.answer('The policy does not provide a telephone number [S9].',
                          bundle('The policy does not provide a telephone number.'))
        self.assertEqual(out['status'], 'unverified')

    def test_document_gap_with_no_retrieval_is_valid_in_mixed_routing(self):
        out = generate_grounded_answer('What is the refund window?', bundle(), 'MIXED',
            lambda _: '[DOCUMENT] The documents do not contain the refund window.')
        self.assertEqual(out['status'], 'abstained')
        self.assertEqual(out['attempts'], 1)
        self.assertEqual(out['citations'], [])

    def test_three_argument_status_api_and_conflict_are_preserved(self):
        self.assertEqual(classify_status('The fee is 83.', {'a'}, True), 'answered')
        self.assertEqual(classify_status("I couldn't find the information.", set(), False), 'abstained')
        self.assertEqual(classify_status('The sources disagree on the fee [S1][S2].', {'a','b'}, True), 'conflict')
        self.assertEqual(classify_status('The clinic does not provide emergency care [S1].',
            {'a'}, True, [{'ref':'S1','content':None}]), 'answered')


if __name__ == '__main__':
    unittest.main()
