"""
Centralised retrieval settings (Phase 2.7).

Every value can be overridden with an environment variable (or a line in
.env, which database.py already loads). Defaults reproduce the behaviour
the project had before Phase 2, except where a benchmark justified a change
(see docs/phase2_report.md).
"""
import os

from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, default))


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _opt_float(name: str):
    value = os.getenv(name, "").strip()
    return float(value) if value else None


# --- candidate generation ---------------------------------------------------
VECTOR_TOP_K = _int("VECTOR_TOP_K", 10)       # chunks requested from pgvector
BM25_TOP_K = _int("BM25_TOP_K", 10)           # chunks requested from keyword search
BM25_DROP_STOPWORDS = _bool("BM25_DROP_STOPWORDS", False)
BM25_BACKEND = os.getenv("BM25_BACKEND", "memory")   # memory (rank_bm25) | fts (PostgreSQL)

# --- fusion -----------------------------------------------------------------
RRF_K = _int("RRF_K", 60)
RRF_TOP_K = _int("RRF_TOP_K", 10)             # fused candidates kept (reranker input)

# --- reranking ----------------------------------------------------------------
RERANK_ENABLED = _bool("RERANK_ENABLED", True)
RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
RERANK_TOP_K = _int("RERANK_TOP_K", 10)       # candidates sent to the cross-encoder

# --- final selection --------------------------------------------------------
FINAL_TOP_K = _int("FINAL_TOP_K", 5)          # chunks handed to the LLM
RERANK_SCORE_MARGIN = _float("RERANK_SCORE_MARGIN", 2.0)   # keep chunks within best-margin
RERANK_MIN_SCORE = _opt_float("RERANK_MIN_SCORE")          # absolute floor; unset = off

# --- vector similarity floor ------------------------------------------------
# Cosine similarity (1 - distance). Unset = no floor (previous behaviour).
SIMILARITY_THRESHOLD = _opt_float("SIMILARITY_THRESHOLD")

# --- embeddings ------------------------------------------------------------
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIM = _int("EMBEDDING_DIM", 384)    # must match document_chunks.embedding

# --- ingestion resource limits (A3) -------------------------------------------
MAX_PDF_SIZE_MB = _float("MAX_PDF_SIZE_MB", 50)    # reject larger files before parsing
MAX_PDF_PAGES = _int("MAX_PDF_PAGES", 500)         # reject PDFs with more pages (checked before text extraction)

# --- chunking (ingestion) ---------------------------------------------------
CHUNK_SIZE = _int("CHUNK_SIZE", 100)          # words
CHUNK_OVERLAP = _int("CHUNK_OVERLAP", 20)     # words
CHUNK_STRATEGY = os.getenv("CHUNK_STRATEGY", "words")   # words | sentences

# --- answer generation (Phase 3) -------------------------------------------
CONTEXT_MAX_CHARS = _int("CONTEXT_MAX_CHARS", 12000)     # total document text sent to the LLM
CONTEXT_MAX_CHUNKS = _int("CONTEXT_MAX_CHUNKS", 8)       # hard cap on chunks in a prompt
HISTORY_MAX_TURNS = _int("HISTORY_MAX_TURNS", 4)         # recent user/assistant pairs sent
HISTORY_MAX_CHARS = _int("HISTORY_MAX_CHARS", 2400)
ANSWER_MAX_RETRIES = _int("ANSWER_MAX_RETRIES", 1)       # regenerations after a failed validation
