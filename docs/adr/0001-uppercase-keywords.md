# ADR-0001: EARS keywords are recognised only in upper case

**Status:** accepted
**Date:** 2026-08-14

## Context

`kept` must read acceptance criteria written in EARS. Two criteria that look
nearly identical mean different things:

```
WHEN the cart is empty AND the user is anonymous THEN the system SHALL redirect
WHEN the user submits a name and email address   THEN the system SHALL validate
```

The first `AND` is a logical operator joining two separate conditions. The second
`and` is ordinary English inside one condition. Getting this wrong changes the
meaning of the requirement, and a verdict engine built on a misread requirement is
worse than useless.

No regular expression distinguishes these reliably. Neither does a word list:
"and", "if", "when", and "then" all appear constantly in normal requirement prose.

## Decision

Structural keywords are recognised **only when written entirely in upper case**.
The keywords are `WHEN`, `WHILE`, `IF`, `WHERE`, `THEN`, `SHALL`, `SHOULD`, `MAY`,
`MUST`, `NOT`, `AND`, `OR`.

Additionally, a span delimited by backticks is always ordinary text, whatever it
contains.

## Consequences

Accepted:

- Lower-case `if`, `and`, `then` are ordinary words. Requirement prose can use
  them freely.
- A criterion written in lower case throughout will not parse. It gets a `W001`
  diagnostic naming the word to capitalise, rather than being accepted with a
  wrong reading.
- `THE` is deliberately *not* a keyword. Subject parsing consumes words up to the
  modality, so "THE system", "the system", and "the Refund Service" all work with
  no special cases.
- An unterminated backtick degrades to an ordinary word. A stray backtick in
  prose should not cost an author a criterion.

Rejected alternatives:

- **Heuristic disambiguation** (part-of-speech tagging, a model). Non-deterministic
  and unauditable, which violates the no-model rule in
  `.kiro/steering/verification-integrity.md`.
- **Requiring one condition per clause.** Correct in theory, but it would reject
  the majority of real specifications.

## The backtick rule was found by dogfooding

This component's own `requirements.md` broke this component's own parser.

REQ-1.1 enumerates the EARS keywords in order to specify how they are recognised.
Written bare, the parser read those enumerated keywords as grammar: a criterion
*about* `WHEN` was parsed as a criterion *using* `WHEN` twice, producing a
spurious empty-clause diagnostic.

The fix honours a convention authors already follow. Quoting a keyword in
backticks now means "I am describing this, not using it". This also makes
`` `SHALL NOT` `` a single word rather than a modality plus a negation.

Recorded because it is a good illustration of why the tool is dogfooded: the
defect was invisible from the implementation and obvious from the artefact.
