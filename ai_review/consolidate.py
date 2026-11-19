"""Read-only source validation and deterministic AI ledger consolidation.

No evaluator, provider, database, original scorer or held-out runner is imported.
Initial JSONL byte streams are preserved and sealed in an exclusive manifest.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
NAMES = ('source_verification', 'label_review', 'scoring_fairness')
JUDGMENTS = {'AI_PASS', 'AI_CORRECTION_RECOMMENDED', 'AI_AMBIGUOUS', 'AI_INSUFFICIENT_EVIDENCE'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def norm(text):
    return ' '.join(text.split()).lower()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def index_rows(rows, expected):
    indexed = {}
    for row in rows:
        cid = row.get('case_id')
        require(cid in expected, f'unknown case {cid}')
        require(cid not in indexed, f'duplicate case {cid}')
        indexed[cid] = row
    require(set(indexed) == set(expected), f'missing cases {sorted(set(expected)-set(indexed))}')
    return indexed


def substantive(text):
    return isinstance(text, str) and len(text.strip()) >= 30 and norm(text) not in {
        'source verified and expected answer supported.',
        'reviewed the source and found no issues.',
        'the expected answer is correct and supported by evidence.',
    }


def validate_evidence(evidence, pages):
    if evidence.get('evidence_type') == 'negative_coverage_review':
        require(substantive(evidence.get('absence_rationale')), 'missing negative evidence rationale')
        require(bool(evidence.get('domain_documents')), 'negative coverage missing sources')
        for document in evidence['domain_documents']:
            validate_evidence(dict(document, pages_examined=document['pages_reviewed'], location=evidence['scope']), pages)
        return
    if 'pages_examined' in evidence:
        doc = evidence.get('document')
        require(substantive(evidence.get('location')), 'missing absence location')
        require(evidence['pages_examined'] == sorted(p for d, p in pages if d == doc), 'incomplete negative coverage')
        for page in evidence['pages_examined']:
            require((doc, page) in pages and evidence.get('pdf_sha256') == pages[doc, page]['pdf_sha256'], 'negative coverage source mismatch')
        return
    doc, page = evidence.get('document'), evidence.get('page')
    require((doc, page) in pages, f'unknown source/page {doc}:{page}')
    source = pages[doc, page]
    require(evidence.get('pdf_sha256') == source['pdf_sha256'], f'source hash mismatch {doc}')
    if evidence.get('pdf_path'):
        require(evidence['pdf_path'] == source['pdf_path'], f'source path mismatch {doc}')
    if evidence.get('page_text_sha256'):
        require(evidence['page_text_sha256'] == sha(source['text'].encode()), f'page text hash mismatch {doc}:{page}')
    quote = evidence.get('quote', evidence.get('text'))
    require(isinstance(quote, str) and len(norm(quote)) >= 8, f'missing/short source quotation {doc}:{page}')
    require(norm(quote) in norm(source['text']), f'quote not on actual PDF page {doc}:{page}')


def validate_review(row, case, pages, dataset_sha, module_hashes):
    require(row.get('reviewer_type') == 'AI', 'reviewer must be AI')
    judgment = row.get('judgment', row.get('reviewer_judgment'))
    require(judgment in JUDGMENTS, f'invalid AI judgment {judgment}')
    rationale = row.get('rationale', row.get('source_based_rationale', row.get('source_facts_and_case_rationale')))
    require(substantive(rationale), f'blank/boilerplate rationale {case["id"]}')
    confidence = row.get('confidence')
    require(type(confidence) in (float, int) and 0 <= confidence <= 1, 'invalid confidence')
    identity = row.get('dataset_identity', {})
    if 'dataset_sha256' in identity:
        require(identity['dataset_sha256'] == dataset_sha, 'dataset hash mismatch')
    mh = identity.get('module_sha256')
    if isinstance(mh, dict):
        require(mh == module_hashes, 'module hashes mismatch')
    elif isinstance(mh, str):
        require(mh == module_hashes[f'eval/phase35/{case["_module"]}.py'], 'module hash mismatch')
    else:
        path = f'eval/phase35/{case["_module"]}.py'
        require(identity.get('path') == path and identity.get('sha256') == module_hashes[path], 'module identity mismatch')
    refs = row.get('source_evidence', row.get('evidence_references', []))
    if not refs:
        require(judgment == 'AI_INSUFFICIENT_EVIDENCE' and substantive(row.get('insufficient_evidence_reason')), 'missing source evidence without explicit exception')
    for ref in refs:
        validate_evidence(ref, pages)
    for document in row.get('source_revision_hashes', []):
        require((document['document'], 1) in pages and document.get('pdf_sha256') == pages[document['document'], 1]['pdf_sha256'], 'source revision mismatch')
    for document in row.get('inspected_source_pages', []):
        validate_evidence(dict(document, pages_examined=document['pages'], location='Entire declared source inspected for scoring fairness.'), pages)
    for path, digest in row.get('frozen_scorer_identity', {}).items():
        require(path in ('eval/answer_scoring.py', 'eval/phase35/run_eval.py'), 'unexpected scorer source')
        require(sha((ROOT/path).read_bytes().replace(b'\r\n', b'\n')) == digest, 'frozen scorer hash mismatch')
    correction = row.get('proposed_correction', row.get('minimal_proposed_change'))
    require(judgment != 'AI_CORRECTION_RECOMMENDED' or bool(correction), 'correction missing proposed change')
    timestamp = row.get('review_timestamp_utc', row.get('review_timestamp'))
    require(isinstance(timestamp, str) and datetime.fromisoformat(timestamp).tzinfo is not None, 'missing zoned review timestamp')
    execution = row.get('agent_execution_name', row.get('reviewer_execution_identity', row.get('reviewer_execution_id')))
    require(isinstance(execution, str) and execution.startswith('/root/'), 'missing execution identity')
    return dict(judgment=judgment, rationale=rationale, evidence_references=refs,
                proposed_correction=correction, execution_identity=execution, confidence=confidence,
                review_timestamp=timestamp)


def context():
    from eval.framework.integrity import load_dataset, dataset_hash, file_hashes, split_of
    import pymupdf
    docs, all_cases = load_dataset()
    cases = {c['id']: c for c in all_cases if split_of(c['id']) == 'heldout'}
    require(len(cases) == 113, 'expected exactly 113 original held-out cases')
    pages, sources = {}, {}
    extracts = norm((ROOT/'docs/remediation/heldout_review/source_pages.md').read_text())
    for document, dataset_pages in docs.items():
        relative = f'docs/remediation/heldout_review/source_pdfs/{document}'
        path = ROOT/relative
        digest = sha(path.read_bytes())
        with pymupdf.open(path) as pdf:
            require(len(pdf) == len(dataset_pages), 'PDF/dataset page count mismatch')
            for i, page in enumerate(pdf):
                text = page.get_text()
                require(norm(text) == norm(dataset_pages[i]), f'PDF/dataset page text mismatch {document}:{i+1}')
                require(norm(text) in extracts, f'PDF/extracted page text mismatch {document}:{i+1}')
                pages[document, i+1] = dict(text=text, pdf_sha256=digest, pdf_path=relative)
        sources[relative] = digest
    return cases, pages, dataset_hash(all_cases), file_hashes(), sources


def load_initials(cases, pages, dataset_sha, modules):
    originals, normalized, hashes = {}, {}, {}
    for name in NAMES:
        path = ROOT/f'ai_review/initial/{name}.jsonl'
        content = path.read_bytes()
        rows = index_rows([json.loads(line) for line in content.splitlines()], cases)
        originals[name] = rows
        normalized[name] = {cid: validate_review(row, cases[cid], pages, dataset_sha, modules) for cid, row in rows.items()}
        hashes[str(path.relative_to(ROOT))] = sha(content)
    return originals, normalized, hashes


def build(adjudications=None, seal=False):
    cases, pages, dataset_sha, modules, sources = context()
    originals, reviews, hashes = load_initials(cases, pages, dataset_sha, modules)
    manifest_path = ROOT/'ai_review/initial_manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        require(manifest['initial_file_sha256'] == hashes, 'immutable initial bytes changed')
        require(manifest['dataset_sha256'] == dataset_sha and manifest['module_sha256'] == modules and manifest['source_pdf_sha256'] == sources, 'sealed source/dataset identity changed')
    else:
        manifest = dict(schema_version=1, reviewer_type='AI', created_at=datetime.now(timezone.utc).isoformat(),
            git_head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
            dataset_sha256=dataset_sha, module_sha256=modules, source_pdf_sha256=sources,
            initial_file_sha256=hashes, cases=sorted(cases), exact_model_id=None,
            model_identity_reason='Runtime does not expose an exact model identifier; no model identity inferred.',
            immutability='Initial byte streams preserved; exclusively created hash manifest detects subsequent changes.')
        if seal:
            with manifest_path.open('x') as out:
                json.dump(manifest, out, indent=2, sort_keys=True); out.write('\n')
    decisions = {}
    if adjudications is not None:
        require(adjudications.get('reviewer_type') == 'AI', 'lead reviewer must be AI')
        require(adjudications.get('lead_execution_identity') == '/root', 'missing actual lead execution identity')
        require(bool(adjudications.get('prior_exposure')), 'lead prior exposure disclosure required')
        lead_time = adjudications.get('review_timestamp_utc')
        require(isinstance(lead_time, str) and datetime.fromisoformat(lead_time).tzinfo is not None, 'missing zoned lead review timestamp')
        decisions = adjudications['decisions']
        require(set(decisions) <= set(cases), 'unknown adjudication case')
    ledger = []
    pending = []
    for cid, case in cases.items():
        initial = {name: reviews[name][cid] for name in NAMES}
        judgments = {x['judgment'] for x in initial.values()}
        issue = judgments != {'AI_PASS'}
        decision = decisions.get(cid)
        if issue and decision is None:
            pending.append(cid)
        source = initial['source_verification']
        final_judgment = 'AI_PASS' if judgments == {'AI_PASS'} else 'AI_AMBIGUOUS'
        rationale = source['rationale']
        correction = None
        status = 'CONSENSUS_SOURCE_VALIDATED' if not issue else 'LEAD_ADJUDICATION_PENDING'
        if decision:
            final_judgment = decision['judgment']
            require(final_judgment in JUDGMENTS, f'invalid adjudication {cid}')
            require(substantive(decision.get('rationale')), f'blank adjudication rationale {cid}')
            require(decision.get('status') in ('RESOLVED','UNRESOLVED_POLICY'), 'invalid adjudication status')
            require(bool(decision.get('evidence_references')), f'adjudication source evidence missing {cid}')
            for evidence in decision['evidence_references']:
                validate_evidence(evidence, pages)
            require(final_judgment != 'AI_CORRECTION_RECOMMENDED' or bool(decision.get('proposed_correction')), 'adjudication correction missing proposed change')
            rationale, correction, status = decision['rationale'], decision.get('proposed_correction'), decision['status']
        merged_evidence = []
        for evidence in [ref for review in initial.values() for ref in review['evidence_references']] + (decision.get('evidence_references', []) if decision else []):
            if evidence not in merged_evidence:
                merged_evidence.append(evidence)
        ledger.append(dict(case_id=cid, reviewer_type='AI', review_track='AI_REVIEW_COMPLETE' if not pending and adjudications is not None else 'AI_REVIEW_INCOMPLETE',
            dataset_identity=dict(dataset_sha256=dataset_sha, module=case['_module'], module_sha256=modules[f'eval/phase35/{case["_module"]}.py'], split='heldout'),
            source_revision_hashes=sources,
            provenance_manifest=dict(path='ai_review/initial_manifest.json', git_head=manifest['git_head'], created_at=manifest['created_at']),
            source_facts=source['rationale'], evidence_references=merged_evidence,
            reviewer_judgment=final_judgment, proposed_correction=correction, rationale=rationale,
            confidence=min([x['confidence'] for x in initial.values()]+([decision['confidence']] if decision and 'confidence' in decision else [])),
            review_timestamp=max([x['review_timestamp'] for x in initial.values()]+([adjudications['review_timestamp_utc']] if adjudications else [])),
            model_identity=None, model_identity_reason=manifest['model_identity_reason'],
            execution_identities=[x['execution_identity'] for x in initial.values()]+['/root/ai_review_ledger','/root'],
            initial_judgments={name:dict(initial_file=f'ai_review/initial/{name}.jsonl', initial_file_sha256=hashes[f'ai_review/initial/{name}.jsonl'], record=originals[name][cid]) for name in NAMES},
            verification_status='ALL_INITIAL_EVIDENCE_QUOTATIONS_AND_HASHES_VERIFIED_AGAINST_ACTUAL_PDF_PAGES',
            disagreement_status='INITIAL_JUDGMENTS_DIFFER' if len(judgments)>1 else 'INITIAL_JUDGMENTS_AGREE',
            adjudication_status=status, lead_adjudication=decision,
            lead_prior_exposure=adjudications.get('prior_exposure') if adjudications else None,
            formal_status='OFFICIAL_HUMAN_CERTIFIED_EVALUATION_PENDING'))
    complete = adjudications is not None and not pending
    for row in ledger:
        row['review_track'] = 'AI_REVIEW_COMPLETE' if complete else 'AI_REVIEW_INCOMPLETE'
    return ledger, pending, manifest


def validate_published(rows, expected_ledger):
    """Reject missing/duplicate/unknown IDs and any alteration of validated proof."""
    expected = {row['case_id']: row for row in expected_ledger}
    indexed = index_rows(rows, expected)
    for cid, row in indexed.items():
        require(row == expected[cid], f'published ledger proof/content mismatch {cid}')
    return True


def publish(ledger, pending, path):
    require(not pending and len(ledger) == 113 and all(row['review_track'] == 'AI_REVIEW_COMPLETE' for row in ledger), f'cannot publish before complete lead adjudication: {pending}')
    with Path(path).open('x') as out:
        for row in ledger:
            out.write(json.dumps(row, sort_keys=True, ensure_ascii=False)+'\n')
    validate_published([json.loads(line) for line in Path(path).read_text().splitlines()], ledger)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seal', action='store_true')
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    path = ROOT/'ai_review/adjudications.json'
    adjudications = json.loads(path.read_text()) if path.exists() else None
    ledger, pending, _ = build(adjudications, args.seal)
    if args.publish:
        require(adjudications is not None and not pending, f'cannot publish before lead adjudication: {pending}')
        publish(ledger, pending, ROOT/'AI_HELDOUT_113_REVIEW.jsonl')
    print(json.dumps(dict(validated_cases=len(ledger), pending_adjudication=pending, published=args.publish)))

if __name__ == '__main__':
    main()
