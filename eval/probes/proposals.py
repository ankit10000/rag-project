"""Proposed case-definition changes and synthetic cases used by the scorer probes.

Everything here is applied to IN-MEMORY copies of the dataset. Nothing on disk changes, and every
proposal remains PENDING_OWNER_DECISION.

PROPOSALS are the 15 Phase D corrections (docs/remediation/phase_d_decision_package), with the
Phase E1 correction listed in PHASE_D_CORRECTIONS. POTENTIAL_PROPOSALS model potential issues that
a probe needs in order to state a reachable v2 expectation (TP-02 for P-TS1-09).
"""
import copy

TA_D4_EXTRA_SOURCE = {"document": "calder_sound_tile_study_TR-2026-07.pdf", "page": 4,
                      "span": "production cost per tile was not recorded"}

# proposal id -> (case id, {field: new value}). "_append_gold_sources" extends the current list.
PROPOSALS = {
    "TA-01": ("A-conflict-03", {"category": "multi_page", "expect_conflict": False,
                                "gold_facts": [["48 hours", "48-hour"]]}),
    "TA-02": ("D-conflicting-02", {"category": "multi_page", "expect_conflict": False, "gold_facts": [["31 Nm"]]}),
    "TA-03": ("B-follow-01", {"forbidden": []}),
    "TA-04": ("C-direct-06", {"forbidden": []}),
    "TA-05": ("C-multi_chunk-03", {"gold_facts": [["2 per year", "2 on-site visits", "2 visits", "2 engineer visits",
                                                   "two on-site visits", "two visits", "two engineer visits",
                                                   "two per year"], ["£0", "waived"]]}),
    "TA-06": ("A-multichunk-01", {"question": "Can I have my flu shot together with the other age-based jabs, "
                                              "and from what ages are those other ones free?"}),
    "TA-07": ("D-injection-03", {"gold_facts": [[" 5 litres", " 5 liters", " 5 l ", "five litres"],
                                                ["1 hour", "one hour"]]}),
    "TA-08": ("A-multipage-02", {"gold_facts": [["adult who is not the patient", "adult other than the patient",
                                                 "not the patient", "other than the patient"],
                                                ["10:00"], ["16:00"]]}),
    "TA-09": ("D-multi_page-02", {"gold_facts": [["level 4", "cut-resistant"], ["plant manager"], ["HSE officer"]]}),
    "TA-10": ("B-direct-04", {"gold_facts": [["21 and 22 June", "21-22 June", "21–22 June", "June 21 and 22",
                                              "June 21-22", "June 21–22", "21st and 22nd June"]]}),
    # DATA-1 (E1, lead-verified): Phase D had G1 ["battery"], which misses the source wording "Batteries".
    "TA-11": ("C-multi_page-01", {"gold_facts": [["battery", "batteries"], ["filter"], ["90 days"]]}),
    "TA-D1": ("D-conflicting-01", {"category": "multi_page", "expect_conflict": False,
                                   "gold_facts": [["750 h", "750 hours"]]}),
    "TA-D2": ("D-conflicting-03", {"category": "multi_page", "expect_conflict": False, "gold_facts": [["21 days"]]}),
    "TA-D3": ("D-conflicting-04", {"category": "multi_page", "expect_conflict": False,
                                   "gold_facts": [["USD 64", "$64", "64 USD"]]}),
    "TA-D4": ("B-comp-04", {"_append_gold_sources": [TA_D4_EXTRA_SOURCE]}),
}

PHASE_D_CORRECTIONS = {
    "TA-11": "G1 ['battery'] -> ['battery', 'batteries'] (DATA-1: 'battery' is not a substring of 'Batteries')",
}

# Potential issues (Phase D POTENTIAL_ISSUE_DECISIONS.md), modelled only where a probe needs them.
POTENTIAL_PROPOSALS = {
    # TP-02 also covers A-followup-01 (3 visitors); only the A-compound-03 half is modelled here.
    "TP-02": ("A-compound-03", {"gold_facts": [["2 visitors", "two visitors", "max 2", "two people", "2 people",
                                                "maximum of 2", "maximum of two", "up to two"]]}),
}

# Superseded proposal versions, kept so a probe can show why they were corrected (lookup only).
SUPERSEDED_PROPOSALS = {
    "TA-11-PHASE-D": ("C-multi_page-01", {"gold_facts": [["battery"], ["filter"], ["90 days"]]}),
}

SYNTHETIC = {  # minimal cases for pure matching behaviour (not dataset cases)
    "SYN-NUM": {"id": "SYN-NUM", "category": "direct_factual", "question": "q", "history": [],
                "gold_facts": [["$65"]], "forbidden": [], "expect_abstain": False, "expect_partial": False,
                "expect_conflict": False, "tier": "both", "tier1_chunks": None,
                "gold_sources": [{"document": "Marlow_Fen_Water_Use_and_Public_Health_Bylaw_2025-14.pdf",
                                  "page": 2, "span": "The permit costs $65"}]},
}


def all_proposals() -> dict:
    """Every proposal a probe target may name (PROP:<id>)."""
    return {**PROPOSALS, **POTENTIAL_PROPOSALS, **SUPERSEDED_PROPOSALS}


def apply_changes(case: dict, changes: dict) -> dict:
    """Return a deep copy of ``case`` with ``changes`` applied (the input is never modified)."""
    out = copy.deepcopy(case)
    for key, value in copy.deepcopy(changes).items():
        if key == "_append_gold_sources":
            out["gold_sources"] = out["gold_sources"] + value
        else:
            out[key] = value
    return out


def case_for(target: str, by_id: dict) -> dict:
    """target: dataset case id | 'PROP:<proposal id>' | synthetic id. Always a fresh copy."""
    if target.startswith("PROP:"):
        case_id, changes = all_proposals()[target[5:]]
        return apply_changes(by_id[case_id], changes)
    if target in SYNTHETIC:
        return copy.deepcopy(SYNTHETIC[target])
    return copy.deepcopy(by_id[target])


def patched_cases(cases: list, proposal_ids=None) -> list:
    """Dataset with the chosen proposals (default: the 15 Phase D proposals) applied in memory."""
    chosen = PROPOSALS if proposal_ids is None else {p: all_proposals()[p] for p in proposal_ids}
    by_case = {}
    for case_id, changes in chosen.values():
        if case_id in by_case:
            raise ValueError(f"two proposals target {case_id}")
        by_case[case_id] = changes
    return [apply_changes(c, by_case[c["id"]]) if c["id"] in by_case else c for c in cases]
