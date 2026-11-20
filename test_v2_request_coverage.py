"""Provider-free tests for conservative explicit request coverage diagnostics."""
import copy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from services.request_coverage import (build_request_plan, coverage_feedback,
                                       coverage_prompt, decompose_question,
                                       request_coverage)


class CoverageTests(unittest.TestCase):
    def test_compound_fields_have_bounded_deterministic_queries(self):
        question = 'According to Project.pdf, give the budget, team size and development duration.'
        plan = build_request_plan(question)
        self.assertEqual(plan['mode'], 'fields')
        self.assertEqual([f['id'] for f in plan['facets']], ['budget', 'team', 'duration'])
        queries = decompose_question(question)
        self.assertEqual(len(queries), 3)
        self.assertTrue(all('According to Project.pdf:' in q for q in queries))
        self.assertNotIn('duration', queries[0])
        self.assertIn('team', queries[1])
        self.assertEqual(decompose_question(question, 1), queries[:1])
        self.assertEqual(decompose_question(question, 0), [])

    def test_single_fact_does_not_decompose_or_require_extra_generation(self):
        self.assertEqual(build_request_plan('What is the budget?')['mode'], 'none')
        self.assertEqual(decompose_question('What is the budget?'), [])
        self.assertEqual(coverage_prompt(request_coverage('What is the budget?', [])), '')

    def test_missing_requested_field_requires_actual_source_signal(self):
        sources = [{'ref': 'S1', 'content': 'Development takes 2–3 years. Estimated team: 10–15 people. Rough budget: $1M–$5M.'}]
        report = request_coverage('Give budget, team and duration.', sources, 'The budget is $1M–$5M and team is 10–15 people [S1].')
        self.assertEqual([f['id'] for f in report['concrete_missing']], ['duration'])
        self.assertIn('S1', coverage_feedback(report))
        self.assertIn('Do not invent', coverage_feedback(report))

    def test_no_false_repair_for_unobserved_source_fact(self):
        report = request_coverage('Give budget and team size.', [{'ref': 'S1', 'content': 'The budget is $2M.'}], 'The budget is $2M. Team size is not stated [S1].')
        self.assertEqual(report['context_unobserved'], ['team'])
        self.assertEqual(report['concrete_missing'], [])
        self.assertEqual(coverage_feedback(report), '')

    def test_complete_compound_synonyms_do_not_force_repair(self):
        sources = [{'ref': 'S1', 'content': 'Budget $2M. Team of 10 people. Timeline 3 years.'}]
        report = request_coverage('Give budget, team, duration.', sources, '$2M [S1]. 10 people [S1]. 3 years [S1].')
        self.assertEqual(report['concrete_missing'], [])
        self.assertIn('not semantic entailment', report['caveat'])

    def test_numbered_source_heading_coverage_exposes_lost_items(self):
        question = 'List all four implementation phases and their month ranges.'
        sources = [{'ref': 'S1', 'content': 'Phase 1 – Planning 0–6. Phase 2 – MVP 6–15.'},
                   {'ref': 'S2', 'content': 'Phase 3 – Pilot 15–21. Phase 4 – Launch 21–30.'}]
        report = request_coverage(question, sources, 'Phase 1 Planning 0–6 [S1]. Phase 2 MVP 6–15 [S1].')
        self.assertEqual(report['mode'], 'enumeration')
        self.assertEqual(report['enumeration_count'], 4)
        self.assertEqual([f['id'] for f in report['concrete_missing']], ['phase_3', 'phase_4'])
        self.assertEqual(report['concrete_missing'][0]['evidence_refs'], ['S2'])
        self.assertEqual(decompose_question(question), [])

    def test_source_heading_titles_cover_list_without_literal_phase_numbers(self):
        sources = [{'ref': 'S1', 'content': 'Phase 1 – Planning & Prototype (0–6 mo): requirements. Phase 2 – MVP Development (6–15 mo): build. Phase 3 – Pilot & Feedback (15–21 mo): evaluate. Phase 4 – Launch & Scale (21–30 mo): launch.'}]
        answer = 'Planning and Prototype: 0–6 months. MVP Development: 6–15 months. Pilot & Feedback: 15–21 months. Launch and Scale: 21–30 months [S1].'
        report = request_coverage('List all four phases.', sources, answer)
        self.assertEqual(report['concrete_missing'], [])
        self.assertEqual(report['facets'][0]['source_titles'], ['Planning & Prototype'])

    def test_list_count_never_invents_unobserved_phase_evidence(self):
        report = request_coverage('List all four phases.', [{'ref': 'S1', 'content': 'Phase 1 Planning. Phase 2 MVP.'}], 'Phase 1 Planning. Phase 2 MVP [S1].')
        self.assertEqual(report['context_unobserved'], ['phase_3', 'phase_4'])
        self.assertEqual(report['concrete_missing'], [])

    def test_uncounted_list_only_checks_observed_headings(self):
        report = request_coverage('List each stage.', [{'ref': 'S1', 'content': 'Stage 2 Build. Stage 3 Launch.'}], 'Stage 2 Build [S1].')
        self.assertEqual([f['id'] for f in report['concrete_missing']], ['stage_3'])
        self.assertIsNone(report['enumeration_count'])

    def test_comparison_retains_entity_identity(self):
        question = 'Compare on-premises and public cloud hosting costs according to Plan.pdf.'
        sources = [{'ref': 'S1', 'content': 'On-Premises: high upfront cost.'},
                   {'ref': 'S2', 'content': 'Public Cloud: no upfront cost.'}]
        report = request_coverage(question, sources, 'On premises has high upfront cost [S1].')
        self.assertEqual(report['mode'], 'comparison')
        self.assertEqual([f['label'] for f in report['facets']], ['on-premises', 'public cloud'])
        self.assertEqual([f['label'] for f in report['concrete_missing']], ['public cloud'])
        self.assertEqual(len(decompose_question(question)), 2)

    def test_ambiguous_pronoun_comparison_does_not_guess(self):
        self.assertEqual(build_request_plan('Compare it and that.')['mode'], 'none')

    def test_comparison_source_filename_is_scope_not_entity_name(self):
        plan = build_request_plan('Compare on-premises and public cloud hosting in Executive Summary.pdf.')
        self.assertEqual([f['label'] for f in plan['facets']], ['on-premises', 'public cloud'])

    def test_hosting_qualifier_does_not_hide_complete_deployment_comparison(self):
        question = 'Compare on-premises and public cloud hosting in Executive Summary.pdf in terms of upfront cost and scalability.'
        sources = [{'ref': 'S1', 'content': 'On-Premises: high upfront cost; limited scalability.'},
                   {'ref': 'S2', 'content': 'Public Cloud: no upfront cost; virtually unlimited scalability.'}]
        report = request_coverage(question, sources, 'On-premises has high upfront cost and limited scalability [S1]. Public cloud has no upfront cost and virtually unlimited scalability [S2].')
        self.assertEqual([f['label'] for f in report['facets']], ['on-premises', 'public cloud'])
        self.assertEqual(report['concrete_missing'], [])
        self.assertTrue(all(f['evidence_refs'] for f in report['facets']))
        arbitrary = build_request_plan('Compare Cedar and Acme Hosting.')
        self.assertEqual(arbitrary['facets'][1]['label'], 'Acme Hosting')

    def test_generic_compound_clause_decomposition_does_not_claim_coverage(self):
        question = 'According to Plan.pdf, which engine generates speech and how is the generated content filtered?'
        queries = decompose_question(question)
        self.assertEqual(len(queries), 2)
        self.assertIn('which engine generates speech', queries[0])
        self.assertNotIn('content filtered', queries[0])
        self.assertIn('how is the generated content filtered', queries[1])
        report = request_coverage(question, [{'ref': 'S1', 'content': 'The speech engine is local.'}], 'Speech is local [S1].')
        self.assertEqual(report['mode'], 'clauses')
        self.assertEqual(report['concrete_missing'], [])

    def test_explicit_negative_fact_is_mentioned_not_rejected(self):
        sources = [{'ref': 'S1', 'content': 'No fax service is offered. Phone support is available.'}]
        report = request_coverage('Give fax and phone information.', sources, 'No fax service is offered. Phone support is available [S1].')
        self.assertEqual(report['concrete_missing'], [])
        self.assertTrue(all(f['answer_mentions'] for f in report['facets']))

    def test_absence_reporting_remains_accepted_without_fabricated_values(self):
        report = request_coverage('Give fax and phone information.', [{'ref': 'S1', 'content': 'Fax number is not stated. Phone number is not stated.'}], 'The fax and phone numbers are not stated [S1].')
        self.assertEqual(report['concrete_missing'], [])

    def test_supported_requested_fact_is_not_covered_by_keyword_in_refusal(self):
        sources = [{'ref': 'S1', 'content': 'Budget: $1M–$5M. Team: 10–15 people.'}]
        report = request_coverage('Give budget and team.', sources, 'Team is 10–15 people [S1]. Budget is not provided.')
        self.assertEqual([f['id'] for f in report['concrete_missing']], ['budget'])
        self.assertTrue(report['facets'][0]['refused_supported_item'])
        gap = request_coverage('Give budget and team.', [{'ref': 'S1', 'content': 'Budget is not stated. Team is 10 people.'}], 'Budget is not stated. Team is 10 people [S1].')
        self.assertEqual(gap['concrete_missing'], [])

    def test_cross_page_database_cloud_budget_has_two_focused_queries(self):
        question = 'According to Executive Summary.pdf, which database stores user accounts and what is the proposed annual cloud budget?'
        queries = decompose_question(question)
        self.assertEqual(len(queries), 2)
        self.assertIn('annual cloud budget', queries[0])
        self.assertNotIn('which database', queries[0])
        self.assertIn('which database stores user accounts', queries[1])
        self.assertNotIn('annual cloud budget', queries[1])

    def test_core_and_additional_features_are_distinct_requested_groups(self):
        question = 'List core MVP features and suggested additional features.'
        plan = build_request_plan(question)
        self.assertEqual(plan['mode'], 'fields')
        self.assertEqual([f['id'] for f in plan['facets']], ['core_features', 'additional_features'])
        report = request_coverage(question, [{'ref': 'S1', 'content': 'Core Features (MVP): video lessons.'}, {'ref': 'S2', 'content': 'Suggested Additional Features: offline access.'}], 'Core MVP features include video lessons [S1].')
        self.assertEqual([f['id'] for f in report['concrete_missing']], ['additional_features'])

    def test_additional_group_is_not_relabelled_as_later_delivery(self):
        question = 'List core MVP features and suggested additional features.'
        report = request_coverage(question, [{'ref': 'S1', 'content': 'Suggested Additional Features: Performance Analytics.'},
                                             {'ref': 'S2', 'content': 'Feature prioritization table: Performance Analytics — MVP; Gamification — Later.'}])
        additional = next(facet for facet in report['facets'] if facet['id'] == 'additional_features')
        self.assertEqual(additional['label'], 'suggested additional features')
        self.assertNotIn('later', additional['query_terms'])
        self.assertEqual(additional['evidence_refs'], ['S1'])
        prompt = coverage_prompt(report)
        self.assertIn('"additional" does not by itself mean "later"', prompt)
        self.assertIn('If the supplied narrative and a table assign differing priorities', prompt)
        self.assertIn('do not silently reconcile', prompt)
        self.assertIn('without evidence', prompt)
        later = build_request_plan('Give core features and later features.')
        self.assertEqual(next(f['label'] for f in later['facets'] if f['id'] == 'additional_features'), 'later features')

    def test_all_feature_list_checks_actual_bullet_headings_not_just_group_word(self):
        source = {'ref': 'S1', 'document_name': 'plan.pdf', 'page_number': 2,
                  'content': 'Suggested Additional Features: • Adaptive Learning Paths: personalize. • Gamification: badges. • Multilingual Support: Hindi and regional languages. • Offline Access & Mobile App: download videos/notes.'}
        question = 'List all core MVP features and suggested additional features.'
        report = request_coverage(question, [source], 'Additional features include Adaptive Learning Paths and Gamification [S1].')
        missing = {item['label'] for item in report['concrete_missing']}
        self.assertIn('Multilingual Support', missing)
        self.assertIn('Offline Access & Mobile App', missing)
        self.assertNotIn('Gamification', missing)
        complete = request_coverage(question, [source], 'Additional features: Adaptive Learning Paths; Gamification; Multilingual Support; Offline Access and Mobile App [S1].')
        self.assertEqual(complete['concrete_missing'], [])

    def test_feature_check_does_not_borrow_bullets_from_unrelated_page(self):
        sources = [{'ref': 'S1', 'document_name': 'plan.pdf', 'page_number': 2,
                    'content': 'Suggested Additional Features: • Multilingual Support: Hindi.'},
                   {'ref': 'S2', 'document_name': 'plan.pdf', 'page_number': 15,
                    'content': '• Team: ten people. • Milestones: launch.'}]
        report = request_coverage('List all features.', sources, 'Multilingual Support [S1].')
        self.assertEqual(report['concrete_missing'], [])
        self.assertEqual([f['label'] for f in report['facets']], ['Multilingual Support'])

    def test_feature_paraphrases_cover_vocabulary_families_without_template_words(self):
        sources = [{'ref': 'S1', 'content': 'Core Features: • AI-generated Video Lessons: lectures. • Topic-wise Notes & Summaries: notes. • Test Series & Quizzes: quizzes. • Question Bank & Q&A: questions.'},
                   {'ref': 'S2', 'content': 'Suggested Additional Features: • Multilingual Support: Hindi and regional languages. • Offline Access & Mobile App: downloads.'}]
        question = 'List all core MVP features and all suggested additional features.'
        complete = request_coverage(question, sources, 'Core MVP: AI-generated video lectures, topic-wise notes, quizzes and question banks [S1]. Additional: Hindi and regional languages; downloadable videos for offline study [S2].')
        self.assertEqual(complete['concrete_missing'], [])
        incomplete = request_coverage(question, sources, 'Core MVP: video lessons, summaries, test series and Q&A [S1]. Additional features are planned [S2].')
        self.assertEqual({f['label'] for f in incomplete['concrete_missing']}, {'Multilingual Support', 'Offline Access & Mobile App'})

    def test_unknown_heading_paraphrase_is_uncertain_not_forced_partial(self):
        report = request_coverage('List all features.', [{'ref': 'S1', 'content': 'Additional Features: • Neuroadaptive Synergy Control: selects a useful pacing strategy.'}], 'The app selects a useful pacing strategy [S1].')
        self.assertEqual(report['concrete_missing'], [])
        self.assertEqual(report['diagnostic_missing'], ['heading_neuroadaptive_synergy_control'])

    def test_saved_live02_complete_answer_passes_one_generation(self):
        # Read the immutable restricted development artifact; do not copy its
        # source text into ordinary application logs or alter historical data.
        root = Path(__file__).parent / 'v2_evidence/reliability-20261119/live-02'
        if not (root / 'long_section.json').exists():
            self.skipTest('optional immutable live-02 development artifact is not present')
        record = json.loads((root / 'long_section.json').read_text())
        trace = json.loads((root / 'long_section-trace.json').read_text())
        request = next(event['raw'] for event in trace['events'] if event['stage'] == 'generation_request')
        bundle = {'sources': request['sources'], 'context_text': request['context_text']}
        answer = record['result']['answer']
        report = request_coverage(record['question'], bundle['sources'], answer)
        self.assertEqual(report['concrete_missing'], [])
        from services.answer_service import generate_grounded_answer
        generate = Mock(return_value='[DOCUMENT] ' + answer)
        with patch.dict(os.environ, {'RAG_V2': '1'}):
            outcome = generate_grounded_answer(record['question'], bundle, 'DOCUMENT', generate)
        self.assertEqual(outcome['status'], 'answered')
        self.assertEqual(generate.call_count, 1)

    def test_source_and_answer_are_not_mutated_and_citation_text_not_evidence(self):
        sources = [{'ref': 'S1', 'content': 'Budget is $1M. Team of five people.'}]
        before = copy.deepcopy(sources)
        request_coverage('Give budget and team.', sources, 'Budget $1M [S1].')
        self.assertEqual(sources, before)
        self.assertEqual(request_coverage('Give budget and team.', [], 'Budget and team [S1].')['concrete_missing'], [])

    def test_numbered_list_bound_and_pure_empty_inputs(self):
        self.assertEqual(build_request_plan('List all 99 phases.')['mode'], 'none')
        self.assertEqual(request_coverage(None, None)['facets'], [])
        report = request_coverage('List all four phases.', [{'ref': 'S1', 'content': 'Phase 1 A.'}])
        self.assertFalse(report['answer_checked'])
        self.assertEqual(report['concrete_missing'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
