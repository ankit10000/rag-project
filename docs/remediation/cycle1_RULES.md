# Cycle 1 — shared rules for all agents (Phase 1 tests P1-04, P1-08)

Project: `C:\Users\vijay puri\Downloads\rag-project` (Python 3.14 RAG app, Windows; Git Bash + PowerShell; PostgreSQL 18 + pgvector). Python: `.venv\Scripts\python.exe`.

## Hard rules
- NEVER touch database `rag_db`. Run tests ONLY via `.venv\Scripts\python.exe run_tests.py [test_file.py]` (uses scratch DB `rag_test_scratch`; the runner blocks outbound network for unit/integration tests). Never set `DATABASE_URL` by hand.
- NO live Gemini calls. Mock every LLM touch point (e.g. `mock.patch.object` on `services.memory_decision_service.generate_answer`, `services.automatic_memory_service.decide_memory_action`, `services.memory_service.generate_answer`, `services.memory_cleanup_service.*`).
- Do NOT modify application code (`services/`, `main.py`), `.env`, `requirements.txt`, `services/retrieval_config.py`, `services/database.py`. Allowed: new/rewritten test files, registering files in `run_tests.py` CATEGORIES, docs under `docs/remediation/`. If a test reveals an application defect, DO NOT fix it: report it as a candidate defect with a minimal reproduction.
- No `git add/commit/restore`. No deleting files/databases/data. No dependency installs. Never print `.env` contents or credentials.
- Every test file starts with `import testsafe` then `testsafe.require_scratch_db()` (before importing services). No hard-coded conversation ids: create with `services.conversation_service.create_conversation`, clean up. Tests must `sys.exit(1)` on any failure and print PASS/FAIL lines.
- Create files with the Write/Edit tools (bash heredocs corrupt backslashes on this machine).
- Context: read `docs/remediation/MASTER_GAP_REGISTER.md` and section "B2. Phase 1 test plan" of `docs/remediation/p4_07_verification_and_phase1_plan.md` (the APPROVED plan). Be concise; do not re-read the whole repo.
- Pin existing behaviour, do not change it. Candidate defects to PROBE and report only: detector false positives such as "How do I clear memory in Python?" / "remove the memory leak"; `decide_memory_action` not handling `generate_answer` raising or returning `None`.
- Outputs go to `docs/remediation/cycle1_0N_<role>.md`; return a short summary (<= 40 lines) as your final message.
