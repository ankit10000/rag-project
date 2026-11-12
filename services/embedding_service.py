
from sentence_transformers import SentenceTransformer

from services import retrieval_config as cfg

# Load the configured embedding model (default "all-MiniLM-L6-v2", override
# with the EMBEDDING_MODEL environment variable). Vectors stored with one model
# are NOT comparable with vectors from another, even if the dimensions match.
model = SentenceTransformer(cfg.EMBEDDING_MODEL)


def generate_embeddings(texts: list[str]):

    embeddings = model.encode(
        texts,
        normalize_embeddings=True
    )

    return embeddings
