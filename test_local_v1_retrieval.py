"""Local-v1.0 retrieval, citation and model-identity regressions; all I/O mocked."""
import testsafe
testsafe.require_scratch_db()
import contextlib
import io
import os
import unittest
from unittest.mock import patch
import numpy as np
from services import rag_service as rag
from services import hybrid_search_service as hybrid
from services import embedding_service as embedding
from services import retrieval_config as cfg
from services import local_release_profile as profile
from services.answer_service import generate_grounded_answer
from services.context_assembly_service import assemble_context
from services.grounding_service import unsupported_numbers

ROWS=[(1,'manual.pdf',1,'The first inspection interval is 30 days.',0.1),
      (2,'manual.pdf',2,'The warranty lasts 90 days from purchase.',0.2)]
HITS=[{'chunk':row,'rrf_score':0.1/(i+1),'rerank_score':10.0-i} for i,row in enumerate(ROWS)]


class LocalRetrievalTests(unittest.TestCase):
    def quiet(self,fn,*args,**kwargs):
        with contextlib.redirect_stdout(io.StringIO()): return fn(*args,**kwargs)

    def answer(self,raw,kind='DOCUMENT'):
        with patch.object(cfg,'ANSWER_MAX_RETRIES',0):
            return generate_grounded_answer('What inspection and warranty terms apply?',assemble_context(HITS),kind,lambda prompt:raw)

    def test_classifier_requires_exact_enum_before_skipping_retrieval(self):
        for raw,expected in [('MEMORY','MEMORY'),(' mixed \n','MIXED'),('DOCUMENT','DOCUMENT'),
                             ('NOT MEMORY','DOCUMENT'),('MEMORY or DOCUMENT','DOCUMENT'),
                             ('I cannot classify MEMORY','DOCUMENT'),('', 'DOCUMENT'),(None,'DOCUMENT'),({},'DOCUMENT')]:
            with self.subTest(raw=raw),patch.object(rag,'generate_answer',return_value=raw):
                self.assertEqual(rag.classify_question('question'),expected)

    def test_malformed_rewrite_uses_original_query(self):
        answer=dict(answer='ok',sources=[],citations=[],status='answered',issues=[],attempts=1)
        with patch.dict(os.environ,{'LOCAL_V1_PROFILE':''}),patch.object(rag,'rewrite_query',return_value={'bad':'rewrite'}), \
             patch.object(rag,'classify_question',return_value='DOCUMENT') as classify, \
             patch.object(rag,'hybrid_search_detailed',return_value={'results':HITS,'rerank_status':'ok'}) as search, \
             patch.object(rag,'generate_grounded_answer',return_value=answer):
            self.quiet(rag.ask_question,'original question')
        classify.assert_called_once_with('original question')
        search.assert_called_once_with('original question',top_k=cfg.FINAL_TOP_K)

    def test_malformed_memory_classification_reaches_document_retrieval(self):
        with patch.dict(os.environ,{'LOCAL_V1_PROFILE':'1'}),patch.object(rag,'rewrite_query',return_value='question'), \
             patch.object(rag,'generate_answer',return_value='NOT MEMORY'), \
             patch.object(rag,'hybrid_search_detailed',return_value={'results':[],'rerank_status':'skipped'}) as search:
            result=self.quiet(rag.ask_question,'question')
        self.assertEqual(search.call_count,1);self.assertEqual(result['status'],'abstained')

    def test_two_page_hybrid_retrieval_preserves_page_identity_without_rerank(self):
        with patch.object(hybrid,'semantic_search',return_value=ROWS),patch.object(hybrid,'keyword_search',return_value=list(reversed(ROWS))), \
             patch.object(hybrid,'rerank_results',side_effect=AssertionError('rerank disabled')):
            got=hybrid.hybrid_search_detailed('inspection warranty',top_k=2,rerank=False)
        self.assertEqual(got['rerank_status'],'disabled')
        self.assertEqual({r['chunk'][2] for r in got['results']},{1,2})
        self.assertEqual({s['page_number'] for s in assemble_context(got['results'])['sources']},{1,2})

    def test_two_page_valid_answer_has_each_actual_page_citation(self):
        result=self.answer('[DOCUMENT] The inspection interval is 30 days [S1]. The warranty lasts 90 days [S2].')
        self.assertEqual(result['status'],'answered')
        self.assertEqual([(c['chunk_id'],c['page']) for c in result['citations']],[(1,1),(2,2)])

    def test_wrong_page_numeric_citation_is_rejected_or_removed(self):
        raw='[DOCUMENT] The warranty lasts 90 days [S1].'
        result=self.answer(raw)
        self.assertEqual(result['status'],'unverified');self.assertEqual(result['citations'],[])
        self.assertTrue(unsupported_numbers('The warranty lasts 90 days [S1].',assemble_context(HITS)['sources']))

    def test_mixed_memory_tag_cannot_bypass_document_grounding(self):
        result=self.answer('[MEMORY] The warranty lasts 999 days from purchase.',kind='MIXED')
        self.assertEqual(result['status'],'unverified');self.assertEqual(result['citations'],[])
        memory=self.answer('[MEMORY] You prefer concise answers.',kind='MEMORY')
        self.assertEqual(memory['status'],'answered')

    def test_local_no_rerank_fail_closed_and_default_behavior_unchanged(self):
        outcome=dict(answer='ok',sources=[],citations=[],status='answered',issues=[],attempts=1)
        for flag in ['1','']:
            for ranking in ['disabled','failed:OSError']:
                with self.subTest(flag=flag,ranking=ranking),patch.dict(os.environ,{'LOCAL_V1_PROFILE':flag}), \
                     patch.object(rag,'rewrite_query',return_value='question'),patch.object(rag,'classify_question',return_value='DOCUMENT'), \
                     patch.object(rag,'hybrid_search_detailed',return_value={'results':HITS,'rerank_status':ranking}), \
                     patch.object(rag,'generate_grounded_answer',return_value=outcome) as generate:
                    got=self.quiet(rag.ask_question,'question')
                if flag=='1':
                    self.assertEqual(got['status'],'unverified');self.assertEqual(got['issues'],['local_v1_rerank_required'])
                    self.assertEqual(generate.call_count,0);self.assertEqual(got['citations'],[])
                else:
                    self.assertEqual(got['status'],'answered');self.assertEqual(generate.call_count,1)

    def test_local_verified_ranking_and_memory_route_remain_available(self):
        self.assertEqual(profile.PROFILE_NAME,'local-v1.0')
        with patch.dict(os.environ,{'LOCAL_V1_PROFILE':'1'}):
            self.assertFalse(profile.requires_verified_ranking('DOCUMENT',HITS,'ok'))
            self.assertFalse(profile.requires_verified_ranking('MEMORY',HITS,'disabled'))
            self.assertFalse(profile.requires_verified_ranking('DOCUMENT',[],'skipped'))
        with patch.dict(os.environ,{'LOCAL_V1_PROFILE':'true'}): self.assertFalse(profile.enabled())


