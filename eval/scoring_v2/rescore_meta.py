"""Pure sidecar hashing and three-way-diff helpers; accepts source bytes."""
import ast
import hashlib
import json
from eval.framework.hashing import portable_sha256

RESTATED_FUNCTIONS = {
    'build_chunks': 'services/ingestion_service.py',
    'chunk_dedupe_key': 'services/ingestion_service.py',
    'extract_text': 'services/pdf_parser.py',
    'build_scratch_corpus': 'eval/phase35/run_eval.py',
}


def ast_hashes(source, names):
    tree = ast.parse(source)
    nodes = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for n in tree.body:
        if isinstance(n, ast.Assign):
            for target in n.targets:
                if isinstance(target, ast.Name):
                    nodes[target.id] = n
    return {name: hashlib.sha256(ast.dump(nodes[name]).encode()).hexdigest() for name in names}


def source_pins(sources):
    hashes = {name: ast_hashes(sources[path].decode(), [name])[name]
              for name, path in RESTATED_FUNCTIONS.items()}
    hashes['services/chunker.py'] = portable_sha256(sources['services/chunker.py'], 'text')
    tree = ast.parse(sources['services/ingestion_service.py'])
    minimum = next((n.value.value for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'MIN_PAGE_WORDS' for t in n.targets)
                    and isinstance(n.value, ast.Constant)), None)
    return hashes, minimum


def scorer_identity(sources, annotations_bytes):
    modules = {path: portable_sha256(data, 'text') for path, data in sorted(sources.items())}
    ann_hash = portable_sha256(annotations_bytes, 'text')
    records = dict(modules, **{'eval/scoring_v2/annotations.json': ann_hash})
    digest = hashlib.sha256(''.join(f'{path}\t{value}\n' for path, value in sorted(records.items())).encode()).hexdigest()
    return {'name': 'phase35-scorer', 'version': '2.1.0', 'tables_version': '2.1.0',
            'sha256': digest, 'module_sha256': modules, 'annotations_sha256': ann_hash,
            'annotation_schema': 'phase35-scorer-annotations/1'}


def change_codes(v1, v2):
    """Report changed signals and applicable rule families, never a policy label."""
    changed = [key for key in v1 if key in v2 and v1[key] != v2[key]]
    codes = []
    mapping = {'fact_recall': '§4.3/§7.4-polarity', 'forbidden_hits': '§9-forbidden',
               'abstain_ok': '§10.2-abstention', 'partial_ok': '§10.3-partial',
               'conflict_ok': '§11-disagreement', 'ungrounded_numbers': '§5-typed-guard'}
    for key in changed:
        if key in mapping:
            codes.append(mapping[key])
    if v2.get('history_echo'):
        codes.append('§8-echo')
    if changed and not codes:
        codes.append('§13.2-result')
    return sorted(set(codes)), changed


def diff_markdown(rows):
    lines = ['# Offline scorer comparison', '', 'Not an acceptance report or human-approved golden list.', '',
             '| Case | Dataset/reconstruction drift | v1 current | v2 | Applicable rule codes |',
             '|---|---|---|---|---|']
    for row in rows:
        drift = row['v1_stored'] != row['v1_current']
        flip = row['v1_current'].get('correct') != row['v2'].get('correct')
        if drift or flip:
            lines.append(f"| {row['id']} | {drift} | {row['v1_current'].get('correct')} | {row['v2'].get('correct')} | {', '.join(row['rule_codes'])} |")
    return '\n'.join(lines) + '\n'


def verify_header_manifest(manifest, header, cases, file_hashes):
    """Bind header evidence to the manifest committed at the pinned revision."""
    from eval.framework.integrity import dataset_hash
    content = manifest['content']
    canonical = json.dumps(content,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    dataset = content['dataset']
    return (digest == manifest['content_sha256'] == header['dataset_manifest_content_sha256']
            and dataset['dataset_version'] == header['dataset_version']
            and dataset['dataset_sha256'] == dataset_hash(cases)
            and dataset['file_sha256'] == file_hashes)
