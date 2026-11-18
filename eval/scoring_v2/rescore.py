"""Opt-in OFFLINE scorer v2.1 runner (WP5 §12–14); never invokes evaluation.

Run header contract: dataset_manifest_content_sha256, dataset_version,
git_head, file_sha256 (all four data modules), and for tier2 chunk_config
{chunk_size,chunk_overlap,chunk_strategy}, chunk_count, chunk_table_sha256.
Header manifest proof must match the manifest committed at git_head; older
revisions without one require operator pinning for non-acceptance diagnostics.
Exit 2 covers acceptance prerequisites pending WP7/owner approval (the spec
assigns no special code to this configuration error). No real-case
annotation policy is inferred. Outputs are new files, opened exclusively.
"""
import argparse
import datetime
import json
import platform
from pathlib import Path
import subprocess
import sys
import unicodedata
from . import context
from .rescore_meta import (RESTATED_FUNCTIONS, ast_hashes, source_pins,
                          scorer_identity, change_codes, diff_markdown, verify_header_manifest)
from eval.framework.hashing import portable_sha256, raw_sha256
from eval.framework.integrity import dataset_hash
from eval.phase35.run_eval import score_generic, split_of

ROOT = Path(__file__).resolve().parents[2]
DATA_FILES = [f'eval/phase35/data_{letter}.py' for letter in 'ABCD']


class RescoreError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def load_pinned_dataset(root, revision=None, header=None):
    if header is not None and not isinstance(header, dict):
        raise RescoreError(5, 'run header must be an object')
    header = header or {}
    rev = header.get('git_head') or revision
    if not isinstance(rev, str) or not rev or rev.startswith('-'):
        raise RescoreError(5, 'dataset revision is required')
    required = ('dataset_manifest_content_sha256', 'dataset_version', 'git_head', 'file_sha256')
    if header and (any(key not in header for key in required) or not isinstance(header.get('file_sha256'), dict)):
        raise RescoreError(5, 'incomplete run-header dataset pin')
    try:
        resolved = subprocess.check_output(['git', 'rev-parse', '--verify', f'{rev}^{{commit}}'], cwd=root, stderr=subprocess.PIPE).decode().strip()
        if revision and header:
            explicit = subprocess.check_output(['git', 'rev-parse', '--verify', f'{revision}^{{commit}}'], cwd=root, stderr=subprocess.PIPE).decode().strip()
            if explicit != resolved:
                raise RescoreError(5, 'run header and operator revision disagree')
        docs, cases, hashes = {}, [], {}
        for path in DATA_FILES:
            data = subprocess.check_output(['git', 'show', f'{resolved}:{path}'], cwd=root, stderr=subprocess.PIPE)
            hashes[path] = portable_sha256(data, 'text')
            if header and header['file_sha256'].get(path, header['file_sha256'].get(Path(path).name)) != hashes[path]:
                raise RescoreError(5, f'dataset hash mismatch: {path}')
            namespace = {'__name__': f'pinned_{Path(path).stem}'}
            exec(compile(data, path, 'exec'), namespace)
            for name, pages in namespace['DOCUMENTS'].items():
                if name in docs:
                    raise RescoreError(5, 'duplicate pinned document')
                docs[name] = pages
            cases.extend(dict(case, _module=Path(path).stem) for case in namespace['CASES'])
    except (subprocess.CalledProcessError, KeyError, TypeError, SyntaxError) as exc:
        raise RescoreError(5, f'cannot load pinned dataset: {type(exc).__name__}') from exc
    from eval.phase35.validate import validate
    if validate(docs, cases):
        raise RescoreError(5, 'pinned dataset validation failed')
    if header:
        try:
            blob = subprocess.check_output(['git','show',f'{resolved}:eval/phase35/frozen_manifest.json'],cwd=root,stderr=subprocess.PIPE)
            if not verify_header_manifest(json.loads(blob),header,cases,hashes):
                raise RescoreError(5,'run header does not match pinned manifest/dataset')
        except (subprocess.CalledProcessError,ValueError,KeyError,TypeError) as exc:
            raise RescoreError(5,'run header lacks independently verifiable pinned manifest evidence') from exc
    pin = {'manifest_content_sha256': header.get('dataset_manifest_content_sha256'),
           'dataset_version': header.get('dataset_version'), 'pin_source': 'run_header' if header else 'operator_git_rev',
           'git_rev': resolved, 'file_sha256': hashes}
    return docs, cases, pin


