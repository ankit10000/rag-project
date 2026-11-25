"""Actual GOC/Present transcript: trusted date, informal requests and follow-ups."""
import os
os.environ.setdefault('DATABASE_URL','postgresql://nobody@127.0.0.1:1/rag_test_scratch')
os.environ.setdefault('TESTSAFE_BLOCK_NETWORK','1')
import testsafe
testsafe.require_scratch_db()

from datetime import date
import unittest
from unittest.mock import patch,MagicMock
from services.tenure_calculation import (duration_intent,joining_intent,resolve_employer,
    result_from_rows,answer_employment_duration,calculation_from_sources)
from services.tenant_context import tenant_scope

AS_OF=date(2026,11,25)
TEXT='Full Stack Developer | GOC Productions | Apr 2026 – Present · Full-time'
ROWS=[(31,'owned-resume',1,TEXT)]
OWNER='00000000-0000-4000-8000-000000000001'
EXPERIENCE='how much experience to Ankit in GOC Productions'
JOINING='when Ankit joined the Goc Productions company'
FOLLOWUP='can you calculate exact year and months'
TYPO='how much months he spended in GO Productions?'
HISTORY=[{'role':'user','content':EXPERIENCE},
         {'role':'assistant','content':'Ankit worked from Jan 1900 to Jan 2099.'}]


