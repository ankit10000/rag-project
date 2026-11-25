"""25 Nov browser failures: deterministic arithmetic and scoped missing information."""
import os
os.environ.setdefault('DATABASE_URL','postgresql://nobody@127.0.0.1:1/rag_test_scratch')
os.environ.setdefault('TESTSAFE_BLOCK_NETWORK','1')
import testsafe
testsafe.require_scratch_db()

import unittest
from unittest.mock import patch,MagicMock
from services.tenure_calculation import result_from_rows,calculation_from_sources
from services.answer_service import generate_grounded_answer,classify_status

TEXT=('Employee: Mira Vale. Employer: Cedarbridge Labs.\n'
      'Employment: February 2022 to November 2025.\n'
      'Education: Bachelor of Technology in Computer Science.\n'
      'Institution: Eastmere Institute of Technology. Study period: 2016 to 2020.\n'
      'The office explicitly does not provide a fax service.')
QUESTION=("Using only RAG_E2E_Check_20261125.pdf: what are Mira Vale's employment start "
          'and end dates at Cedarbridge Labs, how long did she work there in years and '
          'months, and what degree and institution did she attend? Cite the source page.')

def source(text=TEXT,ref='S4',document='owned-doc',page=1,cid=17):
    return dict(content=text,ref=ref,document_name=document,page_number=page,chunk_id=cid)


