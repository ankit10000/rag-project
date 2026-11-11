
def chunk_text(
    text: str,
    chunk_size: int = 100,
    overlap: int = 20
) -> list[str]:

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    words = text.split()

    chunks = []

    step = chunk_size - overlap

    for start in range(0, len(words), step):

        chunk_words = words[start:start + chunk_size]

        if not chunk_words:
            break

        chunks.append(" ".join(chunk_words))

        if start + chunk_size >= len(words):
            break

    return chunks


import re

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])")


def split_sentences(text: str) -> list[str]:
    """Paragraph-aware sentence splitter (no external dependency)."""
    sentences = []

    for paragraph in re.split(r"\n\s*\n", text):
        paragraph = " ".join(paragraph.split())

        if paragraph:
            sentences.extend(_SENTENCE_RE.split(paragraph))

    return [s for s in sentences if s.strip()]


def chunk_text_sentences(
    text: str,
    chunk_size: int = 100,
    overlap: int = 20,
) -> list[str]:
    """
    Pack whole sentences into chunks of at most ~chunk_size words.
    The next chunk starts with the last sentences of the previous one
    (up to `overlap` words). A sentence longer than chunk_size is split
    by words so no chunk can grow unbounded.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    units = []

    for sentence in split_sentences(text):
        words = sentence.split()

        if len(words) <= chunk_size:
            units.append(words)
        else:
            step = chunk_size - overlap
            for start in range(0, len(words), step):
                units.append(words[start:start + chunk_size])

    chunks, current = [], []

    for unit in units:

        if current and len(current) + len(unit) > chunk_size:
            chunks.append(" ".join(current))

            carry = []
            for previous in reversed(current_units):
                if len(carry) + len(previous) > overlap:
                    break
                carry = previous + carry

            current = list(carry)
            current_units = [carry] if carry else []

        if not current:
            current_units = []

        current = current + unit
        current_units.append(unit)

    if current:
        chunks.append(" ".join(current))

    return chunks


def chunk_page(text: str, chunk_size: int, overlap: int, strategy: str = "words"):
    """Dispatch used by ingestion and the benchmark."""
    if strategy == "sentences":
        return chunk_text_sentences(text, chunk_size, overlap)

    return chunk_text(text, chunk_size, overlap)
