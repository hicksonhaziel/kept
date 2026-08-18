"""Mutants, and choosing which ones to run. Pure: no I/O."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from kept.attack.operators import Mutation

#: Default ceiling per criterion. The point is a trustworthy signal within a
#: demo-length run, not an exhaustive score, so the cap is deliberately low and
#: always recorded in the output.
DEFAULT_CAP = 12


@dataclass(frozen=True, slots=True)
class Mutant:
    """One change to one file."""

    path: str
    index: int
    line: int
    operator: str
    description: str

    @property
    def key(self) -> str:
        return f"{self.path}:{self.line}:{self.operator}:{self.index}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "operator": self.operator,
            "description": self.description,
            "key": self.key,
        }


@dataclass(frozen=True, slots=True)
class Assignment:
    """A mutant and the criteria whose covered lines it falls on."""

    mutant: Mutant
    criteria: tuple[str, ...]


def from_mutations(path: str, mutations: tuple[Mutation, ...]) -> tuple[Mutant, ...]:
    return tuple(
        Mutant(
            path=path,
            index=mutation.index,
            line=mutation.line,
            operator=mutation.operator,
            description=mutation.description,
        )
        for mutation in mutations
    )


def select(
    mutants_by_path: Mapping[str, tuple[Mutant, ...]],
    covered: Mapping[str, Mapping[str, tuple[int, ...]]],
    *,
    cap: int = DEFAULT_CAP,
) -> tuple[Assignment, ...]:
    """Choose mutants to run, scoped to what each criterion actually executes.

    Selection happens per criterion, then the results are grouped by mutant. That
    grouping is what makes the run affordable: several criteria often cover the
    same line, and one patched file can answer for all of them in a single test
    process.

    Args:
        mutants_by_path: Every available mutant, keyed by source path.
        covered: Per criterion, per path, the lines its passing oracles executed.
        cap: Maximum mutants to select per criterion.
    """
    chosen: dict[str, set[str]] = {}
    lookup: dict[str, Mutant] = {}

    for criterion in sorted(covered):
        per_path = covered[criterion]
        candidates: list[Mutant] = []
        for path, lines in sorted(per_path.items()):
            line_set = set(lines)
            candidates.extend(
                mutant
                for mutant in mutants_by_path.get(path, ())
                if mutant.line in line_set
            )

        candidates.sort(key=_ordering)
        for mutant in _spread(candidates, cap):
            lookup[mutant.key] = mutant
            chosen.setdefault(mutant.key, set()).add(criterion)

    return tuple(
        Assignment(mutant=lookup[key], criteria=tuple(sorted(chosen[key])))
        for key in sorted(chosen, key=lambda k: _ordering(lookup[k]))
    )


def _ordering(mutant: Mutant) -> tuple[str, int, str, int]:
    return (mutant.path, mutant.line, mutant.operator, mutant.index)


def _spread(candidates: list[Mutant], cap: int) -> list[Mutant]:
    """Take up to `cap` mutants, spread across distinct lines and operators.

    Taking the first `cap` in order would pile every mutant onto the first line or
    two of a function and say nothing about the rest. Round-robin over lines gives
    a criterion's whole covered region a chance to be probed.
    """
    if cap <= 0 or len(candidates) <= cap:
        return candidates

    buckets: dict[int, list[Mutant]] = {}
    for mutant in candidates:
        buckets.setdefault(mutant.line, []).append(mutant)

    taken: list[Mutant] = []
    depth = 0
    while len(taken) < cap:
        added = False
        for line in sorted(buckets):
            if depth < len(buckets[line]):
                taken.append(buckets[line][depth])
                added = True
                if len(taken) == cap:
                    break
        if not added:
            break
        depth += 1

    taken.sort(key=_ordering)
    return taken


def cache_key(*, source_hash: str, mutant: Mutant, oracles: tuple[str, ...]) -> str:
    """Identify a mutant run by everything that could change its outcome."""
    payload = "\n".join(
        [source_hash, mutant.path, str(mutant.index), mutant.operator, *sorted(oracles)]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
