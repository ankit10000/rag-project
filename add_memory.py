"""Manually add a memory only when its source user message is specified."""

import argparse
import re


CONVERSATION_ID = "c19ff16f-df58-423e-aa76-9c6b86171d78"
MEMORY_TEXT = (
    "The RAG application uses sentence-transformers/all-MiniLM-L6-v2 "
    "for embeddings, generating 384-dimensional vectors."
)
_ASCII_POSITIVE_INTEGER = re.compile(r"[0-9]+", re.ASCII)
_BIGINT_MAX = 2 ** 63 - 1


def _source_id_arg(value: str) -> int:
    """Parse the CLI's required positive ASCII integer source ID."""
    if not _ASCII_POSITIVE_INTEGER.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "source message ID must contain positive ASCII digits only"
        )

    source_id = int(value)
    if not 1 <= source_id <= _BIGINT_MAX:
        raise argparse.ArgumentTypeError(
            "source message ID must be within the positive bigint range"
        )
    return source_id


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-message-id",
        required=True,
        type=_source_id_arg,
        help="ID of a user message in the configured conversation that supports this memory",
    )
    args = parser.parse_args(argv)

    # Use the same storage boundary as automatic writes. It verifies that the
    # source is a user message in this conversation before inserting anything.
    from services.memory_storage_service import save_memory

    try:
        saved = save_memory(
            conversation_id=CONVERSATION_ID,
            memory_text=MEMORY_TEXT,
            source_message_id=args.source_message_id,
        )
    except ValueError as error:
        parser.error(f"source message rejected: {error}")

    print("Memory saved successfully." if saved else "Memory already exists; no new row was added.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
