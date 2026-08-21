"""The evidence ledger: a commit-pinned record the repository commits.

Deterministic by construction. Sorted keys, no wall-clock values, repository
relative paths. The same commit and the same settings produce a byte-identical
file, which is what lets a reader reproduce a published number.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kept.ids import SCHEMA_VERSION
from kept.verdict import Evidence, Judgement, Missed, Ruling, UnpinnedLine, Verdict

LEDGER_FILENAME = "ledger.json"
KEPT_DIRECTORY = ".kept"


class LedgerError(ValueError):
    """Raised when a ledger file cannot be trusted."""


@dataclass(frozen=True, slots=True)
class Settings:
    """The knobs that could change a verdict, recorded so a reader can reproduce it."""

    threshold: float
    cap: int
    seed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"threshold": self.threshold, "cap": self.cap, "seed": self.seed}


@dataclass(frozen=True, slots=True)
class Ledger:
    kept_version: str
    settings: Settings
    rulings: tuple[Ruling, ...] = ()
    unpinned: tuple[UnpinnedLine, ...] = ()
    excluded: tuple[tuple[str, str], ...] = ()
    sources: tuple[tuple[str, str], ...] = ()
    commit: str | None = None

    @property
    def counts(self) -> dict[str, int]:
        tally = {str(verdict): 0 for verdict in Verdict}
        for ruling in self.rulings:
            tally[str(ruling.verdict)] += 1
        return tally

    @property
    def promises(self) -> int:
        return len(self.rulings)

    def get(self, criterion: str) -> Ruling | None:
        for ruling in self.rulings:
            if ruling.criterion == criterion:
                return ruling
        return None

    def headline(self) -> str:
        counts = self.counts
        parts = [f"{self.promises} promises"]
        for verdict in Verdict:
            count = counts[str(verdict)]
            if count or verdict in {Verdict.KEPT, Verdict.WEAK}:
                parts.append(f"{count} {verdict}")
        return " · ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "kept_version": self.kept_version,
            "commit": self.commit,
            "settings": self.settings.to_dict(),
            "summary": {"promises": self.promises, **self.counts},
            "criteria": [ruling.to_dict() for ruling in self.rulings],
            "unpinned": [entry.to_dict() for entry in self.unpinned],
            "excluded": [
                {"criterion": criterion, "reason": reason} for criterion, reason in self.excluded
            ],
            "sources": dict(self.sources),
        }


@dataclass(frozen=True, slots=True)
class Drift:
    """How a stored ledger differs from current reality."""

    stale: tuple[str, ...] = ()
    vanished: tuple[str, ...] = ()
    added: tuple[str, ...] = ()
    changed_sources: tuple[str, ...] = ()

    @property
    def is_stale(self) -> bool:
        return bool(self.stale or self.vanished or self.added or self.changed_sources)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stale": list(self.stale),
            "vanished": list(self.vanished),
            "added": list(self.added),
            "changed_sources": list(self.changed_sources),
        }


@dataclass(frozen=True, slots=True)
class Regression:
    """A promise that lost ground against the committed ledger."""

    criterion: str
    was: str
    now: str

    def to_dict(self) -> dict[str, Any]:
        return {"criterion": self.criterion, "was": self.was, "now": self.now}


#: Verdict quality, worst to best. A move down this ladder is a regression.
_RANK = {
    str(Verdict.BROKEN): 0,
    str(Verdict.STALE): 1,
    str(Verdict.UNPROVEN): 2,
    str(Verdict.WEAK): 3,
    str(Verdict.KEPT): 4,
}


def build(
    judgement: Judgement,
    *,
    kept_version: str,
    settings: Settings,
    sources: Mapping[str, str],
    commit: str | None = None,
) -> Ledger:
    return Ledger(
        kept_version=kept_version,
        settings=settings,
        rulings=tuple(sorted(judgement.rulings, key=lambda r: criterion_order(r.criterion))),
        unpinned=tuple(
            sorted(judgement.unpinned, key=lambda u: (u.path, u.line, u.operator, u.description))
        ),
        excluded=judgement.excluded,
        sources=tuple(sorted(sources.items())),
        commit=commit,
    )


def dumps(ledger: Ledger) -> str:
    return json.dumps(ledger.to_dict(), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def ledger_path(root: Path) -> Path:
    return root / KEPT_DIRECTORY / LEDGER_FILENAME


def save(ledger: Ledger, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(ledger), encoding="utf-8")


def load(path: Path) -> Ledger | None:
    """Read a stored ledger. A missing file is absence, not an error."""
    if not path.is_file():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        msg = f"{path} is not valid JSON: {error}"
        raise LedgerError(msg) from error

    version = payload.get("schema_version")
    if not isinstance(version, int) or version > SCHEMA_VERSION:
        msg = f"{path} declares schema_version {version!r}, which this kept cannot read"
        raise LedgerError(msg)

    settings = payload.get("settings") or {}
    return Ledger(
        kept_version=str(payload.get("kept_version", "unknown")),
        settings=Settings(
            threshold=float(settings.get("threshold", 1.0)),
            cap=int(settings.get("cap", 0)),
            seed=int(settings.get("seed", 0)),
        ),
        rulings=tuple(_read_ruling(entry) for entry in payload.get("criteria", [])),
        excluded=tuple(
            (entry["criterion"], entry["reason"]) for entry in payload.get("excluded", [])
        ),
        sources=tuple(sorted((payload.get("sources") or {}).items())),
        commit=payload.get("commit"),
    )


def drift(stored: Ledger, *, hashes: Mapping[str, str], sources: Mapping[str, str]) -> Drift:
    """Find where a stored ledger no longer describes the current repository.

    Same identifier with a different content hash means the promise was reworded,
    so the recorded evidence was gathered against a different promise. A changed
    source hash means the evidence was gathered against different code. Either way
    the entry is stale: it exists, but it no longer applies.
    """
    recorded = {ruling.criterion: ruling.content_hash for ruling in stored.rulings}

    reworded = (
        criterion
        for criterion, digest in recorded.items()
        if hashes.get(criterion, digest) != digest
    )
    stale = sorted(reworded, key=criterion_order)
    vanished = sorted((c for c in recorded if c not in hashes), key=criterion_order)
    added = sorted((c for c in hashes if c not in recorded), key=criterion_order)
    stored_sources = dict(stored.sources)
    changed = sorted(
        path for path, digest in stored_sources.items() if sources.get(path, digest) != digest
    )

    return Drift(
        stale=tuple(c for c in stale if c not in vanished),
        vanished=tuple(vanished),
        added=tuple(added),
        changed_sources=tuple(changed),
    )


def regressions(stored: Ledger, fresh: Ledger) -> tuple[Regression, ...]:
    """Promises that lost ground. This is what the gate fails on.

    A gate on absolute quality would make kept unadoptable on an existing
    codebase. A gate on regression can be turned on the day you install it.
    """
    found: list[Regression] = []
    for ruling in fresh.rulings:
        previous = stored.get(ruling.criterion)
        if previous is None:
            continue
        was, now = str(previous.verdict), str(ruling.verdict)
        if _RANK.get(now, 0) < _RANK.get(was, 0):
            found.append(Regression(criterion=ruling.criterion, was=was, now=now))
    return tuple(sorted(found, key=lambda r: criterion_order(r.criterion)))


def criterion_order(criterion: str) -> tuple[int, int, str]:
    """Sort REQ-2.10 after REQ-2.9 rather than lexicographically."""
    body = criterion.removeprefix("REQ-")
    requirement, _, position = body.partition(".")
    try:
        return (int(requirement), int(position), criterion)
    except ValueError:
        return (10**9, 10**9, criterion)


def source_hashes(root: Path, paths: Iterable[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(set(paths)):
        candidate = root / path
        if candidate.is_file():
            hashes[path] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    return hashes


def current_commit(root: Path) -> str | None:
    """The commit the ledger describes, or None outside a repository."""
    try:
        # Fixed argv, no shell.
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _read_ruling(entry: Mapping[str, Any]) -> Ruling:
    raw = entry.get("evidence") or {}
    mutants = raw.get("mutants") or {}
    evidence = Evidence(
        oracles=tuple((item["nodeid"], item["status"]) for item in raw.get("oracles", [])),
        covered=tuple(
            (path, tuple(lines)) for path, lines in sorted((raw.get("covered") or {}).items())
        ),
        probed=int(mutants.get("probed", 0)),
        killed=int(mutants.get("killed", 0)),
        discriminating=int(mutants.get("discriminating", 0)),
        unpinned=int(mutants.get("unpinned", 0)),
        missed=tuple(
            Missed(
                path=item["path"],
                line=int(item["line"]),
                operator=item["operator"],
                description=item["description"],
                caught_by=tuple(item.get("caught_by", ())),
            )
            for item in raw.get("missed", [])
        ),
    )
    return Ruling(
        criterion=entry["criterion"],
        content_hash=entry.get("content_hash", ""),
        verdict=Verdict(entry["verdict"]),
        evidence=evidence,
        reason=entry.get("reason"),
    )
