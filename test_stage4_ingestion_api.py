"""Batch 2 / Stage 4: API upload path (POST /api/v1/documents) end to end.

In-process FastAPI app (TestClient, loopback Host), scratch database only
(testsafe; run via run_tests.py, e.g. --db rag_ingestion_test), a temporary
upload directory, a test-only bearer token from RAG_API_TOKEN, and the REAL
embedding model offline for the successful upload. No network, no LLM.
Cleanup removes only s4api_* documents and the temporary directory.
"""
import testsafe
testsafe.require_scratch_db()

import os
import secrets
import shutil
import sys
import tempfile
from unittest import mock

import pymupdf

os.environ["RAG_API_TOKEN"] = secrets.token_urlsafe(32)   # test-only token, never printed

from fastapi.testclient import TestClient  # noqa: E402

import backend.config as api_config  # noqa: E402
from backend.app import app  # noqa: E402
import services.ingestion_service as ingestion  # noqa: E402
from services import retrieval_config as cfg  # noqa: E402
from services.database import get_connection  # noqa: E402

FAILURES = []
PREFIX = "s4api_"
UPLOAD_DIR = tempfile.mkdtemp(prefix="s4api_uploads_")
AUTH = {"Authorization": "Bearer " + os.environ["RAG_API_TOKEN"]}


def check(label, cond):
    print(f"{'PASS' if cond else 'FAIL'} | {label}")
    if not cond:
        FAILURES.append(label)


def words(tag, n):
    return " ".join(f"{tag}w{i:03d}" for i in range(1, n + 1))


def pdf_bytes(pages):
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(40, 40, 555, 800), text, fontsize=8)
    data = doc.tobytes()
    doc.close()
    return data


def chunk_rows(name):
    with get_connection() as conn:
        return conn.execute("SELECT page_number, chunk_id, md5(content) FROM document_chunks "
                            "WHERE document_name = %s ORDER BY 1, 2", (name,)).fetchall()


def leftovers():
    return sorted(f for f in os.listdir(UPLOAD_DIR) if f.startswith("."))


def cleanup():
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE document_name LIKE %s", (PREFIX + "%",))


def upload(client, name, data, replace=False, content_type="application/pdf"):
    return client.post("/api/v1/documents", params={"replace": str(replace).lower()}, headers=AUTH,
                       files={"file": (name, data, content_type)})


