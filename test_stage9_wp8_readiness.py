"""WP8 diagnostic readiness/proposal tests; no DB, providers or adoption."""
import testsafe
testsafe.require_scratch_db()
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from eval.acceptance_preparation import readiness as r
from eval.framework.hashing import portable_sha256

ROOT=Path(__file__).resolve().parent


def evidence():
    return {key:dict(status='PASS',summary='Synthetic deterministic evidence',
                    artifacts=[dict(path='tests/evidence.json',sha256='a'*64)])
            for key in r.EVIDENCE_REQUIREMENTS}


def fixture():
    source=b'unchanged\n'
    content={'manifest_format':'phase35-frozen-manifest/1','assets':[
        dict(path='eval/frozen.py',kind='text',group='scorer',portable_sha256=portable_sha256(source,'text'))]}
    manifest={'content':content,'content_sha256':hashlib.sha256(r._canonical(content)).hexdigest()}
    sources={'eval/frozen.py':source,'eval/scoring_v2/score.py':b'v2\n',
             'eval/runner_preparation/offline.py':b'prep\n'}
    return manifest,sources


class ReadinessTests(unittest.TestCase):
    def test_passing_engineering_is_never_formal_adoption(self):
        got=r.assess_readiness(evidence())
        self.assertTrue(got['engineering_preparation_complete'])
        self.assertEqual(got['engineering_gaps'],[])
        for key in ('formal_acceptance_ready','adoption_allowed','refreeze_allowed'):
            self.assertIs(got[key],False)
        self.assertEqual(got['accepted_default'],'v1')
        self.assertEqual(got['pending_owner_decisions'],list(r.REQUIRED_DECISIONS))

    def test_missing_failed_or_not_run_evidence_stays_visible(self):
        for status in ('FAIL','NOT_RUN'):
            current=evidence();current['annotation_validation']['status']=status
            got=r.assess_readiness(current)
            self.assertFalse(got['engineering_preparation_complete'])
            self.assertIn('annotation_validation',got['engineering_gaps'])
        got=r.assess_readiness({})
        self.assertEqual(len(got['engineering_gaps']),len(r.EVIDENCE_REQUIREMENTS))

    def test_malformed_evidence_cannot_be_a_healthy_zero(self):
        bad=[None,[],{'unknown':True}]
        for entry in [True,{'status':True,'summary':'fake','artifacts':[]},
                      {'status':'PASS','summary':'fake','artifacts':[]},
                      {'status':'PASS','summary':'fake','artifacts':[{'path':'../bad','sha256':'a'*64}]},
                      {'status':'PASS','summary':'fake','artifacts':[{'path':'a','sha256':'bad'}]}]:
            current=evidence();current['annotation_validation']=entry;bad.append(current)
        for value in bad:
            with self.subTest(value=value),self.assertRaises(ValueError):r.assess_readiness(value)

    def test_asserted_approvals_are_not_authenticated_review(self):
        record={'decision':'V5_scorer_adoption','claimed_status':'APPROVED',
                'artifact':{'path':'owner/assertion.json','sha256':'b'*64}}
        got=r.assess_readiness(evidence(),[record])
        self.assertEqual(got['review_assertions'][0]['verification'],'UNVERIFIED')
        self.assertFalse(got['adoption_allowed'])
        self.assertIn('V5_scorer_adoption',got['pending_owner_decisions'])
        for value in [True,{'approved':True},[{'approved':True}]]:
            with self.subTest(value=value),self.assertRaises(ValueError):r.assess_readiness(evidence(),value)

    def test_checklists_and_proposals_are_deterministic_and_detached(self):
        values=evidence();before=copy.deepcopy(values)
        got=r.assess_readiness(values);self.assertEqual(got,r.assess_readiness(values))
        got['checks'][0]['summary']='edited';self.assertEqual(values,before)
        manifest,sources=fixture();before=copy.deepcopy(manifest)
        first=r.propose_refreeze(manifest,sources)
        self.assertEqual(first,r.propose_refreeze(manifest,dict(reversed(list(sources.items())))))
        self.assertEqual(manifest,before)
        self.assertNotIn('content',first)
        self.assertNotIn('content_sha256',first)
        self.assertFalse(first['activation_allowed']);self.assertFalse(first['refreeze_executed'])
        self.assertIsNone(first['approved_acceptance_scorer'])
        self.assertIsNone(first['approved_v2_thresholds'])
        self.assertIsNone(first['future_patched_runner_gate_hashes'])

    def test_proposal_portable_hashes_are_crlf_neutral_and_source_sensitive(self):
        manifest,sources=fixture();first=r.propose_refreeze(manifest,sources)
        converted={p:data.replace(b'\n',b'\r\n') for p,data in sources.items()}
        self.assertEqual(first,r.propose_refreeze(manifest,converted))
        changed=dict(sources);changed['eval/scoring_v2/score.py']=b'new\n'
        self.assertNotEqual(first['proposal_sha256'],r.propose_refreeze(manifest,changed)['proposal_sha256'])

    def test_parent_mismatch_missing_assets_and_unsafe_candidates_refused(self):
        manifest,sources=fixture()
        for mutation in ('hash','missing','changed','outside','traversal','notbytes'):
            m=copy.deepcopy(manifest);s=dict(sources)
            if mutation=='hash':m['content_sha256']='0'*64
            elif mutation=='missing':s.pop('eval/frozen.py')
            elif mutation=='changed':s['eval/frozen.py']=b'changed'
            elif mutation=='outside':s['eval/phase35/new_thresholds.json']=b'{}'
            elif mutation=='traversal':s['../outside.py']=b'bad'
            else:s['eval/scoring_v2/score.py']='not bytes'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):r.propose_refreeze(m,s)

    def test_current_inventory_is_only_a_candidate_and_preserves_parent(self):
        manifest_path=ROOT/'eval/phase35/frozen_manifest.json';before=manifest_path.read_bytes()
        manifest=json.loads(before)
        sources={a['path']:(ROOT/a['path']).read_bytes() for a in manifest['content']['assets']}
        for folder in ('eval/scoring_v2','eval/runner_preparation'):
            for p in (ROOT/folder).iterdir():
                if p.suffix in ('.py','.json'):sources[p.relative_to(ROOT).as_posix()]=p.read_bytes()
        proposal=r.propose_refreeze(manifest,sources)
        self.assertEqual(len(proposal['preserved_assets']),27)
        self.assertEqual(len(proposal['candidate_assets']),20)
        self.assertEqual(proposal['parent_frozen_manifest_content_sha256'],manifest['content_sha256'])
        self.assertTrue(all(a['disposition']=='CANDIDATE_SNAPSHOT_NOT_APPROVED' for a in proposal['candidate_assets']))
        self.assertEqual(manifest_path.read_bytes(),before)

    def test_import_reads_no_files_and_loads_no_services(self):
        script="import builtins,socket,sys; builtins.open=lambda *a,**k:(_ for _ in ()).throw(AssertionError('read')); socket.socket.connect=lambda *a,**k:(_ for _ in ()).throw(AssertionError('network')); import eval.acceptance_preparation.readiness; assert not any(x=='services' or x.startswith('services.') for x in sys.modules)"
        result=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_all_44_protected_source_hashes_remain_unchanged(self):
        from test_stage9_v2_integrity import PROTECTED
        self.assertEqual(len(PROTECTED),44)
        for path,expected in PROTECTED.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),expected)


if __name__=='__main__':unittest.main()
