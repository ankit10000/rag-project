"""WP8 clarification evidence, preserving experimental behavior without owner sign-off."""
import testsafe
testsafe.require_scratch_db()
import copy
from pathlib import Path
import unittest
import unicodedata
from eval.acceptance_preparation.clarifications import (
    SPEC,RESOLVED,PENDING,clarification_register,clarification_summary,validate_clarifications,
)
from eval.scoring_v2 import score_case,validate_annotations
from eval.scoring_v2.normalize import M,contains
from eval.scoring_v2.text_units import split
from eval.probes.v2_spec_fixtures import case
from eval.framework.integrity import dataset_hash


def score(answer,c,ann=None,status='answered'):
    return score_case(c,{'answer':answer,'status':status,'citations':[{'chunk_id':1}]},
                      {1:('synthetic',1)},{1},'1800 2000 £4.99 30 days',c['history'],ann)


class ClarificationTests(unittest.TestCase):
    def test_register_structure_exact_source_quotes_and_no_approval(self):
        register=clarification_register();self.assertEqual(validate_clarifications(register),[])
        text=Path(SPEC).read_text()
        self.assertEqual(clarification_summary(),dict(total=8,resolved_engineering=5,
            pending_ids=['SC-06','SC-07','SC-08'],independent_review_required=8,acceptance_approved=False))
        for record in register['clarifications']:
            self.assertFalse(record['acceptance_approved']);self.assertFalse(record['code_change_needed'])
            self.assertTrue(record['test_added']);self.assertTrue(record['independent_review_required'])
            self.assertEqual(record['review_status'],'NOT_REVIEWED')
            for original in record['source']['original_language']:
                with self.subTest(id=record['id'],quote=original): self.assertIn(original,text)
        register['clarifications'][0]['title']='caller change'
        self.assertNotEqual(register,clarification_register())

    def test_register_rejects_approval_laundering_missing_decisions_and_duplicates(self):
        mutations=[lambda r:r.update(acceptance_approved=True),lambda r:r['clarifications'][0].update(acceptance_approved=True),
            lambda r:r['clarifications'][0].update(review_status='APPROVED'),
            lambda r:r['clarifications'][5].update(proposed_resolution=''),
            lambda r:r['clarifications'][5].update(resolution_status=RESOLVED),
            lambda r:r['clarifications'].append(copy.deepcopy(r['clarifications'][0])),
            lambda r:r['clarifications'].pop(),lambda r:r['clarifications'][0].update(resolution_status='ACCEPTED')]
        for mutate in mutations:
            register=clarification_register();mutate(register)
            with self.subTest(register=register): self.assertTrue(validate_clarifications(register))

    def _assert_probes(self,expected):
        from eval.probes.scorer_regression import run
        from eval.probes.probe_data import PROBES
        probes=[p for p in PROBES if p['id'] in expected]
        self.assertEqual(len(probes),len(expected))
        for result in run(probes=probes,v2_fn=score_case):
            with self.subTest(probe=result['probe']['id']):
                self.assertEqual(result['v1_mismatches'],[])
                self.assertEqual(result['v2_mismatches'],[])
                self.assertEqual(result['probe']['v2'],expected[result['probe']['id']])
                self.assertEqual(result['v2'],expected[result['probe']['id']])

    def test_sc01_appendix_b_explicit_probe_values(self):
        self._assert_probes({'P-TS1-06':False,'P-TS1-08':False,'P-TS4-10':False,'P-E2-STAT-06':True})

    def test_sc02_quantity_only_plural_boundary(self):
        self.assertFalse(contains(M('Tuesdays'),M('Tuesday')))
        self.assertFalse(contains(M('filters'),M('filter')))
        self.assertTrue(contains(M('2 visitors'),M('2 visitor')))
        self.assertTrue(contains(M('2 visitor'),M('2 visitors')))
        self._assert_probes({'P-TS4-11':False,'P-TA11-2':False,'P-E2-TA11-3':False})

    def test_sc03_quote_map_survives_nfkc(self):
        self.assertEqual(unicodedata.normalize('NFKC','″'),'′′')
        for glyph in '“”„″': self.assertEqual(M(glyph+'value'+glyph),'"value"')
        for glyph in '’‘‛′': self.assertEqual(M('it'+glyph+'s'),"it's")
        self.assertEqual(M(M('″value″')),M('″value″'))

    def test_sc04_number_word_quantity_idempotence(self):
        for raw,expected in [('twelve months','12 month'),('twenty-four hours','24 h'),
                             ('two litres','2 l'),('ninety-nine percent','99%'),('five dollars','usd 5')]:
            with self.subTest(raw=raw):
                self.assertEqual(M(raw),expected)
                self.assertEqual(M(M(raw)),expected)
        self.assertEqual(M('1.0'),'1.0')
        self.assertEqual(M('one hundred and twenty days'),'one hundred and twenty days')

    def test_sc05_full_sample_and_richer_annotations_valid(self):
        c=case(gold=[['1,800'],['30 days'],['same appointment']],forbidden=['2,000'],conflict=True,
            history=[{'role':'user','content':'What is the cap?'},{'role':'assistant','content':'The cap is 2,000.'}])
        entry={'forbidden':[{'text':'2,000','kind':'assertion','source':'dataset'}],
               'history_wrong_values':[{'text':'2,000','turn':1}],'negatable_groups':[2],'conflict_groups':[[0,1]]}
        full={'schema':'phase35-scorer-annotations/1','dataset_version':'synthetic-example',
              'dataset_sha256':dataset_hash([c]),'cases':{c['id']:entry}}
        docs={'synthetic':['Cap 1800, superseded 2000, 30 days and same appointment.']}
        self.assertEqual(validate_annotations(entry),[])
        self.assertEqual(validate_annotations(full,[c],docs),[])
        for collection in ['forbidden','history_wrong_values']:
            bad=copy.deepcopy(full);bad['cases'][c['id']][collection].append(copy.deepcopy(entry[collection][0]))
            with self.subTest(collection=collection): self.assertTrue(validate_annotations(bad,[c],docs))
        for field,value in [('negatable_groups',[3]),('conflict_groups',[[0,3]]),('history_wrong_values',[{'text':'2,000','turn':0}])]:
            bad=copy.deepcopy(full);bad['cases'][c['id']][field]=value
            with self.subTest(field=field): self.assertTrue(validate_annotations(bad,[c],docs))

    def test_sc06_epistemic_comma_scope_remains_pending(self):
        c=case(gold=[['£4.99']],forbidden=['Visa'],partial=True)
        ann={'forbidden':[{'text':'Visa','kind':'assertion'}]}
        comma='Basic is £4.99. The documents do not say whether Visa is accepted, but Visa is fine.'
        separated=comma.replace(', but','; but')
        self.assertEqual(len(split(comma)[1].clauses),1)
        self.assertEqual(score(comma,c,ann)['forbidden_hits'],[])
        self.assertTrue(score(comma,c,ann)['correct']) # observed residual, NOT approved interpretation
        self.assertEqual(score(separated,c,ann)['forbidden_hits'],['Visa'])
        self.assertFalse(score(separated,c,ann)['correct'])
        record=clarification_register()['clarifications'][5]
        self.assertEqual(record['resolution_status'],PENDING)
        self.assertFalse(record['acceptance_approved'])

    def test_sc07_tens_one_grammar_remains_pending(self):
        for raw in ['one','twenty-one','thirty one','ninety-one']:
            with self.subTest(raw=raw): self.assertEqual(M(raw),raw)
        for raw,expected in [('twenty-two','22'),('thirty two','32'),('ninety-nine','99')]:
            self.assertEqual(M(raw),expected)
        self.assertEqual(clarification_register()['clarifications'][6]['resolution_status'],PENDING)

    def test_sc08_unknown_status_policy_remains_pending(self):
        c=case(gold=[['30 days']])
        for status in ['future-unknown-status','',None]:
            with self.subTest(status=status):
                result=score('30 days',c,status=status)
                self.assertTrue(result['correct']);self.assertEqual(result['status'],status)
        for status in [True,123,[],{}]:
            with self.subTest(status=status),self.assertRaises(ValueError): score('30 days',c,status=status)
        self.assertEqual(clarification_register()['clarifications'][7]['resolution_status'],PENDING)


if __name__=='__main__': unittest.main()
