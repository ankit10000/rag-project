"""Verified arithmetic, entity/date binding, tenant scope and legacy guardrails."""
import os
import unittest
from unittest.mock import patch,MagicMock
from services.tenure_calculation import duration_intent,employer_hint,resolve_employer,result_from_rows

TEXT='Old project description. Cedar Systems Pvt. Ltd. Feb 2022 – Nov 2025 Software Engineer. Readibots - Enterprise connector platform.'
ROWS=[(7,'resume-a',1,TEXT)]

class TenureTests(unittest.TestCase):
    def test_original_grammar_and_generic_employers(self):
        self.assertTrue(duration_intent('calculate the year of experience in cedar company'))
        self.assertEqual(employer_hint('calculate the year of experience in cedar company'),['cedar'])
        self.assertEqual(employer_hint('How long did Jordan work at Cedar Systems?'),['cedar','systems'])
        self.assertEqual(employer_hint('calculate the Cedar duration in years and months'),['cedar'])
        self.assertIsNone(employer_hint('calculate duration in years and months'))
        self.assertFalse(duration_intent('Who is Jordan?'))

    def test_exact_closed_month_difference_and_citation(self):
        r=result_from_rows(ROWS,['cedar'])
        self.assertEqual(r['status'],'answered');self.assertIn('3 years 9 months (45 months)',r['answer'])
        self.assertIn('February 2022 to November 2025',r['answer']);self.assertTrue(r['validation']['valid'])
        self.assertEqual(r['calculation']['total_months'],45);self.assertEqual(r['citations'][0]['chunk_id'],7)
        self.assertIn('exact days are not specified',r['answer'])

    def test_no_rounding_or_inclusive_year_overcount(self):
        for start,end,total,phrase in [('Dec 2023','Jan 2024',1,'1 month'),('Feb 2022','Feb 2023',12,'1 year'),('Feb 2022','Feb 2022',0,'0 months')]:
            r=result_from_rows([(9,'doc',2,f'Cedar Labs {start} to {end}')],['cedar'])
            self.assertEqual(r['calculation']['total_months'],total);self.assertIn(phrase,r['answer'])

    def test_never_borrows_other_employer_or_project_dates(self):
        self.assertIsNone(result_from_rows([(1,'doc',1,'Cedar partner Other Firm Feb 2022–Nov 2025')],['cedar']))
        self.assertIsNone(result_from_rows(ROWS,['readibots']))
        self.assertIsNone(result_from_rows([(1,'doc',1,'Cedar worked on a project. Other Labs Feb 2022–Nov 2025')],['cedar']))

    def test_ambiguous_documents_or_multiple_stints_require_clarification(self):
        for rows in (ROWS+[(8,'resume-b',1,TEXT)],ROWS+[(8,'resume-a',1,'Cedar Systems Pvt. Ltd. Jan 2010–Feb 2011')]):
            r=result_from_rows(rows,['cedar']);self.assertEqual(r['status'],'abstained')
            self.assertNotIn('calculation',r);self.assertIn('ambiguous_employment_period',r['issues'])

    def test_duplicate_overlapping_chunks_do_not_make_second_job(self):
        r=result_from_rows(ROWS+[(8,'resume-a',1,TEXT)],['cedar'])
        self.assertEqual(r['calculation']['total_months'],45)

    def test_missing_open_or_reverse_dates_are_not_invented(self):
        for text in ('Cedar Labs Feb 2022–Present','Cedar Labs 2022–2025','Cedar Labs Nov 2025–Feb 2022','Cedar Labs engineering company'):
            self.assertIsNone(result_from_rows([(1,'doc',1,text)],['cedar']))

    def test_history_supplies_referent_not_date_evidence(self):
        h=[{'role':'user','content':'How long did Jordan work at Cedar?'},{'role':'assistant','content':'Cedar Jan 2000–Jan 2090'}]
        self.assertEqual(resolve_employer('Calculate the duration using those employment dates.',h),['cedar'])
        r=result_from_rows(ROWS,resolve_employer('Calculate the duration using those employment dates.',h))
        self.assertEqual(r['calculation']['total_months'],45)
        self.assertIsNone(resolve_employer('Who is Cedar?',h))

    def test_generated_arbitrary_numbers_remain_blocked(self):
        from services.grounding_service import unsupported_numbers
        sources=[{'ref':'S1','content':TEXT,'document_name':'resume-a'}]
        self.assertTrue(unsupported_numbers('The calculated duration is 99 years [S1].',sources))
        self.assertTrue(unsupported_numbers('The duration is 3 years 9 months [S1].',sources))

    def test_duration_route_uses_no_model_and_legacy_route_does_not_use_tool(self):
        from services import rag_service as rag
        verified=result_from_rows(ROWS,['cedar'])
        with patch.dict(os.environ,{'RAG_V2':'1'}),patch('services.tenure_calculation.answer_employment_duration',return_value=verified),patch.object(rag,'generate_answer') as model,patch.object(rag,'rewrite_query') as rewrite:
            self.assertEqual(rag.ask_question('calculate the year of experience in cedar company'),verified)
            model.assert_not_called();rewrite.assert_not_called()
        with patch.dict(os.environ,{'RAG_V2':'0'}),patch('services.tenure_calculation.answer_employment_duration') as tool,patch.object(rag,'rewrite_query',return_value='question'),patch.object(rag,'classify_question',return_value='MEMORY'),patch.object(rag,'generate_answer',return_value='[MEMORY] You prefer concise answers.'):
            rag.ask_question('How long did I work at Cedar?');tool.assert_not_called()

    def test_lookup_is_owner_scoped_and_refuses_missing_context(self):
        from services.tenure_calculation import answer_employment_duration
        from services.tenant_context import tenant_scope
        with patch('services.database.get_connection') as get:
            with self.assertRaises(PermissionError):answer_employment_duration('calculate years of experience at Cedar')
            get.assert_not_called()
        c=MagicMock();c.execute.return_value.fetchall.return_value=ROWS
        with tenant_scope('00000000-0000-4000-8000-000000000001'),patch('services.database.get_connection') as get:
            get.return_value.__enter__.return_value=c
            r=answer_employment_duration('calculate years of experience at Cedar')
        self.assertEqual(r['calculation']['total_months'],45)
        self.assertIn('dc.owner_id=%s',c.execute.call_args.args[0]);self.assertEqual(c.execute.call_args.args[1][0],'00000000-0000-4000-8000-000000000001')

