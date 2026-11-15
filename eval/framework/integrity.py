"""Dataset validation, manifests and split integrity (read-only, no side effects).

Builds on eval/phase35/validate.py (schema, unique ids, spans on pages, gold
facts on gold pages) and ADDS checks; it never rewrites a dataset, never
repairs a case and never writes a manifest unless a caller explicitly asks
(see cli.py, which refuses to overwrite).

The split rule is duplicated from eval/phase35/run_eval.py:split_of (that
module cannot be imported: it opens a database connection at import time).
``runner_split_logic_matches()`` verifies the duplicate against the runner's
source text with ``ast`` (no execution) so a silent divergence is detected.
"""

import ast
import hashlib
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_MODULES = ("data_A", "data_B", "data_C", "data_D")
RUNNER_PATH = os.path.join(ROOT, "eval", "phase35", "run_eval.py")

ALLOWED_TIERS = ("both", "answer_only")
SPLITS = ("dev", "heldout")


def split_of(case_id: str) -> str:
    """Identical to eval/phase35/run_eval.py:split_of (verified by ast)."""
    return "dev" if int(hashlib.sha1(case_id.encode()).hexdigest(), 16) % 10 < 3 else "heldout"


_EXPECTED_SPLIT_RETURN = (
    'return "dev" if int(hashlib.sha1(case_id.encode()).hexdigest(), 16) % 10 < 3 else "heldout"'
)


