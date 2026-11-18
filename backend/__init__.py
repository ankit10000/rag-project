"""Local v1.0 — single-user HTTP API around the existing RAG services.

Importing this package (or backend.app) does NOT connect to a database,
does NOT load the embedding/reranker models and does NOT create an LLM
client: heavy service modules are imported lazily inside request handlers.
"""

API_VERSION = "v1"
APP_VERSION = "1.0.0"
