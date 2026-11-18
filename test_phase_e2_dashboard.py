"""Acceptance dashboard cannot launder preparation evidence into approval."""
import testsafe
testsafe.require_scratch_db()
import copy
import hashlib
import json
from pathlib import Path
import unittest
from eval.acceptance_preparation.dashboard import build_status, STATES


def record():
    return dict(id='review', status='PENDING_INDEPENDENT_REVIEW',
                category='independent_review', summary='Review not performed',
                owner_role='Independent reviewer; person unassigned',
                next_action='Record a judgment under the exposure policy',
                can_continue_independently=False,
                evidence=[dict(path='review/evidence.json', sha256='a' * 64)])


class DashboardTests(unittest.TestCase):
    def test_published_dashboard_reproduces_states_and_evidence_hashes(self):
        root=Path(__file__).resolve().parent
        published=json.loads((root/'phase_e2_acceptance_status.json').read_text())
        rebuilt=build_status(published['requirements'])
        for key,value in rebuilt.items():self.assertEqual(published[key],value)
        self.assertEqual({r['category'] for r in published['requirements']},
                         {'engineering','review_package','independent_review',
                          'specification','owner_decision','external_evidence','inactive_integration'})
        for row in published['requirements']:
            for item in row['evidence']:
                self.assertEqual(hashlib.sha256((root/item['path']).read_bytes()).hexdigest(),item['sha256'])

    def test_pending_review_is_visible_and_never_activation(self):
        rows=[record()]; before=copy.deepcopy(rows); result=build_status(rows)
        self.assertEqual(result['status_counts']['PENDING_INDEPENDENT_REVIEW'],1)
        self.assertEqual(result['status_counts']['ACCEPTED'],0)
        self.assertEqual(set(result['status_counts']),set(STATES))
        self.assertFalse(result['acceptance_approved'])
        self.assertFalse(result['activation_allowed'])
        self.assertFalse(result['refreeze_executed'])
        result['requirements'][0]['summary']='changed'
        self.assertEqual(rows,before)

    def test_engineering_evidence_is_not_acceptance(self):
        row=record();row.update(status='ENGINEERING_COMPLETE',category='engineering',
                               can_continue_independently=True)
        self.assertFalse(build_status([row])['acceptance_approved'])
        row['status']='ACCEPTED'
        with self.assertRaises(ValueError):build_status([row])

    def test_unknown_duplicate_missing_and_unsafe_records_refused(self):
        bad=[None,[],[record(),record()]]
        for field,value in [('status','PASS'),('category','misc'),('next_action',''),
                            ('can_continue_independently',1),('evidence',[])]:
            row=record();row[field]=value;bad.append([row])
        for path in ('/absolute','../outside','a\\b',''):
            row=record();row['evidence'][0]['path']=path;bad.append([row])
        row=record();row['evidence'][0]['sha256']='bad';bad.append([row])
        row=record();del row['owner_role'];bad.append([row])
        for rows in bad:
            with self.subTest(rows=rows),self.assertRaises(ValueError):build_status(rows)

    def test_approval_blocked_work_cannot_be_marked_independent(self):
        row=record();row.update(status='BLOCKED_BY_APPROVAL',category='inactive_integration',
                               can_continue_independently=True)
        with self.assertRaises(ValueError):build_status([row])
        row['can_continue_independently']=False
        self.assertFalse(build_status([row])['activation_allowed'])


if __name__=='__main__':unittest.main()
