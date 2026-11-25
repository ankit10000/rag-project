"""Synthetic regressions for bounded user references, live scope and operands."""
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from backend.errors import ApiError
from services.request_coverage import request_coverage
from services.tenure_calculation import answer_employment_duration, calculation_from_sources
from services.tenant_context import tenant_scope
from services.v2_evidence_recovery import explicit_document_scope
from services.v2_request_contract import build_request_contract


OWNER = '00000000-0000-4000-8000-000000000001'
TODAY = date(2026, 11, 25)


def users(*questions):
    return [{'role': 'user', 'content': q} for q in questions]


class RequestContractTests(unittest.TestCase):
    def test_challenge_rechecks_latest_user_task_after_unit_change(self):
        history = users('When did Eden join Ember Labs?', 'How many months?')
        history.insert(1, {'role': 'assistant', 'content': 'Slate Labs from January 1970. [S7]'})
        out = build_request_contract('Are you sure?', history, as_of=TODAY)
        self.assertEqual(out['resolved_question'], 'How many months did Eden work at ember labs?')
        self.assertEqual(out['previous_user_turns'], [0, 2])
        self.assertEqual(out['as_of'], '2026-11-25')

    def test_user_reference_never_uses_assistant_alone(self):
        out = build_request_contract('Calculate that.', [{'role':'assistant','content':'Quartz Ltd Jan 2020–2023.'}])
        self.assertEqual(out['intent'], 'clarify')

    def test_challenge_proposed_number_is_not_a_verified_operand(self):
        history=users('How many months did Eden work at Ember Labs?')
        out=build_request_contract('Are you sure? I thought it was 90 months.',history)
        self.assertEqual(out['resolved_question'], history[0]['content'])
        self.assertNotIn('90',out['resolved_question'])

    def test_change_to_education_then_duration_does_not_reuse_employer(self):
        history = users('When did Eden join Ember Labs?', 'What about his education?')
        out = build_request_contract('Where is this mentioned?', history)
        self.assertTrue(out['source_location'])
        self.assertEqual(out['resolved_question'], 'What are the academic qualifications of Eden?')
        self.assertEqual(build_request_contract('How many months?', history)['intent'], 'clarify')

    def test_document_scope_is_reauthorized_and_new_literal_overrides_prior(self):
        history = users('According to North CV.pdf, when did Eden join Ember Labs?')
        self.assertIn('North CV.pdf', build_request_contract('Which page?', history)['scope_question'])
        self.assertEqual(build_request_contract('Which page in West.pdf?',history)['scope_question'],'Which page in West.pdf?')
        self.assertEqual(build_request_contract('Compare Silver and Bronze in Plan.pdf.', history)['previous_user_turns'],[])

    def test_other_company_requires_a_unique_contrast(self):
        history=users('When did Eden join Ember Labs?', 'When did Eden join Slate Works?')
        out=build_request_contract('And the other company?',history)
        self.assertIn('join ember labs',out['resolved_question'])
        self.assertEqual(build_request_contract('And the other company?',history[:1])['intent'],'clarify')
        self.assertEqual(build_request_contract('And the other company?',history+users('When did Eden join Terra Works?'))['intent'],'clarify')

    def test_numeric_and_precision_contract_contains_only_requested_fields(self):
        self.assertEqual(build_request_contract('Give the budget.')['fields'],['budget'])
        fields=build_request_contract('Give the budget, team size and timeline.')['fields']
        self.assertEqual(fields,['budget','team','duration'])

    def test_simple_keyword_answer_is_incomplete_against_named_field_values(self):
        report = request_coverage('Give team size and timeline.', [{'ref':'S2','content':'Team size: 8 people. Timeline: 12 months.'}],
                                  'The team and timeline are known [S2].')
        self.assertEqual([f['id'] for f in report['concrete_missing']], ['team','duration'])
        self.assertTrue(all(f['evidence_state']=='SUPPORTED_DIRECT' for f in report['facets']))

    def test_answer_values_bind_to_their_specific_fields_and_refs(self):
        report=request_coverage('Give the team size and budget.',[
            {'ref':'S1','content':'Budget: 8 credits. Team size: 4 people.'},
            {'ref':'S2','content':'There were 4 tests.'}],
            'The team has 8 people [S1]. The budget is 8 credits [S2].')
        for facet in report['facets']:
            self.assertTrue(facet['unsupported_answer_clauses'])
            self.assertFalse(facet['answer_mentions'])

    def test_component_amounts_do_not_establish_total(self):
        report=request_coverage('Give the total budget and team size.',
            [{'ref':'S1','content':'Component budget: $300. Team size: 4 people.'}],
            'The total budget is $300 [S1]. The team consists of 4 people [S1].')
        budget,team=report['facets']
        self.assertEqual(budget['evidence_state'],'NOT_FOUND_IN_SEARCHED_SCOPE')
        self.assertTrue(budget['unsupported_answer_clauses'])
        self.assertTrue(team['answer_mentions'])

    def test_different_named_projects_do_not_establish_conflict(self):
        def state(text):
            report=request_coverage('Give the budget and team size.',[{'ref':'S1','content':text}])
            return report['facets'][0]['evidence_state']
        self.assertEqual(state('Project Red budget: $10. Project Blue budget: $20.'),'AMBIGUOUS')
        self.assertEqual(state('Project Red budget: $10. Project Red budget: $20.'),'CONFLICTING')

    def test_single_total_question_rejects_component_amount(self):
        report=request_coverage('What is the total project budget?',
            [{'ref':'S1','content':'Hardware budget: $500.'}], 'The budget is $500 [S1].')
        self.assertEqual(report['facets'][0]['evidence_state'],'NOT_FOUND_IN_SEARCHED_SCOPE')
        self.assertTrue(report['facets'][0]['unsupported_answer_clauses'])


