"""Current behavior and unselected SC-06/07/08 decision proposals; no policy adoption."""
import testsafe
testsafe.require_scratch_db()
import collections
import hashlib
import importlib
import json
from pathlib import Path
import re
import unittest
from eval.acceptance_preparation.clarifications import clarification_register,validate_clarifications
from eval.scoring_v2 import score_case
from eval.scoring_v2.normalize import M
from eval.scoring_v2.text_units import split
from eval.scoring_v2.signals import clause_abstention
from eval.scoring_v2.rescore import load_pinned_dataset,ROOT
from eval.probes.v2_spec_fixtures import case

FOLDER=Path(__file__).resolve().parent/'eval/acceptance_preparation/clarifications'


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def current_score(answer,c,ann=None,status='answered',present=True):
    result={'answer':answer,'citations':[{'chunk_id':1}]}
    if present: result['status']=status
    try:
        got=score_case(c,result,{1:('synthetic',1)},{1},'£4.99 30 days 45 days',c['history'],ann)
        return {'outcome':'SCORED',**{k:got[k] for k in ['correct','fact_recall','forbidden_hits','abstain_ok','partial_ok','conflict_ok','status']}}
    except ValueError as exc: return {'outcome':'ValueError','message':str(exc)}


class ClarificationDecisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.package=json.loads((FOLDER/'decision_package.json').read_text())

    def test_package_references_canonical_register_and_retains_import_identity(self):
        module=importlib.import_module('eval.acceptance_preparation.clarifications')
        self.assertEqual(Path(module.__file__).name,'clarifications.py')
        self.assertFalse((FOLDER/'__init__.py').exists())
        ref=self.package['canonical_register']
        self.assertEqual(ref['snapshot'],clarification_register())
        self.assertEqual(validate_clarifications(ref['snapshot']),[])
        self.assertEqual(ref['sha256'],digest(ROOT/ref['path']))
        self.assertEqual(ref['markdown_sha256'],digest(ROOT/ref['markdown_path']))
        self.assertEqual(self.package['specification']['sha256'],digest(ROOT/self.package['specification']['path']))
        for path,sha in self.package['implementation_sources'].items(): self.assertEqual(digest(ROOT/path),sha,path)

    def test_owner_fields_blank_and_resolutions_not_formally_adopted(self):
        self.assertEqual(self.package['state'],'PREPARED_FOR_REVIEW')
        self.assertFalse(self.package['acceptance_approved'])
        self.assertEqual(self.package['official_scorer'],'v1')
        self.assertEqual(set(self.package['owner_decisions']),{'SC-06','SC-07','SC-08'})
        for decision in self.package['owner_decisions'].values():
            self.assertEqual(decision['status'],'PENDING_OWNER_DECISION')
            self.assertTrue(all(v is None for k,v in decision.items() if k!='status'))
        for record in self.package['canonical_register']['snapshot']['clarifications']:
            self.assertFalse(record['acceptance_approved'])
            self.assertEqual(record['review_status'],'NOT_REVIEWED')
            self.assertTrue(record['independent_review_required'])

    def test_sc06_all_formal_examples_and_contrast_boundary_controls(self):
        c=case(gold=[['£4.99']],forbidden=['Visa','Mastercard','Amex'],partial=True)
        ann={'forbidden':[{'text':word,'kind':'assertion'} for word in c['forbidden']]}
        rows=self.package['sc06']['regression_examples'];self.assertEqual(len(rows),19)
        for row in rows:
            with self.subTest(example=row['id']):
                actual=current_score(row['answer'],c,ann)
                self.assertEqual(actual,row['current_result'])
                self.assertEqual(actual['correct'],row['alternative_A_expected_correct'])
        byid={row['id']:row for row in rows}
        self.assertTrue(byid['SC06-SPEC-RESIDUAL']['current_result']['correct'])
        self.assertFalse(byid['SC06-SPEC-RESIDUAL']['alternative_B_expected_correct'])
        for key in ['SC06-SEMICOLON','SC06-PERIOD','SC06-DASH','SC06-PAREN','SC06-ASSERT-FIRST','SC06-NO-EPI']:
            self.assertFalse(byid[key]['current_result']['correct'])
        self.assertTrue(byid['SC06-AND']['alternative_B_expected_correct'])
        self.assertTrue(byid['SC06-NON-TOKEN']['alternative_B_expected_correct'])

    def test_sc06_spec_examples_exhaustive_and_proposed_precedence_explicit(self):
        references=self.package['sc06']['affected_specification_examples']
        self.assertEqual({r['section'] for r in references},{'§6.1.5','§7.2 E','§7.5 C-14','§7.5 C-15','§7 residual','Appendix B P-TS3-05'})
        alternative=self.package['sc06']['alternatives']['B']
        self.assertGreaterEqual(len(alternative['precedence']),5)
        self.assertIn('not implemented',alternative['version_effect'])
        self.assertIn('Do not change the global splitter',alternative['change'])

    def test_sc07_narrow_grammar_and_proposed_21_31_idempotence(self):
        section=self.package['sc07']
        self.assertIn('<two..nine>',section['exact_wording'])
        for row in section['regression_examples']:
            with self.subTest(input=row['input']):
                self.assertEqual(M(row['input']),row['current_normalized'])
                self.assertEqual(M(M(row['input'])),row['current_twice'])
                self.assertEqual(row['current_normalized'],row['current_twice'])
                self.assertEqual(row['alternative_A_expected'],row['current_normalized'])
        bytext={r['input']:r for r in section['regression_examples']}
        self.assertEqual(bytext['twenty-one']['current_normalized'],'twenty-one')
        self.assertEqual(bytext['thirty one']['current_normalized'],'thirty one')
        self.assertEqual(bytext['twenty-one']['alternative_B_expected'],'21')
        self.assertEqual(bytext['twenty-one months']['alternative_B_expected'],'21 month')
        self.assertEqual(bytext['one']['alternative_B_expected'],'one')
        self.assertIn('not implemented',section['alternatives']['B']['version_effect'])

    def test_sc08_full_status_category_matrix_and_proposed_error_contracts(self):
        section=self.package['sc08']
        cases={'fact':(case(gold=[['30 days']]),'30 days'),
            'abstention':(case(gold=[],abstain=True),'Cannot find information.'),
            'partial':(case(gold=[['30 days']],partial=True),'30 days'),
            'conflict':(case(gold=[['30 days'],['45 days']],conflict=True),'30 days but 45 days')}
        self.assertEqual(len(section['current_matrix']),14)
        for row in section['current_matrix']:
            for kind,(c,answer) in cases.items():
                with self.subTest(category=row['input_category'],case=kind):
                    self.assertEqual(current_score(answer,c,status=row['input_status'],present=row['status_field_present']),row['current_results'][kind])
        self.assertEqual(set(section['alternatives']),{'A','B','C'})
        self.assertIn('ValueError',section['alternatives']['B']['contract'])
        self.assertIn('canonical error',section['alternatives']['C']['contract'])
        self.assertIn('V-9',section['alternatives']['C']['contract'])
        self.assertIn('Do not rewrite annotation bytes',section['annotation_compatibility'])

    def test_historical_impact_dev_only_counts_recomputed_without_proposed_scoring(self):
        impact=self.package['historical_dev_impact'];_,cases,pin=load_pinned_dataset(ROOT,impact['dataset_revision'])
        byid={c['id']:c for c in cases}
        self.assertEqual(impact['dataset_revision'],pin['git_rev'])
        adv=re.compile(r'\b(?:but|however|whereas|while|although|though|yet)\b')
        ones=re.compile(r'\b(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)[ -]one\b',re.I)
        for tier,want in impact['tiers'].items():
            rows=[json.loads(line) for line in (ROOT/want['source_path']).read_text().splitlines()]
            self.assertEqual(len(rows),47 if tier=='1' else 42)
            self.assertEqual(digest(ROOT/want['source_path']),want['source_sha256'])
            sc06=set();sc07=set()
            for row in rows:
                self.assertEqual(row['split'],'dev')
                for sentence in split(row['answer']):
                    for clause in sentence.clauses:
                        normalized=M(clause.text)
                        signals=[s for s in clause_abstention(normalized) if s['family'].startswith('A') or s['family'] in ('B','C')]
                        if any(adv.search(normalized,s['span'][1]) for s in signals): sc06.add(row['id'])
                c=byid[row['id']]
                text=' '.join([row['answer']]+[a for g in c['gold_facts'] for a in g]+c['forbidden']+[m['content'] for m in c['history']])
                if ones.search(text): sc07.add(row['id'])
            self.assertEqual(sorted(sc06),want['sc06_epistemic_then_adversative_same_clause_candidate_ids'])
            self.assertEqual(sorted(sc07),want['sc07_tens_one_candidate_ids'])
            self.assertEqual(dict(collections.Counter(r.get('status') for r in rows)),want['status_counts'])
            self.assertEqual(want['missing_status'],0);self.assertEqual(want['null_status'],0)
            self.assertEqual(want['unknown_string_status'],0)
        self.assertTrue(any('not predicted correctness flips' in x for x in impact['limitations']))


if __name__=='__main__': unittest.main()
