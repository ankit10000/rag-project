"""Stage 9 Phase E2: data-driven scorer regression probes (supersedes the Phase D script).

Each probe runs one synthetic answer through the FROZEN v1 scorer
(eval/phase35/run_eval.py:score_generic) and asserts the expected v1 sub-signals. The Phase D
script (docs/remediation/phase_d_decision_package/scorer_regression_probes.py) is kept unchanged
as a historical record; every one of its 72 probe ids is carried here (some corrected).

Per-probe fields (see probe_data.probe):
  id, limitation, target (case id | PROP:<proposal> | synthetic id), answer, truth,
  status       result status, default "answered" (also abstained / unverified / error / partial)
  citations    "all_gold" (default) | "none" | list of chunk ids (may include ids outside the context)
  context      "gold" (default: gold pages only, ids 1..n) | "tier1" (run_eval.tier1_context, seeded)
  extra_context  extra non-gold (document, page) pairs appended to a "gold" context
  annotations  dict recorded for v2 (may be empty); v1 never reads it
  v1           expected v1 sub-signals (asserted key by key)
  v2, v2_reason  intended v2 outcome per the E1 audit (None = not decidable yet, with a reason)
  classification, reason

v2 contract (scorer v2 does not exist yet): ``--v2 MODULE`` imports MODULE and, if it defines
``score_case(case, result, chunk_pair, context_ids, context_text, history, annotations)`` returning a
dict with at least "correct", compares it with each probe's v2 expectation. A module without
score_case is reported and skipped (exit 0 for the v2 part).

No database, no network, no LLM, no evaluation run. Writes nothing unless --write-matrix PATH is
given; that creates a NEW file (mode "x").

    DATABASE_URL=postgresql://nobody@127.0.0.1:1/rag_test_scratch HF_HUB_OFFLINE=1 \\
      .venv/bin/python -B -m eval.probes.scorer_regression [--validate-proposals] [--write-matrix OUT.csv] [--v2 MODULE]
"""
import argparse
import csv
import importlib
import sys

from eval.framework.integrity import load_dataset
from eval.phase35 import validate as V
from eval.phase35.run_eval import score_generic, tier1_context
from eval.probes.probe_data import PROBES
from eval.probes.proposals import POTENTIAL_PROPOSALS, PROPOSALS, case_for, patched_cases

V2_SIGNATURE = "score_case(case, result, chunk_pair, context_ids, context_text, history, annotations)"
V1_KEYS = ("correct", "fact_recall", "forbidden_hits", "abstain_ok", "partial_ok", "conflict_ok", "fabricated",
           "citation_completeness", "citation_correctness", "ungrounded_numbers", "unsupported")


def dataset():
    docs, cases = load_dataset()
    return docs, cases, {c["id"]: c for c in cases}


def _gold_context(case, docs, extra):
    gold = list(dict.fromkeys((s["document"], s["page"]) for s in case["gold_sources"]))
    pairs = [(g, True) for g in gold] + [(tuple(e), False) for e in extra]
    chunk_pair = {i + 1: (key if is_gold else None) for i, (key, is_gold) in enumerate(pairs)}
    text = " ".join(docs[d][p - 1] for (d, p), _ in pairs)
    return chunk_pair, text


def _tier1_context(case, docs):
    results, chunk_pair, _ = tier1_context(case, docs)
    return chunk_pair, " ".join(r["chunk"][3] for r in results)


def build_inputs(probe, case, docs):
    """Return (result, chunk_pair, context_ids, context_text) exactly as score_generic receives them."""
    if probe["context"] == "tier1":
        chunk_pair, context_text = _tier1_context(case, docs)
    elif probe["context"] == "gold":
        chunk_pair, context_text = _gold_context(case, docs, probe["extra_context"])
    else:
        raise ValueError(f"{probe['id']}: unknown context mode {probe['context']!r}")
    citations = probe["citations"]
    if citations == "all_gold":
        cited = [cid for cid, pair in chunk_pair.items() if pair is not None]
    elif citations == "none":
        cited = []
    elif isinstance(citations, list):
        cited = list(citations)
    else:
        raise ValueError(f"{probe['id']}: unknown citations mode {citations!r}")
    result = {"answer": probe["answer"], "status": probe["status"], "citations": [{"chunk_id": c} for c in cited]}
    return result, chunk_pair, set(chunk_pair), context_text


