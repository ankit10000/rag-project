"""
Mechanical validation of the Phase 3.5 dataset (authors run this on their own
data_<X>.py file; the runner runs it on everything).

    .venv\\Scripts\\python.exe eval\\phase35\\validate.py [data_A data_B ...]

What it can prove: schema is complete, ids are unique, every gold source span is
literally present on the stated page of the stated document, and every gold fact
(at least one alternative) literally appears on its gold source pages.
What it cannot prove: that a question is a good question or that the expected
answer is what a person would write. That needs human review (see review_sheet).
"""
import importlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

CATEGORIES = [
    "direct_factual", "multi_chunk", "compound", "multi_page", "no_answer",
    "irrelevant_retrieval", "conflicting", "missing_metadata", "follow_up",
    "prompt_injection",
]
REQUIRED = ("id", "category", "question", "history", "gold_facts", "forbidden", "gold_sources",
            "expect_abstain", "expect_partial", "expect_conflict", "citation_note",
            "review_note", "tier", "tier1_chunks")


def norm(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def load(module_names):
    docs, cases = {}, []
    for name in module_names:
        mod = importlib.import_module(f"eval.phase35.{name}")
        for fname, pages in mod.DOCUMENTS.items():
            if fname in docs:
                raise ValueError(f"duplicate document name {fname}")
            docs[fname] = pages
        for case in mod.CASES:
            case = dict(case)
            case["_module"] = name
            cases.append(case)
    return docs, cases


def validate(docs, cases):
    errors = []
    ids = set()
    page_text = {(d, i + 1): norm(t) for d, pages in docs.items() for i, t in enumerate(pages)}

    for c in cases:
        cid = c.get("id", "?")
        for key in REQUIRED:
            if key not in c:
                errors.append(f"{cid}: missing key {key}")
        if errors and errors[-1].startswith(f"{cid}: missing"):
            continue
        if cid in ids:
            errors.append(f"{cid}: duplicate id")
        ids.add(cid)
        if c["category"] not in CATEGORIES:
            errors.append(f"{cid}: bad category {c['category']}")
        if c["tier"] not in ("both", "answer_only"):
            errors.append(f"{cid}: bad tier")
        if not c["question"].strip():
            errors.append(f"{cid}: empty question")
        for m in c["history"]:
            if m.get("role") not in ("user", "assistant") or not m.get("content"):
                errors.append(f"{cid}: bad history item")
        if c["category"] == "follow_up" and not c["history"]:
            errors.append(f"{cid}: follow_up needs history")

        abstain = c["expect_abstain"]
        if abstain:
            if c["gold_facts"] or c["gold_sources"]:
                errors.append(f"{cid}: abstain case must have no gold facts/sources")
        else:
            if not c["gold_facts"] or not c["gold_sources"]:
                errors.append(f"{cid}: answerable case needs gold_facts and gold_sources")

        union = ""
        for src in c["gold_sources"]:
            key = (src.get("document"), src.get("page"))
            if key not in page_text:
                errors.append(f"{cid}: gold source {key} does not exist")
                continue
            union += " " + page_text[key]
            if norm(src.get("span")) not in page_text[key]:
                errors.append(f"{cid}: span not on {key}: {src.get('span')!r}")

        for alts in c["gold_facts"]:
            if not alts or not any(norm(a) and norm(a) in union for a in alts):
                errors.append(f"{cid}: gold fact not found on gold pages: {alts}")

        if c["tier"] == "answer_only":
            chunks = c["tier1_chunks"]
            if chunks is None:
                errors.append(f"{cid}: answer_only case needs tier1_chunks")
            else:
                for ch in chunks:
                    if "content" not in ch or "document" not in ch or "page" not in ch:
                        errors.append(f"{cid}: bad tier1 chunk")
        if c["category"] in ("irrelevant_retrieval", "missing_metadata") and c["tier"] != "answer_only":
            errors.append(f"{cid}: {c['category']} must be tier=answer_only")
        distinct = {(x.get("document"), x.get("page")) for x in c["gold_sources"]}
        if c["category"] == "conflicting" and not (c["expect_conflict"] and len(distinct) >= 2):
            errors.append(f"{cid}: conflicting case needs expect_conflict and >=2 distinct gold pages")
    return errors


def summary(cases):
    counts = {c: 0 for c in CATEGORIES}
    for case in cases:
        counts[case["category"]] = counts.get(case["category"], 0) + 1
    return counts


if __name__ == "__main__":
    names = sys.argv[1:] or ["data_A", "data_B", "data_C", "data_D"]
    docs, cases = load(names)
    errs = validate(docs, cases)
    print(f"{len(docs)} documents, {sum(len(p) for p in docs.values())} pages, {len(cases)} cases")
    print(summary(cases))
    for e in errs:
        print("ERROR", e)
    print("VALID" if not errs else f"{len(errs)} ERRORS")
    sys.exit(1 if errs else 0)
