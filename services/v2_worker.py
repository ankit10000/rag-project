"""One durable ingestion attempt, with lease heartbeats outside inference transactions."""
from __future__ import annotations
import os
from pathlib import Path
import threading
from services import v2_jobs as jobs
from services.database import get_connection
from services.tenant_context import tenant_scope


class LeaseLost(RuntimeError):
    pass


def process_one(owner_id, worker_id, *, lease_seconds=120, extract=None, embed=None):
    """Return False when idle, True when an attempt was handled.

    Injection hooks exist for deterministic integration fixtures; the CLI always
    uses the real local OCR/native path and configured embedding model.
    """
    if not 5<=lease_seconds<=600:raise ValueError('invalid lease')
    with tenant_scope(owner_id):
        job=jobs.claim(worker_id,lease_seconds)
        if job is None:return False
        stopped,lost=threading.Event(),threading.Event()
        progress=[0]
        def renew():
            with tenant_scope(owner_id):
                while not stopped.wait(lease_seconds/3):
                    try:
                        if not jobs.heartbeat(job,progress[0],lease_seconds):
                            lost.set();return
                    except Exception:
                        lost.set();return
        thread=threading.Thread(target=renew,name='rag-lease-heartbeat',daemon=True)
        thread.start()
        try:
            with get_connection() as conn:
                row=conn.execute("SELECT storage_path,version,status FROM documents WHERE id=%s",(job['document_id'],)).fetchone()
            if not row or str(row[1])!=job['document_version'] or row[2] in ('deleted','cancelled'):raise LeaseLost()
            path=Path(row[0]).resolve()
            root=Path(os.getenv('RAG_V2_UPLOAD_DIR','data/v2_uploads')).resolve()/str(owner_id)
            if not path.is_relative_to(root) or not path.is_file():raise ValueError('invalid storage reference')
            from services.ocr_service import extract_pages,OCROptions
            extraction=extract or extract_pages
            pages=extraction(str(path),options=OCROptions(),cancelled=lost.is_set,
                             progress=lambda page,total:progress.__setitem__(0,min(70,int(page/total*70))))
            if lost.is_set():raise LeaseLost()
            from services.ingestion_service import build_chunks,validate_embeddings
            from services.chunker import chunk_page
            from services import retrieval_config as cfg
            chunks=build_chunks(job['document_id'],pages,lambda text:chunk_page(text,cfg.CHUNK_SIZE,cfg.CHUNK_OVERLAP,cfg.CHUNK_STRATEGY))
            if not chunks:raise ValueError('no usable text')
            from services.embedding_service import generate_embeddings
            vectors=(embed or generate_embeddings)([c['content'] for c in chunks])
            validate_embeddings(vectors,len(chunks),cfg.EMBEDDING_DIM)
            progress[0]=90
            if lost.is_set() or not jobs.publish(job,pages,chunks,vectors):raise LeaseLost()
        except LeaseLost:
            pass # Cancellation/expiry owns state; stale attempt must never overwrite it.
        except Exception as error:
            from services.ocr_service import OCRUnavailable,OCRError
            code='ocr_unavailable' if isinstance(error,OCRUnavailable) else 'ocr_failed' if isinstance(error,OCRError) else 'processing_failed'
            jobs.fail(job,code)
        finally:
            stopped.set()
            # Never return while a heartbeat can still write. Database connect,
            # statement and lock waits are already bounded by database.py.
            thread.join()
        return True