cleanup()
try:
    with mock.patch.object(api_config, "UPLOAD_DIR", UPLOAD_DIR), \
            TestClient(app, base_url="http://127.0.0.1") as client:

        # valid upload with the real embedding model
        r = upload(client, "s4api_valid.pdf", pdf_bytes([words("v1", 150), words("v2", 30)]))
        body = r.json()
        check("[api] valid PDF -> 201 indexed with chunk count", r.status_code == 201 and body.get("status") == "indexed"
              and body.get("chunks", 0) > 0 and body.get("replaced") is False)
        stored = chunk_rows("s4api_valid.pdf")
        check("[api] chunks persisted in the scratch database", len(stored) == body.get("chunks"))
        check("[api] the file is stored in the upload directory; no temp files left",
              os.path.isfile(os.path.join(UPLOAD_DIR, "s4api_valid.pdf")) and leftovers() == [])
        g = client.get("/api/v1/documents/s4api_valid.pdf", headers=AUTH)
        check("[api] GET /documents/{name} reports the stored pages/chunks", g.status_code == 200)

        # error cases
        cases = [
            ("wrong extension", "s4api_notes.txt", b"hello world", 422, "unsupported_file_type"),
            ("empty file", "s4api_empty.pdf", b"", 422, "empty_file"),
            ("non-PDF renamed to .pdf", "s4api_fake.pdf", b"plain text, not a PDF\n" * 50, 422, "invalid_pdf"),
            ("corrupt PDF", "s4api_corrupt.pdf", b"%PDF-1.7\n" + os.urandom(2000), 422, "invalid_pdf"),
            ("PDF without text", "s4api_blank.pdf", pdf_bytes(["", ""]), 422, "ingestion_failed"),
        ]
        for label, name, data, status, code in cases:
            r = upload(client, name, data)
            err = r.json().get("error", {})
            check(f"[api] {label} -> {status} {code}", r.status_code == status and err.get("code") == code)
            check(f"[api] {label}: no rows, no stored file, no temp files",
                  chunk_rows(name) == [] and not os.path.exists(os.path.join(UPLOAD_DIR, name)) and leftovers() == [])
            check(f"[api] {label}: response leaks no path, trace or document text",
                  UPLOAD_DIR not in r.text and "Traceback" not in r.text and "plain text" not in r.text)

        with mock.patch.object(cfg, "MAX_PDF_SIZE_MB", 0.001):
            r = upload(client, "s4api_big.pdf", pdf_bytes([words("big", 400)] * 3))
        check("[api] oversized file -> 413 file_too_large (existing contract)",
              r.status_code == 413 and r.json()["error"]["code"] == "file_too_large" and leftovers() == [])

        # duplicate name: 409 unless replace=true; a failed replace keeps the previous version
        r = upload(client, "s4api_valid.pdf", pdf_bytes([words("other", 60)]))
        check("[api] same name without replace -> 409, original untouched",
              r.status_code == 409 and chunk_rows("s4api_valid.pdf") == stored)

        def failing_embedder(texts):
            raise RuntimeError("simulated embedding failure")
        with mock.patch.object(ingestion, "generate_embeddings", side_effect=failing_embedder):
            r = upload(client, "s4api_valid.pdf", pdf_bytes([words("other", 60)]), replace=True)
        check("[api] embedding failure on replace -> 500 ingestion_error (internal, distinguishable from 422)",
              r.status_code == 500 and r.json()["error"]["code"] == "ingestion_error"
              and "simulated" not in r.text)
        with open(os.path.join(UPLOAD_DIR, "s4api_valid.pdf"), "rb") as f:
            restored_file_ok = f.read(5) == b"%PDF-"
        check("[api] failed replace: previous chunks AND previous file restored, no temp/backup files",
              chunk_rows("s4api_valid.pdf") == stored and restored_file_ok and leftovers() == [])

        r = upload(client, "s4api_valid.pdf", b"%PDF-1.4\n" + os.urandom(500), replace=True)
        check("[api] corrupt replacement -> 422 invalid_pdf, previous version kept",
              r.status_code == 422 and r.json()["error"]["code"] == "invalid_pdf"
              and chunk_rows("s4api_valid.pdf") == stored and leftovers() == [])

        r = upload(client, "s4api_valid.pdf", pdf_bytes([words("new", 40)]), replace=True)
        check("[api] valid replace -> 201 replaced=true, stale chunks gone",
              r.status_code == 201 and r.json()["replaced"] is True and len(chunk_rows("s4api_valid.pdf")) == 1)

        r = upload(client, "S4API_VALID.PDF", pdf_bytes([words("case", 40)]))
        print(f"INFO | upload differing only in case from an existing file -> {r.status_code}")
        check("[api] a name differing only in case does not silently create a second copy on a case-insensitive "
              "filesystem (409) or is stored separately", r.status_code in (201, 409))
        if r.status_code == 201:
            check("[api] case-variant stored as its own document; original untouched",
                  len(chunk_rows("s4api_valid.pdf")) == 1)

        r = client.post("/api/v1/documents", files={"file": ("s4api_noauth.pdf", pdf_bytes([words("n", 30)]))})
        check("[api] upload without token -> 401", r.status_code == 401)
finally:
    with get_connection() as conn:
        conn.execute("DELETE FROM document_chunks WHERE lower(document_name) LIKE %s", (PREFIX + "%",))
    shutil.rmtree(UPLOAD_DIR, ignore_errors=True)
    check("[cleanup] no s4api_* rows remain", chunk_rows("s4api_valid.pdf") == [])

print(f"\n{len(FAILURES)} check(s) failed")
sys.exit(1 if FAILURES else 0)