class BrowserReliabilityHotfixTests(unittest.TestCase):
    def answer(self,text,sources=None,question=QUESTION):
        sources=sources or [source()]
        bundle={'sources':sources,'context_text':'\n'.join(f"[{s['ref']}] {s['content']}" for s in sources)}
        prompts=[]
        def generate(prompt):
            prompts.append(prompt)
            return '[DOCUMENT] '+text
        with patch.dict(os.environ,{'RAG_V2':'1'}),patch('services.answer_service.cfg.ANSWER_MAX_RETRIES',0):
            result=generate_grounded_answer(question,bundle,'DOCUMENT',generate)
        self.assertEqual(len(prompts),1,'one normal answer attempt; no extra provider call')
        return result,prompts[0]

    def test_labeled_employment_field_binds_dates_and_excludes_label_from_name(self):
        out=result_from_rows([(17,'owned-doc',1,TEXT)],['cedarbridge','labs'])
        self.assertEqual(out['calculation']['total_months'],45)
        self.assertIn('3 years 9 months',out['answer'])
        self.assertNotIn('Labs Employment',out['answer'])

    def test_labeled_field_never_crosses_other_employer_employee_or_section(self):
        for text in ('Cedarbridge Labs. Other Firm. Employment: Feb 2022 to Nov 2025',
                     'Cedarbridge Labs. Employee: Other Person. Employment: Feb 2022 to Nov 2025',
                     'Cedarbridge Labs. Project: Lantern. Employment: Feb 2022 to Nov 2025',
                     'Cedarbridge Labs.\n\nEmployment: Feb 2022 to Nov 2025',
                     'Cedarbridge Labs. Education: Feb 2022 to Nov 2025'):
            with self.subTest(text=text):
                self.assertIsNone(result_from_rows([(17,'owned-doc',1,text)],['cedarbridge','labs']))

    def test_exact_failed_answer_gains_calculation_without_losing_education(self):
        failed=("Mira Vale's employment at Cedarbridge Labs lasted from February 2022 to November 2025 [S4]. "
                'The provided documents do not contain the calculation of how long she worked there in years and months [S4]. '
                'She earned a Bachelor of Technology in Computer Science from the Eastmere Institute of Technology [S4].')
        out,prompt=self.answer(failed)
        self.assertEqual(out['status'],'answered')
        self.assertIn('3 years 9 months (45 months)',out['answer'])
        self.assertIn('Bachelor of Technology in Computer Science',out['answer'])
        self.assertIn('Eastmere Institute of Technology',out['answer'])
        self.assertNotIn('do not contain the calculation',out['answer'])
        self.assertEqual(out['calculation']['source_ref'],'S4')
        self.assertEqual(out['citations'],[{'ref':'S4','document':'owned-doc','page':1,'chunk_id':17}])
        self.assertIn('application has verified the employment date arithmetic',prompt)
        self.assertNotIn('45 months',prompt,'derived numbers are rendered after ordinary model grounding')

    def test_compound_request_does_not_short_circuit_the_other_requested_fields(self):
        from services import rag_service as rag
        expected={'status':'answered','answer':'full compound answer','retrieved':[]}
        with patch.dict(os.environ,{'RAG_V2':'1'}),patch('services.tenure_calculation.answer_employment_duration') as direct,patch.object(rag,'rewrite_query',return_value=QUESTION),patch.object(rag,'classify_question',return_value='DOCUMENT'),patch.object(rag,'_answer_from_route',return_value=expected) as route:
            self.assertEqual(rag.ask_question(QUESTION),expected)
            direct.assert_not_called()
            self.assertEqual(route.call_args.args[0],QUESTION)

    def test_calculation_uses_only_final_sources_not_question_dates_or_history(self):
        question=QUESTION+' The duration is 99 years from January 1900 to January 1999.'
        out=calculation_from_sources(question,[source()],history=[{'role':'assistant','content':'Cedarbridge Labs Jan 1900 to Jan 1999'}])
        self.assertEqual(out['calculation']['total_months'],45)
        self.assertIsNone(calculation_from_sources(QUESTION,[source('No employment dates are listed.')]))
        self.assertIsNone(calculation_from_sources(QUESTION,[source(),source(document='another-doc',cid=18)]))

    def test_arbitrary_model_numbers_are_still_rejected(self):
        out,_=self.answer('She earned a Bachelor of Technology and has 99 years of experience [S4].')
        self.assertNotIn('99 years',out['answer'])
        from services.grounding_service import unsupported_numbers
        self.assertTrue(unsupported_numbers('She worked for 45 months [S4].',[source()]))

    def test_literal_missing_telephone_is_partial_without_rejecting_negative_fax_fact(self):
        sources=[source('Total project budget: 83,000 credits.',ref='S1',page=2),source(ref='S2')]
        text=('The total project budget is 83,000 credits [S1]. '
              'The office explicitly does not provide a fax service [S2]. '
              "Mira Vale's telephone number is unavailable in the provided documents [S1][S2].")
        out,_=self.answer(text,sources,question='Give the project budget, fax service and telephone number.')
        self.assertEqual(out['status'],'partial')
        self.assertEqual([c['ref'] for c in out['citations']],['S1','S2'])
        self.assertIn('does not provide a fax service',out['answer'])

    def test_pure_unavailable_number_abstains_but_literal_unavailable_service_is_a_fact(self):
        for text in ("Mira Vale's telephone number is unavailable in the provided documents [S4].",
                     'The telephone number was unavailable from the retrieved sources [S4].'):
            self.assertEqual(classify_status(text,{'owned-doc'},True,[source()]),'abstained')
        for text in ('The fax service is unavailable [S4].',
                     'Wheelchair access is unavailable [S4].',
                     'The office explicitly does not provide a fax service [S4].'):
            self.assertEqual(classify_status(text,{'owned-doc'},True,[source(text)]),'answered')

    def test_missing_telephone_stays_partial_alongside_a_verified_calculation(self):
        out,_=self.answer("Mira Vale's telephone number is unavailable in the provided documents [S4].",question='How long did Mira work at Cedarbridge Labs, and what is her telephone number?')
        self.assertEqual(out['status'],'partial')
        self.assertIn('45 months',out['answer'])
        self.assertIn('telephone number is unavailable',out['answer'])

    def test_request_for_exact_days_retains_the_unanswered_precision_gap(self):
        out,_=self.answer('She attended Eastmere Institute of Technology [S4].',question='Calculate the exact days of employment at Cedarbridge Labs, and name the institution.')
        self.assertEqual(out['status'],'partial')
        self.assertIn('exact days are not specified',out['answer'])

    def test_duration_gap_does_not_drop_a_fact_in_the_same_sentence(self):
        out,_=self.answer('The documents do not contain a duration calculation, but she earned a Bachelor of Technology in Computer Science [S4].')
        self.assertIn('Bachelor of Technology in Computer Science',out['answer'])
        self.assertIn('45 months',out['answer'])

    def test_missing_salary_still_abstains_without_inventing_a_value(self):
        out,_=self.answer("I couldn't find sufficient information in the provided documents [S4].",question="What is Mira Vale's annual salary?")
        self.assertEqual(out['status'],'abstained')
        self.assertNotIn('calculation',out)

    def test_duration_lookup_respects_the_explicit_owned_document_scope(self):
        from services.tenure_calculation import answer_employment_duration
        from services.tenant_context import tenant_scope
        conn=MagicMock();conn.execute.return_value.fetchall.return_value=[(17,'owned-doc',1,TEXT)]
        with tenant_scope('00000000-0000-4000-8000-000000000001'),patch('services.v2_evidence_recovery.explicit_document_scope',return_value=['owned-doc']),patch('services.database.get_connection') as get:
            get.return_value.__enter__.return_value=conn
            out=answer_employment_duration('Using resume.pdf, how long did Mira work at Cedarbridge Labs?')
        self.assertEqual(out['calculation']['total_months'],45)
        self.assertIn('dc.owner_id=%s',conn.execute.call_args.args[0])
        self.assertIn('dc.document_name=ANY(%s)',conn.execute.call_args.args[0])
        self.assertEqual(conn.execute.call_args.args[1][-1],['owned-doc'])
        with tenant_scope('00000000-0000-4000-8000-000000000001'),patch('services.v2_evidence_recovery.explicit_document_scope',return_value=[]),patch('services.database.get_connection') as get:
            self.assertIsNone(answer_employment_duration('Using foreign.pdf, calculate years of experience at Cedarbridge Labs'))
            get.assert_not_called()


if __name__=='__main__':unittest.main()
