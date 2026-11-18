# WP8 — Real-case annotation review preparation

Status: deterministic annotation validation and review preparation complete. Independent annotation review remains pending. No approval, correction, scorer adoption or re-freeze is implied.

## Actual inventory and validation

- Annotation source: `eval/scoring_v2/annotations.json`, schema `phase35-scorer-annotations/1`.
- Source raw SHA-256: `d3dccb413152ba525a6c9c51baaba2d1220fd58253cc919b3b43cb296dee60b0`.
- Dataset version: `phase35-corrected-2026-11-12`; dataset SHA-256: `5c58796af13ffe296a08421d9119bbb7f23430d7070d4ace3b281a82e9a7d6a1`.
- Baseline revision: `690fcfbbf0abdf43b274161a5e6545f7ad11c325`; frozen manifest content SHA-256: `1b73a208d22fcfe00a51bf027df0b2e2fe490ceaebc207dbf64504c8da0fbf97`.
- Entries: **160 / 160** dataset case IDs, with no unknown or duplicated IDs. All entries are the existing literal-only baseline; no assertion, distractor, disclosure, history-wrong-value, negatable or conflict-group decisions were authored.
- Forbidden annotation entries: **66**, all `literal` and `source: dataset`.
- AV-1–AV-10 validation: **160 structurally VALID; 0 INVALID**. Missing/duplicate/inconsistent annotation records: **0**. Original gold source document/page/span links resolve against the supplied frozen dataset pages.
- Review dispositions: **160 NEEDS_INDEPENDENT_REVIEW; 0 VALID/approved, INVALID, AMBIGUOUS or NOT_APPLICABLE dispositions**. A structurally valid literal baseline does not prove semantic sufficiency or independent review.

`WP8_ANNOTATION_REVIEW_LEDGER.csv` retains each original annotation as JSON, the annotation-source hash, complete dataset pin, exact referenced document/page/span, verbatim page text and page-text SHA-256. Structural validation and review disposition occupy separate columns. Full page text is evidence from the existing dataset, not newly reconstructed runtime model context. Reading all case definitions is an annotation audit, not held-out evaluation.

No richer annotation proposal was inferred. Pending TA-03 and V-3/V-5 choices can affect whether assertion, history, distractor or other annotations should be proposed; the ledger does not silently apply those choices. Literal-only entries may be technically valid while remaining semantically incomplete for intended v2 policy.

Historical comparison inputs are inventoried separately in `wp8_evidence/flip_inputs/index.json`: two byte-identical historical annotation copies share raw SHA-256 `b4f6ed739756f3ca3c57bb83f9c21acfad87413b9d4a3d2e1322abca01f4452a`. That 160-case baseline passes full annotation validation against its pinned `c1bbcae` dataset in the flip-reconstruction suite. It is not silently relabelled as the current dataset or merged into the current 160-record review count. The current and historical annotation versions both remain unreviewed. A separate boundary-aware scan of current literal forbidden strings against gold alternatives found zero potential overlaps; it establishes no subjective label approval.

## Existing review workbooks — read-only OOXML inventory

The inventory used `zipfile` and `xml.etree.ElementTree` on original bytes; no workbook was opened through an authoring library or saved.

| Existing artifact | Review case rows | Nonblank decisions | Blank decisions | Raw SHA-256 |
|---|---:|---:|---:|---|
| `docs/remediation/dev_review/dev_review_sheet.xlsx` | 7 | 0 | 7 | `6b94f3431c6c1f8e16b5401a824e2b9ddfa9fb0160c16da6485bb4da50922b09` |
| `docs/remediation/heldout_review/heldout_review_sheet_CURRENT_HUMAN_REVIEW.xlsx` | 113 | 0 | 113 | `300dc43fb76b1884015583d60e12834f7e50086c0afbaad765ad536e8c491467` |

The dev workbook contains seven flagged development cases, not all 47 development cases. The held-out workbook contains all 113 held-out review cases. Their current review-decision cells are blank. These workbook records concern dataset review and do not establish independent review of the new scorer annotations.

`docs/remediation/heldout_review/REVIEW_SIGNOFF_REPORT.md` explicitly states “AI-assisted review, NOT an independent human review” and records independent human review as not performed. Its existing AI review is historical evidence only. `PHASE_E2_REMAINING_DECISIONS.md` and all 15 entries in `wp4/REVISED_PROPOSALS.json` retain pending owner-decision status. No sign-off was manufactured and no frozen review or correction record was modified.

## Runnable audit and tests

New pure API: `eval.acceptance_preparation.annotations.audit_annotations(annotation_bytes, cases, docs, *, dataset_pin)`; `ledger_csv(audit)` renders a separate ledger. `workbook_inventory(bytes)` returns read-only worksheet counts and review-decision cells. The caller supplies and verifies the actual source file identities; the pure audit cannot independently attest arbitrary supplied git/file hashes. It does verify the annotation dataset hash/version against supplied cases and explicit pin.

A reproducible CLI creates a **new** ledger with exclusive mode `x` and prints structural/review counts:

```sh
.venv/bin/python -B -m eval.acceptance_preparation.annotations --ledger /private/tmp/wp8-annotation-review-new.csv
```

It reads current source bytes, dataset file hashes, manifest identity and git revision; an existing destination is refused. Re-running into a different new path produces the same ledger for identical inputs.

The auditor rejects duplicate JSON keys, malformed/nonfinite JSON, missing/unknown case IDs, invalid provenance and source links; it preserves original values without repairing annotations. It calls the unchanged authoritative scorer annotation validator and records contextual findings. A suspected preliminary richer-annotation validation issue was not reproduced by the specification specialist; no validator defect or code change is claimed.

Command (exit **0**, **7 unittest methods passed**, including AV-1 through AV-10 adversarial subcases):

```sh
DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch TESTSAFE_BLOCK_NETWORK=1 HF_HUB_OFFLINE=1 \
.venv/bin/python -B -m unittest test_stage9_wp8_annotations -v
```

Tests cover deterministic original-annotation preservation, exact source references, missing/unknown/duplicate inputs, pin mismatches, all ten AV rejection families, CSV round trips and read-only OOXML decision counting. No database, provider call, held-out evaluation or scoring of real answers was run by this workstream.

## Remaining independent review

A reviewer must decide the adequacy and intended interpretation of the literal baseline and any separately proposed richer annotations, with exact source evidence. Formal specification clarifications, human-approved scorer flips, adoption and re-freezing remain separate owner-controlled requirements. Existing dataset-review statuses cannot substitute for those decisions.
