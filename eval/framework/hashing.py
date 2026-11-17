"""Portable content hashing for frozen evaluation assets (pure, read-only).

Why: the historical freeze hashes were taken on Windows, where some text files
were checked out with CRLF line endings, so the same content hashed
differently on macOS. A portable hash removes only that difference.

Normalization rules (applied to TEXT assets only; binary assets are hashed raw):
  1. Every CRLF pair (b"\\r\\n") becomes LF (b"\\n").
  2. Nothing else changes: a lone CR, trailing whitespace, tabs, Unicode
     normalization form and the final newline are hashed exactly as stored.
  3. A UTF-8 byte-order mark is PRESERVED. Git keeps a BOM byte-for-byte on
     every platform, so it is not a portability difference; adding or
     removing a BOM is a real content change and changes the hash.

The git blob id is computed from the same normalized bytes, so for a text file
committed with LF endings it equals the blob id in the repository
(``git ls-files -s``) on every platform.
"""

import hashlib

HASH_ALGORITHM = "sha256"
TEXT_NORMALIZATION = "CRLF -> LF only; UTF-8 BOM preserved; lone CR and all other bytes unchanged"
BINARY_NORMALIZATION = "none (raw bytes)"
KINDS = ("text", "binary")


def normalize(data: bytes, kind: str) -> bytes:
    if kind not in KINDS:
        raise ValueError(f"unknown asset kind {kind!r}; expected one of {KINDS}")
    return data.replace(b"\r\n", b"\n") if kind == "text" else data


def portable_sha256(data: bytes, kind: str) -> str:
    return hashlib.sha256(normalize(data, kind)).hexdigest()


def raw_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha1(data: bytes, kind: str) -> str:
    """Git object id of the normalized content (as `git hash-object` computes it)."""
    content = normalize(data, kind)
    return hashlib.sha1(b"blob %d\x00" % len(content) + content).hexdigest()
