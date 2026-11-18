"""Explicit local-v1.0 release constraints; existing app defaults stay unchanged.

The fixed model is a configuration restriction, not evidence of the model that
created pre-existing database vectors. Only a separately verified empty local
index ingested with this profile can establish that provenance without schema
007; no historical vector identity is inferred or backfilled here.
"""
import os

PROFILE_NAME = "local-v1.0"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


def enabled():
    return os.getenv("LOCAL_V1_PROFILE") == "1"


def require_embedding_model(model_name):
    if enabled() and model_name != EMBEDDING_MODEL:
        raise ValueError(
            f"{PROFILE_NAME} requires EMBEDDING_MODEL={EMBEDDING_MODEL}; "
            "existing vector model provenance cannot be inferred"
        )


def requires_verified_ranking(question_type, results, rerank_status):
    return (enabled() and question_type in ("DOCUMENT", "MIXED")
            and bool(results) and rerank_status != "ok")
