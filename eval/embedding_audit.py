"""Read-only audit of the production embeddings (does not write anything)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

from services import retrieval_config as cfg  # noqa: E402
from services.database import get_connection  # noqa: E402
from services.embedding_service import generate_embeddings, model  # noqa: E402

with get_connection() as conn:
    rows = conn.execute(
        "SELECT id, content, embedding, vector_dims(embedding) FROM document_chunks ORDER BY id"
    ).fetchall()
    memories = conn.execute(
        "SELECT count(*), min(vector_dims(embedding)), max(vector_dims(embedding)) FROM conversation_memories"
    ).fetchone()

dims = {r[3] for r in rows}
norms = np.array([np.linalg.norm(np.array(r[2].to_list())) for r in rows])
fresh = generate_embeddings([r[1] for r in rows])
cos = np.array([float(np.dot(fresh[i], np.array(rows[i][2].to_list()))) for i in range(len(rows))])

print("configured model      :", cfg.EMBEDDING_MODEL)
print("loaded model dim      :", model.get_embedding_dimension(), "max_seq_length:", model.max_seq_length)
print("stored chunk dims     :", dims, "(expected", cfg.EMBEDDING_DIM, ")")
print("chunk count           :", len(rows))
print("stored norm min/max   :", round(float(norms.min()), 4), round(float(norms.max()), 4))
print("re-embed cosine to stored (min):", round(float(cos.min()), 6), "-> same model for documents and queries" if cos.min() > 0.999 else "-> MISMATCH")
print("memory table (count,min dim,max dim):", memories)
