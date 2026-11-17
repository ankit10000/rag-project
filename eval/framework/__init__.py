"""Phase 4 evaluation framework (infrastructure only).

Modules
  integrity          dataset validation, manifests, split integrity (read-only)
  safety             run-request gates (wired into run_eval.py), frozen thresholds, overwrite protection
  hashing            portable (CRLF -> LF) SHA-256 and git blob ids
  frozen_manifest    build/verify the frozen Phase 3.5 manifest (eval/phase35/frozen_manifest.json)
  retrieval_metrics  Recall/Precision@K, MRR, nDCG@K, page/document recall
  answer_metrics     aggregation of the EXISTING per-case answer scores
  memory_metrics     conversational-memory evaluation interfaces and metrics
  regression         baseline vs current per-case comparison
  providers          provider/model/usage attribution (provider-independent)
  reporting          standardized report structure and Markdown rendering
  cli                file-based commands (validate/manifest/compare/report);
                     it never calls a model and never runs an evaluation

Importing this package has no side effects: it never imports
eval/phase35/run_eval.py, never connects to a database, and never calls an
LLM provider.
"""

FRAMEWORK_VERSION = "phase4-1.0"
