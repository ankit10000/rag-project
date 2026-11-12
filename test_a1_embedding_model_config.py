"""A1: EMBEDDING_MODEL configuration controls the model loader.

Pure unit test: SentenceTransformer is replaced by a recording fake, so nothing is downloaded or loaded.
Module copies are executed under private names; the real services.embedding_service stays untouched.
"""
import testsafe
testsafe.require_scratch_db()

import importlib.util
import os
import sys
from unittest import mock

import numpy as np
import sentence_transformers

from services import retrieval_config as real_cfg
import services.ingestion_service as ingestion

ROOT = os.path.dirname(os.path.abspath(__file__))
FAILURES = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def load_copy(filename, private_name):
    spec = importlib.util.spec_from_file_location(private_name, os.path.join(ROOT, "services", filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeModel:
    calls = []

    def __init__(self, name, dim=384):
        self.name, self.dim = name, dim
        FakeModel.calls.append(name)

    def encode(self, texts, normalize_embeddings=False):
        self.last_normalize = normalize_embeddings
        return np.zeros((len(texts), self.dim))


def load_embedding_service(model_name=None, factory=FakeModel):
    FakeModel.calls = []
    ctx = mock.patch.object(sentence_transformers, "SentenceTransformer", side_effect=factory)
    cfg_ctx = (mock.patch.object(real_cfg, "EMBEDDING_MODEL", model_name) if model_name is not None
               else mock.patch.object(real_cfg, "EMBEDDING_MODEL", real_cfg.EMBEDDING_MODEL))
    with ctx, cfg_ctx:
        return load_copy("embedding_service.py", "_a1_embedding_copy")


# 1. default configuration
env = {k: v for k, v in os.environ.items() if k != "EMBEDDING_MODEL"}
with mock.patch.dict(os.environ, env, clear=True):
    cfg_default = load_copy("retrieval_config.py", "_a1_cfg_default")
check("[default] EMBEDDING_MODEL defaults to all-MiniLM-L6-v2", cfg_default.EMBEDDING_MODEL == "all-MiniLM-L6-v2")
check("[default] EMBEDDING_DIM defaults to 384", cfg_default.EMBEDDING_DIM == 384)

# 2. environment override
with mock.patch.dict(os.environ, {"EMBEDDING_MODEL": "some/other-model"}):
    cfg_override = load_copy("retrieval_config.py", "_a1_cfg_override")
check("[env] EMBEDDING_MODEL env var overrides the model name", cfg_override.EMBEDDING_MODEL == "some/other-model")

# 3. loader receives the configured name
svc = load_embedding_service()
check("[loader] with the default config the loader is called once with 'all-MiniLM-L6-v2'",
      FakeModel.calls == ["all-MiniLM-L6-v2"] == [real_cfg.EMBEDDING_MODEL])
svc = load_embedding_service("some/other-model")
check("[loader] a different configured name is what the loader receives (no hardcoded model)",
      FakeModel.calls == ["some/other-model"] and svc.model.name == "some/other-model")

# 6. default behaviour unchanged: encode with normalisation, output passed through
svc = load_embedding_service()
out = svc.generate_embeddings(["a", "b", "c"])
check("[default behaviour] generate_embeddings still encodes with normalize_embeddings=True and returns the array",
      svc.model.last_normalize is True and out.shape == (3, 384))

# 4. dimension validation against the configured dimension (raises before any DB access)
svc768 = load_embedding_service(factory=lambda name: FakeModel(name, dim=768))
page = [{"page_number": 1, "text": " ".join(f"word{i}" for i in range(40))}]
with mock.patch.object(ingestion, "extract_text", return_value=page), \
        mock.patch.object(ingestion.os.path, "getsize", return_value=1), \
        mock.patch.object(ingestion, "generate_embeddings", side_effect=svc768.generate_embeddings):
    try:
        ingestion.ingest_pdf("a1_dummy.pdf")
        err = None
    except Exception as error:  # noqa: BLE001
        err = error
check("[dim] a configured model producing 768-d vectors is rejected by the EMBEDDING_DIM guard (ValueError, nothing stored)",
      isinstance(err, ValueError) and "EMBEDDING_DIM" in str(err) and "768" in str(err))
check("[dim] the guard compares against cfg.EMBEDDING_DIM (384 by default)", real_cfg.EMBEDDING_DIM == 384)

# 5. loading failure: same as before (propagates at import time, no silent fallback to another model)
def failing(name):
    raise OSError(f"cannot load {name}")
try:
    load_embedding_service("missing/model", factory=failing)
    err = None
except Exception as error:  # noqa: BLE001
    err = error
check("[failure] an unloadable model raises at import (OSError), with no silent fallback to the default model",
      isinstance(err, OSError) and "missing/model" in str(err))

# the real module was not disturbed
check("[isolation] the real services.embedding_service module is not the test copy",
      sys.modules.get("services.embedding_service") is not None
      and getattr(sys.modules["services.embedding_service"], "__name__", "") != "_a1_embedding_copy")

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
