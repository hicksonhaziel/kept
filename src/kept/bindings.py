"""The criterion-to-oracle map. Human-owned, reviewable, committed."""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from kept.ids import SCHEMA_VERSION

BINDINGS_FILENAME = "bindings.toml"
KEPT_DIRECTORY = ".kept"


class Origin(StrEnum):
    """Where a binding came from."""

    ANNOTATION = "annotation"  # harvested from a @pytest.mark.verifies marker
    MANUAL = "manual"  # written by hand in bindings.toml


class BindingsError(ValueError):
    """Raised when a bindings file cannot be trusted."""


@dataclass(frozen=True, slots=True)
class Binding:
    """One criterion and the oracles that claim to verify it."""

    criterion: str
    oracles: tuple[str, ...]
    origin: Origin = Origin.ANNOTATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "criterion": self.criterion,
            "oracles": list(self.oracles),
            "origin": str(self.origin),
        }


@dataclass(frozen=True, slots=True)
class Unverifiable:
    """A criterion deliberately excluded from verdicts, with a stated reason.

    Recorded rather than silently ignored, so an exclusion is a visible choice a
    reviewer can challenge.
    """

    criterion: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {"criterion": self.criterion, "reason": self.reason}


@dataclass(frozen=True, slots=True)
class BindingSet:
    bindings: tuple[Binding, ...] = ()
    unverifiable: tuple[Unverifiable, ...] = ()

    def oracles_for(self, criterion: str) -> tuple[str, ...]:
        for binding in self.bindings:
            if binding.criterion == criterion:
                return binding.oracles
        return ()

    def is_unverifiable(self, criterion: str) -> bool:
        return any(entry.criterion == criterion for entry in self.unverifiable)

    @property
    def bound_criteria(self) -> frozenset[str]:
        return frozenset(binding.criterion for binding in self.bindings)

    def human_authored(self) -> BindingSet:
        """Only the parts of this set a person wrote.

        Annotation-derived entries in a bindings file are a generated view, not a
        source of truth. Treating them as input would let the file mask a deleted
        marker, which is exactly the kind of stale evidence kept exists to catch.
        """
        return BindingSet(
            bindings=tuple(b for b in self.bindings if b.origin is Origin.MANUAL),
            unverifiable=self.unverifiable,
        )

    @property
    def all_oracles(self) -> tuple[str, ...]:
        found: set[str] = set()
        for binding in self.bindings:
            found.update(binding.oracles)
        return tuple(sorted(found))

    def unbound(self, criteria: Iterable[str]) -> tuple[str, ...]:
        """Criteria with no oracle and no stated exclusion. These are UNPROVEN."""
        bound = self.bound_criteria
        return tuple(
            sorted(
                criterion
                for criterion in criteria
                if criterion not in bound and not self.is_unverifiable(criterion)
            )
        )

    def orphaned(self, criteria: Iterable[str]) -> tuple[str, ...]:
        """Bound criteria that no longer exist in the specification."""
        known = set(criteria)
        return tuple(sorted(self.bound_criteria - known))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "bindings": [binding.to_dict() for binding in self.bindings],
            "unverifiable": [entry.to_dict() for entry in self.unverifiable],
        }


def merge(discovered: BindingSet, manual: BindingSet) -> BindingSet:
    """Combine harvested and hand-written bindings.

    Manual entries win: a person overriding an annotation is the whole point of
    the file being reviewable.
    """
    by_criterion: dict[str, Binding] = {b.criterion: b for b in discovered.bindings}
    for binding in manual.bindings:
        by_criterion[binding.criterion] = binding

    unverifiable = {entry.criterion: entry for entry in discovered.unverifiable}
    unverifiable.update({entry.criterion: entry for entry in manual.unverifiable})

    return BindingSet(
        bindings=tuple(sorted(by_criterion.values(), key=_sort_key)),
        unverifiable=tuple(sorted(unverifiable.values(), key=_unverifiable_key)),
    )


def bindings_path(root: Path) -> Path:
    return root / KEPT_DIRECTORY / BINDINGS_FILENAME