@unittest.skipUnless(os.getenv('RAG_V2_DB_TEST')=='1','explicit guarded scratch integration required')
class TenureIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_v2_integration import V2Integration
        V2Integration.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        from test_v2_integration import V2Integration
        V2Integration.tearDownClass.__func__(cls)

    def test_two_owner_same_company_dates_remain_isolated_through_chat(self):
        import uuid
        from services.tenant_context import tenant_scope
        from services.database import get_connection
        from services import retrieval_config as cfg
        import main
        from test_v2_integration import V2Integration
        for which,user,dates,months in [('a',self.a,'Feb 2022 – Nov 2025',45),('b',self.b,'Jan 2020 – Jan 2021',12)]:
            did=uuid.uuid4()
            with tenant_scope(user.id),get_connection() as c:
                self.assertEqual(c.execute('SELECT current_database()').fetchone()[0],'rag_test_scratch')
                c.execute("INSERT INTO documents(id,filename,storage_path,status,embedding_model,embedding_dim) VALUES(%s,'fixture.pdf','synthetic-only','ready',%s,384)",(did,cfg.EMBEDDING_MODEL))
                c.execute('INSERT INTO document_chunks(document_name,page_number,chunk_id,content,embedding) VALUES(%s,1,1,%s,%s::vector)',(str(did),'Cedar Systems Pvt. Ltd. '+dates+' Software Engineer.','['+','.join(['0.01']*384)+']'))
            headers=V2Integration.headers(self,which)
            conversation=self.client.post('/api/v2/conversations',json={'title':'tenure fixture'},headers=headers).json()['conversation_id']
            with patch.object(main,'search_memories',return_value=[]),patch('services.llm_service.get_client',side_effect=AssertionError('provider calls forbidden')):
                r=self.client.post('/api/v2/chat',json={'conversation_id':conversation,'message':'calculate the year of experience in cedar company'},headers=headers)
            self.assertEqual(r.status_code,200,r.text)
            out=r.json();self.assertEqual(out['status'],'answered');self.assertEqual(out['calculation']['total_months'],months)
            self.assertEqual(out['citations'][0]['document_id'],str(did))
            self.assertEqual(out['calculation']['source_document'],str(did))

if __name__=='__main__':unittest.main(verbosity=2)
