# Phase 3.5 frozen evaluation manifest

**File:** `eval/phase35/frozen_manifest.json`. **Created:** 2026-11-17 (Stage 9 Phase E0).
**Dataset version label:** `phase35-corrected-2026-11-12` (the date of `HELDOUT_DATASET_CORRECTIONS.md`).

This manifest **records** the current frozen inputs. It changes nothing, re-freezes nothing and authorizes nothing. Held-out execution still needs the independent human review and separate, explicit approval (`HELDOUT_THRESHOLD_FREEZE.md`, rule 4).

## Commands

```
# generate (writes a NEW file; refuses to overwrite)
python -m eval.framework.cli frozen-manifest --dataset-version phase35-corrected-2026-11-12 --output eval/phase35/frozen_manifest.json

# verify (read-only): rebuilds the content from the working tree and compares it
python -m eval.framework.cli verify-frozen-manifest --manifest eval/phase35/frozen_manifest.json
```

Neither command opens a database, calls a provider or runs an evaluation.

## Format (`phase35-frozen-manifest/1`)

| Key | Deterministic? | Contents |
|---|---|---|
| `content_sha256` | yes | SHA-256 of `content` as canonical JSON (sorted keys, `,`/`:` separators, UTF-8) |
| `content.hashing` | yes | algorithm and the normalization rules below |
| `content.dataset` | yes | `integrity.build_manifest`: per-module portable SHA-256, `dataset_sha256`, `split_sha256`, 12 documents / 56 pages, 160 cases, split counts 47 dev / 113 held-out, per-split Tier 1 / Tier 2 / answer-only counts (held-out 113 / 106 / 7), category counts, split membership (ids only), validator result (`valid`, errors, warnings) |
| `content.thresholds` | yes | `safety.FROZEN_THRESHOLDS` (dev 41/47, 28/42; held-out 97/113 @85%, 69/106 @65%) |
| `content.source_pdfs_match_dataset_documents` | yes | the 12 source PDF names equal the dataset document names |
| `content.assets[]` | yes | `group`, `path`, `kind` (text/binary), `portable_sha256`, `git_blob_sha1` |
| `provenance` | **no** | generation time (UTC), git HEAD, platform, Python version, raw SHA-256 of every asset. Informational only and excluded from `content_sha256` |

**Asset groups:**
- `dataset`: `data_A..D.py`
- `validator`: `validate.py`
- `scorer`: `run_eval.py`, `answer_scoring.py`
- `thresholds`: `HELDOUT_THRESHOLD_FREEZE.md`
- `dataset_corrections`: `HELDOUT_DATASET_CORRECTIONS.md`
- `source_pages`: `heldout_review/source_pages.md`
- `human_review`: the workbook (`.xlsx`), both review CSVs, the review README and `REVIEW_SIGNOFF_REPORT.md`
- `source_pdf`: the 12 PDFs

## Hash normalization rules

1. **Text assets:** every CRLF (`\r\n`) becomes LF (`\n`). Nothing else changes:
   - a lone CR, trailing whitespace, tabs, the Unicode form and the final newline are hashed as stored;
   - a **UTF-8 BOM is preserved**: git keeps it on every platform, so adding or removing one is a real content change.
2. **Binary assets** (PDF, XLSX): raw bytes, no normalization.
3. **`git_blob_sha1`** = SHA-1 of `blob <len>\0` + the normalized bytes. For an LF-committed text file this equals the repository blob (`git ls-files -s`) on every platform.
4. **Raw SHA-256** values are kept in `provenance.raw_sha256` only; they legitimately differ between a Windows and a macOS checkout.

**Relation to the historical (Windows) hashes:**
- `data_A..D.py` and `answer_scoring.py`: the portable hash equals the recorded value.
- `validate.py` and `source_pages.md`: the recorded value is the whole-file CRLF form.
- The two review CSVs: the recorded value is a Windows `csv` serialization (BOM + CRLF row terminators, LF inside quoted fields).
- In every case, the Windows bytes normalize to exactly the macOS bytes, so the portable hash is the same on both platforms. `test_stage9_e0_frozen_manifest.py` proves this for `validate.py` and both CSVs against the recorded values.

