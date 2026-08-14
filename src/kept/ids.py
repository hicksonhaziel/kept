"""Stable criterion identifiers and content hashing. See docs/adr/0002."""

from __future__ import annotations

import hashlib
import re

SCHEMA_VERSION = 1
HASH_ALGORITHM = "sha256"
DISPLAY_HASH_LENGTH = 12

_WHITESPACE_RUN = re.compile(r"\s+")


def normalise_text(text: str) -> str:
    """Collapse whitespace runs and strip the ends. Case is preserved."""
    return _WHITESPACE_RUN.sub(" ", text).strip()


def content_hash(text: str) -> str:
    """Full hex digest of the whitespace-normalised text."""
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()


def display_hash(digest: str) -> str:
    """Shorten a digest for human-facing output only."""
    return digest[:DISPLAY_HASH_LENGTH]


def requirement_id(number: int) -> str:
    """Build a requirement identifier such as `REQ-3`."""
    if number < 1:
        msg = f"requirement number must be >= 1, got {number}"
        raise ValueError(msg)
    return f"REQ-{number}"


def criterion_id(requirement_number: int, position: int) -> str:
    """Build a criterion identifier such as `REQ-3.2`. Both parts are one-based."""
    if position < 1:
        msg = f"criterion position must be >= 1, got {position}"
        raise ValueError(msg)
    return f"{requirement_id(requirement_number)}.{position}"
