# Proposed runtime provenance contract

Status: PREPARED_FOR_REVIEW. This detached extension proposal does not change the frozen runner, gate, manifest, thresholds or official v1 selection. A structurally verified hash is not authentication or acceptance.

`capture_record(identity, resolved_config, scoring_chunks, scoring_context, prompt_context, *, run_header_bytes, origin, prompt_truncated)` captures supplied actual bytes/text. `verify_record(record, *, run_header_bytes, expected_identity=None, expected_config=None)` returns `STRUCTURALLY_VERIFIED`, `UNVERIFIED_CALLER_CLAIM`, the preserved origin and `official_acceptance: false`, or raises `ValueError`. Neither function reads configuration, environment variables, files, defaults, provider services or a database.

## Schema `phase35-proposed-runtime-provenance/1`

The record contains:

- `identity`: scorer name/version/aggregate SHA-256, nonempty repository-relative `module_hashes`, annotation SHA-256, full 40-hex source and dataset revisions, dataset content SHA-256 and base `run_header_hash`. Optional development tier/split, nonempty profile/policy IDs and their SHA-256 values remain explicit; no threshold is required or invented.
- `identity_sha256`: SHA-256 of canonical identity JSON.
- `resolved_config` and its canonical SHA-256: every allowlisted value must be supplied, without secret keys or default lookup.
- `scoring_context.ordered_chunks`: each actual ordered chunk has positive unique ID, document/page and original exact text plus UTF-8 SHA-256. Missing document/page are allowed together only for explicitly identified Tier 1 missing-metadata evidence. `ordered_chunks_sha256` covers the ordered records, including source references and text. `content` captures the actual joined scoring text independently.
- `prompt_context.content`: the separately captured actual prompt-context text or bytes, with byte length and SHA-256. It is not substituted from scoring context. Text is stored as UTF-8 text; arbitrary bytes are stored as base64 with the digest over decoded original bytes.
- `prompt_context.truncated`: an explicit caller-supplied boolean.
- `origin`: exactly `ORIGINAL_RUNTIME_CAPTURE` or `HISTORICAL_RECONSTRUCTION`. Both are unsigned caller claims; neither proves when or where a runtime occurred.
- `authenticity`: always `UNVERIFIED_CALLER_CLAIM`; `official_acceptance`: always false.
- `record_sha256`: SHA-256 of canonical complete record content excluding this field. Verification checks the incoming digest before rebuilding, then compares canonical bytes; Python's `True == 1` or `1.0 == 1` cannot hide malformed metadata.

Canonical JSON uses sorted keys, compact separators, UTF-8, unescaped Unicode, and rejects NaN/infinity. Array order is retained. Context byte hashes do **not** normalize line endings. Explicit empty scoring chunks and empty context are valid; missing chunks/text are not filled in.

## Resolved configuration allowlist

Every field below is required. No API key, connection string, credential, environment dump, model secret or unrecognized config key is accepted. Caller-supplied document names and identity labels must themselves be nonsecret; this helper does not inspect arbitrary external sources for confidentiality.

| Field | Required explicit value |
|---|---|
| `chunk_size` | positive integer |
| `chunk_overlap` | integer from zero to chunk size minus one |
| `chunk_strategy` | `words` or `sentences` |
| `min_page_words` | positive integer |
| `dedupe` | `sha1(ws-collapsed lower)` for this proposed pipeline |
| `extractor` | `get_text(sort=True)` for this proposed pipeline |
| `document_order` | unique ordered document names supplied by the actual producer |
| `scoring_context_join` | `space_join_raw` or `space_join_stripped`, explicitly supplied |
| `prompt_context_truncation` | `none`, `prefix_chars`, or `external` |
| `prompt_context_limit_chars` | null for `none`; explicit nonnegative integer for `prefix_chars`; explicit integer or null for `external` |

These recognized pipeline names define the proposal's supported capture scope; they do not assert historical runtime values. A future different extractor/dedupe contract requires a new reviewed schema rather than relabeling it as this one.

`none` explicitly means byte-identical scoring and prompt contexts with no truncation. `prefix_chars` verifies the exact Unicode character prefix and whether truncation actually occurred. `external` preserves independently assembled/formatted prompt bytes and caller truncation metadata without inferring any relationship to scoring text; null limit means no limit has been supplied, not a guessed default. Capturing context alone does not imply capture of the entire rendered model prompt, system instructions or transport request: the producer must identify and separately hash those artifacts if needed.

## Detached run-header extension proposal

1. Capture and retain the original immutable **base** run-header bytes.
2. Supply their raw SHA-256 as identity `run_header_hash` and verify against those bytes during capture. The field is a base-header identity, not the hash of a future header containing its own extension.
3. Retain this detached context/config capture and its `record_sha256`.
4. A proposed external run index may bind `{base_run_header_sha256, runtime_capture_record_sha256}`. It must not be presented as an existing production header, and must not be included recursively inside either hashed input.
5. Independently verify the actual runtime producer, source revision, module/annotation/dataset byte identities and ordered context source. No unsigned self-consistent JSON can prove authenticity.

History roles, if runtime prompt material contains conversation history, remain part of its exact captured bytes; the helper does not synthesize, merge or relabel them. This proposal does not broaden numeric grounding to assistant turns.

## Historical evidence boundaries

`upload_identity_register.json` enumerates all seven exact `(1)`-named expected uploads, retained repository paths, raw digests and byte counts. Original uploads remain unavailable. Only the annotation expected upload digest is known; the other six are null. Even a matching known annotation digest does not establish receipt/equality of unavailable original bytes.

`historical_limitations.json` binds the retained hardened Tier 2 sidecar and records its 135 reconstructed chunks and 42 exact rows, pinned data revision, assumed configuration, and reconstruction hashes. Original runtime-resolved config, database ordering and exact prompt bytes remain unestablished. No ingestion, database access or production evaluation was performed to manufacture missing evidence.
