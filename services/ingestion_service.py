
from services.pdf_parser import extract_text, PDFLimitExceeded, UnsupportedFileTypeError
import hashlib
import os
import re

from services import retrieval_config as cfg
from services.chunker import chunk_page
from services.embedding_service import generate_embeddings
from services.database import get_connection


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

    # Step 1: Extract PDF text (the page-count limit is enforced inside, before extraction)
    pages = extract_text(pdf_path)

    # Step 2: Generate chunks
    all_chunks = []
    seen_chunks = set()

    for page in pages:

        if len(page["text"].split()) < 10:
            continue

        chunks = chunk_page(
            page["text"],
            cfg.CHUNK_SIZE,
            cfg.CHUNK_OVERLAP,
            cfg.CHUNK_STRATEGY,
        )

        for index, content in enumerate(chunks, start=1):

            # Duplicate prevention: identical text inside one document
            # (repeated headers/footers, re-ingested pages) is stored once.
            digest = hashlib.sha1(
                re.sub(r"\s+", " ", content).lower().encode("utf-8")
            ).hexdigest()

            if digest in seen_chunks:
                continue

            seen_chunks.add(digest)

            all_chunks.append({
                "document_name": document_name,
                "page_number": page["page_number"],
                "chunk_id": index,
                "content": content
            })

    if not all_chunks:
        raise ValueError("No usable chunks found in PDF")

    print("Total chunks:", len(all_chunks))

    # Step 3: Generate embeddings
    texts = [
        chunk["content"]
        for chunk in all_chunks
    ]

    embeddings = generate_embeddings(texts)

    # Never write vectors that do not match the column definition.
    if embeddings.shape[1] != cfg.EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dimension {embeddings.shape[1]} does not match "
            f"EMBEDDING_DIM={cfg.EMBEDDING_DIM}"
        )

    # One vector per chunk, otherwise zip() below would silently drop chunks.
    if len(embeddings) != len(all_chunks):
        raise ValueError(
            f"Embedding count {len(embeddings)} does not match "
            f"chunk count {len(all_chunks)}"
        )

    # Step 4: Store in PostgreSQL
    with get_connection() as conn:

        with conn.cursor() as cursor:

            for chunk, embedding in zip(all_chunks, embeddings):

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
                    [chunk["page_number"] for chunk in all_chunks],
                    [chunk["chunk_id"] for chunk in all_chunks],
                )
            )

    print("PDF ingestion completed successfully!")
