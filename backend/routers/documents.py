"""Document management: list, details, upload + ingest. No delete endpoint.

Ingestion reuses services.ingestion_service.ingest_pdf unchanged (A2 upsert +
stale-chunk cleanup in one transaction, A3 size/page limits, A4 .pdf-only,
F1 embedding checks). The stored document_name is the saved file's basename.

Deletion is NOT exposed: the repository has no document-deletion service, and
removing chunks safely would also need BM25/embedding cache and file cleanup
semantics that are not defined yet (documented as deferred).
"""

import os
import re
import uuid

from fastapi import APIRouter, File, Query, UploadFile

from backend import config
from backend.dependencies import ingestion_lock
from backend.errors import ApiError, conflict, not_found, unprocessable
from backend.schemas import DocumentDetail, DocumentSummary, IngestResponse

router = APIRouter(prefix="/documents", tags=["documents"])

_SAFE = re.compile(r"[^A-Za-z0-9._ \-]+")
_CHUNK = 1024 * 1024


def safe_pdf_filename(original: str) -> str:
    """Server-side file name: basename only, restricted characters, .pdf only."""
    name = (original or "").replace("\\", "/").split("/")[-1]
    name = _SAFE.sub("_", name).strip(" .")
    name = re.sub(r"\s+", " ", name)
    if not name.lower().endswith(".pdf") or len(name) <= 4:
        raise unprocessable("unsupported_file_type", "only .pdf files can be uploaded")
    if len(name) > config.MAX_FILENAME_LENGTH:
        stem = name[:-4][: config.MAX_FILENAME_LENGTH - 4].rstrip(" .")
        name = stem + ".pdf"
    return name


def _document_name_param(name: str) -> str:
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise unprocessable("invalid_document_name", "invalid document name")
    return name


@router.get("", response_model=list[DocumentSummary])
def list_documents():
    from backend.repositories import list_documents as repo_list
    return [DocumentSummary(**d) for d in repo_list()]


@router.get("/{document_name}", response_model=DocumentDetail)
def get_document(document_name: str):
    from backend.repositories import get_document as repo_get
    doc = repo_get(_document_name_param(document_name))
    if doc is None:
        raise not_found("document")
    return DocumentDetail(status="indexed", **doc)


@router.post("", response_model=IngestResponse, status_code=201)
def upload_and_ingest(file: UploadFile = File(...),
                      replace: bool = Query(False, description="re-ingest an existing document of the same name")):
    from services import retrieval_config as cfg

    final_name = safe_pdf_filename(file.filename)
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    upload_dir = os.path.realpath(config.UPLOAD_DIR)
    final_path = os.path.realpath(os.path.join(upload_dir, final_name))
    if os.path.dirname(final_path) != upload_dir:              # path traversal guard
        raise unprocessable("invalid_document_name", "invalid document name")

    limit = int(cfg.MAX_PDF_SIZE_MB * 1024 * 1024)
    temp_path = os.path.join(upload_dir, f".upload-{uuid.uuid4().hex}.part")

    with ingestion_lock:
        from backend.repositories import get_document as repo_get

        existing = repo_get(final_name)
        if (existing or os.path.exists(final_path)) and not replace:
            raise conflict("a document with this name already exists (use replace=true to re-ingest)")

        written = 0
        try:
            with open(temp_path, "xb") as out:
                while True:
                    block = file.file.read(_CHUNK)
                    if not block:
                        break
                    written += len(block)
                    if written > limit:
                        raise ApiError(413, "file_too_large", f"file exceeds MAX_PDF_SIZE_MB={cfg.MAX_PDF_SIZE_MB}")
                    out.write(block)
            if written == 0:
                raise unprocessable("empty_file", "uploaded file is empty")
        except BaseException:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        # Keep the previous file (if any) until the new version is ingested, so a
        # failed re-ingest restores both the database state (ingest_pdf is one
        # transaction) and the file on disk.
        backup_path = None
        if os.path.exists(final_path):
            backup_path = os.path.join(upload_dir, f".previous-{uuid.uuid4().hex}.pdf.bak")
            os.replace(final_path, backup_path)
        os.replace(temp_path, final_path)

        from services.ingestion_service import ingest_pdf
        from services.pdf_parser import PDFLimitExceeded, UnsupportedFileTypeError

        try:
            ingest_pdf(final_path)
        except BaseException as exc:
            _restore_previous(final_path, backup_path)
            if isinstance(exc, (PDFLimitExceeded, UnsupportedFileTypeError)):
                raise unprocessable("ingestion_rejected", type(exc).__name__) from None
            if isinstance(exc, ValueError):
                raise unprocessable("ingestion_failed",
                                    "the PDF could not be ingested (no usable text or invalid embeddings)") from None
            if isinstance(exc, Exception):
                raise ApiError(500, "ingestion_error", "ingestion failed; previous document state was preserved") from None
            raise

        if backup_path and os.path.exists(backup_path):
            os.remove(backup_path)

        stored = repo_get(final_name)

    return IngestResponse(document_name=final_name, status="indexed",
                          chunks=stored["chunks"] if stored else 0, replaced=bool(existing))


def _restore_previous(path: str, backup_path) -> None:
    """Undo the file swap after a failed ingestion: drop the new file and put
    the previous version (if there was one) back. The database is unchanged
    because ingest_pdf rolls back its single transaction on failure."""
    if os.path.exists(path):
        os.remove(path)
    if backup_path and os.path.exists(backup_path):
        os.replace(backup_path, path)
