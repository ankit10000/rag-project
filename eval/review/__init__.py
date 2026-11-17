"""Ground-truth review tooling (Stage 9 Phase B). Development-only; needs openpyxl.

Modules
  workbook      read a review workbook (held-out or development) into plain data
  checks        structural/completeness validation and progress counts (read-only)
  sources       mechanical source lookup: document, PDF, page, span location
  dev_artifact  build the separate development review workbook (new file only)
  cli           command line: validate, progress, locate, check-sources, build-dev-review

Nothing here decides a case, writes a reviewer decision, edits an existing
workbook, touches a database or calls a model. Source lookup is mechanical:
finding a span on a page says nothing about whether it supports a gold fact.
"""
