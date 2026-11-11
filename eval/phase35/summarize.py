"""
Summarise Phase 3.5 results and export the human-review sheet.

    .venv\\Scripts\\python.exe eval\\phase35\\summarize.py [--sheet]

Reads eval/phase35/results/tier*_*.jsonl and writes eval/phase35/results/REPORT.md.
--sheet also writes eval/phase35/review_sheet.csv (one row per case) for human review.
"""
import csv
import json
import math
import os
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from eval.phase35 import validate as V  # noqa: E402
from eval.phase35.run_eval import DATA_MODULES, split_of  # noqa: E402

RESULTS = os.path.join(ROOT, "eval", "phase35", "results")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))] if values else 0.0


def metrics(rows, cases_by_id):
    n = len(rows)
    if not n:
        return None
    sc = [r["score"] for r in rows]
    answerable = [r for r in rows if not cases_by_id[r["id"]]["expect_abstain"]]
    abst_rows = [r for r in rows if r["score"]["abstain_ok"] is not None]
    correct = sum(s["correct"] for s in sc)
    lo, hi = wilson(correct, n)
    return {
        "n": n,
        "correct": correct / n, "correct_ci": (lo, hi),
        "correct_lenient": sum(s["correct_lenient"] for s in sc) / n,
        "unsupported_rate": sum(s["unsupported"] for s in sc) / n,
        "citation_correctness": statistics.mean(s["citation_correctness"] for s in sc),
        "citation_completeness": statistics.mean(
            r["score"]["citation_completeness"] for r in answerable) if answerable else None,
        "abstention_accuracy": (sum(bool(r["score"]["abstain_ok"]) for r in abst_rows) / len(abst_rows)) if abst_rows else None,
        "fabricated_total": sum(s["fabricated"] for s in sc),
        "ungrounded_number_cases": sum(bool(s["ungrounded_numbers"]) for s in sc),
        "latency_median": statistics.median(r["latency_s"] for r in rows),
        "latency_p95": pct([r["latency_s"] for r in rows], 95),
        "llm_calls_mean": statistics.mean(r["llm_calls"] for r in rows),
        "prompt_tokens_mean": statistics.mean(r["prompt_tokens"] for r in rows),
        "output_tokens_mean": statistics.mean(r["output_tokens"] for r in rows),
        "tokens_total": sum(r["prompt_tokens"] + r["output_tokens"] for r in rows),
        "retrieval_page_recall": (statistics.mean(
            r["score"]["retrieval_page_recall"] for r in rows
            if r["score"].get("retrieval_page_recall") is not None) if any(
            r["score"].get("retrieval_page_recall") is not None for r in rows) else None),
    }


def fmt(v, digits=3):
    if v is None:
        return "-"
    if isinstance(v, tuple):
        return f"[{v[0]:.2f}, {v[1]:.2f}]"
    return f"{v:.{digits}f}" if isinstance(v, float) else str(v)


