
from services.pdf_parser import extract_text, PDFLimitExceeded, UnsupportedFileTypeError
import hashlib
import os
import re

from services import retrieval_config as cfg
from services.chunker import chunk_page
from services.embedding_service import generate_embeddings
from services.database import get_connection

# Pages with fewer words than this are skipped by ingest_pdf (unchanged since Phase 2).
MIN_PAGE_WORDS = 10


# --- shared building blocks (Stage 4) ----------------------------------------
# ingest_pdf and the evaluation harness (eval/harness.load_corpus) use these
# same functions for chunk de-duplication, embedding validation and the
# transactional write, so the two paths cannot drift apart.

def chunk_dedupe_key(content: str) -> str:
    """Identity of a chunk's text for de-duplication inside one document."""
    return hashlib.sha1(re.sub(r"\s+", " ", content).lower().encode("utf-8")).hexdigest()


def build_chunks(document_name: str, pages: list[dict], chunk_fn,
                 min_words: int = MIN_PAGE_WORDS, dedupe: bool = True) -> list[dict]:
    """Chunk every page and return chunk records in document order.

    pages: [{"page_number": int, "text": str}, ...]. chunk_id restarts at 1 on
    every page. Identical chunk text inside the document (repeated headers/
    footers) is stored once when dedupe is true.
    """
    chunks = []
    seen = set()

    for page in pages:

        if len(page["text"].split()) < min_words:
            continue

        for index, content in enumerate(chunk_fn(page["text"]), start=1):

            if dedupe:
                digest = chunk_dedupe_key(content)
                if digest in seen:
                    continue
                seen.add(digest)

            chunks.append({
                "document_name": document_name,
                "page_number": page["page_number"],
                "chunk_id": index,
                "content": content,
            })

    return chunks


def validate_embeddings(embeddings, chunk_count: int, expected_dim: int | None = None) -> None:
    """Never write vectors that do not match the column or the chunk list."""
    if expected_dim is not None and embeddings.shape[1] != expected_dim:
        raise ValueError(
            f"Embedding dimension {embeddings.shape[1]} does not match "
            f"EMBEDDING_DIM={expected_dim}"
        )

    # One vector per chunk, otherwise zip() would silently drop chunks.
    if len(embeddings) != chunk_count:
        raise ValueError(
            f"Embedding count {len(embeddings)} does not match "
            f"chunk count {chunk_count}"
        )


def write_document_chunks(cursor, document_name: str, chunks: list[dict], embeddings) -> None:
    """Upsert one document's chunks and drop its stale chunks, on the caller's
    transaction (the caller commits or rolls back both together)."""
    for chunk, embedding in zip(chunks, embeddings):

        cursor.execute(
            """
            INSERT INTO document_chunks
            (
                document_name,
                page_number,
                chunk_id,
                content,
                embedding
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (
                document_name,
                page_number,
                chunk_id
            )
            DO UPDATE SET
                content = EXCLUDED.content,
                embedding = EXCLUDED.embedding
            """,
            (
                chunk["document_name"],
                chunk["page_number"],
                chunk["chunk_id"],
                chunk["content"],
                embedding.tolist()
            )
        )

    # Same transaction: drop chunks of THIS document that are absent
    # from the new version (e.g. a shorter re-ingest). Runs only after
    # every insert/update above succeeded; any failure rolls back both.
    cursor.execute(
        """
        DELETE FROM document_chunks
        WHERE document_name = %s
        AND NOT EXISTS (
            SELECT 1
            FROM unnest(%s::int[], %s::int[]) AS keep(page_number, chunk_id)
            WHERE keep.page_number = document_chunks.page_number
            AND keep.chunk_id = document_chunks.chunk_id
        )
        """,
        (
            document_name,
            [chunk["page_number"] for chunk in chunks],
            [chunk["chunk_id"] for chunk in chunks],
        )
    )


# --- the application's ingestion entry point ---------------------------------

def ingest_pdf(pdf_path: str):

    document_name = pdf_path.split("/")[-1].split("\\")[-1]

    print("Starting document ingestion...")

    # Step 0a: only PDF files are supported (extension check, case-insensitive).
    extension = os.path.splitext(document_name)[1]
    if extension.lower() != ".pdf":
        raise UnsupportedFileTypeError(
            f"Unsupported file type {extension or '(no extension)'!r} for "
            f"{document_name!r}: only .pdf files can be ingested"
        )

    # Step 0b: file-size limit, from file metadata only (the file is not read).
    size_bytes = os.path.getsize(pdf_path)
    if size_bytes > cfg.MAX_PDF_SIZE_MB * 1024 * 1024:
        raise PDFLimitExceeded(
            f"PDF file is {size_bytes / (1024 * 1024):.2f} MB, exceeding "
            f"MAX_PDF_SIZE_MB={cfg.MAX_PDF_SIZE_MB}"
        )

    # Step 1: Extract PDF text (the page-count limit is enforced inside, before
    # extraction; unreadable files raise InvalidPDFError, a ValueError)
    pages = extract_text(pdf_path)

    # Step 2: Generate chunks (duplicate text inside one document is stored once)
    all_chunks = build_chunks(
        document_name,
        pages,
        lambda text: chunk_page(text, cfg.CHUNK_SIZE, cfg.CHUNK_OVERLAP, cfg.CHUNK_STRATEGY),
    )

    if not all_chunks:
        raise ValueError("No usable chunks found in PDF")

    print("Total chunks:", len(all_chunks))

    # Step 3: Generate embeddings
    texts = [
        chunk["content"]
        for chunk in all_chunks
    ]

    embeddings = generate_embeddings(texts)

    validate_embeddings(embeddings, len(all_chunks), cfg.EMBEDDING_DIM)

    # Step 4: Store in PostgreSQL — ONE transaction: leaving the block commits,
    # any exception rolls back the upserts and the stale-chunk delete together.
    with get_connection() as conn:

        with conn.cursor() as cursor:

            write_document_chunks(cursor, document_name, all_chunks, embeddings)

    print("PDF ingestion completed successfully!")
