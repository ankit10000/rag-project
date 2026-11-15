"""Batch 1: provider configuration and lazy LLM client (pure unit test).

No API call, no network, no database access: module copies are executed under
private names with a controlled environment, and genai.Client is replaced by a
recording fake. The real services.llm_service module is not modified.
"""
import testsafe
testsafe.require_scratch_db()

import importlib.util
import os
import sys
from unittest import mock

import dotenv

ROOT = os.path.dirname(os.path.abspath(__file__))
FAILURES = []


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def load_copy(relpath, private_name):
    spec = importlib.util.spec_from_file_location(private_name, os.path.join(ROOT, relpath))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GEMINI_VARS = ("GEMINI_MODEL", "GEMINI_FALLBACK_MODELS", "GEMINI_API_KEY")


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in GEMINI_VARS}
    env.update(extra)
    return env


def load_config(**env):
    # load_dotenv is disabled so the developer's real .env cannot leak into the test.
    with mock.patch.dict(os.environ, clean_env(**env), clear=True), \
            mock.patch.object(dotenv, "load_dotenv", return_value=False):
        return load_copy("services/llm_config.py", "_b1_llm_config")


# 1. defaults (unchanged from the previous llm_service constants)
cfg = load_config()
check("[default] primary model is gemini-3.5-flash-lite", cfg.MODEL_NAME == "gemini-3.5-flash-lite")
check("[default] fallback order is gemini-3.1-flash-lite, gemini-2.5-flash",
      cfg.FALLBACK_MODELS == ["gemini-3.1-flash-lite", "gemini-2.5-flash"])

# 2. environment overrides and list parsing
cfg = load_config(GEMINI_MODEL="m-primary", GEMINI_FALLBACK_MODELS=" a , ,b,")
check("[env] GEMINI_MODEL overrides the primary model", cfg.MODEL_NAME == "m-primary")
check("[env] GEMINI_FALLBACK_MODELS is split, trimmed, empties dropped", cfg.FALLBACK_MODELS == ["a", "b"])

# 3. key presence only
with mock.patch.dict(os.environ, clean_env(), clear=True):
    check("[key] api_key_configured() is False without GEMINI_API_KEY", cfg.api_key_configured() is False)
with mock.patch.dict(os.environ, clean_env(GEMINI_API_KEY="dummy-not-a-key"), clear=True):
    check("[key] api_key_configured() is True with GEMINI_API_KEY", cfg.api_key_configured() is True)
    check("[source] a variable not in .env is reported as process environment or .env, never its value",
          cfg.setting_source("GEMINI_API_KEY") in ("process environment", ".env"))
with mock.patch.dict(os.environ, clean_env(), clear=True):
    check("[source] unset variable -> code default", cfg.setting_source("GEMINI_MODEL") == "code default")


# 4. llm_service imports WITHOUT a key; the client is created lazily; missing key -> clear error
class FakeClient:
    created = []

    def __init__(self, api_key=None, http_options=None):
        FakeClient.created.append(api_key)


import google.genai as genai_pkg  # noqa: E402

with mock.patch.dict(os.environ, clean_env(), clear=True), \
        mock.patch.object(dotenv, "load_dotenv", return_value=False), \
        mock.patch.object(genai_pkg, "Client", FakeClient):
    sys.modules["services.llm_config"] = load_copy("services/llm_config.py", "_b1_llm_config_for_svc")
    try:
        svc = load_copy("services/llm_service.py", "_b1_llm_service")
        import_error = None
    except Exception as error:  # noqa: BLE001
        import_error = error
    finally:
        sys.modules.pop("services.llm_config", None)
    check("[lazy] llm_service imports without GEMINI_API_KEY", import_error is None)
    check("[lazy] no client is created at import", FakeClient.created == [])
    try:
        svc.get_client()
        err = None
    except Exception as error:  # noqa: BLE001
        err = error
    check("[missing key] the first request raises ValueError('GEMINI_API_KEY is missing from .env')",
          isinstance(err, ValueError) and "GEMINI_API_KEY is missing" in str(err))

    os.environ["GEMINI_API_KEY"] = "dummy-not-a-key"
    first, second = svc.get_client(), svc.client
    check("[lazy] with a key the client is created once and reused (also via llm_service.client)",
          first is second and FakeClient.created == ["dummy-not-a-key"])
    check("[selection] provider order is primary then fallbacks without duplicates",
          svc._model_order() == [svc.MODEL_NAME] + [m for m in svc.FALLBACK_MODELS if m != svc.MODEL_NAME])

# 5. providers router uses llm_config (no ast parsing) and never returns a key value
import backend.routers.providers as providers  # noqa: E402

src = open(os.path.join(ROOT, "backend", "routers", "providers.py"), encoding="utf-8").read()
check("[router] providers router no longer parses source code with ast", "import ast" not in src)
with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "dummy-secret-value"}):
    body = providers.list_providers().model_dump()
from services import llm_config as real_cfg  # noqa: E402
info = body["providers"][0]
check("[router] reports the effective primary/fallback models from llm_config",
      info["primary_model"] == real_cfg.MODEL_NAME and info["fallback_models"] == real_cfg.FALLBACK_MODELS)
check("[router] key presence only; the key value never appears in the response",
      info["api_key_configured"] is True and "dummy-secret-value" not in repr(body))

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