class SourceScopeTests(unittest.TestCase):
    def resolve(self, question, rows):
        conn=MagicMock()
        conn.execute.return_value.fetchall.return_value=rows
        with tenant_scope(OWNER),patch('services.database.get_connection') as get:
            get.return_value.__enter__.return_value=conn
            return explicit_document_scope(question)

    def test_unknown_longer_name_and_mixed_missing_are_closed(self):
        owned=[('a','Plan.pdf','ready')]
        for q in ['Use PrivatePlan.pdf.', 'Use Draft Plan.pdf.', 'Compare Plan.pdf and Secret.pdf.']:
            with self.subTest(q=q):
                self.assertEqual(self.resolve(q,owned),[])

    def test_longer_exact_name_and_two_owned_names(self):
        rows=[('a','Plan.pdf','ready'),('b','Draft Plan.pdf','ready')]
        self.assertEqual(self.resolve('Read Draft Plan.pdf.',rows),['b'])
        self.assertEqual(self.resolve('Compare Draft Plan.pdf and Plan.pdf.',rows),['a','b'])

    def test_unready_is_operational_error_and_absent_stays_closed(self):
        for state in ['processing','failed']:
            with self.assertRaises(ApiError) as exc:
                self.resolve('Read Plan.pdf.',[('a','Plan.pdf',state)])
            self.assertEqual(exc.exception.code,'document_not_ready')
        self.assertEqual(self.resolve('Read Plan.pdf.',[]),[])


class PersonBindingTests(unittest.TestCase):
    @staticmethod
    def lookup(question,rows,headers=()):
        conn=MagicMock()
        conn.execute.return_value.fetchall.side_effect=[rows,headers]
        with tenant_scope(OWNER),patch('services.database.get_connection') as get:
            get.return_value.__enter__.return_value=conn
            return answer_employment_duration(question,scope=['owned'],as_of=TODAY)

    def test_wrong_name_cannot_borrow_labeled_employee_dates(self):
        text='Employee: Mira Vale. Employer: Ember Labs. Employment: Feb 2022 to Nov 2025.'
        out=self.lookup('When did Priya join Ember Labs?',[(10,'owned',1,text)])
        self.assertEqual(out['status'],'abstained')
        self.assertEqual(out['citations'],[])
        self.assertNotIn('2022',out['answer'])
        self.assertIsNone(calculation_from_sources('How long did Priya work at Ember Labs?',
             [{'ref':'S3','document_name':'owned','page_number':1,'chunk_id':10,'content':text}]))

    def test_same_owned_resume_heading_can_anchor_employment_elsewhere(self):
        employment=(10,'owned',2,'Ember Labs Feb 2022 – Nov 2025')
        heading=(11,'owned',1,'Eden Vale\nSoftware Engineer')
        out=self.lookup('How many months did Eden work at Ember Labs?',[employment],[heading])
        self.assertEqual(out['calculation']['total_months'],45)
        self.assertEqual([c['page'] for c in out['citations']],[2,1])
        sources=[{'ref':ref,'document_name':row[1],'page_number':row[2],'chunk_id':row[0],'content':row[3]}
                 for ref,row in [('S7',employment),('S1',heading)]]
        derived=calculation_from_sources('How many months did Eden work at Ember Labs?',sources)
        self.assertEqual(derived['calculation']['source_ref'],'S7')
        self.assertEqual(derived['validation']['cited_refs'],['S7','S1'])
        self.assertEqual([c['ref'] for c in derived['citations']],['S7','S1'])
        self.assertIn('Eden [S1]',derived['answer'])
        self.assertIn('45 months',derived['answer'])

    def test_cross_document_headings_are_never_identity_evidence(self):
        out=self.lookup('When did Eden join Ember Labs?',[(10,'owned',2,'Ember Labs Feb 2022 – Nov 2025')],
                        [(11,'different',1,'Eden Vale\nSoftware Engineer')])
        self.assertEqual(out['status'],'abstained')

    def test_two_named_people_in_one_document_are_not_one_person(self):
        text='Employee: Eden Vale. Employee: Eden Marsh. Employer: Ember Labs. Employment: Feb 2022 to Nov 2025.'
        out=self.lookup('When did Eden join Ember Labs?',[(10,'owned',1,text)])
        self.assertNotEqual(out['status'],'answered')
