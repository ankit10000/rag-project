"""Phase 3 — deterministic memory category classification (pure, no DB/LLM).

The current schema has no category column, so categories are computed at
runtime from the memory text (see docs/remediation/proposals/
005_memory_category.sql.proposed for an unapplied persistence proposal).
Rules are ordered keyword/phrase patterns with word boundaries; the first
category whose pattern matches wins, otherwise OTHER. The same text always
gets the same category. No model, no similarity, no external data.
"""

import re

PROFILE = "profile"
PREFERENCES = "preferences"
GOALS = "goals"
PROJECTS = "projects"
SKILLS = "skills"
RELATIONSHIPS = "relationships"
ROUTINES = "routines"
OTHER = "other"

CATEGORIES = (PROFILE, PREFERENCES, GOALS, PROJECTS, SKILLS, RELATIONSHIPS, ROUTINES, OTHER)

# Display order used by the context assembler.
CATEGORY_LABELS = {
    PROFILE: "Profile",
    PREFERENCES: "Preferences",
    GOALS: "Goals",
    PROJECTS: "Projects",
    SKILLS: "Skills",
    RELATIONSHIPS: "Relationships",
    ROUTINES: "Routines",
    OTHER: "Other",
}


def _rx(*phrases):
    return re.compile(r"\b(?:" + "|".join(phrases) + r")\b", re.IGNORECASE)


# Precedence matters: more specific signals first.
_RULES = (
    (RELATIONSHIPS, _rx(
        r"wife", r"husband", r"partner", r"friends?", r"mother", r"father", r"mom", r"dad",
        r"brother", r"sister", r"sons?", r"daughters?", r"manager", r"colleagues?", r"boss",
        r"teammates?", r"girlfriend", r"boyfriend", r"cousins?", r"mentor")),
    (ROUTINES, _rx(
        r"every (?:day|morning|evening|night|week|weekend|month)", r"daily", r"weekly",
        r"usually", r"routine", r"habit", r"each (?:day|week|morning)", r"always")),
    (GOALS, _rx(
        r"goals?", r"wants? to", r"plans? to", r"aims? to", r"aspires? to", r"hopes? to",
        r"learning", r"learn", r"target", r"preparing for", r"intends? to")),
    (PREFERENCES, _rx(
        r"prefers?", r"preferences?", r"likes?", r"loves?", r"favou?rite", r"enjoys?",
        r"dislikes?", r"hates?", r"would rather")),
    (PROJECTS, _rx(
        r"projects?", r"building", r"builds?", r"app", r"application", r"repositor(?:y|ies)",
        r"repo", r"products?", r"working on", r"developing", r"startup")),
    (SKILLS, _rx(
        r"experience (?:with|in)", r"experienced", r"proficient", r"skilled", r"skills?",
        r"familiar with", r"knows", r"expert", r"years of", r"uses?", r"using")),
    (PROFILE, _rx(
        r"works? as", r"job", r"occupation", r"employed", r"engineer", r"developer",
        r"student", r"studying", r"stud(?:y|ies)", r"degree", r"graduated", r"lives? in",
        r"based in", r"born", r"years old", r"name is", r"profession", r"company")),
)


def classify_memory_text(text) -> str:
    """Return one of CATEGORIES for a memory text (deterministic)."""
    if not isinstance(text, str) or not text.strip():
        return OTHER
    for category, pattern in _RULES:
        if pattern.search(text):
            return category
    return OTHER


# Markers of a short-lived state ("today", "right now"). Used only to stop a
# temporary statement from OVERWRITING a long-term fact; it never deletes or
# blocks storing anything by itself.
_TEMPORARY = _rx(
    r"today", r"tonight", r"right now", r"this (?:morning|afternoon|evening)",
    r"at the moment", r"for now", r"temporarily")


def is_temporary_statement(text) -> bool:
    return isinstance(text, str) and bool(_TEMPORARY.search(text))
