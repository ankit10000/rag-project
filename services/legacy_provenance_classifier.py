"""Phase 2 — deterministic classification of historical memory provenance.

PURE module: no database, no network, no LLM, no text or timestamp heuristics.
It only evaluates the provenance FACTS collected by
``services/legacy_provenance_inventory.py`` (one ``MemoryProvenanceFacts`` per
memory) and assigns exactly one category plus a list of recorded issues.

Categories (precedence top to bottom):

USER_SUPPORTED
    At least one source reference is a VALID USER SOURCE:
      * the referenced message exists,
      * it belongs to the memory's conversation,
      * its actual messages.role is 'user', and
      * for a modern memory_sources row, the stored source_role is 'user'
        and the row's own conversation_id equals the memory's.
    A legacy scalar conversation_memories.source_message_id stores no role, so
    the joined message's actual role is authoritative for it.
    One valid user source is sufficient; any other invalid or assistant-origin
    references are still recorded as issues (mixed-source handling).

MISSING_SOURCE
    No source reference at all: no memory_sources row AND a NULL legacy scalar.

INCONSISTENT_SOURCE
    No valid user source, and at least one STRUCTURAL issue: a referenced
    message that does not exist, a foreign-conversation reference, a modern
    row whose conversation differs from the memory's, a stored source_role
    that disagrees with the actual role (or is NULL), an unknown link_kind,
    or a legacy scalar that has no matching modern row (the two
    representations disagree).

ASSISTANT_ONLY_OR_UNVERIFIED
    References exist and are structurally consistent, but none is a valid
    user source (e.g. every source is an assistant message).

link_kind is never used as role evidence: 'legacy' describes how a row entered
memory_sources (the migration backfill), not who wrote the message.
"""

from dataclasses import dataclass, field

USER_SUPPORTED = "USER_SUPPORTED"
ASSISTANT_ONLY_OR_UNVERIFIED = "ASSISTANT_ONLY_OR_UNVERIFIED"
MISSING_SOURCE = "MISSING_SOURCE"
INCONSISTENT_SOURCE = "INCONSISTENT_SOURCE"
CATEGORIES = (USER_SUPPORTED, ASSISTANT_ONLY_OR_UNVERIFIED, MISSING_SOURCE, INCONSISTENT_SOURCE)

KNOWN_LINK_KINDS = ("origin", "update", "confirmation", "legacy")

# Issue codes. STRUCTURAL issues make a memory without user support INCONSISTENT_SOURCE;
# INFORMATIONAL issues are recorded but do not by themselves change the category.
MODERN_MESSAGE_MISSING = "MODERN_SOURCE_MESSAGE_MISSING"
LEGACY_MESSAGE_MISSING = "LEGACY_SOURCE_MESSAGE_MISSING"
MODERN_FOREIGN_CONVERSATION = "MODERN_SOURCE_FOREIGN_CONVERSATION"
LEGACY_FOREIGN_CONVERSATION = "LEGACY_SOURCE_FOREIGN_CONVERSATION"
MODERN_LINK_CONVERSATION_MISMATCH = "MODERN_LINK_CONVERSATION_MISMATCH"
STORED_ROLE_MISMATCH = "STORED_SOURCE_ROLE_MISMATCH"
STORED_ROLE_NULL = "STORED_SOURCE_ROLE_NULL"
UNKNOWN_LINK_KIND = "UNKNOWN_LINK_KIND"
LEGACY_NOT_IN_MODERN = "LEGACY_SCALAR_WITHOUT_MODERN_LINK"
MODERN_ASSISTANT_SOURCE = "MODERN_ASSISTANT_SOURCE"
LEGACY_ASSISTANT_SOURCE = "LEGACY_ASSISTANT_SOURCE"
MODERN_NON_USER_ROLE = "MODERN_NON_USER_NON_ASSISTANT_ROLE"
LEGACY_NON_USER_ROLE = "LEGACY_NON_USER_NON_ASSISTANT_ROLE"

STRUCTURAL_ISSUES = frozenset({
    MODERN_MESSAGE_MISSING, LEGACY_MESSAGE_MISSING, MODERN_FOREIGN_CONVERSATION,
    LEGACY_FOREIGN_CONVERSATION, MODERN_LINK_CONVERSATION_MISMATCH, STORED_ROLE_MISMATCH,
    STORED_ROLE_NULL, UNKNOWN_LINK_KIND, LEGACY_NOT_IN_MODERN,
})


@dataclass(frozen=True)
class ModernLinkFact:
    """One memory_sources row joined to messages BY MESSAGE ID ONLY (so a
    foreign-conversation reference stays visible)."""
    source_message_id: int
    link_conversation_id: str           # memory_sources.conversation_id
    link_kind: str | None               # memory_sources.link_kind
    stored_role: str | None             # memory_sources.source_role
    message_exists: bool
    message_conversation_id: str | None  # messages.conversation_id (None if missing)
    actual_role: str | None             # messages.role (None if missing)


@dataclass(frozen=True)
class LegacyScalarFact:
    """The legacy conversation_memories.source_message_id, joined BY ID ONLY."""
    source_message_id: int
    message_exists: bool
    message_conversation_id: str | None
    actual_role: str | None


@dataclass(frozen=True)
class MemoryProvenanceFacts:
    memory_id: int
    conversation_id: str
    modern_links: tuple = ()             # tuple[ModernLinkFact, ...]
    legacy_scalar: LegacyScalarFact | None = None


@dataclass(frozen=True)
class Issue:
    code: str
    representation: str                 # "modern" | "legacy"
    source_message_id: int
    detail: str = ""


