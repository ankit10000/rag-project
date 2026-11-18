"""Development-only WP7 comparison bundles, delegating unchanged WP6 scoring.

Example: python -m eval.runner_preparation.offline --results DEV.jsonl --tier 1
 --dataset-rev REV --annotations ANNOTATIONS.json --scorer-version 2.1.0
 --output-root /private/tmp/comparisons --run-id local-check

No live evaluation, acceptance flag, held-out split, fallback, implicit scorer
upgrade or annotations are provided. Official runner, gate and defaults remain
untouched. Historical reconstruction remains diagnostic evidence only. Output
roots must use physical paths; symlink components are deliberately refused.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from .selection import select_scorer
from .provenance import _json


def _context_preflight(source_bytes):
    """Reject malformed/missing/duplicate context rather than completing a bundle."""
    rows = []
    for number, line in enumerate(source_bytes.decode('utf-8').splitlines(), 1):
        try:
            row = _json(line.encode('utf-8'))
            if not isinstance(row, dict) or row.get('split') != 'dev':
                raise ValueError('only development rows are allowed')
            if row.get('status') != 'error':
                tier = row.get('tier')
                key = 'context' if tier == 1 else 'retrieved' if tier == 2 else None
                items = row.get(key) if key else None
                if not isinstance(items, list):
                    raise ValueError('missing context items')
                ids = []
                for item in items:
                    if not isinstance(item, dict) or type(item.get('chunk_id')) is not int or item['chunk_id'] <= 0:
                        raise ValueError('invalid context reference')
                    ids.append(item['chunk_id'])
                if len(ids) != len(set(ids)):
                    raise ValueError('duplicate context IDs')
            rows.append(row)
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f'invalid development input row {number}: {exc}') from exc
    if not rows:
        raise ValueError('source results are empty')
    return rows


def _identity(annotation_bytes, repository_root):
    from eval.scoring_v2.rescore_meta import scorer_identity
    root = Path(repository_root)
    sources = {p.relative_to(root).as_posix():p.read_bytes()
               for p in sorted((root/'eval/scoring_v2').glob('*.py'))}
    return scorer_identity(sources,annotation_bytes)


def prepare_comparison(results, annotations, output_root, run_id, *, tier,
                       scorer_version, dataset_rev=None, run_header=None,
                       chunk_config=None, split='dev'):
    """Build a provenance-bound, exclusively published diagnostic bundle.

    Explicitly requires the v2 version and caller-provided complete annotations.
    The publish directory is controlled by artifacts.publish_bundle, never an
    official evaluation result path. A failed reconstruction/provenance check
    raises before the bundle is completed or becomes visible at its final path.
    """
    if split != 'dev' or type(tier) is not int or tier not in (1,2):
        raise ValueError('only development tier 1 or 2 comparisons are supported')
    if scorer_version != '2.1.0':
        raise ValueError('offline comparison requires explicit scorer version 2.1.0')
    if bool(dataset_rev) == bool(run_header):
        raise ValueError('exactly one dataset revision or run header is required')
    if annotations is None:
        raise ValueError('annotations must be supplied explicitly')
    source_path, annotation_path = Path(results), Path(annotations)
    source_bytes, annotation_bytes = source_path.read_bytes(), annotation_path.read_bytes()
    source_rows = _context_preflight(source_bytes)
    if any(row.get('tier') != tier for row in source_rows):
        raise ValueError('source tier differs from requested tier')
    annotation_object = _json(annotation_bytes)
    select_scorer(scorer_version,development=True,annotations=annotation_object)
    from eval.scoring_v2 import rescore as wp6
    from .artifacts import publish_bundle
    from .provenance import validate_comparison_inputs, verify_reconstruction
    identity = _identity(annotation_bytes,wp6.ROOT)
    header_bytes = Path(run_header).read_bytes() if run_header else None
    header = _json(header_bytes) if header_bytes else None
    docs,cases,pin = wp6.load_pinned_dataset(wp6.ROOT,dataset_rev,header)
    expected_pin = dict(pin,dataset_version=pin['dataset_version'] or annotation_object['dataset_version'])
    by_id = {case['id']:case for case in cases}
    table = None
    if tier == 2:
        config = wp6.parse_config(header['chunk_config'] if header else (chunk_config or '100,20,words'))
        from services.chunker import chunk_page
        table = wp6.context.build_tier2_chunks(wp6.render_pages(docs),config,chunk_page)
    reconstructed = {}
    for row in source_rows:
        if row['status'] == 'error':
            raise ValueError('exact context is required; error-row policy remains pending')
        if row['id'] not in by_id:
            raise ValueError('source case is missing from the pinned dataset')
        _,_,text,_,_ = verify_reconstruction(row,by_id[row['id']],docs,tier=tier,table=table,header=header)
        reconstructed[row['id']] = wp6.context.text_sha256(text)

    def build(staging):
        output = staging/'comparison.v2.jsonl'
        args = argparse.Namespace(results=str(source_path),tier=tier,
            run_header=str(run_header) if run_header else None,dataset_rev=dataset_rev,
            chunk_config=chunk_config,annotations=str(annotation_path),output=str(output),
            acceptance=False,allow_page_superset=False)
        sidecar = wp6.rescore(args)
        persisted = _json(Path(str(output)+'.scoring.json').read_bytes())
        if persisted != sidecar:
            raise ValueError('persisted scoring sidecar differs from returned metadata')
        rows = [_json(line.encode('utf-8')) for line in output.read_text().splitlines()]
        if sidecar.get('acceptance_eligible') is not False:
            raise ValueError('experimental comparison must not claim acceptance')
        if sidecar.get('dataset',{}).get('run_time') != expected_pin:
            raise ValueError('dataset provenance changed during comparison')
        expected_header = hashlib.sha256(header_bytes).hexdigest() if header_bytes is not None else None
        if sidecar.get('source_results',{}).get('run_header_sha256') != expected_header:
            raise ValueError('run-header provenance differs from captured bytes')
        if sidecar.get('scorer') != identity:
            raise ValueError('scorer source identity changed during comparison')
        if any(row.get('reconstruction_status') != 'exact' for row in rows):
            raise ValueError('context reconstruction mismatch; refusing completed bundle')
        for meta in sidecar['rows']:
            if reconstructed.get(meta['id']) != meta['context_sha256']:
                raise ValueError('reconstructed context changed during comparison')
        proof = validate_comparison_inputs(source_bytes,annotation_bytes,sidecar,rows)
        if source_path.read_bytes() != source_bytes or annotation_path.read_bytes() != annotation_bytes:
            raise ValueError('source results or annotations changed during comparison')
        if run_header and Path(run_header).read_bytes() != header_bytes:
            raise ValueError('run header changed during comparison')
        if _identity(annotation_bytes,wp6.ROOT) != identity:
            raise ValueError('scorer sources changed during comparison')
        with (staging/'provenance.json').open('x',encoding='utf-8') as handle:
            json.dump(proof,handle,sort_keys=True,indent=2,ensure_ascii=False)
            handle.write('\n')

    return publish_bundle(output_root,run_id,scorer_version=scorer_version,build_fn=build)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',required=True)
    parser.add_argument('--annotations',required=True)
    parser.add_argument('--tier',type=int,choices=(1,2),required=True)
    parser.add_argument('--split',choices=('dev',),default='dev')
    parser.add_argument('--scorer-version',choices=('2.1.0',),required=True)
    pin = parser.add_mutually_exclusive_group(required=True)
    pin.add_argument('--dataset-rev'); pin.add_argument('--run-header')
    parser.add_argument('--chunk-config')
    parser.add_argument('--output-root',required=True)
    parser.add_argument('--run-id',required=True)
    args = parser.parse_args(argv)
    from .artifacts import PublicationDurabilityError
    try:
        final = prepare_comparison(args.results,args.annotations,args.output_root,args.run_id,
            tier=args.tier,scorer_version=args.scorer_version,dataset_rev=args.dataset_rev,
            run_header=args.run_header,chunk_config=args.chunk_config,split=args.split)
        print(final)
        return 0
    except PublicationDurabilityError as exc:
        print(f'bundle committed at {exc.path}; durability confirmation failed; preserve its run ID',file=sys.stderr)
        return 2
    except (OSError,ValueError,TypeError,KeyError,NotImplementedError) as exc:
        print(f'development comparison refused: {exc}',file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
