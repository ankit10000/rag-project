
import re


# Conservative detector: only clear, imperative memory-management
# requests match. Anything ambiguous returns False so the message
# goes through the normal RAG flow.
FORGET_PATTERNS = [
    # Explicit imperative requests at the start
    r"^(?:(?:please|kindly|can you|could you|would you|will you)\s+)*"
    r"(?:forget|erase)\s+(?:about\s+)?"
    r"(?:my|me|everything|all|what i|that i|the fact|our)\b",

    # Explicitly stop retaining information
    r"\bstop\s+remembering\b",

    # Explicit negated memory instructions
    r"^(?:(?:please|kindly|can you|could you)\s+)*"
    r"(?:don['’]?t|do not)\s+(?:remember|keep|store|save)\b"
    r".*\b(?:my|me|this|that|it)\b",

    # Explicit memory deletion terms
    r"\b(?:delete|remove|erase|clear|wipe)\b"
    r".*\b(?:memory|memories)\b",
]


def is_explicit_memory_delete_request(message: str) -> bool:
    if not message:
        return False

    message = re.sub(r"\s+", " ", message.lower().strip())

    return any(
        re.search(pattern, message)
        for pattern in FORGET_PATTERNS
    )