@dataclass
class Classification:
    memory_id: int
    conversation_id: str
    category: str
    valid_user_source_ids: list = field(default_factory=list)
    modern_source_ids: list = field(default_factory=list)
    legacy_source_id: int | None = None
    issues: list = field(default_factory=list)   # list[Issue], deterministic order

    @property
    def issue_codes(self) -> list:
        return sorted({i.code for i in self.issues})

    def as_dict(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "conversation_id": self.conversation_id,
            "category": self.category,
            "valid_user_source_ids": list(self.valid_user_source_ids),
            "modern_source_ids": list(self.modern_source_ids),
            "legacy_source_id": self.legacy_source_id,
            "issues": [
                {"code": i.code, "representation": i.representation,
                 "source_message_id": i.source_message_id, "detail": i.detail}
                for i in self.issues
            ],
        }


def _same(a, b) -> bool:
    return a is not None and b is not None and str(a) == str(b)


def _evaluate_modern(link: ModernLinkFact, conversation_id: str):
    """Return (is_valid_user_source, [Issue, ...]) for one modern row."""
    issues = []
    sid = link.source_message_id

    def add(code, detail=""):
        issues.append(Issue(code, "modern", sid, detail))

    if link.link_kind not in KNOWN_LINK_KINDS:
        add(UNKNOWN_LINK_KIND, f"link_kind={link.link_kind!r}")
    if not _same(link.link_conversation_id, conversation_id):
        add(MODERN_LINK_CONVERSATION_MISMATCH)
    if link.stored_role is None:
        add(STORED_ROLE_NULL)

    if not link.message_exists:
        add(MODERN_MESSAGE_MISSING)
        return False, issues

    if not _same(link.message_conversation_id, conversation_id):
        add(MODERN_FOREIGN_CONVERSATION)
    if link.stored_role is not None and link.stored_role != link.actual_role:
        add(STORED_ROLE_MISMATCH, f"stored={link.stored_role!r} actual={link.actual_role!r}")
    if link.actual_role == "assistant":
        add(MODERN_ASSISTANT_SOURCE)
    elif link.actual_role != "user":
        add(MODERN_NON_USER_ROLE, f"actual={link.actual_role!r}")

    valid = (
        _same(link.link_conversation_id, conversation_id)
        and _same(link.message_conversation_id, conversation_id)
        and link.actual_role == "user"
        and link.stored_role == "user"
    )
    return valid, issues


def _evaluate_legacy(scalar: LegacyScalarFact, conversation_id: str):
    issues = []
    sid = scalar.source_message_id

    def add(code, detail=""):
        issues.append(Issue(code, "legacy", sid, detail))

    if not scalar.message_exists:
        add(LEGACY_MESSAGE_MISSING)
        return False, issues
    if not _same(scalar.message_conversation_id, conversation_id):
        add(LEGACY_FOREIGN_CONVERSATION)
    if scalar.actual_role == "assistant":
        add(LEGACY_ASSISTANT_SOURCE)
    elif scalar.actual_role != "user":
        add(LEGACY_NON_USER_ROLE, f"actual={scalar.actual_role!r}")

    valid = _same(scalar.message_conversation_id, conversation_id) and scalar.actual_role == "user"
    return valid, issues


def classify_memory(facts: MemoryProvenanceFacts) -> Classification:
    """Deterministically classify one memory from its provenance facts only."""
    links = sorted(facts.modern_links, key=lambda l: (l.source_message_id, str(l.link_kind)))
    valid_ids, issues = set(), []

    for link in links:
        valid, found = _evaluate_modern(link, facts.conversation_id)
        issues.extend(found)
        if valid:
            valid_ids.add(link.source_message_id)

    legacy = facts.legacy_scalar
    if legacy is not None:
        valid, found = _evaluate_legacy(legacy, facts.conversation_id)
        issues.extend(found)
        if valid:
            valid_ids.add(legacy.source_message_id)
        if legacy.source_message_id not in {l.source_message_id for l in links}:
            issues.append(Issue(LEGACY_NOT_IN_MODERN, "legacy", legacy.source_message_id,
                                "legacy scalar has no matching memory_sources row"))

    if valid_ids:
        category = USER_SUPPORTED
    elif not links and legacy is None:
        category = MISSING_SOURCE
    elif any(i.code in STRUCTURAL_ISSUES for i in issues):
        category = INCONSISTENT_SOURCE
    else:
        category = ASSISTANT_ONLY_OR_UNVERIFIED

    issues.sort(key=lambda i: (i.representation, i.source_message_id, i.code))
    return Classification(
        memory_id=facts.memory_id,
        conversation_id=str(facts.conversation_id),
        category=category,
        valid_user_source_ids=sorted(valid_ids),
        modern_source_ids=[l.source_message_id for l in links],
        legacy_source_id=legacy.source_message_id if legacy else None,
        issues=issues,
    )


def classify_all(facts_list) -> list:
    """Classify many memories, ordered by memory_id for deterministic output."""
    return [classify_memory(f) for f in sorted(facts_list, key=lambda f: f.memory_id)]


def summarize(classifications) -> dict:
    """Counts per category and per issue code (deterministic key order)."""
    by_category = {c: 0 for c in CATEGORIES}
    by_issue = {}
    mixed = 0
    for c in classifications:
        by_category[c.category] += 1
        for code in c.issue_codes:
            by_issue[code] = by_issue.get(code, 0) + 1
        if c.category == USER_SUPPORTED and c.issues:
            mixed += 1
    return {
        "total_memories": sum(by_category.values()),
        "by_category": by_category,
        "user_supported_with_recorded_issues": mixed,
        "by_issue_code": dict(sorted(by_issue.items())),
    }
