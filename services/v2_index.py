"""Reject unknown or incompatible tenant vector provenance before retrieval."""
from services.database import get_connection
from services import retrieval_config as cfg

def require_index_identity(owner):
    with get_connection() as c:
        incompatible=c.execute('''SELECT 1 FROM documents d WHERE d.owner_id=%s
            AND EXISTS(SELECT 1 FROM document_chunks dc WHERE dc.document_id=d.id)
            AND (d.embedding_model IS DISTINCT FROM %s OR d.embedding_dim IS DISTINCT FROM %s)
            LIMIT 1''',(owner,cfg.EMBEDDING_MODEL,cfg.EMBEDDING_DIM)).fetchone()
    if incompatible:
        from backend.errors import ApiError
        raise ApiError(409,'index_model_mismatch','document index requires reprocessing with the configured embedding model')
