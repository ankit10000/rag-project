"""Pure reconstruction/verification of the context contracts in WP5 §12.

PDF rendering and extraction belong to rescore; this module accepts extracted
page text and an explicitly supplied pure chunk function.
"""
import hashlib
import re
from eval.phase35.run_eval import tier1_context
from eval.phase35.validate import norm


def text_sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def tier1_items(case, docs):
    items, pair, ids = tier1_context(case, docs)
    texts = [item['chunk'][3].strip() for item in items]
    normalized = [norm(text) for text in texts]
    valid = (all(texts) and len(ids) == len(items) and len(set(normalized)) == len(texts)
             and len(items) <= 8 and sum(map(len, texts)) <= 12000)
    return items, pair, ids, ' '.join(texts), valid


def verify_tier1(row, case, docs):
    items, pair, ids, text, valid = tier1_items(case, docs)
    rebuilt = [(i['chunk'][0], i['chunk'][1], i['chunk'][2], pair[i['chunk'][0]] is not None) for i in items]
    try:
        stored = [(c['chunk_id'], c['document'], c['page'], c['gold']) for c in row['context']]
        if any(type(cid) is not int or (page is not None and type(page) is not int) or type(gold) is not bool
               or (doc is not None and not isinstance(doc, str)) for cid, doc, page, gold in stored):
            stored = None
    except (KeyError, TypeError):
        stored = None
    status = 'exact' if valid and rebuilt == stored else 'mismatch:order_or_ref'
    if status == 'exact' and 'context_sha256' in row and row['context_sha256'] != text_sha256(text):
        status = 'mismatch:context_sha256'
    mode = ('tier1_exact_hash_verified' if 'context_sha256' in row else 'tier1_reconstructed_exact')
    return pair, ids, text if status == 'exact' else None, status, mode if status == 'exact' else 'unavailable_mismatch'


def build_tier2_chunks(pages_by_doc, cfg, chunk_fn):
    """Restate ingestion using extracted (page_number, text) pairs, in order."""
    size, overlap, strategy = cfg
    if type(size) is not int or type(overlap) is not int or size <= 0 or not 0 <= overlap < size or strategy not in ('words', 'sentences'):
        raise ValueError('invalid chunk configuration')
    table = []
    for document, pages in pages_by_doc.items():
        seen = set()
        for page, text in pages:
            if not text.strip() or len(text.split()) < 10:
                continue
            for content in chunk_fn(text, size, overlap, strategy):
                key = hashlib.sha1(re.sub(r'\s+', ' ', content).lower().encode()).hexdigest()
                if key in seen:
                    continue
                seen.add(key)
                table.append({'id': len(table) + 1, 'document': document, 'page': page,
                              'sha256': text_sha256(content), 'content': content})
    return table


def chunk_table_sha256(table):
    return text_sha256(''.join(f"{r['id']}\t{r['document']}\t{r['page']}\t{r['sha256']}\n" for r in table))


def verify_tier2(row, table, case, header=None):
    by_id = {chunk['id']: chunk for chunk in table}
    gold = {(s['document'], s['page']) for s in case['gold_sources']}
    retrieved = row.get('retrieved')
    if not isinstance(retrieved, list):
        return {}, set(), None, 'mismatch:retrieved', 'unavailable_mismatch'
    citations = row.get('citations', [])
    if not isinstance(citations, list):
        return {}, set(), None, 'mismatch:ref', 'unavailable_mismatch'
    refs = retrieved + citations
    if any(not isinstance(r, dict) or type(r.get('chunk_id')) is not int
           or type(r.get('page_number', r.get('page'))) is not int
           or not isinstance(r.get('document_name', r.get('document')), str)
           or ('document_name' in r and 'document' in r and r['document_name'] != r['document'])
           or ('page_number' in r and 'page' in r and r['page_number'] != r['page']) for r in refs):
        return {}, set(), None, 'mismatch:ref', 'unavailable_mismatch'
    pair, ids, contents = {}, set(), []
    status = 'exact'
    for item in refs:
        chunk = by_id.get(item.get('chunk_id'))
        doc = item.get('document_name', item.get('document'))
        page = item.get('page_number', item.get('page'))
        if chunk is None or (doc, page) != (chunk['document'], chunk['page']):
            status = 'mismatch:ref'
        elif item.get('chunk_sha256', chunk['sha256']) != chunk['sha256']:
            status = 'mismatch:chunk_sha256'
    for item in retrieved:
        cid = item['chunk_id']
        chunk = by_id.get(cid)
        key = (item.get('document_name', item.get('document')), item.get('page_number', item.get('page')))
        pair[cid] = key if key in gold else None
        ids.add(cid)
        if chunk:
            contents.append(chunk['content'])
    header = header or {}
    if header.get('chunk_count', len(table)) != len(table):
        status = 'mismatch:chunk_count'
    if header.get('chunk_table_sha256', chunk_table_sha256(table)) != chunk_table_sha256(table):
        status = 'mismatch:chunk_table_sha256'
    text = ' '.join(contents)
    if 'context_sha256' in row and row['context_sha256'] != text_sha256(text):
        status = 'mismatch:context_sha256'
    mode = 'tier2_exact_hash_verified' if 'context_sha256' in row else 'tier2_reconstructed_exact'
    return pair, ids, text if status == 'exact' else None, status, mode if status == 'exact' else 'unavailable_mismatch'


def page_superset(row, docs):
    refs = list(dict.fromkeys((r.get('document_name', r.get('document')), r.get('page_number', r.get('page')))
                             for r in row.get('retrieved', [])))
    return ' '.join(docs[doc][page - 1] for doc, page in refs)
