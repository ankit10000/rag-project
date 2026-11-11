
from services.pdf_parser import extract_text
from services.chunker import chunk_text
from services.embedding_service import generate_embeddings
from services.database import get_connection


def ingest_pdf(pdf_path: str):

    document_name = pdf_path.split("/")[-1].split("\\")[-1]

    print("Starting document ingestion...")

    # Step 1: Extract PDF text
    pages = extract_text(pdf_path)

    # Step 2: Generate chunks
    all_chunks = []

    for page in pages:

        if len(page["text"].split()) < 10:
            continue

        chunks = chunk_text(
            page["text"],
            chunk_size=100,
            overlap=20
        )

        for index, content in enumerate(chunks, start=1):

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

    print("PDF ingestion completed successfully!")