## Use by the runner gate

`run_eval.py --split heldout|all` calls `safety.runner_gate`, which:
1. loads this manifest and rejects it if `content_sha256` does not match its content;
2. rebuilds the content and refuses on **any** asset, dataset, threshold or format difference;
3. requires an approval file bound to this manifest's `content_sha256`.

**Consequence:** any change to a listed asset blocks held-out execution until the manifest is regenerated. That includes filling in the human-review workbook, any scorer change and any dataset correction. Regenerating it is a re-freeze and needs the user's approval.

## `run_eval.py`: accepted non-scoring implementation change (Phase E0 / E0.1)

**Decision (user, Phase E0.1):** the runner change is accepted as a **non-scoring implementation modification**. Thresholds and scorer definitions were **not** re-frozen.

- **What changed:** module-level imports and `main()`; `bootstrap_execution` and `enforce_split_gate` were added (the split gate, plus the E0.1 refusal of `--limit` with `heldout`/`all`).
- **What did not change:** every split, scoring and tier function, and the `NUM_RE` / `REF_RE` / `DATA_MODULES` constants, are **AST-identical** to `69e8b8e`. That covers `split_of`, `score_generic`, `norm_numbers`, `tier1_context`, `run_tier1`, `run_tier2`, `build_scratch_corpus` and `load_all`.

| | Original freeze (`69e8b8e`) | Current implementation |
|---|---|---|
| SHA-256 | `3b066a5b3b4c1de908cb5a555db17762af2bd70606f0854d5f2ba0ce7106e989` (Windows-recorded; identical raw on macOS) | `9d4670ce5488499ec79f0cc50598993fc2594ba9d1edb95555b1a6ae379ace94` (portable) |
| git blob | `c96a69c1e04a6aef67354d74967123728f6f3716` | `596d8d571abd54a12e64920d9638a2dedcaf0f0c` |

- `HELDOUT_THRESHOLD_FREEZE.md` is **unchanged** and still shows the original hash. That hash is the historical record of the scorer as frozen.
- **The integrity reference for the current working tree is this manifest.**

## Notes added in Phase E2 (2026-11-17)

These notes change no asset and no hash. The manifest still reports `frozen manifest REPRODUCED` (`content_sha256` `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`).

### Commands: interpreter and working directory

Run the commands above **from the repository root**, with the project interpreter rather than a bare `python`:
- macOS: `.venv/bin/python -B -m eval.framework.cli …`
- Windows: `.venv\Scripts\python.exe -B -m eval.framework.cli …`

The environment variables and the full command list are in `STAGE9_RUNBOOK.md`.

### Line-reference drift in the frozen freeze document (DOC-11)

`HELDOUT_THRESHOLD_FREEZE.md:22` says Tier 2 evaluates only cases with `tier == "both"` and cites `run_eval.py:269-270`. That was correct at `69e8b8e`. After the accepted E0/E0.1 change, the same two lines are now at **`run_eval.py:303-304`**:

```
303:    if args.tier == "2":
304:        chosen = [c for c in chosen if c["tier"] == "both"]
```

- The code itself is unchanged; only its position moved.
- `HELDOUT_THRESHOLD_FREEZE.md` is a frozen asset (group `thresholds`), so it is **not** edited to fix the reference. Read the citation as `303-304` for the current file and `269-270` for `69e8b8e`.
- Correct it at the next owner-approved re-freeze, together with the rule 2 hash update.

### Re-freeze

Regenerating this manifest is a re-freeze, and the CLI refuses to overwrite an existing manifest. The ordered procedure, including the manual move of the old manifest and the list of documents that quote `content_sha256`, is in `STAGE9_RUNBOOK.md` §6 ("Re-freeze procedure").