class PresentTenureTests(unittest.TestCase):
    def lookup(self,question,history=None):
        c=MagicMock();c.execute.return_value.fetchall.return_value=ROWS
        with tenant_scope(OWNER),patch('services.database.get_connection') as get,patch('services.tenure_calculation._as_of_date',return_value=AS_OF):
            get.return_value.__enter__.return_value=c
            return answer_employment_duration(question,history)

    def test_exact_informal_experience_question_is_a_duration_request(self):
        self.assertTrue(duration_intent(EXPERIENCE))
        self.assertEqual(resolve_employer(EXPERIENCE,[]),['goc','productions'])

    def test_present_requires_an_explicit_trusted_as_of_date(self):
        self.assertIsNone(result_from_rows(ROWS,['goc','productions']))
        with self.assertRaises(TypeError):result_from_rows(ROWS,['goc','productions'],as_of='2099-01-01')

    def test_actual_source_has_seven_months_with_explicit_current_date_and_precision(self):
        out=result_from_rows(ROWS,['goc','productions'],as_of=AS_OF)
        self.assertEqual(out['status'],'answered')
        self.assertEqual(out['calculation']['total_months'],7)
        self.assertEqual(out['calculation']['years'],0)
        self.assertEqual(out['calculation']['remaining_months'],7)
        self.assertEqual(out['calculation']['as_of'],'2026-11-25')
        self.assertEqual(out['calculation']['end_source'],'application_clock_for_explicit_present')
        self.assertIn('April 2026 to Present',out['answer'])
        self.assertIn('25 November 2026',out['answer'])
        self.assertIn('approximately 7 months',out['answer'])
        self.assertIn('exact days are not specified',out['answer'])
        self.assertNotIn('Productions |',out['answer'])

    def test_informal_experience_lookup_uses_the_trusted_clock(self):
        out=self.lookup(EXPERIENCE)
        self.assertEqual(out['calculation']['total_months'],7)
        self.assertEqual(out['citations'][0]['chunk_id'],31)

    def test_joining_question_returns_source_start_without_unasked_duration(self):
        self.assertTrue(joining_intent(JOINING))
        out=self.lookup(JOINING)
        self.assertIn('April 2026',out['answer'])
        self.assertNotIn('calculation',out)
        self.assertNotIn('7 months',out['answer'])
        self.assertEqual(out['status'],'answered')

    def test_bare_followup_uses_user_employer_reference_not_assistant_dates(self):
        self.assertTrue(duration_intent(FOLLOWUP))
        self.assertEqual(resolve_employer(FOLLOWUP,HISTORY),['goc','productions'])
        out=self.lookup(FOLLOWUP,HISTORY)
        self.assertEqual(out['calculation']['total_months'],7)
        self.assertEqual(out['calculation']['start'],'2026-04')
        self.assertIsNone(resolve_employer(FOLLOWUP,[HISTORY[1]]))
        self.assertIsNone(resolve_employer(FOLLOWUP,[]))

    def test_pronoun_typo_followup_has_one_unique_recent_user_reference(self):
        self.assertTrue(duration_intent(TYPO))
        self.assertEqual(resolve_employer(TYPO,HISTORY),['goc','productions'])
        self.assertEqual(self.lookup(TYPO,HISTORY)['calculation']['total_months'],7)

    def test_typo_is_not_a_global_company_alias_or_cross_tenant_guess(self):
        self.assertEqual(resolve_employer(TYPO,[]),['go','productions'])
        self.assertEqual(resolve_employer('how many months did Ankit work in GO Productions?',HISTORY),['go','productions'])
        ambiguous=HISTORY+[{'role':'user','content':'How long did he work at GOP Productions?'}]
        self.assertEqual(resolve_employer(TYPO,ambiguous),['go','productions'])
        self.assertEqual(resolve_employer('How many months did he work at Another Firm?',HISTORY),['another','firm'])

    def test_dates_in_a_question_cannot_replace_the_clock(self):
        out=self.lookup('As of December 2099, '+EXPERIENCE)
        self.assertEqual(out['calculation']['total_months'],7)
        self.assertEqual(out['calculation']['as_of'],'2026-11-25')

    def test_current_period_does_not_roll_forward_closed_jobs(self):
        rows=[(31,'owned-resume',1,'GOC Productions Apr 2026 – Sep 2026')]
        self.assertEqual(result_from_rows(rows,['goc','productions'],as_of=AS_OF)['calculation']['total_months'],5)

    def test_future_start_reverse_dates_missing_start_and_other_employer_are_not_invented(self):
        for text in ('GOC Productions Dec 2026 – Present',
                     'GOC Productions Present',
                     'GOC Productions Nov 2026 – Apr 2026',
                     'GOC Productions project. Other Firm Apr 2026 – Present',
                     'GOC Productions.\n\nEmployment: Apr 2026 – Present'):
            with self.subTest(text=text):
                self.assertIsNone(result_from_rows([(31,'owned-resume',1,text)],['goc','productions'],as_of=AS_OF))

    def test_ambiguous_owned_documents_or_stints_still_require_clarification(self):
        for extra in ((32,'other-resume',1,TEXT),(32,'owned-resume',1,'GOC Productions Jan 2025 – Present')):
            out=result_from_rows(ROWS+[extra],['goc','productions'],as_of=AS_OF)
            self.assertEqual(out['status'],'abstained')
            self.assertNotIn('calculation',out)

    def test_selected_context_calculation_keeps_original_ref_and_page(self):
        sources=[{'ref':'S3','chunk_id':31,'document_name':'owned-resume','page_number':1,'content':TEXT}]
        with patch('services.tenure_calculation._as_of_date',return_value=AS_OF):
            out=calculation_from_sources(EXPERIENCE,sources)
        self.assertEqual(out['calculation']['source_ref'],'S3')
        self.assertIn('[S3]',out['answer'])
        self.assertIsNone(calculation_from_sources(JOINING,sources))

    def test_direct_answers_require_owner_and_never_call_generation_or_rewriting(self):
        from services import rag_service as rag
        with patch('services.database.get_connection') as get:
            with self.assertRaises(PermissionError):answer_employment_duration(EXPERIENCE)
            get.assert_not_called()
        for question,history in ((EXPERIENCE,[]),(JOINING,[]),(FOLLOWUP,HISTORY),(TYPO,HISTORY)):
            conn=MagicMock();conn.execute.return_value.fetchall.return_value=ROWS
            with self.subTest(question=question),tenant_scope(OWNER),patch.dict(os.environ,{'RAG_V2':'1'}),patch('services.database.get_connection') as get,patch('services.tenure_calculation._as_of_date',return_value=AS_OF),patch.object(rag,'generate_answer',side_effect=AssertionError('no provider')),patch.object(rag,'rewrite_query',side_effect=AssertionError('no provider')):
                get.return_value.__enter__.return_value=conn
                self.assertEqual(rag.ask_question(question,history=history)['status'],'answered')

    def test_generated_arbitrary_numbers_and_standalone_fuzzy_aliases_remain_blocked(self):
        from services.grounding_service import unsupported_numbers
        sources=[{'ref':'S1','content':TEXT,'document_name':'owned-resume'}]
        self.assertTrue(unsupported_numbers('He worked for 99 months [S1].',sources))
        self.assertIsNone(result_from_rows(ROWS,['go','productions'],as_of=AS_OF))

    def test_literal_go_employer_wins_over_a_history_typo_correction(self):
        sources=[{'ref':'S3','chunk_id':31,'document_name':'owned-resume','page_number':1,'content':TEXT},
                 {'ref':'S4','chunk_id':32,'document_name':'owned-resume','page_number':2,'content':'GO Productions Oct 2026 – Present'}]
        with patch('services.tenure_calculation._as_of_date',return_value=AS_OF):
            out=calculation_from_sources(TYPO,sources,HISTORY)
            self.assertEqual(out['calculation']['total_months'],1)
            self.assertEqual(out['calculation']['source_ref'],'S4')
            sources[1]['content']='GO Productions does not list employment dates.'
            self.assertIsNone(calculation_from_sources(TYPO,sources,HISTORY))

    def test_bare_followup_after_saved_typo_keeps_the_source_verified_employer(self):
        history=HISTORY+[{'role':'user','content':FOLLOWUP},
                         {'role':'assistant','content':'Dates are repeated.'},
                         {'role':'user','content':TYPO},
                         {'role':'assistant','content':'GOC Productions Apr 2026 to Present.'}]
        self.assertEqual(resolve_employer(FOLLOWUP,history),['goc','productions'])
        self.assertEqual(self.lookup(FOLLOWUP,history)['calculation']['total_months'],7)

    def test_bare_followup_after_typo_still_prefers_a_literal_existing_go_record(self):
        history=HISTORY+[{'role':'user','content':TYPO}]
        sources=[{'ref':'S3','chunk_id':31,'document_name':'owned-resume','page_number':1,'content':TEXT},
                 {'ref':'S4','chunk_id':32,'document_name':'owned-resume','page_number':2,'content':'GO Productions Oct 2026 – Present'}]
        with patch('services.tenure_calculation._as_of_date',return_value=AS_OF):
            out=calculation_from_sources(FOLLOWUP,sources,history)
        self.assertEqual(out['calculation']['total_months'],1)
        self.assertEqual(out['calculation']['source_ref'],'S4')


if __name__=='__main__':unittest.main()