def pipeline_metadata(root):
    from .tables import RESTATED_SOURCE_AST_SHA256
    paths = set(RESTATED_FUNCTIONS.values()) | {'services/chunker.py'}
    sources = {path: (root / path).read_bytes() for path in paths}
    hashes, minimum = source_pins(sources)
    if hashes != RESTATED_SOURCE_AST_SHA256 or minimum != 10:
        raise RescoreError(6, 'restated pipeline source hash mismatch')
    return hashes


def render_pages(docs):
    import pymupdf
    extracted = {}
    for name, pages in docs.items():
        with pymupdf.open() as pdf:
            for text in pages:
                page = pdf.new_page()
                page.insert_textbox(pymupdf.Rect(36, 36, 559, 806), text, fontsize=9)
            data = pdf.tobytes()
        with pymupdf.open(stream=data, filetype='pdf') as pdf:
            extracted[name] = [(page.number + 1, page.get_text(sort=True)) for page in pdf]
    return extracted


def parse_config(value):
    try:
        if isinstance(value, dict):
            config = (value['chunk_size'], value['chunk_overlap'], value['chunk_strategy'])
        else:
            size, overlap, strategy = value.split(',')
            config = (int(size), int(overlap), strategy)
        size, overlap, strategy = config
        if type(size) is not int or type(overlap) is not int or size <= 0 or not 0 <= overlap < size or strategy not in ('words', 'sentences'):
            raise ValueError()
        return config
    except (ValueError, TypeError, KeyError, AttributeError):
        raise RescoreError(4, 'invalid chunk config; expected SIZE,OVERLAP,words|sentences') from None


def read_rows(data, tier, cases):
    by_id, seen, rows = {case['id']: case for case in cases}, set(), []
    for index, line in enumerate(data.decode('utf-8').splitlines(), 1):
        try:
            row = json.loads(line)
            case = by_id[row['id']]
            if row['id'] in seen or type(row['tier']) is not int or row['tier'] != tier or row['split'] != 'dev' or split_of(row['id']) != 'dev':
                raise ValueError('duplicate, tier mismatch, or non-dev row')
            if row.get('question') != case['question'] or not isinstance(row['score'], dict):
                raise ValueError('question or score mismatch')
            if not isinstance(row.get('answer'), str) or row.get('status') not in ('answered','abstained','unverified','error','partial','conflict') or not isinstance(row.get('citations'), list):
                raise ValueError('invalid result fields')
            if any(not isinstance(c, dict) or type(c.get('chunk_id')) is not int for c in row['citations']):
                raise ValueError('invalid citation')
            seen.add(row['id']); rows.append(row)
        except (ValueError, TypeError, KeyError) as exc:
            raise RescoreError(4, f'invalid source row {index}: {exc}') from exc
    if not rows:
        raise RescoreError(4, 'source results are empty')
    return rows, by_id


