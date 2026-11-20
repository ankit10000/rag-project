"""Person qualifications must retrieve education, not substitute career facts."""
import os
import unittest
from unittest.mock import patch,Mock
from services import rag_service as rag
from services.v2_routing import qualification_subject,education_retrieval

BIO={'chunk':(1,'person-a.pdf',1,'Jordan Example is a software engineer with four years of work experience.',.1),'rrf_score':.03,'rerank_score':2.}
DEGREE={'chunk':(2,'person-a.pdf',2,'EDUCATION Example University 2018 – 2022 Bachelor of Technology in Computer Science.',.2),'rrf_score':.02,'rerank_score':1.}
QUERY='what is the qualifications of Jordan Example'

class QualificationTests(unittest.TestCase):
    def test_person_question_recognized_without_hardcoded_name(self):
        self.assertEqual(qualification_subject(QUERY),['jordan','example'])
        self.assertEqual(qualification_subject("What are Jordan's qualifications?"),['jordan'])
        self.assertIsNone(qualification_subject('What qualifications are required for this role?'))
        self.assertIsNone(qualification_subject("What are Jordan's professional qualifications and experience?"))

    def test_second_retrieval_is_scoped_to_named_persons_document(self):
        search=Mock(return_value={'results':[DEGREE],'rerank_status':'ok'})
        result=education_retrieval(QUERY,{'results':[BIO]},search,5)
        self.assertEqual(result['results'],[DEGREE]);self.assertEqual(search.call_args.kwargs['document_names'],['person-a.pdf'])
        self.assertNotIn('Jordan',search.call_args.args[0])

    def test_missing_degree_never_substitutes_career_summary(self):
        search=Mock(return_value={'results':[BIO],'rerank_status':'ok'})
        self.assertEqual(education_retrieval(QUERY,{'results':[BIO]},search,5)['results'],[])

    def test_same_name_in_multiple_documents_does_not_guess(self):
        other={**BIO,'chunk':(3,'person-b.pdf',1,BIO['chunk'][3],.1)}
        search=Mock();self.assertIsNone(education_retrieval(QUERY,{'results':[BIO,other]},search,5));search.assert_not_called()

    def test_actual_pipeline_uses_degree_and_cites_original_page(self):
        with patch.dict(os.environ,{'RAG_V2':'1'}),patch.object(rag,'rewrite_query',return_value=QUERY),patch.object(rag,'classify_question',return_value='DOCUMENT'),patch.object(rag,'hybrid_search_detailed',side_effect=[{'results':[BIO,DEGREE],'rerank_status':'ok'},{'results':[DEGREE],'rerank_status':'ok'}]) as search,patch.object(rag,'generate_answer',return_value='[DOCUMENT] Jordan holds a Bachelor of Technology in Computer Science from Example University (2018–2022) [S1].') as generate:
            result=rag.ask_question(QUERY)
        self.assertEqual(result['status'],'answered');self.assertEqual(result['citations'][0]['page'],2)
        prompt=generate.call_args.args[0];self.assertIn('Do not substitute professional experience',prompt)
        self.assertIn('Jordan Example',prompt);self.assertIn('Bachelor of Technology',prompt)
        self.assertEqual(search.call_count,2)

    def test_legacy_prompt_unchanged(self):
        from services.answer_prompt import build_answer_prompt
        with patch.dict(os.environ,{'RAG_V2':'0'}):prompt=build_answer_prompt(QUERY,[],'')
        self.assertNotIn('This asks for academic qualifications',prompt)


class ExplicitEducationTests(unittest.TestCase):
    def test_exact_saved_explicit_section_question_uses_authorized_scope(self):
        q='In Browser_Check_Morgan_Vale.pdf, what is listed under EDUCATION? Please give the degree, institute and study dates.'
        search=Mock(return_value={'results':[DEGREE],'rerank_status':'ok'})
        r=education_retrieval(q,{'results':[BIO]},search,5,authorized_scope=['person-a.pdf'])
        self.assertEqual(r['results'],[DEGREE])
        self.assertEqual(search.call_args.kwargs['document_names'],['person-a.pdf'])
    def test_explicit_section_without_unique_owned_scope_does_not_guess(self):
        search=Mock()
        q='What is listed under EDUCATION?'
        self.assertIsNone(education_retrieval(q,{'results':[BIO]},search,5))
        self.assertIsNone(education_retrieval(q,{'results':[BIO]},search,5,authorized_scope=[]))
        search.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
