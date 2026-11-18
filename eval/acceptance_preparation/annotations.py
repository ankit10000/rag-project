"""WP8 read-only annotation audit; structural validity never means human approval.

Consumes explicit source bytes and pinned dataset objects. It neither changes
annotations nor reads or writes review workbooks. Workbook inventories accept
bytes and inspect OOXML with the standard library only.
"""
import collections
import csv
import hashlib
import io
import json
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile
from eval.framework.integrity import dataset_hash
from eval.scoring_v2.annotations import entry_errors, validate_annotations
from eval.phase35.validate import norm

SCHEMA = 'phase35-wp8-annotation-audit/1'
DISPOSITIONS = ('VALID', 'INVALID', 'AMBIGUOUS', 'NEEDS_INDEPENDENT_REVIEW', 'NOT_APPLICABLE')
LEDGER_FIELDS = ('case_id', 'original_annotation_json', 'annotation_source_sha256',
                 'dataset_pin_json', 'source_refs_json', 'structural_validation',
                 'validation_errors_json', 'review_disposition', 'review_basis')


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _parse(data):
    if not isinstance(data, bytes):
        raise ValueError('annotation source must be bytes')
    def pairs(entries):
        out = {}
        for key, value in entries:
            if key in out:
                raise ValueError('duplicate JSON key: ' + key)
            out[key] = value
        return out
    try:
        return json.loads(data, object_pairs_hook=pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError('non-finite JSON: ' + value)))
    except (UnicodeError, ValueError) as exc:
        raise ValueError('invalid annotation document: ' + str(exc)) from exc


def source_references(case, docs):
    """Exact supplied frozen-data pages and spans; never synthesize a source."""
    references, errors = [], []
    for source in case.get('gold_sources', []):
        if not isinstance(source, dict):
            errors.append('SOURCE: malformed gold source'); continue
        document, page, span = (source.get(key) for key in ('document', 'page', 'span'))
        pages = docs.get(document) if isinstance(document, str) else None
        valid = isinstance(pages, list) and type(page) is int and 1 <= page <= len(pages)
        text = pages[page - 1] if valid else None
        reference = dict(document=document, page=page, gold_span=span, page_text=text,
                         page_text_sha256=_sha(text.encode('utf-8')) if isinstance(text, str) else None)
        references.append(reference)
        if not isinstance(text, str):
            errors.append('SOURCE: missing document/page reference')
        elif not isinstance(span, str) or not norm(span) or norm(span) not in norm(text):
            errors.append('SOURCE: gold span absent from referenced page')
    return references, errors


