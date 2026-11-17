"""Stage 9 Phase E2 / WP2: the three dev-only runners after the E0 run_eval change.

The runners must have no side effect on import and must switch to the scratch DB
BEFORE importing services.* (services.database reads DATABASE_URL at import).
Tripwires: psycopg connects raise; harness.use_scratch_database only records and
sets an unreachable URL; services.* are stubs from a recording meta-path finder.
No database, provider, network, model download, runner main() or held-out case.
"""
import testsafe
testsafe.require_scratch_db()

import contextlib
import importlib.abc
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import types
from unittest import mock

import psycopg

from eval import harness
from eval.phase35 import run_eval as R

ROOT = os.path.dirname(os.path.abspath(__file__))
RUNNERS = ["eval.stage6_live_dev_eval", "eval.stage8_p3_live_dev_eval", "eval.h1_relevance_gate"]
SCRATCH_URL = "postgresql://nobody@127.0.0.1:1/rag_phase35_eval"   # never connected to
FAILURES = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


# ------------------------------------------------- (a)/(e) fresh interpreter --
CHILD = r"""
import testsafe
testsafe.require_scratch_db()
import importlib, json, os, sys
import psycopg
calls = []
def trip(name):
    def fn(*args, **kwargs):
        calls.append(name)
        raise RuntimeError("tripwire " + name)
    return fn
psycopg.connect = trip("psycopg.connect")
psycopg.Connection.connect = classmethod(trip("psycopg.Connection.connect"))
from eval import harness
harness.use_scratch_database = trip("use_scratch_database")
from eval.phase35 import run_eval
run_eval.bootstrap_execution = trip("bootstrap_execution")
url = os.environ["DATABASE_URL"]
importlib.import_module(sys.argv[1])
print(json.dumps({"calls": calls, "url_unchanged": os.environ["DATABASE_URL"] == url,
                  "services": sorted(m for m in sys.modules if m == "services" or m.startswith("services."))}))
"""


def test_import_has_no_side_effect():
    for name in RUNNERS:
        proc = subprocess.run([sys.executable, "-B", "-c", CHILD, name], cwd=ROOT, env=dict(os.environ),
                              capture_output=True, text=True, timeout=120)
        check(f"{name}: fresh-interpreter import succeeded", proc.returncode == 0)
        if proc.returncode != 0:
            print(proc.stderr[-2000:])
            continue
        out = json.loads(proc.stdout.strip().splitlines()[-1])
        check(f"{name}: import made no DB connect / scratch switch / bootstrap", out["calls"] == [])
        check(f"{name}: import left DATABASE_URL unchanged", out["url_unchanged"])
        check(f"{name}: no services.* module imported at import time", out["services"] == [])


# ------------------------------------------------------- in-process sandbox --
def fake_connection(db_name):
    """Stub get_connection(): answers the runners' preflight queries, never connects."""
    def execute(sql, params=None):
        row = ((db_name, 135, 12) if "count(DISTINCT" in sql
               else (db_name,) if "current_database()" in sql else (135,))
        return types.SimpleNamespace(fetchone=lambda: row)
    return contextlib.nullcontext(types.SimpleNamespace(execute=execute))


def _stub(**attrs):
    return lambda mod: mod.__dict__.update(attrs)


def service_stubs(state):
    def database(mod):
        mod.DATABASE_URL = os.environ["DATABASE_URL"]          # what the real module reads at import
        state["database_url_at_import"] = mod.DATABASE_URL
        mod.get_connection = lambda: fake_connection(state["db_name"])

    answer = lambda *a, **k: {"answer": "stub", "attempts": 1, "issues": [], "status": "ok"}  # noqa: E731
    fn = lambda *a, **k: None  # noqa: E731
    return {
        "services": _stub(), "services.database": database,
        "services.llm_service": _stub(MODEL_NAME="stub-model", FALLBACK_MODELS=[], usage_log=[],
                                      generate_answer=fn, get_client=fn),
        "services.answer_service": _stub(generate_grounded_answer=answer),
        "services.context_assembly_service": _stub(assemble_context=fn),
        "services.rag_service": _stub(ask_question=lambda *a, **k: {"retrieval_status": "ok"},
                                      generate_grounded_answer=answer, rewrite_query=fn, classify_question=fn),
        "services.retrieval_config": _stub(VECTOR_TOP_K=1),
        "services.embedding_service": _stub(generate_embeddings=fn),
        "services.hybrid_search_service": _stub(hybrid_search_detailed=fn, keyword_search=fn),
        "services.rrf_service": _stub(reciprocal_rank_fusion=fn),
        "services.search_service": _stub(semantic_search=fn),
    }