def score_probe(probe, docs, by_id):
    case = case_for(probe["target"], by_id)
    return score_generic(case, *build_inputs(probe, case, docs))


def v1_mismatches(probe, score) -> list:
    """Expected v1 sub-signals that the observed score does not reproduce."""
    out = []
    for key, want in probe["v1"].items():
        got = score[key]
        same = abs(got - want) < 1e-9 if isinstance(want, float) else got == want
        if not same:
            out.append(f"{key}: expected {want!r}, observed {got!r}")
    return out


def load_v2(module_name):
    """Return (score_case or None, message). Never raises for a missing entry point."""
    module = importlib.import_module(module_name)
    fn = getattr(module, "score_case", None)
    if not callable(fn):
        return None, f"v2 module {module_name!r} has no {V2_SIGNATURE}; v2 expectations skipped"
    return fn, f"v2 module {module_name!r} loaded"


def score_v2(fn, probe, docs, by_id):
    case = case_for(probe["target"], by_id)
    result, chunk_pair, context_ids, context_text = build_inputs(probe, case, docs)
    return fn(case, result, chunk_pair, context_ids, context_text, case["history"], dict(probe["annotations"]))


def validate_proposals(docs, cases) -> dict:
    """validate.py on the dataset with the Phase D proposals (and, separately, the potential ones) applied."""
    return {
        "phase_d_15": V.validate(docs, patched_cases(cases)),
        "phase_d_15_plus_potential": V.validate(
            docs, patched_cases(cases, list(PROPOSALS) + list(POTENTIAL_PROPOSALS))),
    }


def run(probes=PROBES, v2_fn=None):
    """Score every probe. Returns rows with the observed v1 score, mismatches and v2 outcome."""
    docs, _, by_id = dataset()
    rows = []
    for probe in probes:
        score = score_probe(probe, docs, by_id)
        row = {"probe": probe, "score": score, "v1_mismatches": v1_mismatches(probe, score), "v2": None}
        if v2_fn is not None:
            row["v2"] = score_v2(v2_fn, probe, docs, by_id)["correct"]
        rows.append(row)
    return rows


def _matrix_row(row):
    p, s = row["probe"], row["score"]
    return {"probe_id": p["id"], "limitation": p["limitation"], "target": p["target"], "context": p["context"],
            "citations": p["citations"] if isinstance(p["citations"], str) else " ".join(map(str, p["citations"])),
            "status": p["status"], "candidate_answer": p["answer"], "answer_truth": p["truth"],
            "expected_v1": p["v1"]["correct"], "observed_v1": s["correct"], "proposed_v2": p["v2"],
            "v2_reason": p["v2_reason"] or "", "classification": p["classification"], "reason": p["reason"],
            "phase_d_change": p["phase_d_change"] or ""}


def main(argv=None):
    sys.modules.setdefault("services", None)   # any provider/database service import now fails loudly
    ap = argparse.ArgumentParser()
    ap.add_argument("--v2", help=f"module defining {V2_SIGNATURE}; omit while v2 does not exist")
    ap.add_argument("--write-matrix", help="NEW csv path (never overwritten)")
    ap.add_argument("--validate-proposals", action="store_true")
    args = ap.parse_args(argv)
    v2_fn = None
    if args.v2:
        v2_fn, message = load_v2(args.v2)
        print(message)
    rows, failures = run(v2_fn=v2_fn), []
    for row in rows:
        p = row["probe"]
        ok = not row["v1_mismatches"] and (row["v2"] is None or p["v2"] is None or row["v2"] == p["v2"])
        if not ok:
            failures.append(p["id"])
        print(f"{'PASS' if ok else 'FAIL'} | {p['id']:13} {p['limitation']:6} {p['target']:20} "
              f"v1={row['score']['correct']!s:5} v2_exp={p['v2']!s:5} {'; '.join(row['v1_mismatches'])}")
    if args.validate_proposals:
        docs, cases, _ = dataset()
        for label, errors in validate_proposals(docs, cases).items():
            print(f"validate.py with {label} applied in memory: {'VALID' if not errors else errors}")
            if errors:
                failures.append(f"validate:{label}")
    if args.write_matrix:
        with open(args.write_matrix, "x", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(_matrix_row(rows[0])), lineterminator="\n")
            writer.writeheader()
            writer.writerows(_matrix_row(r) for r in rows)
    print(f"\n{len(rows)} probes; {len(failures)} failure(s) {failures if failures else ''}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
