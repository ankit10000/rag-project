# P2-02 report — sentence-based chunking verification

Date: 2026-11-12. Scope: P2-02 only (P2-03 not started). Default word strategy unchanged in behaviour. Nothing committed. No Gemini, no network, no model download (network blocked for every run). `rag_db` untouched. "Executed" = run in this session; "static" = code inspection.

## Existing behaviour (static inspection, then confirmed by executed probes before any edit)
- **Word strategy** `chunk_text(text, size, overlap)`: whitespace words, step = size − overlap, stops when a window reaches the end (so it never emits a window that only repeats words); empty/whitespace → `[]`; `size <= 0` or `overlap < 0` or `overlap >= size` → `ValueError`.
- **Sentence strategy** `chunk_text_sentences`: `split_sentences` splits paragraphs on blank lines, collapses all whitespace, then splits after `.`, `!` or `?` **only when followed by whitespace and an ASCII capital, digit, quote or `(`**. Sentences are packed greedily up to `chunk_size` words; the next chunk starts with the trailing whole sentences that fit in `overlap` words; a sentence longer than `chunk_size` is split into word windows (step size − overlap). Same `ValueError` validation as words. `chunk_page(text, size, overlap, strategy)` dispatches `"sentences"` → sentence strategy; anything else (including unknown names) → words. Ingestion default strategy: `words`.
- Undefined/limited (pinned in the tests as *current behaviour*, not requirements): `Dr. Smith`, `U.S. Army` split after the abbreviation; lowercase continuation (`e.g. this`, `etc. and`) and decimals/versions (`3.14`, `v2.0.1`) do not split; non-ASCII sentence starts (Cyrillic, accented, CJK) and the Devanagari danda / CJK full stop are not boundaries; paragraph breaks are not preserved in chunks (paragraphs merge when they fit); overlap is only whole sentences ≤ `overlap` words, so with long sentences there is no overlap.

## Application defects found by the tests and corrected (`services/chunker.py`, sentence strategy only)
Both found by executing randomised invariant checks against the unmodified code (3 000 random inputs).
1. **Chunk could exceed `chunk_size`.** After emitting a chunk, the carried overlap sentences were prepended to the incoming sentence without re-checking the size. Example (size 100, overlap 20; sentences of 60, 10, 10, 95 words): chunks `[80, 115]`. In 1 775 of 3 000 random cases at least one chunk exceeded `chunk_size` (up to size + overlap − 1), while the word strategy never does and the docstring promises a bound. **Fix:** `carry_limit = min(overlap, chunk_size - len(unit))` when choosing the carry. Result for the example: `[80, 95]`.
2. **Redundant trailing window for long sentences.** The word-window split of an over-long sentence used `range(0, n, step)` without the stop rule `chunk_text` has, so a final window consisting only of words already in the previous window was created and glued onto the last chunk, duplicating words. Example: one 250-word sentence, size 100 / overlap 20 → `[100, 100, 100]` with the last 10 words twice. **Fix:** stop after the window that reaches the end (`if start + chunk_size >= len(words): break`). Result: `[100, 100, 90]`.
Executed before/after comparison on random inputs (5 000 cases): all outputs that changed were cases where the old output had an oversize chunk or a chunk with repeated words; unchanged otherwise. Chunks containing repeated words: 2 101 before, 0 after. `chunk_text` (word strategy) is byte-for-byte unchanged (executed check on identical inputs and by the unchanged-behaviour tests).

## Tests — `test_p2_02_sentence_chunking.py` (integration, registered in `run_tests.py`)
**69 PASS, 0 FAIL** (executed with the safe runner, network blocked). Covers: sentence boundaries (`.` `?` `!`, digits/quotes/parentheses, decimals, versions, abbreviations, ellipsis, text without punctuation), paragraphs, single newlines, CRLF, repeated whitespace/tabs, leading/trailing whitespace, empty and whitespace-only input; single short sentence; several sentences in one chunk; exact chunk sizes and sentence-aligned boundaries; overlap 0, below one sentence, one sentence, two sentences, `size − 1`; ordering; content preservation (word sets, first/last word, exact reconstruction with overlap 0); determinism; no empty chunks; the two corrected defects; long sentences (one, mixed with short ones, several, exactly `chunk_size`, `chunk_size + 1`); invalid configuration (sizes ≤ 0, negative or ≥ size overlap, validation on empty text, `size = 1`); Unicode (accents, CJK, emoji) through splitter and chunker; word strategy pinned (`[100, 100, 90]`, starts at words 0/80/160, empty input, short text, never above size); strategy dispatch (default words, unknown → words, strategies independent); **600 seeded random trials** asserting no empty chunk, no chunk above `chunk_size`, no repeated words in a chunk, no lost or invented words, source order, determinism; and a scratch-DB ingestion check with `CHUNK_STRATEGY=sentences` using a **deterministic substitute embedder** (no model output is asserted): stored rows equal the sentence chunks with chunk ids 1..n per page, all within `chunk_size` and ending on sentence ends, vectors have 384 dimensions, re-ingestion gives identical rows (deterministic ids), the default words ingestion path is unchanged, other documents' rows untouched, cleanup leaves nothing.

## Regression results (executed)
- `test_p2_02_sentence_chunking.py`: 69 PASS / 0 FAIL.
- `test_retrieval_phase2.py` (existing word/sentence A-B, retrieval pipeline): PASS.
- `test_p2_01_pdf_ingestion.py`: PASS (30 checks, unchanged).
- Full default suite (`run_tests.py --clean`): **25 / 25 passed, 0 failed**; `rag_db` fingerprint unchanged: **True**.

## Mutation results (executed; repository files not edited, modules loaded from modified source)
| Mutation | Result |
|---|---|
| overlap removed | caught: 6 FAIL |
| chunk order reversed | caught: 16 FAIL |
| chunk ids zero-based (ingestion) | caught: 2 FAIL |
| loss of sentence content (last word dropped) | caught: 25 FAIL |
| empty chunk appended | caught: 7 FAIL (run then aborted by a later exception) |
| size fix reverted (oversize chunks) | caught: 4 FAIL |
| trailing-window fix reverted (duplicate words) | caught: 4 FAIL |
| long-sentence window one word too big | caught: 6 FAIL |
| word strategy step changed | caught: 2 FAIL |
All nine caught; none untestable.

## Files changed
- `services/chunker.py` — two small scoped fixes in `chunk_text_sentences` (above).
- New: `test_p2_02_sentence_chunking.py`, `docs/remediation/P2_02_SENTENCE_CHUNKING_REPORT.md`.
- `run_tests.py` — registered the new test (integration).
No schema, retrieval default, ranking or ingestion code change. The default word strategy is not used differently anywhere.

## Remaining limitations
- Boundary detection is English/ASCII-centric (pinned): non-ASCII sentence starts, CJK/Devanagari terminators and abbreviations before capitals are not handled; no change made because the contract is undefined and the user did not ask for one.
- The sentence strategy is not the default; switching `CHUNK_STRATEGY` is a retrieval-quality decision not made here (the earlier benchmark owns that).
- Overlap with long sentences is word-based only for sentences above `chunk_size`; otherwise overlap is whole sentences and may be empty by design.
- Paragraph structure and headings are not preserved in chunks.
- The ingestion check uses a deterministic embedder; real-model behaviour for sentence chunks was not asserted.
