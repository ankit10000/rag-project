"""Stage 9 Phase E2: scorer regression probes (eval/probes) as a registered unit test.

Pure: the frozen v1 scorer is called on synthetic answers; proposals are applied to in-memory
copies only. No database, no LLM, no network, no evaluation run. The only file written is a
matrix CSV inside a temporary directory.
"""
import testsafe
testsafe.require_scratch_db()

import ast
import contextlib
import csv
import io
import os
import sys
import tempfile
import types

from eval.framework.frozen_manifest import load_frozen_manifest
from eval.framework.integrity import ROOT, dataset_hash, load_dataset
from eval.probes import scorer_regression as H
from eval.probes.probe_data import PROBES
from eval.probes.proposals import PROPOSALS, SYNTHETIC, all_proposals, case_for
from eval.probes.schema import S, probe

FAILURES = []
PHASE_D_DIR = os.path.join(ROOT, "docs", "remediation", "phase_d_decision_package")
MANIFEST_PATH = os.path.join(ROOT, "eval", "phase35", "frozen_manifest.json")


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def phase_d_probes():
    """The Phase D PROBES literal, read with ast (the Phase D script is never imported or run)."""
    with open(os.path.join(PHASE_D_DIR, "scorer_regression_probes.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "PROBES" for t in node.targets):
            return ast.literal_eval(_TrueFalse().visit(node.value))
    return []


class _TrueFalse(ast.NodeTransformer):
    """The Phase D literal uses the names T and F for True and False."""

    def visit_Name(self, node):
        if node.id in ("T", "F"):
            return ast.copy_location(ast.Constant(node.id == "T"), node)
        return node


docs, cases = load_dataset()
by_id = {c["id"]: c for c in cases}
dataset_before = dataset_hash(cases)

# ------------------------------------------------------------------- structure --
ids = [p["id"] for p in PROBES]
check(f"probe ids are unique ({len(ids)} probes)", len(ids) == len(set(ids)))
bad_targets = []
for p in PROBES:
    t = p["target"]
    if t.startswith("PROP:"):
        ok = t[5:] in all_proposals() and all_proposals()[t[5:]][0] in by_id
    else:
        ok = t in by_id or t in SYNTHETIC
    if not ok:
        bad_targets.append(p["id"])
check("every probe target exists (case id, proposal on an existing case, or synthetic)", bad_targets == [])
check("every proposal targets an existing case", all(cid in by_id for cid, _ in all_proposals().values()))
check("every probe asserts at least the 7 core v1 sub-signals",
      all({"correct", "fact_recall", "forbidden_hits", "abstain_ok", "partial_ok", "conflict_ok", "fabricated"}
          <= set(p["v1"]) for p in PROBES))
check("every undecided v2 expectation carries a reason", all(p["v2"] is not None or p["v2_reason"] for p in PROBES))
try:
    probe("X", "TS-1", "A-noanswer-01", "a", "wrong", S(True, 1.0, [], True, None, None), None, "c", "r")
    check("schema: undecided v2 without a reason is refused", False)
except ValueError:
    check("schema: undecided v2 without a reason is refused", True)

# ------------------------------------------------------------- dataset pin --
manifest, problems = load_frozen_manifest(MANIFEST_PATH)
check("frozen manifest loads (self-consistent)", manifest is not None and problems == [])
pinned = manifest is not None and manifest["content"]["dataset"]["dataset_sha256"] == dataset_before
if not pinned:
    print("SKIP | dataset differs from the frozen manifest's dataset_sha256: the probe v1 expectations are "
          "pinned to the frozen dataset and were NOT asserted. Re-record them for the new dataset version.")

# ----------------------------------------------------------- v1 sub-signals --
if pinned:
    rows = H.run()
    for row in rows:
        p = row["probe"]
        check(f"{p['id']}: v1 sub-signals as recorded (correct={p['v1']['correct']}) "
              f"{'; '.join(row['v1_mismatches'])}", row["v1_mismatches"] == [])
    print(f"      {len(rows)} probes; v1 correct=True for {sum(r['score']['correct'] for r in rows)}")
    tampered = dict(PROBES[0], v1=dict(PROBES[0]["v1"], correct=not PROBES[0]["v1"]["correct"]))
    check("negative control: a wrong recorded expectation is reported as a mismatch",
          H.v1_mismatches(tampered, rows[0]["score"]) != [])
check("probes never modify the dataset (hash unchanged after scoring)", dataset_hash(load_dataset()[1]) == dataset_before)
check("in-memory proposal copies leave the loaded cases untouched", dataset_hash(cases) == dataset_before)

# ---------------------------------------------- Phase D matrix correspondence --
with open(os.path.join(PHASE_D_DIR, "SCORER_REGRESSION_MATRIX.csv"), encoding="utf-8", newline="") as fh:
    matrix = list(csv.DictReader(fh))
by_probe = {p["id"]: p for p in PROBES}
check(f"Phase D matrix: all {len(matrix)} rows are harness probes", len(matrix) == 72
      and all(r["probe_id"] in by_probe for r in matrix))
literal = phase_d_probes()
check("Phase D script PROBES literal read (72) and equal to the matrix ids",
      [t[0] for t in literal] == [r["probe_id"] for r in matrix])
check("Phase D matrix rows equal the script literal (target, answer, expected v1, proposed v2)",
      [(r["target"], r["candidate_answer"], r["expected_v1"], r["proposed_v2"]) for r in matrix]
      == [(t[2], t[3], str(t[5]), str(t[6])) for t in literal])
differing = []
for pid, _lim, target, answer, truth, v1_exp, v2_exp, _cls, _reason in literal:
    p = by_probe[pid]
    same = (p["target"], p["answer"], p["truth"], p["v1"]["correct"], p["v2"]) == (target, answer, truth, v1_exp, v2_exp)
    if not same:
        differing.append(pid)
corrected = sorted(p["id"] for p in PROBES if p["phase_d_change"])
print(f"      corrected Phase D probes: {corrected}")
check("Phase D probes differ from the harness only where a correction is recorded", sorted(differing) == corrected)
check("the corrected set is exactly P-TS1-06, P-TS1-09, P-TAD4-1",
      corrected == ["P-TAD4-1", "P-TS1-06", "P-TS1-09"])

# ------------------------------------------------------------- proposals --
check("15 Phase D proposals modelled", len(PROPOSALS) == 15)
check("TA-11 corrected to G1 ['battery', 'batteries'] (DATA-1)",
      case_for("PROP:TA-11", by_id)["gold_facts"][0] == ["battery", "batteries"])
results = H.validate_proposals(docs, cases)
check("validate.py: all 15 proposals applied in memory -> no errors", results["phase_d_15"] == [])
check("validate.py: 15 proposals + TP-02 applied in memory -> no errors", results["phase_d_15_plus_potential"] == [])

# ---------------------------------------------------------------- v2 hook --
no_entry = types.ModuleType("wp3_fake_v2_missing")
calls = []


def fake_score_case(case, result, chunk_pair, context_ids, context_text, history, annotations):
    calls.append((case["id"], len(history), dict(annotations)))
    return {"correct": True}


with_entry = types.ModuleType("wp3_fake_v2")
with_entry.score_case = fake_score_case
sys.modules.update({"wp3_fake_v2_missing": no_entry, "wp3_fake_v2": with_entry})
fn, message = H.load_v2("wp3_fake_v2_missing")
check("v2 hook: a module without score_case is skipped with a message", fn is None and "skipped" in message)
fn, _ = H.load_v2("wp3_fake_v2")
sample = [by_probe["P-TS3-01"], by_probe["P-E2-HIST-01"]]
v2_rows = H.run(sample, v2_fn=fn)
check("v2 hook: score_case receives case, history and the probe's annotations",
      [r["v2"] for r in v2_rows] == [True, True] and calls[0] == ("B-follow-01", 2, sample[0]["annotations"])
      and calls[1][2] == {"history_wrong_values": ["$85", "14 days"]})
del sys.modules["wp3_fake_v2_missing"], sys.modules["wp3_fake_v2"]

# ---------------------------------------------------------- CLI matrix output --
with tempfile.TemporaryDirectory() as tmp:
    out = os.path.join(tmp, "matrix.csv")
    with contextlib.redirect_stdout(io.StringIO()):
        code = H.main(["--write-matrix", out]) if pinned else 0
    if pinned:
        with open(out, encoding="utf-8", newline="") as fh:
            written = list(csv.DictReader(fh))
        check("CLI: exit 0 and a matrix row per probe", code == 0 and len(written) == len(PROBES))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                H.main(["--write-matrix", out])
            check("CLI: an existing matrix file is never overwritten", False)
        except FileExistsError:
            check("CLI: an existing matrix file is never overwritten", True)

check("no services.* module imported (provider/database layer untouched)",
      sys.modules.get("services") is None and not any(m.startswith("services.") for m in sys.modules))

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