def _unique_json_object(pairs):
    """Reject ambiguous original annotation records instead of overwriting them."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate annotation JSON key: {key}')
        result[key] = value
    return result


def rescore(args, root=ROOT):
    from . import score_case, validate_annotations
    source_path = Path(args.results)
    source_bytes = source_path.read_bytes()
    header_bytes = Path(args.run_header).read_bytes() if args.run_header else None
    try:
        header = json.loads(header_bytes) if header_bytes else None
    except ValueError as exc:
        raise RescoreError(5, 'invalid run header JSON') from exc
    docs, cases, pin = load_pinned_dataset(root, args.dataset_rev, header)
    annotations_bytes = Path(args.annotations).read_bytes()
    try:
        ann = json.loads(annotations_bytes, object_pairs_hook=_unique_json_object)
        errors = validate_annotations(ann, cases, docs)
        if errors:
            raise ValueError('; '.join(errors))
    except (ValueError, TypeError, KeyError) as exc:
        raise RescoreError(7, f'annotation validation failed: {exc}') from exc
    rows, by_id = read_rows(source_bytes, args.tier, cases)
    pins = pipeline_metadata(root)
    manifest = json.loads((root / 'eval/phase35/frozen_manifest.json').read_bytes())
    modules = {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted((root / 'eval/scoring_v2').glob('*.py'))}
    identity = scorer_identity(modules, annotations_bytes)
    table, tier2 = [], {}
    if args.tier == 2:
        if header and any(k not in header for k in ('chunk_config', 'chunk_count', 'chunk_table_sha256')):
            raise RescoreError(5, 'run header lacks tier2 chunk proof')
        config = parse_config(header['chunk_config'] if header else (args.chunk_config or '100,20,words'))
        if header and args.chunk_config and parse_config(args.chunk_config) != config:
            raise RescoreError(5, 'operator chunk config disagrees with run header')
        from services.chunker import chunk_page
        table = context.build_tier2_chunks(render_pages(docs), config, chunk_page)
        tier2 = dict(zip(('chunk_size', 'chunk_overlap', 'chunk_strategy'), config),
                     min_page_words=10, dedupe='sha1(ws-collapsed lower)', rect=[36,36,559,806], fontsize=9,
                     extractor='get_text(sort=True)', chunk_config_source='run_header' if header else 'assumed_default',
                     chunk_count=len(table), chunk_table_sha256=context.chunk_table_sha256(table), restated_source_ast_sha256=pins)
    output, row_meta = [], []
    counts = dict.fromkeys(('exact','mismatch','error_row','fallback','drift','v2_flips'), 0)
    for row in rows:
        case = by_id[row['id']]
        if row['status'] == 'error':
            pair, ids, text, status, mode = {}, set(), None, 'error_row', 'unavailable_error_row'
        else:
            pair, ids, text, status, mode = (context.verify_tier1(row,case,docs) if args.tier == 1 else context.verify_tier2(row,table,case,header))
        counts['exact' if status == 'exact' else 'error_row' if status == 'error_row' else 'mismatch'] += 1
        if status.startswith('mismatch') and args.tier == 2 and args.allow_page_superset:
            text, mode = context.page_superset(row,docs), 'tier2_page_superset_NON_ACCEPTANCE'
            counts['fallback'] += 1
        current = score_generic(case,row,pair,ids,text or '')
        if args.tier == 2:
            gold = {(s['document'], s['page']) for s in case['gold_sources']}
            refs = [(r.get('document_name', r.get('document')), r.get('page_number', r.get('page')))
                    for r in row.get('retrieved', [])]
            current.update(retrieval_page_recall=len(gold & set(refs))/len(gold) if gold else None,
                           retrieval_first_gold_rank=next((i for i,r in enumerate(refs,1) if r in gold),None))
        if row['status'] == 'error':
            current = dict(correct=False,correct_lenient=False,unsupported=False,citation_correctness=0.0,
                           citation_completeness=0.0,fabricated=0,abstain_ok=None,fact_recall=0.0,
                           forbidden_hits=[],ungrounded_numbers=[],partial_ok=None,conflict_ok=None,status='error')
        v2 = score_case(case,row,pair,ids,text,case['history'],ann['cases'][case['id']])
        codes, changed = change_codes(current,v2)
        counts['drift'] += row['score'] != current
        counts['v2_flips'] += current.get('correct') != v2.get('correct')
        output.append(dict(id=row['id'],tier=args.tier,split=row['split'],v1_stored=row['score'],v1_current=current,
                           v2=v2,context_mode=mode,reconstruction_status=status,rule_codes=codes,changed_signals=changed))
        row_meta.append(dict(id=row['id'],tier=args.tier,context_mode=mode,reconstruction_status=status,
                             context_sha256=context.text_sha256(text) if text is not None else None,
                             chunk_sha256={str(cid): table[cid-1]['sha256'] for cid in ids if 0 < cid <= len(table)}))
    eligible = (pin['pin_source'] == 'run_header' and not any(counts[k] for k in ('mismatch','error_row','fallback','drift'))
                and manifest['content'].get('acceptance_scorer') == {k:identity[k] for k in ('name','version','sha256')})
    if args.acceptance:
        if counts['mismatch'] or counts['fallback']:
            raise RescoreError(4, 'context reconstruction mismatch; acceptance refused')
        if counts['drift']:
            raise RescoreError(8, 'v1 stored/current drift; acceptance refused')
        if not eligible:
            raise RescoreError(2, 'acceptance requires run-header pin, frozen v2 scorer identity and pending V-5/V-9 policy')
    runner = (root / 'eval/phase35/run_eval.py').read_bytes()
    validator = (root / 'eval/phase35/validate.py').read_bytes()
    import pymupdf
    sidecar = dict(sidecar_format='phase35-scoring-sidecar/1',scorer=identity,
        v1=dict(answer_scoring_sha256=portable_sha256((root/'eval/answer_scoring.py').read_bytes(),'text'),
                run_eval_sha256=portable_sha256(runner,'text'),ast_sha256=ast_hashes(runner.decode(),['score_generic','norm_numbers','tier1_context','NUM_RE','REF_RE','split_of']),
                validate_sha256=portable_sha256(validator,'text'),validate_norm_ast_sha256=ast_hashes(validator.decode(),['norm'])['norm']),
        dataset=dict(run_time=dict(pin,dataset_version=pin['dataset_version'] or ann['dataset_version']),
                     current=dict(manifest_content_sha256=manifest['content_sha256'],dataset_version=manifest['content']['dataset']['dataset_version'])),
        source_results=dict(path=str(source_path),sha256=raw_sha256(source_bytes),rows=len(rows),run_header_sha256=raw_sha256(header_bytes) if header_bytes else None),
        environment=dict(python=platform.python_version(),unicodedata=unicodedata.unidata_version,pymupdf_bind=pymupdf.VersionBind,mupdf=pymupdf.VersionFitz,platform=platform.platform()),
        context_config=dict(tier1=dict(function='run_eval.tier1_context',context_max_chars=12000,context_max_chunks=8,assumption_checked=args.tier==1),tier2=tier2),
        rows=row_meta,counts=counts,acceptance_eligible=eligible,generated_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    out = Path(args.output)
    diff = out.with_suffix('.diff.md')
    paths = [out,Path(str(out)+'.scoring.json'),diff]
    if any(p.resolve() == source_path.resolve() for p in paths):
        raise RescoreError(4,'output must not be source results')
    payloads = [''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in output),json.dumps(sidecar,indent=2,ensure_ascii=False)+'\n',diff_markdown(output)]
    if len({p.resolve() for p in paths}) != 3 or any(p.exists() for p in paths):
        raise FileExistsError('an output path already exists or aliases another output')
    handles, created = [], []
    try:
        for path in paths:
            handles.append(path.open('x',encoding='utf-8'))
            created.append(path)
        for handle,payload in zip(handles,payloads):
            handle.write(payload)
    except BaseException:
        for handle in handles:
            handle.close()
        for path in created:
            path.unlink()
        raise
    finally:
        for handle in handles:
            handle.close()
    return sidecar


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',required=True)
    parser.add_argument('--tier',type=int,choices=[1,2],required=True)
    pin = parser.add_mutually_exclusive_group()
    pin.add_argument('--run-header'); pin.add_argument('--dataset-rev')
    parser.add_argument('--chunk-config')
    parser.add_argument('--annotations',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--acceptance',action='store_true')
    parser.add_argument('--allow-page-superset',action='store_true')
    args = parser.parse_args(argv)
    try:
        rescore(args)
        return 0
    except RescoreError as exc:
        print(str(exc),file=sys.stderr); return exc.code
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'rescore refused: {type(exc).__name__}: {exc}',file=sys.stderr); return 2


if __name__ == '__main__':
    raise SystemExit(main())