def load(path: Path) -> BindingSet:
    """Read a bindings file. A missing file is an empty set, not an error."""
    if not path.is_file():
        return BindingSet()

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        msg = f"{path} is not valid TOML: {error}"
        raise BindingsError(msg) from error

    version = data.get("schema_version", SCHEMA_VERSION)
    if not isinstance(version, int) or version > SCHEMA_VERSION:
        msg = f"{path} declares schema_version {version!r}, which this kept cannot read"
        raise BindingsError(msg)

    parsed = tuple(_read_binding(entry, path) for entry in data.get("binding", []))
    excluded = tuple(_read_unverifiable(entry, path) for entry in data.get("unverifiable", []))
    return BindingSet(
        bindings=tuple(sorted(parsed, key=_sort_key)),
        unverifiable=tuple(sorted(excluded, key=_unverifiable_key)),
    )


def save(bindings: BindingSet, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(bindings), encoding="utf-8")


def dumps(bindings: BindingSet) -> str:
    """Render as TOML. Hand-rolled to keep the core free of a writer dependency."""
    lines = [
        "# Criterion to oracle map. kept verifies; it does not decide what a test",
        "# is supposed to prove.",
        "#",
        '# origin = "annotation"  harvested from a @pytest.mark.verifies marker.',
        "#                        Regenerated on every run and ignored as input, so",
        "#                        deleting a marker is never masked by this file.",
        '# origin = "manual"      written by hand. Authoritative, and overrides an',
        "#                        annotation for the same criterion.",
        "#",
        "# An [[unverifiable]] entry excludes a criterion from verdicts and must",
        "# state why, so the exclusion is a choice a reviewer can challenge.",
        "",
        f"schema_version = {SCHEMA_VERSION}",
    ]

    for binding in bindings.bindings:
        lines += [
            "",
            "[[binding]]",
            f'criterion = "{_escape(binding.criterion)}"',
            f'origin = "{_escape(str(binding.origin))}"',
            "oracles = [",
        ]
        lines += [f'  "{_escape(oracle)}",' for oracle in binding.oracles]
        lines.append("]")

    for entry in bindings.unverifiable:
        lines += [
            "",
            "[[unverifiable]]",
            f'criterion = "{_escape(entry.criterion)}"',
            f'reason = "{_escape(entry.reason)}"',
        ]

    return "\n".join(lines) + "\n"


def _read_binding(entry: object, path: Path) -> Binding:
    if not isinstance(entry, dict):
        msg = f"{path}: each [[binding]] must be a table"
        raise BindingsError(msg)

    criterion = entry.get("criterion")
    if not isinstance(criterion, str) or not criterion:
        msg = f"{path}: a [[binding]] is missing a criterion identifier"
        raise BindingsError(msg)

    raw_oracles = entry.get("oracles", [])
    if not isinstance(raw_oracles, list) or not all(isinstance(o, str) for o in raw_oracles):
        msg = f"{path}: oracles for {criterion} must be a list of test identifiers"
        raise BindingsError(msg)

    origin = entry.get("origin", str(Origin.MANUAL))
    try:
        parsed_origin = Origin(origin)
    except ValueError as error:
        allowed = ", ".join(str(o) for o in Origin)
        msg = f"{path}: origin {origin!r} for {criterion} must be one of: {allowed}"
        raise BindingsError(msg) from error

    return Binding(
        criterion=criterion,
        oracles=tuple(sorted(set(raw_oracles))),
        origin=parsed_origin,
    )


def _read_unverifiable(entry: object, path: Path) -> Unverifiable:
    if not isinstance(entry, dict):
        msg = f"{path}: each [[unverifiable]] must be a table"
        raise BindingsError(msg)

    criterion = entry.get("criterion")
    reason = entry.get("reason")
    if not isinstance(criterion, str) or not criterion:
        msg = f"{path}: an [[unverifiable]] entry is missing a criterion identifier"
        raise BindingsError(msg)
    if not isinstance(reason, str) or not reason.strip():
        msg = (
            f"{path}: {criterion} is marked unverifiable with no reason. "
            f"State why no test can cover it, so a reviewer can disagree."
        )
        raise BindingsError(msg)

    return Unverifiable(criterion=criterion, reason=reason)


def _criterion_key(criterion: str) -> tuple[int, int, str]:
    """Sort REQ-2.10 after REQ-2.9 rather than lexicographically."""
    body = criterion[4:] if criterion.startswith("REQ-") else criterion
    requirement, _, position = body.partition(".")
    try:
        return (int(requirement), int(position), criterion)
    except ValueError:
        return (10**9, 10**9, criterion)


def _sort_key(binding: Binding) -> tuple[int, int, str]:
    return _criterion_key(binding.criterion)


def _unverifiable_key(entry: Unverifiable) -> tuple[int, int, str]:
    return _criterion_key(entry.criterion)


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