def _pin_errors(pin, cases, ann):
    fields = {'dataset_version', 'dataset_sha256', 'file_sha256', 'git_rev', 'manifest_content_sha256'}
    if not isinstance(pin, dict) or set(pin) != fields:
        return ['PROVENANCE: incomplete explicit dataset pin']
    errors = []
    if pin['dataset_sha256'] != dataset_hash(cases) or ann.get('dataset_sha256') != pin['dataset_sha256']:
        errors.append('PROVENANCE: annotation/dataset hash mismatch')
    if not isinstance(pin['dataset_version'], str) or not pin['dataset_version'] or ann.get('dataset_version') != pin['dataset_version']:
        errors.append('PROVENANCE: annotation/dataset version mismatch')
    if not isinstance(pin['git_rev'], str) or not re.fullmatch('[0-9a-f]{40}', pin['git_rev']):
        errors.append('PROVENANCE: full git revision required')
    files = pin['file_sha256']
    expected = {f'eval/phase35/data_{letter}.py' for letter in 'ABCD'}
    if not isinstance(files, dict) or set(files) != expected or any(not isinstance(v, str) or not re.fullmatch('[0-9a-f]{64}', v) for v in files.values()):
        errors.append('PROVENANCE: incomplete dataset file identities')
    if not isinstance(pin['manifest_content_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', pin['manifest_content_sha256']):
        errors.append('PROVENANCE: manifest identity required')
    return errors


def audit_annotations(annotation_bytes, cases, docs, *, dataset_pin):
    """Audit all case entries, retaining originals and pending review separately.

    This function consumes provenance supplied by the caller; file-byte/pin
    verification belongs to the caller. It does not attest a human reviewed it.
    """
    source_hash = _sha(annotation_bytes)
    try:
        ann = _parse(annotation_bytes)
        if not isinstance(ann, dict):
            raise ValueError('annotation root must be an object')
    except ValueError as exc:
        record = dict(case_id='__FILE__', original_annotation_json=annotation_bytes.decode('utf-8', errors='replace'),
                      annotation_source_sha256=source_hash, dataset_pin_json=_json(dataset_pin), source_refs_json='[]',
                      structural_validation='INVALID', validation_errors_json=_json([str(exc)]),
                      review_disposition='INVALID', review_basis='Malformed original preserved; no repair or review inferred.')
        return dict(schema=SCHEMA, annotation_source_sha256=source_hash, records=[record],
                    structural_counts={'INVALID': 1}, disposition_counts={'INVALID': 1}, validation_errors=[str(exc)])
    ids = [case.get('id') for case in cases]
    global_errors = _pin_errors(dataset_pin, cases, ann)
    if any(not isinstance(cid, str) or not cid for cid in ids) or len(ids) != len(set(ids)):
        global_errors.append('DATASET: invalid or duplicate case ids')
    try:
        validator_errors = validate_annotations(ann, cases, docs)
    except (TypeError, ValueError, KeyError, IndexError, AttributeError) as exc:
        validator_errors = ['VALIDATOR: malformed inputs (' + type(exc).__name__ + ')']
    # Preserve the authoritative validator's findings; never repair around them.
    prefix_errors = {cid: [] for cid in ids if isinstance(cid, str)}
    for error in validator_errors:
        matched = next((cid for cid in prefix_errors if error.startswith(cid + ':')), None)
        if matched is None:
            global_errors.append(error)
        else:
            prefix_errors[matched].append(error)
    entries = ann.get('cases')
    if not isinstance(entries, dict):
        entries = {}
    by_id = {case['id']: case for case in cases if isinstance(case.get('id'), str)}
    records = []
    for cid in sorted(set(by_id) | set(entries)):
        case = by_id.get(cid)
        present = cid in entries
        original = entries.get(cid)
        errors = list(global_errors) + prefix_errors.get(cid, [])
        references, source_errors = source_references(case, docs) if case else ([], ['AV-3: unknown case id'])
        errors.extend(source_errors)
        if not present:
            errors.append('AV-3: missing annotation')
        if case and present:
            errors.extend(entry_errors(original, case, docs))
        errors = sorted(set(errors))
        structural = 'INVALID' if errors else 'VALID'
        records.append(dict(case_id=cid, original_annotation_json=_json(original) if present else '',
                            annotation_source_sha256=source_hash, dataset_pin_json=_json(dataset_pin),
                            source_refs_json=_json(references), structural_validation=structural,
                            validation_errors_json=_json(errors),
                            review_disposition='INVALID' if errors else 'NEEDS_INDEPENDENT_REVIEW',
                            review_basis='Deterministic validation only; no independent annotation review evidence supplied.'))
    return dict(schema=SCHEMA, annotation_source_sha256=source_hash, records=records,
                structural_counts=dict(collections.Counter(r['structural_validation'] for r in records)),
                disposition_counts=dict(collections.Counter(r['review_disposition'] for r in records)),
                validation_errors=sorted(set(global_errors + validator_errors)))


def ledger_csv(audit):
    """Render a separate ledger; original annotation values stay serialized."""
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=LEDGER_FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(audit['records'])
    return output.getvalue()


def workbook_inventory(data):
    """Hash and inspect OOXML review cells without opening/saving a workbook."""
    ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    result = dict(sha256=_sha(data), worksheets=[])
    with ZipFile(io.BytesIO(data)) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(si.itertext()) for si in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('m:si', ns)]
        for path in sorted(archive.namelist()):
            if not path.startswith('xl/worksheets/sheet') or not path.endswith('.xml'):
                continue
            rows = []
            for row in ET.fromstring(archive.read(path)).findall('.//m:row', ns):
                cells = {}
                for cell in row.findall('m:c', ns):
                    value_node, inline = cell.find('m:v', ns), cell.find('m:is', ns)
                    value = value_node.text if value_node is not None else ''.join(inline.itertext()) if inline is not None else ''
                    value = strings[int(value)] if cell.get('t') == 's' else value
                    cells[re.sub(r'[0-9]+', '', cell.get('r', ''))] = value or ''
                rows.append(cells)
            header = rows[0] if rows else {}
            decision_column = next((key for key, value in header.items() if value.startswith('reviewer_decision')), None)
            case_column = next((key for key, value in header.items() if value == 'case_id'), None)
            cases = [row for row in rows[1:] if case_column and row.get(case_column)]
            decisions = collections.Counter(row.get(decision_column, '').strip() or 'BLANK' for row in cases) if decision_column else {}
            result['worksheets'].append(dict(path=path, rows=len(rows), case_records=len(cases), decisions=dict(decisions)))
    return result


def main(argv=None):
    """Generate a new review-preparation ledger, never edit the source records."""
    import argparse
    from pathlib import Path
    import subprocess
    from eval.framework.integrity import ROOT, load_dataset, file_hashes
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--annotations', default=str(Path(ROOT)/'eval/scoring_v2/annotations.json'))
    parser.add_argument('--ledger', required=True, help='new output CSV; existing paths are refused')
    args = parser.parse_args(argv)
    docs, cases = load_dataset()
    manifest = json.loads((Path(ROOT)/'eval/phase35/frozen_manifest.json').read_bytes())
    pin = dict(dataset_version=manifest['content']['dataset']['dataset_version'],
               dataset_sha256=dataset_hash(cases), file_sha256=file_hashes(),
               git_rev=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               manifest_content_sha256=manifest['content_sha256'])
    audit = audit_annotations(Path(args.annotations).read_bytes(), cases, docs, dataset_pin=pin)
    with Path(args.ledger).open('x', encoding='utf-8', newline='') as output:
        output.write(ledger_csv(audit))
    print(_json({key: audit[key] for key in ('schema', 'annotation_source_sha256', 'structural_counts', 'disposition_counts')}))
    return 1 if audit['structural_counts'].get('INVALID', 0) else 0


if __name__ == '__main__':
    raise SystemExit(main())