class StubServices(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Serves stub services.* modules and records each import; unknown ones raise ImportError."""

    def __init__(self, factories, calls):
        self.factories, self.calls = factories, calls

    def find_spec(self, name, path, target=None):
        if name == "services" or name.startswith("services."):
            return importlib.util.spec_from_loader(name, self, is_package=(name == "services"))
        return None

    def create_module(self, spec):
        self.calls.append("import:" + spec.name)
        if spec.name not in self.factories:
            raise ImportError(f"unexpected services import {spec.name}")
        mod = types.ModuleType(spec.name)
        if spec.name == "services":
            mod.__path__ = []
        self.factories[spec.name](mod)
        return mod

    def exec_module(self, module):
        pass


@contextlib.contextmanager
def sandbox(db_name="rag_phase35_eval"):
    calls, state = [], {"db_name": db_name}

    def trip(name):
        def fn(*args, **kwargs):
            calls.append(name)
            raise RuntimeError("tripwire " + name)
        return fn

    def fake_use_scratch(name="rag_phase2_eval"):
        calls.append(f"use_scratch_database:{name}")
        os.environ["DATABASE_URL"] = SCRATCH_URL.rsplit("/", 1)[0] + "/" + name
        return os.environ["DATABASE_URL"]

    real_bootstrap = R.bootstrap_execution

    def recorded_bootstrap():
        calls.append("bootstrap_execution")
        real_bootstrap()

    saved = {m: sys.modules.pop(m) for m in list(sys.modules) if m == "services" or m.startswith("services.")}
    finder = StubServices(service_stubs(state), calls)
    sys.meta_path.insert(0, finder)
    try:
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-not-a-key"}), \
                mock.patch.object(psycopg, "connect", trip("psycopg.connect")), \
                mock.patch.object(psycopg.Connection, "connect", classmethod(trip("psycopg.Connection.connect"))), \
                mock.patch.object(harness, "use_scratch_database", fake_use_scratch), \
                mock.patch.object(R, "bootstrap_execution", recorded_bootstrap), \
                mock.patch.object(R, "RESULTS_DIR", os.path.join(tmp, "results")), \
                mock.patch.multiple(R, llm_service=None, generate_grounded_answer=None,
                                    assemble_context=None, generate_answer=None):
            yield calls, state, tmp
    finally:
        sys.meta_path.remove(finder)
        for m in [m for m in sys.modules if m == "services" or m.startswith("services.")]:
            del sys.modules[m]
        sys.modules.update(saved)


def error_of(fn, *args, **kwargs):
    """'' if fn returns, else 'ExceptionName: message'."""
    try:
        fn(*args, **kwargs)
        return ""
    except Exception as error:   # the test inspects the refusal
        return f"{type(error).__name__}: {error}"


def ordered_ok(calls):
    """The scratch switch is recorded, and before the first services.* import."""
    switch = "use_scratch_database:rag_phase35_eval"
    imports = [i for i, c in enumerate(calls) if c.startswith("import:services")]
    return switch in calls and bool(imports) and calls.index(switch) < imports[0]


def no_db(calls):
    return not any(c.startswith("psycopg") for c in calls)


def test_stage6_and_stage8():
    from eval import stage6_live_dev_eval as s6
    from eval import stage8_p3_live_dev_eval as s8

    with mock.patch.multiple(s6, llm=None, rag=None):
        check("stage6: capture_answers before bootstrap fails closed (rag is None)",
              error_of(s6.capture_answers).startswith("AttributeError"))

    with sandbox() as (calls, state, _), mock.patch.multiple(s6, llm=None, rag=None):
        docs, selected = s6.preflight()
        check("stage6: preflight calls run_eval.bootstrap_execution first", calls[:1] == ["bootstrap_execution"])
        check("stage6: scratch switch happens before any services import", ordered_ok(calls))
        check("stage6: services.database saw the scratch DATABASE_URL at import",
              state.get("database_url_at_import") == SCRATCH_URL)
        check("stage6: no psycopg connection attempted", no_db(calls))
        check("stage6: run_eval globals bound after bootstrap",
              None not in (R.llm_service, R.generate_grounded_answer, R.assemble_context, R.generate_answer))
        check("stage6: s6.llm / s6.rag bound after bootstrap", s6.llm is not None and s6.rag is not None)
        check("stage6: dev selection sizes 47 / 42", (len(selected[1]), len(selected[2])) == (47, 42))
        check("stage6: every selected case is dev by split_of",
              all(R.split_of(c["id"]) == "dev" for t in (1, 2) for c in selected[t]))

        s6.capture_answers()
        s6.CAPTURE.clear()
        out = R.generate_grounded_answer("q", {}, "DOCUMENT", None, [], "")
        check("stage6: wrapped run_eval.generate_grounded_answer calls through and records",
              out["answer"] == "stub" and s6.CAPTURE.get("answer", {}).get("attempts") == 1)

        s8.record_rewrite_and_classify()
        check("stage8: rewrite/classify recorders installed on the bootstrapped rag_service",
              s6.rag.rewrite_query.__name__ == "rewrite" and s6.rag.classify_question.__name__ == "classify")
        check("stage8: no psycopg connection attempted", no_db(calls))

    with sandbox(db_name="rag_db") as (calls, _, _), mock.patch.multiple(s6, llm=None, rag=None):
        check("stage6: preflight still refuses an unexpected database state",
              "unexpected evaluation database state" in error_of(s6.preflight))


def test_stage6_rejects_heldout():
    from eval import stage6_live_dev_eval as s6
    docs, cases = R.load_all()
    held = next(c for c in cases if c["split"] == "heldout" and c["tier"] == "both")
    dev2 = [c for c in cases if c["split"] == "dev" and c["tier"] == "both"]
    smuggled = dict(held, split="dev")                       # mislabelled held-out case
    forged = [c for c in cases if c["id"] != dev2[0]["id"] and c["id"] != held["id"]] + [smuggled]

    with sandbox() as (calls, _, tmp), mock.patch.multiple(s6, llm=None, rag=None):
        for tier in (1, 2):                                  # baseline that "agrees" with the forgery
            chosen = [c for c in forged if c["split"] == "dev" and (tier == 1 or c["tier"] == "both")]
            with open(os.path.join(tmp, f"tier{tier}_dev.jsonl"), "w", encoding="utf-8") as fh:
                fh.write("".join(json.dumps({"id": c["id"]}) + "\n" for c in chosen))
        with mock.patch.object(R, "load_all", lambda: (docs, forged)), mock.patch.object(s6, "BASELINE_DIR", tmp):
            msg = error_of(s6.preflight)
        check("stage6: held-out case labelled dev is rejected by split_of",
              msg == "RuntimeError: a non-dev case was selected")

        with mock.patch.object(R, "load_all", lambda: (docs, cases + [smuggled])):
            msg = error_of(s6.preflight)
        check("stage6: extra case vs recorded baseline ids is rejected", "does not match the recorded baseline" in msg)
        check("stage6: rejection paths made no DB connection", no_db(calls))


# ------------------------------------------------------------------------ h1 --
def test_h1():
    from eval import h1_relevance_gate as h1
    names = dict(cfg=None, assemble_context=None, get_connection=None, generate_embeddings=None,
                 hybrid_search_detailed=None, keyword_search=None, reciprocal_rank_fusion=None,
                 semantic_search=None)

    with sandbox() as (calls, state, _), mock.patch.multiple(h1, **names):
        dev, chunks = h1.prepare(no_ingest=True)
        check("h1: prepare switches to rag_phase35_eval before any services import", ordered_ok(calls))
        check("h1: services.database saw the scratch DATABASE_URL at import",
              state.get("database_url_at_import") == SCRATCH_URL)
        check("h1: provider bootstrap not used (retrieval only)", "bootstrap_execution" not in calls)
        check("h1: no LLM / answer service imported",
              "import:services.llm_service" not in calls and "import:services.answer_service" not in calls)
        check("h1: retrieval services bound after bootstrap", all(getattr(h1, n) is not None for n in names))
        check("h1: no psycopg connection attempted", no_db(calls))
        check("h1: selection is Tier 2 dev only",
              bool(dev) and all(R.split_of(c["id"]) == "dev" and c["tier"] == "both" for c in dev))
        check("h1: chunk count read from the (stub) scratch DB", chunks == 135)
        held_ids = {c["id"] for c in R.load_all()[1] if c["split"] == "heldout"}
        check("h1: no held-out case id selected", bool(held_ids) and not ({c["id"] for c in dev} & held_ids))

    with sandbox(db_name="rag_db") as (calls, _, _), mock.patch.multiple(h1, **names):
        check("h1: prepare still refuses a non-scratch current_database()",
              "expected 'rag_phase35_eval'" in error_of(h1.prepare, no_ingest=True))


if __name__ == "__main__":
    test_import_has_no_side_effect()
    test_stage6_and_stage8()
    test_stage6_rejects_heldout()
    test_h1()
    print(f"\n{len(FAILURES)} failure(s)")
    sys.exit(1 if FAILURES else 0)
