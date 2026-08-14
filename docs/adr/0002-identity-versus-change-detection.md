# ADR-0002: Identity is structural, change detection is content-based

**Status:** accepted
**Date:** 2026-08-14

## Context

The ledger records evidence against a criterion, and it must survive edits to the
specification. Two things are needed, and they pull in opposite directions:

1. A criterion needs an identity stable enough that its history persists when the
   wording is improved.
2. `kept` needs to detect when a criterion's meaning has changed, so that evidence
   gathered against the old wording is not silently reported as if it still
   applied.

A single identifier cannot do both. A content-derived identifier changes on every
reword, discarding history. A purely positional identifier never changes, so
rewording goes undetected.

## Decision

Use both, for separate purposes.

**Identity is structural.** `REQ-3.2` is the second criterion of the third
requirement. It is derived from position, not content, and is unaffected by
rewording.

**Change detection is content-based.** A SHA-256 digest over the criterion's
whitespace-normalised text. The algorithm name is stored alongside it, so a future
change of algorithm cannot be mistaken for a change of meaning.

Normalisation collapses whitespace runs and strips the ends. It does **not**
lower-case, because ADR-0001 makes case semantically significant: lower-casing
would erase the difference between the operator `AND` and the prose word "and".

## Consequences

The pair is what makes the `STALE` verdict possible:

| Identifier | Content hash | Meaning |
|---|---|---|
| same | same | evidence still applies |
| same | different | criterion was reworded — evidence is `STALE` |
| absent | — | criterion was deleted |
| new | — | criterion was added, and is `UNPROVEN` until bound |

Accepted costs:

- Reordering criteria *within* one requirement shifts their identifiers.
  Acceptable: reordering is rare, and the alternative is losing history on every
  reword, which is common.
- Renumbering a requirement heading shifts every identifier beneath it. The
  `W003` diagnostic pushes authors to number headings explicitly for this reason.
- A criterion whose wording changes but whose meaning does not still reports
  `STALE`. The tool is deliberately conservative: it reports that evidence needs
  rechecking rather than deciding for itself that a reword was cosmetic.

Rejected alternative: **content-addressed identity with rename detection by
similarity.** It needs a similarity threshold, which is a heuristic, which is a
guess. Under `.kiro/steering/verification-integrity.md` a guess has no place in
the verification path.
