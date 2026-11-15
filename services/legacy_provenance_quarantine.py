"""Phase 2 — quarantine PLAN builder (preparation only, no execution).

PURE module: it turns reviewed inventory classifications into a proposed,
auditable quarantine plan (a list of dicts). It does NOT connect to any
database and contains NO apply/execute function. Applying a plan requires the
proposed schema (docs/remediation/proposals/004_memory_provenance_quarantine.sql.proposed),
a separately approved migration, a rehearsal on an isolated clone, and a
separately approved apply step — none of which exist or were run.

Rules:
  * Only memories whose memory_id is in the explicitly APPROVED set are
    planned; nothing is quarantined just because of its category.
  * USER_SUPPORTED memories are never planned for quarantine, even if approved
    (their invalid extra links are recorded as issues, not quarantined).
  * The plan preserves the original evidence (classification, issues, source
    IDs) verbatim; it never proposes deleting a memory, a link, a message, or
    changing link_kind / source_role / memory text / embeddings.
"""

from services.legacy_provenance_classifier import (
    ASSISTANT_ONLY_OR_UNVERIFIED,
    INCONSISTENT_SOURCE,
    MISSING_SOURCE,
    USER_SUPPORTED,
)

QUARANTINABLE = (ASSISTANT_ONLY_OR_UNVERIFIED, MISSING_SOURCE, INCONSISTENT_SOURCE)

REASONS = {
    ASSISTANT_ONLY_OR_UNVERIFIED: "no verified user source; references are assistant-origin or otherwise unverified",
    MISSING_SOURCE: "no source reference in either the modern or the legacy representation",
    INCONSISTENT_SOURCE: "provenance references are structurally inconsistent (missing/foreign message, role or representation mismatch)",
}


class QuarantinePlanError(ValueError):
    """The requested plan is not allowed by the quarantine rules."""


def build_quarantine_plan(inventory_records, approved_memory_ids, approval_ref: str) -> dict:
    """Return a proposed plan for the approved memories only.

    inventory_records: the "memories" list produced by run_inventory()
    approved_memory_ids: memory IDs a reviewer explicitly approved
    approval_ref: a non-empty reference to the written approval
    """
    if not isinstance(approval_ref, str) or not approval_ref.strip():
        raise QuarantinePlanError("an approval reference is required")

    approved = set(approved_memory_ids or ())
    by_id = {r["memory_id"]: r for r in inventory_records}

    unknown = sorted(approved - set(by_id))
    if unknown:
        raise QuarantinePlanError(f"approved IDs not present in the inventory: {unknown}")

    refused = sorted(m for m in approved if by_id[m]["category"] == USER_SUPPORTED)
    if refused:
        raise QuarantinePlanError(
            f"USER_SUPPORTED memories cannot be quarantined: {refused}")

    entries = []
    for memory_id in sorted(approved):
        record = by_id[memory_id]
        category = record["category"]
        if category not in QUARANTINABLE:
            raise QuarantinePlanError(f"memory {memory_id}: unexpected category {category!r}")
        entries.append({
            "memory_id": memory_id,
            "conversation_id": record["conversation_id"],
            "classification": category,
            "reason": REASONS[category],
            "issues": record.get("issues", []),
            "modern_source_ids": record.get("modern_source_ids", []),
            "legacy_source_id": record.get("legacy_source_id"),
            "memory_text_sha256": record.get("memory_text_sha256"),
            "proposed_action": "INSERT quarantine marker row only (no change to the memory, links, messages or embeddings)",
        })

    return {
        "approval_ref": approval_ref.strip(),
        "planned_count": len(entries),
        "entries": entries,
        "executed": False,
        "note": "Plan only. No database change has been made. Applying requires a separately approved migration, rehearsal and apply step.",
    }