class EmbeddingIdentityTests(unittest.TestCase):
    def setUp(self):
        self.stack=contextlib.ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(embedding,'_model',None))
        self.stack.enter_context(patch.object(embedding,'_model_name',None))
        self.stack.enter_context(patch.object(cfg,'EMBEDDING_MODEL','all-MiniLM-L6-v2'))
        self.stack.enter_context(patch.dict(os.environ,{'LOCAL_V1_PROFILE':''}))
        self.model=type('FakeModel',(),{'encode':lambda self,texts,normalize_embeddings:np.zeros((len(texts),384))})()
        self.factory=self.stack.enter_context(patch.object(embedding,'SentenceTransformer',return_value=self.model))
        embedding.clear_embedding_cache();self.addCleanup(embedding.clear_embedding_cache)

    def test_loaded_model_identity_cannot_change_even_for_same_dimension(self):
        embedding.generate_embeddings(['first'])
        with patch.object(cfg,'EMBEDDING_MODEL','different-same-384-model'):
            with self.assertRaises(embedding.EmbeddingModelMismatchError): embedding.generate_embeddings(['second'])
            with self.assertRaises(embedding.EmbeddingModelMismatchError): embedding.get_model()
        self.assertEqual(self.factory.call_count,1)

    def test_fixed_release_model_pin_is_checked_before_cached_vector_return(self):
        with patch.object(cfg,'EMBEDDING_MODEL','other-model'):
            embedding.generate_embeddings(['cached'])
            with patch.dict(os.environ,{'LOCAL_V1_PROFILE':'1'}):
                with self.assertRaisesRegex(ValueError,'local-v1.0 requires'): embedding.generate_embeddings(['cached'])
        self.assertEqual(self.factory.call_count,1)

    def test_profile_disallows_unsafe_model_before_loading_or_encoding(self):
        with patch.dict(os.environ,{'LOCAL_V1_PROFILE':'1'}),patch.object(cfg,'EMBEDDING_MODEL','other-model'):
            with self.assertRaisesRegex(ValueError,'existing vector model provenance cannot be inferred'): embedding.generate_embeddings(['x'])
        self.factory.assert_not_called()

    def test_model_load_failure_does_not_cache_false_identity(self):
        self.factory.side_effect=OSError('offline model unavailable')
        with self.assertRaises(embedding.EmbeddingModelLoadError): embedding.get_model()
        self.assertIsNone(embedding._model);self.assertIsNone(embedding._model_name)
        self.factory.side_effect=None
        self.assertIs(embedding.get_model(),self.model)
        self.assertEqual(embedding._model_name,cfg.EMBEDDING_MODEL)


if __name__=='__main__': unittest.main()