def table(title, groups, cases_by_id):
    lines = [f"### {title}", "",
             "| Group | n | Correct | 95% CI | Correct (lenient inj.) | Unsupported | Cit. correct | Cit. complete | Abstention acc. | Fabricated | Ungrounded-number cases | Median s | p95 s | Prompt tok (mean) | Out tok (mean) | Retrieval page recall |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, rows in groups:
        m = metrics(rows, cases_by_id)
        if not m:
            continue
        lines.append(
            f"| {name} | {m['n']} | {fmt(m['correct'])} | {fmt(m['correct_ci'])} | {fmt(m['correct_lenient'])} | "
            f"{fmt(m['unsupported_rate'])} | {fmt(m['citation_correctness'])} | {fmt(m['citation_completeness'])} | "
            f"{fmt(m['abstention_accuracy'])} | {m['fabricated_total']} | {m['ungrounded_number_cases']} | "
            f"{fmt(m['latency_median'], 1)} | {fmt(m['latency_p95'], 1)} | {fmt(m['prompt_tokens_mean'], 0)} | "
            f"{fmt(m['output_tokens_mean'], 0)} | {fmt(m['retrieval_page_recall'])} |")
    lines.append("")
    return lines


def failure_block(rows, cases_by_id, docs, limit=60):
    out = ["### Failed cases (strict scoring)", ""]
    failed = [r for r in rows if not r["score"]["correct"]][:limit]
    if not failed:
        out.append("None.")
    for r in failed:
        c = cases_by_id[r["id"]]
        s = r["score"]
        out += [
            f"#### {r['id']} ({r['category']}, tier {r['tier']}, split {r['split']})",
            f"- **Question:** {r['question']}",
            f"- **Expected:** facts {c['gold_facts']} | abstain={c['expect_abstain']} partial={c['expect_partial']} "
            f"conflict={c['expect_conflict']} | forbidden {c['forbidden']}",
            f"- **Gold sources:** {[(x['document'], x['page']) for x in c['gold_sources']]} — review note: {c['review_note']}",
            f"- **Retrieved/context:** {r.get('retrieved') or r.get('context')}",
            f"- **Answer ({r['status']}):** {r['answer'][:700]}",
            f"- **Citations:** {[(x.get('ref'), x.get('document'), x.get('page')) for x in r['citations']]}",
            f"- **Why failed:** fact_recall={s['fact_recall']:.2f} forbidden={s['forbidden_hits']} abstain_ok={s['abstain_ok']} "
            f"partial_ok={s['partial_ok']} conflict_ok={s['conflict_ok']} ungrounded_numbers={s['ungrounded_numbers']} "
            f"cit={s['citation_correctness']:.2f}/{s['citation_completeness']:.2f}",
            "",
        ]
    return out


def main():
    docs, cases = V.load(DATA_MODULES)
    for c in cases:
        c["split"] = split_of(c["id"])
    by_id = {c["id"]: c for c in cases}
    cats = V.CATEGORIES

    lines = ["# Phase 3.5 — independent answer-quality evaluation", "",
             f"Dataset: {len(docs)} unseen documents, {sum(len(p) for p in docs.values())} pages, {len(cases)} cases "
             f"(dev {sum(c['split']=='dev' for c in cases)}, held-out {sum(c['split']=='heldout' for c in cases)}). "
             "Ground truth is author-written and mechanically verified against the page text; "
             "**it has NOT been reviewed by a human yet** (see review_sheet.csv).", ""]

    for tier in ("1", "2"):
        for split in ("heldout", "dev"):
            rows = load(os.path.join(RESULTS, f"tier{tier}_{split}.jsonl"))
            if not rows:
                continue
            label = f"Tier {tier} ({'answer layer only' if tier == '1' else 'end to end'}), {split}"
            groups = [("ALL", rows)] + [(c, [r for r in rows if r["category"] == c]) for c in cats]
            lines += table(label, groups, by_id)
            if split == "heldout":
                lines += failure_block(rows, by_id, docs)

    with open(os.path.join(RESULTS, "REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("wrote", os.path.join(RESULTS, "REPORT.md"))

    if "--sheet" in sys.argv:
        path = os.path.join(ROOT, "eval", "phase35", "review_sheet.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["id", "split", "category", "question", "history (last turn)", "expected facts (any of)",
                        "gold sources (document p.N: span)", "expect_abstain", "expect_partial", "expect_conflict",
                        "forbidden", "author review_note", "REVIEWER_verdict (ok / fix / drop)", "REVIEWER_comment"])
            for c in cases:
                w.writerow([
                    c["id"], c["split"], c["category"], c["question"],
                    c["history"][-1]["content"] if c["history"] else "",
                    " AND ".join("/".join(a) for a in c["gold_facts"]),
                    " || ".join(f"{s['document']} p.{s['page']}: {s['span'][:120]}" for s in c["gold_sources"]),
                    c["expect_abstain"], c["expect_partial"], c["expect_conflict"],
                    ", ".join(c["forbidden"]), c["review_note"], "", ""])
        print("wrote", path)


if __name__ == "__main__":
    main()
