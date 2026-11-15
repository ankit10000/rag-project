"""PROPOSED conversational-memory evaluation cases (definitions only, never executed).

Developer-authored regression fixtures — NOT independent validation and NOT
human-reviewed. They describe deterministic expected outcomes for the Phase 1
and Phase 3 contracts; a future, separately authorized runner would create the
messages in a scratch database (via testsafe), call the services with mocked
LLM decisions/extractions, and pass observed outcomes to memory_metrics.
No historical/production ground truth is used or invented.
Message ids here are fixture-local placeholders (u1, a1, ...), resolved by the
future runner to the ids it creates.
"""

from eval.framework.memory_metrics import MemoryCase

CASES = [
    # ---------------- extraction
    MemoryCase("mem-ext-01", "extraction", "long-term facts extracted, temporary state skipped",
               {"expected_memories": [["Python"], ["Jaipur"]],
                "forbidden_memories": ["tired today"],
                "expected_categories": {"Python": "skills", "Jaipur": "profile"}},
               tags=["phase3"]),
    MemoryCase("mem-ext-02", "extraction", "assistant suggestion is never stored as a user fact",
               {"expected_memories": [], "forbidden_memories": ["React"]}, tags=["phase1"]),
    # ---------------- provenance
    MemoryCase("mem-prov-01", "provenance", "multi-source fact keeps both user sources",
               {"expected_sources": {"Redis": ["u2", "u3"]}}, tags=["phase1"]),
    MemoryCase("mem-prov-02", "provenance", "batch citing an assistant message is rejected before any write",
               {"expected_sources": {}, "expect_batch_rejected": True}, tags=["phase1", "task4"]),
    # ---------------- dedup
    MemoryCase("mem-dedup-01", "dedup", "exact restatement confirms without a model call",
               {"steps": [{"action": "NEW"}, {"action": "SKIPPED", "source_ids": ["u1", "u2"]}]}, tags=["phase3"]),
    MemoryCase("mem-dedup-02", "dedup", "similar wording with a new amount is kept",
               {"steps": [{"action": "NEW"}, {"action": "SAVED", "preserved_details": ["6000"]}]}, tags=["phase3"]),
    # ---------------- update
    MemoryCase("mem-upd-01", "update", "explicit job change updates with the new source",
               {"steps": [{"action": "NEW"}, {"action": "UPDATED", "source_ids": ["u2"],
                                               "old_fact_retained": False}]}, tags=["phase3"]),
    MemoryCase("mem-upd-02", "update", "temporary state never overwrites a fact",
               {"steps": [{"action": "NEW"}, {"action": "SAVED", "old_fact_retained": True}]}, tags=["phase3"]),
    # ---------------- conflict
    MemoryCase("mem-conf-01", "conflict", "relation evidence for five canonical pairs",
               {"relations": ["EXPLICIT_UPDATE", "TEMPORARY_STATE", "TIME_DEPENDENT", "DETAIL_CHANGE", "UNRESOLVED"]},
               tags=["phase3"]),
    # ---------------- context
    MemoryCase("mem-ctx-01", "context", "only user-supported, non-excluded memories enter the context",
               {"expected_included_ids": ["m1", "m3"], "expected_excluded_ids": ["m2", "m4", "m5"],
                "max_memories": 5}, tags=["phase3", "phase2"]),
    # ---------------- lifecycle
    MemoryCase("mem-life-01", "lifecycle", "deleted memory absent and not reintroduced via summary/context",
               {"expected_absent_ids": ["m1"], "deleted_facts": ["PostgreSQL"]}, tags=["phase1"]),
    MemoryCase("mem-life-02", "lifecycle", "failed extraction does not advance the checkpoint",
               {"checkpoint_advanced": False}, tags=["task4"]),
]
