"""Stable identity and change detection for acceptance criteria.

Two separate concerns, deliberately kept apart:

*Identity* is structural. `REQ-3.2` is the second criterion of the third
requirement, and it stays that way when the criterion is reworded. If identity
were derived from content, the ledger would lose the entire history of a promise
every time somebody improved its wording.

*Change detection* is content-based. The hash changes whenever the text changes.

The pair is what makes the STALE verdict possible: same identifier plus a
different content hash means evidence was gathered against a promise that has
since been rewritten, so the evidence no longer applies. See ADR-0002.

This module is pure. It imports nothing from `kept`.
"""

from __future__ import annotations

import hashlib
import re

# Bumped whenever the meaning of a serialised field changes. Consumers compare
# this before trusting a stored artefact.
SCHEMA_VERSION = 1

# Recorded alongside every hash so that a future change of algorithm cannot be
# mistaken for a change of meaning (REQ-3.6).
HASH_ALGORITHM = "sha256"

# Full digests are stored; only display truncates.
DISPLAY_HASH_LENGTH = 12

_WHITESPACE_RUN = re.compile(r"\s+")


def normalise_text(text: str) -> str:
    """Collapse whitespace runs to single spaces and strip the ends.

    Case is preserved. This is not cosmetic: the upper-case keyword rule makes
    case semantically significant, so lower-casing before hashing would erase
    the difference between the logical operator `AND` and the prose word "and"
    (see ADR-0001).
    """
    return _WHITESPACE_RUN.sub(" ", text).strip()


def content_hash(text: str) -> str:
    """Return the full hex digest of the whitespace-normalised text.

    Criteria differing only in line wrapping hash identically (REQ-3.4); any
    non-whitespace edit changes the digest (REQ-3.5).
    """
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()


def display_hash(digest: str) -> str:
    """Shorten a digest for human-facing output only."""
    return digest[:DISPLAY_HASH_LENGTH]


def requirement_id(number: int) -> str:
    """Build a requirement identifier such as `REQ-3`.

    Raises:
        ValueError: if `number` is not a positive integer, since requirement
            numbering is one-based and a zero would silently collide with an
            "unknown" sentinel.
    """
    if number < 1:
        msg = f"requirement number must be >= 1, got {number}"
        raise ValueError(msg)
    return f"REQ-{number}"


def criterion_id(requirement_number: int, position: int) -> str:
    """Build a criterion identifier such as `REQ-3.2`.

    Both components are one-based. `position` is the criterion's place within
    its own requirement, which is why inserting a criterion in requirement 3
    cannot disturb the identifiers in requirement 4 (REQ-3.2).
    """
    if position < 1:
        msg = f"criterion position must be >= 1, got {position}"
        raise ValueError(msg)
    return f"{requirement_id(requirement_number)}.{position}"
