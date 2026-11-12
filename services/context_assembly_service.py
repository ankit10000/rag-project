"""Pure context assembly: dedupe, cap and budget retrieved chunks, assign S-refs.

No DB / LLM / network. Metadata is never invented or altered and the input is
never mutated. Chunk content is treated as untrusted data and is not sanitised
here (the prompt layer handles that).
"""
import re

from services import retrieval_config as cfg

MIN_TRUNCATE_CHARS = 200

# Same shape as citation_service's marker: [S1], [ S2 ], [S1, S3]
_CITATION_MARKER = re.compile(r"\[\s*[Ss]\d+(?:\s*[,;]\s*[Ss]\d+)*\s*\]")


def _norm(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def _page(value):
    if value in (None, "", 0, "0"):
        return None
    return value


def _truncate(text, limit):
    """Cut text to <= limit chars at a word boundary (hard cut if no space)."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if not text[limit].isspace():
        idx = max(cut.rfind(" "), cut.rfind("\n"), cut.rfind("\t"))
        if idx > 0:
            cut = cut[:idx]
    return cut.rstrip()


def _score(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def assemble_context(results, max_chars=None, max_chunks=None):
    """Build the prompt context block from best-first retrieval results."""
    max_chars = cfg.CONTEXT_MAX_CHARS if max_chars is None else max_chars
    max_chunks = cfg.CONTEXT_MAX_CHUNKS if max_chunks is None else max_chunks
    sources, dropped = [], []
    seen_ids, seen_content = set(), set()
    used = 0
    truncated_any = False

    for item in results or []:
        chunk = (item or {}).get("chunk") if isinstance(item, dict) else None
        if not chunk or len(chunk) < 4:
            continue
        cid, doc, page, content = chunk[0], chunk[1], chunk[2], chunk[3]
        raw = chunk[4] if len(chunk) > 4 else None
        text = content.strip() if isinstance(content, str) else ""

        if not text:
            dropped.append({"chunk_id": cid, "reason": "empty"})
            continue
        if cid in seen_ids:
            dropped.append({"chunk_id": cid, "reason": "duplicate_id"})
            continue
        key = _norm(text)
        if key in seen_content:
            dropped.append({"chunk_id": cid, "reason": "duplicate_content"})
            continue
        if len(sources) >= max_chunks:
            dropped.append({"chunk_id": cid, "reason": "max_chunks"})
            truncated_any = True
            continue

        remaining = max_chars - used
        truncated = False
        if len(text) > remaining:
            if not sources:
                text, truncated = _truncate(text, max(remaining, 0)), True
            elif remaining >= MIN_TRUNCATE_CHARS:
                text, truncated = _truncate(text, remaining), True
            else:
                dropped.append({"chunk_id": cid, "reason": "budget"})
                truncated_any = True
                continue
            if not text:
                dropped.append({"chunk_id": cid, "reason": "budget"})
                truncated_any = True
                continue
        truncated_any = truncated_any or truncated

        seen_ids.add(cid)
        seen_content.add(key)
        used += len(text)
        rrf = _score(item.get("rrf_score"))
        rer = _score(item.get("rerank_score"))
        rs = rer if rer is not None else rrf if rrf is not None else _score(raw)
        sources.append({
            "ref": f"S{len(sources) + 1}",
            "chunk_id": cid,
            "document_name": doc if doc else None,
            "page_number": _page(page),
            "content": text,
            "retrieval_score": rs,
            "rrf_score": rrf,
            "rerank_score": rer,
            "truncated": truncated,
        })

    blocks = []
    for s in sources:
        doc = s["document_name"] or "unknown"
        pg = s["page_number"] if s["page_number"] is not None else "unknown"
        # Prompt display only (s["content"] is unchanged): document text must not
        # be able to forge our reference tags, e.g. a fake "[S2] Document: ..." header.
        shown = _CITATION_MARKER.sub("[ref removed]", s["content"])
        blocks.append(f"[{s['ref']}] Document: {doc} | Page: {pg} | Chunk: {s['chunk_id']}\n{shown}")
    return {
        "sources": sources,
        "dropped": dropped,
        "context_text": "\n\n".join(blocks),
        "truncated": truncated_any,
        "total_chars": used,
    }


def source_index(sources):
    """Map ref -> source dict."""
    return {s["ref"]: s for s in (sources or [])}
