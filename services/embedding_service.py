
from sentence_transformers import SentenceTransformer

# Load the embedding model
model = SentenceTransformer("all-MiniLM-L6-v2")


def generate_embeddings(texts: list[str]):

    embeddings = model.encode(
        texts,
        normalize_embeddings=True
    )

    return embeddings
