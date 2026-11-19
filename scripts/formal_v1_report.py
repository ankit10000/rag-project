"""Offline diagnostic report of saved v1 scores; never runs or accepts an evaluation.

After an independently authorized run, supply its raw JSONL and a metadata JSON
whose keys equal ``current_identity()`` plus ``results_sha256``. Example:
  python -B scripts/formal_v1_report.py --results RUN.jsonl --metadata RUN.json \
      --split heldout --tier 1 --output NEW_REPORT.json

Metadata consistency does not authenticate a reviewer, approval, execution or
runtime context. This utility always reports FORMAL_EVALUATION_INCOMPLETE;
the approving authority must separately establish the actual acceptance record.
It does not rescore answers or reinterpret errors. Outputs contain aggregate
metrics and hashes, no prompts, answers or per-case judgments. Publication is a
single fsynced no-replace file, not activation of the official result publisher.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eval.framework import answer_metrics, providers
from eval.framework.safety import threshold_result


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _nonfinite(_):
    raise ValueError('non-finite JSON number')


def parse_json(text):
    return json.loads(text, object_pairs_hook=_pairs, parse_constant=_nonfinite)


def read_rows(raw):
    return [parse_json(line) for line in raw.decode('utf-8').splitlines() if line.strip()]


def current_identity():
    """Verify actual frozen bytes before reporting; never repairs the freeze."""
    from eval.framework.frozen_manifest import load_frozen_manifest, verify_frozen_manifest
    frozen, problems = load_frozen_manifest(str(ROOT/'eval/phase35/frozen_manifest.json'))
    if not problems:
        problems, _ = verify_frozen_manifest(frozen)
    if problems:
        raise ValueError('frozen manifest verification failed')
    return dict(scorer='v1', manifest_sha256=frozen['content_sha256'],
        dataset_sha256=frozen['content']['dataset']['dataset_sha256'],
        dataset_version=frozen['content']['dataset']['dataset_version'],
        source_sha256={name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                       for name in ('eval/phase35/run_eval.py', 'eval/answer_scoring.py')},
        annotation_identity='NOT_APPLICABLE_V1')


def _number(value, *, low=0, high=None):
    try:
        finite = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError('invalid numeric metric')
    if value < low or (high is not None and value > high):
        raise ValueError('numeric metric outside bounds')


def make_report(rows, cases, metadata, identity, *, split, tier):
    """Aggregate supplied scores only; caller supplies dataset cases for testability."""
    from eval.framework.integrity import split_of
    if split not in ('dev', 'heldout') or type(tier) is not int or tier not in (1, 2):
        raise ValueError('explicit supported split and tier required')
    if not isinstance(metadata, dict) or any(metadata.get(k) != v for k, v in identity.items()):
        raise ValueError('result identity differs from verified v1 identity')
    if not isinstance(metadata.get('results_sha256'), str) or not re.fullmatch('[0-9a-f]{64}', metadata['results_sha256']):
        raise ValueError('raw results hash required')
    eligible = {c['id']: c for c in cases if split_of(c['id']) == split
                and (tier == 1 or c['tier'] == 'both')}
    seen = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('id'), str):
            raise ValueError('invalid result record')
        case = eligible.get(row['id'])
        if case is None or row['id'] in seen:
            raise ValueError('unknown, ineligible or repeated case')
        seen.add(row['id'])
        if row.get('split') != split or type(row.get('tier')) is not int or row['tier'] != tier:
            raise ValueError('result split/tier mismatch')
        if row.get('category') != case['category']:
            raise ValueError('result category mismatch')
        status = row.get('status')
        if status not in ('answered', 'abstained', 'partial', 'conflict', 'unverified', 'error'):
            raise ValueError('unknown result status')
        score = row.get('score')
        if not isinstance(score, dict) or score.get('status') != status:
            raise ValueError('missing score or status mismatch')
        for key in ('correct', 'correct_lenient', 'unsupported'):
            if type(score.get(key)) is not bool:
                raise ValueError('non-boolean score')
        for key in ('abstain_ok', 'partial_ok', 'conflict_ok'):
            if key not in score or (score[key] is not None and type(score[key]) is not bool):
                raise ValueError('invalid conditional score')
        for expected, key in (('expect_abstain', 'abstain_ok'), ('expect_partial', 'partial_ok'),
                              ('expect_conflict', 'conflict_ok')):
            if status != 'error' and case.get(expected) and type(score[key]) is not bool:
                raise ValueError('conditional score unavailable')
        for key in ('fact_recall', 'citation_correctness', 'citation_completeness'):
            _number(score.get(key), high=1)
        if type(score.get('fabricated')) is not int or score['fabricated'] < 0:
            raise ValueError('invalid fabricated citation count')
        for key in ('forbidden_hits', 'ungrounded_numbers'):
            if not isinstance(score.get(key), list):
                raise ValueError('invalid issue list')
        if status == 'error' and (score['correct'] or score['correct_lenient']):
            raise ValueError('error row cannot be correct')
        _number(row.get('latency_s'))
        for key in ('llm_calls', 'prompt_tokens', 'output_tokens'):
            if type(row.get(key)) is not int or row[key] < 0:
                raise ValueError('invalid usage count')
    aggregate = answer_metrics.aggregate(rows, eligible)
    # Omit per-case issues: they can contain sensitive model/source text.
    aggregate.pop('per_case')
    threshold = threshold_result(split, tier, aggregate['overall']['correct'], len(rows))
    complete = seen == set(eligible)
    if not complete:
        threshold['status'] = 'INCOMPLETE'
    errors = sum(row['status'] == 'error' for row in rows)
    return dict(schema='formal-v1-diagnostic-report/1',
        formal_outcome='FORMAL_EVALUATION_INCOMPLETE', acceptance_eligible=False,
        authority='NOT_AUTHENTICATED_BY_THIS_TOOL', identity=identity,
        results_sha256=metadata['results_sha256'], split=split, tier=tier,
        complete=complete, expected_cases=len(eligible), missing_cases=len(eligible)-len(seen),
        error_rows=errors, threshold=threshold, metrics=aggregate,
        provider_usage=providers.summarize_rows(rows).as_dict(),
        limitations=['Saved scores are not re-scored or authenticated as executed v1 results.',
            'Metadata consistency cannot prove approval, review or exact runtime contexts.',
            'Threshold PASS/FAIL is mechanical; final error/incomplete disposition needs approved policy.',
            'Citation metrics measure source structure, not claim-level semantic entailment.'])


def publish_new(path, report):
    """Publish fully written bytes without replacing even a dangling final symlink.

    A post-link directory-fsync error can leave a complete destination whose
    durability is unconfirmed. Inspect an existing output after an error; never
    assume nothing was published or overwrite it on retry.
    """
    path = Path(os.path.abspath(path))
    official = ROOT/'eval/phase35/results'
    if path.is_relative_to(official) or path.resolve().is_relative_to(official.resolve()):
        raise ValueError('diagnostic reports cannot enter official results directory')
    # Walk existing parents through directory descriptors without following links.
    directory = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    temporary = '.formal-report-'+uuid.uuid4().hex
    created = False
    try:
        for part in path.parent.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory); directory = child
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=directory)
        created = True
        with os.fdopen(fd, 'wb') as output:
            output.write((json.dumps(report, sort_keys=True, ensure_ascii=False,
                                     indent=2, allow_nan=False)+'\n').encode())
            output.flush(); os.fchmod(output.fileno(), 0o444); os.fsync(output.fileno())
        os.link(temporary, path.name, src_dir_fd=directory, dst_dir_fd=directory,
                follow_symlinks=False)
        os.fsync(directory)
    finally:
        if created:
            os.unlink(temporary, dir_fd=directory)
        os.close(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--split', choices=['dev', 'heldout'], required=True)
    parser.add_argument('--tier', type=int, choices=[1, 2], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    from eval.framework.integrity import load_dataset
    identity = current_identity()
    raw = args.results.read_bytes()
    metadata = parse_json(args.metadata.read_text())
    if not isinstance(metadata, dict) or metadata.get('results_sha256') != hashlib.sha256(raw).hexdigest():
        raise ValueError('raw results do not match metadata hash')
    _, cases = load_dataset()
    report = make_report(read_rows(raw), cases, metadata, identity, split=args.split, tier=args.tier)
    publish_new(args.output, report)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, UnicodeError):
        print('Diagnostic report refused: invalid input, identity or output destination.', file=sys.stderr)
        raise SystemExit(2)