def runner_split_logic_matches(runner_path: str = RUNNER_PATH) -> bool:
    """Static check: the runner's split_of body equals the duplicated rule."""
    tree = ast.parse(open(runner_path, encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "split_of":
            body = [n for n in node.body if not (isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant))]
            expected = ast.parse("def split_of(case_id):\n    " + _EXPECTED_SPLIT_RETURN).body[0].body[0]
            return len(body) == 1 and ast.unparse(body[0]) == ast.unparse(expected)
    return False


def load_dataset(modules=DATA_MODULES):
    """Load documents and cases through the existing validator's loader."""
    from eval.phase35 import validate as V
    return V.load(list(modules))


def file_hashes(modules=DATA_MODULES) -> dict:
    out = {}
    for name in modules:
        path = os.path.join(ROOT, "eval", "phase35", f"{name}.py")
        out[f"eval/phase35/{name}.py"] = hashlib.sha256(open(path, "rb").read()).hexdigest()
    return out


def _canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")


def dataset_hash(cases) -> str:
    """Content hash of all case definitions (order-independent, by id)."""
    h = hashlib.sha256()
    for case in sorted(cases, key=lambda c: c["id"]):
        h.update(_canonical({k: v for k, v in case.items() if not k.startswith("_")}))
    return h.hexdigest()


def split_hash(cases) -> str:
    """Hash of (case_id, split) membership only."""
    pairs = sorted((c["id"], split_of(c["id"])) for c in cases)
    return hashlib.sha256(_canonical(pairs)).hexdigest()


def extra_checks(docs, cases):
    """Additional integrity checks beyond validate.py. Returns (errors, warnings)."""
    from eval.phase35.validate import CATEGORIES

    errors, warnings = [], []
    ids = [c.get("id") for c in cases]
    for cid, n in Counter(ids).items():
        if n > 1:
            errors.append(f"{cid}: duplicate case id ({n} definitions)")

    by_question = {}
    for c in cases:
        cid = c.get("id")
        if c.get("category") not in CATEGORIES:
            errors.append(f"{cid}: unknown category {c.get('category')!r}")
        if c.get("tier") not in ALLOWED_TIERS:
            errors.append(f"{cid}: unknown tier {c.get('tier')!r}")
        flags = [c.get("expect_abstain"), c.get("expect_partial"), c.get("expect_conflict")]
        if any(not isinstance(f, bool) for f in flags):
            errors.append(f"{cid}: expect_* flags must be booleans")
        if c.get("expect_abstain") and (c.get("expect_partial") or c.get("expect_conflict")):
            errors.append(f"{cid}: expect_abstain cannot be combined with partial/conflict")
        for g in c.get("gold_facts") or []:
            if not isinstance(g, list) or not g or not all(isinstance(a, str) and a.strip() for a in g):
                errors.append(f"{cid}: every gold fact group must be a non-empty list of non-empty strings")
                break
        if not isinstance(c.get("forbidden"), list) or not all(isinstance(f, str) and f.strip() for f in c["forbidden"]):
            errors.append(f"{cid}: forbidden must be a list of non-empty strings")
        for s in c.get("gold_sources") or []:
            doc, page = s.get("document"), s.get("page")
            if doc not in docs:
                errors.append(f"{cid}: gold source document not in corpus: {doc!r}")
            elif not isinstance(page, int) or not (1 <= page <= len(docs[doc])):
                errors.append(f"{cid}: gold source page out of range: {doc!r} p.{page!r}")
        # Conflicting definitions: the same question+history asked twice with different expectations.
        key = (c.get("question", "").strip().lower(), json.dumps(c.get("history"), sort_keys=True))
        by_question.setdefault(key, []).append(c)

    for group in by_question.values():
        if len(group) > 1:
            expectations = {json.dumps([g.get("gold_facts"), g.get("expect_abstain"), g.get("expect_partial"),
                                        g.get("expect_conflict")], sort_keys=True) for g in group}
            ids_ = sorted(g["id"] for g in group)
            if len(expectations) > 1:
                errors.append(f"conflicting definitions for the same question: {ids_}")
            else:
                warnings.append(f"duplicate question with identical expectations: {ids_}")

    for c in cases:
        if c.get("expect_conflict") and c.get("category") != "conflicting":
            warnings.append(f"{c.get('id')}: expect_conflict outside the 'conflicting' category")
    return errors, warnings


def build_manifest(dataset_version: str, modules=DATA_MODULES) -> dict:
    """Validate and describe the dataset. Pure computation; writes nothing."""
    from eval.phase35 import validate as V

    docs, cases = load_dataset(modules)
    base_errors = V.validate(docs, cases)
    errors, warnings = extra_checks(docs, cases)
    errors = list(base_errors) + errors
    if not runner_split_logic_matches():
        errors.append("split rule in eval/phase35/run_eval.py differs from eval/framework/integrity.split_of")

    split_counts = Counter(split_of(c["id"]) for c in cases)
    tier_by_split = {
        sp: {
            "tier1_eligible": sum(1 for c in cases if split_of(c["id"]) == sp),
            "tier2_eligible": sum(1 for c in cases if split_of(c["id"]) == sp and c["tier"] == "both"),
            "answer_only": sum(1 for c in cases if split_of(c["id"]) == sp and c["tier"] == "answer_only"),
        }
        for sp in SPLITS
    }
    return {
        "dataset_version": dataset_version,
        "file_sha256": file_hashes(modules),
        "dataset_sha256": dataset_hash(cases),
        "split_sha256": split_hash(cases),
        "documents": len(docs),
        "pages": sum(len(p) for p in docs.values()),
        "case_count": len(cases),
        "split_counts": {sp: split_counts.get(sp, 0) for sp in SPLITS},
        "tier_distribution": tier_by_split,
        "category_counts": dict(sorted(Counter(c["category"] for c in cases).items())),
        "split_membership": {sp: sorted(c["id"] for c in cases if split_of(c["id"]) == sp) for sp in SPLITS},
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def compare_to_manifest(current: dict, frozen: dict) -> list:
    """Differences between a freshly built manifest and a frozen one (no repair)."""
    diffs = []
    for key in ("dataset_sha256", "split_sha256", "case_count", "split_counts", "tier_distribution", "file_sha256"):
        if current.get(key) != frozen.get(key):
            diffs.append(key)
    if current.get("split_membership") != frozen.get("split_membership"):
        diffs.append("split_membership")
    return diffs
