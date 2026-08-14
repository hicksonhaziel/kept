# Design Document

## Overview

The front end is a three-stage pipeline, each stage pure and independently
testable:

```
requirements.md ──▶ markdown.py ──▶ RawCriterion[] ──▶ ears/ ──▶ Criterion[]
    (bytes)          extraction        (text+span)       grammar     (typed IR)
```

`loader.py` is the only component that touches the filesystem. Everything below
it receives strings and returns data. This is what allows the parser test suite
to run with no fixtures on disk and no I/O.

## The keyword-case rule

The central design decision. EARS structural keywords are recognised **only when
written entirely in upper case**.

Consider two criteria:

- `WHEN the cart is empty AND the user is anonymous THEN the system SHALL ...`
- `WHEN the user submits a name and email address THEN the system SHALL ...`

The first `AND` is a logical operator joining two conditions. The second `and`
is ordinary English inside a single condition. No amount of regular expression
cleverness distinguishes them reliably, and guessing wrong changes the meaning of
the requirement. Case is the signal EARS authors already use, so the parser
treats it as normative.

Consequences, accepted deliberately:

- `if`, `when`, `and`, `or`, `not`, `then` in lower case are ordinary words. A
  response clause may therefore contain the word "if" freely.
- A criterion written in lower case throughout will fail to parse. This is
  reported as a diagnostic with a message telling the author to capitalise the
  modality (REQ-1.7), rather than being silently accepted with a wrong reading.
- `THE` is deliberately **not** a keyword. Subject parsing consumes words up to
  the modality, so "THE system", "the system", and "the Refund Service" all work
  without special cases.

### Backtick spans are literal

The case rule alone is not sufficient, and this component's own requirements
document proved it. REQ-1.1 enumerates the EARS keywords in order to specify how
they are recognised. Written bare, the parser read those enumerated keywords as
grammar: a criterion *about* `WHEN` was parsed as a criterion *using* `WHEN`
twice, producing a spurious empty-clause diagnostic.

The fix is to honour a convention authors already follow. A span delimited by
backticks is emitted as one ordinary word token, whatever it contains — upper
case, spaces, or both. This makes `` `SHALL NOT` `` a single word rather than a
modality followed by a negation, and it lets a specification describe its own
notation without the parser mistaking description for use.

An unterminated backtick is treated as an ordinary character rather than an
error, because a stray backtick in prose should not cost an author a criterion.

Both rules are recorded as ADR-0001.

## Grammar

```ebnf
criterion     ::= clause_list? response
clause_list   ::= clause ( ","? clause )*
clause        ::= ( "WHEN" | "WHILE" | "IF" | "WHERE" ) condition
condition     ::= conjunct ( ( "AND" | "OR" ) conjunct )*
conjunct      ::= word+
response      ::= "THEN"? subject modality predicate
subject       ::= word+                     (* up to, not including, modality *)
modality      ::= ( "SHALL" | "SHOULD" | "MAY" | "MUST" ) "NOT"?
predicate     ::= token+                    (* to end of input *)
```

Recursive descent with one token of lookahead. No backtracking is required: every
production is decidable from the current token, because clause openers and
modalities are disjoint keyword sets.

Clause bodies are terminated by the next structural keyword or by end of input,
which is why the lexer must run to completion before parsing rather than
tokenising lazily.

### Pattern classification

Derived from the clause list after parsing, not decided during it:

| Clauses | Pattern |
|---|---|
| none | `UBIQUITOUS` |
| one `WHEN` | `EVENT_DRIVEN` |
| one `WHILE` | `STATE_DRIVEN` |
| one `IF` | `UNWANTED_BEHAVIOUR` |
| one `WHERE` | `OPTIONAL_FEATURE` |
| two or more | `COMPLEX` |

Classification is a pure function of the clause tuple, so it is tested directly
without going through the parser.

### Normativity

Modality determines whether a criterion can carry a verdict at all:

| Modality | Normative |
|---|---|
| `SHALL`, `SHALL NOT`, `MUST`, `MUST NOT` | yes |
| `SHOULD`, `SHOULD NOT`, `MAY` | no — advisory |

Advisory criteria are parsed, identified, and hashed like any other, but the
verdict engine will exclude them from headline promise counts. A criterion that
does not oblige the implementation cannot fairly be called broken (REQ-2.10).

## Intermediate representation

All IR types are frozen slotted dataclasses. Sequence fields are tuples so that
values remain hashable and ordering is explicit.

```
SpecDocument
  name: str                       # from the containing directory
  path: str                       # repository-relative, POSIX separators
  requirements: tuple[Requirement, ...]

Requirement
  id: str                         # "REQ-3"
  number: int
  title: str | None
  user_story: str | None
  criteria: tuple[Criterion, ...]

Criterion
  id: str                         # "REQ-3.2"
  pattern: EarsPattern
  clauses: tuple[Clause, ...]
  subject: str
  modality: Modality
  predicate: str
  is_normative: bool
  raw_text: str
  content_hash: str               # sha256, hex, truncated for display only
  hash_algorithm: str             # "sha256"
  span: Span

Clause
  kind: ClauseKind                # TRIGGER | STATE | UNWANTED | FEATURE
  condition: Condition
  span: Span

Condition
  text: str
  conjuncts: tuple[str, ...]
  operator: LogicalOperator | None    # AND | OR | None

Span
  source: str                     # repository-relative path
  start: int                      # character offset
  end: int
```

`Span` offsets are character indices into the source **file**, not into the
extracted criterion text, so a report can point at the exact line of
`requirements.md` that made the promise. `markdown.py` computes the base offset
of each criterion and `ears/` offsets are rebased onto it.

## Identity and hashing

**Identifier.** `REQ-<requirement number>.<position within requirement>`, both
one-based. Requirement numbers come from the heading when present, otherwise from
ordinal position. Positions are assigned in source order.

The identifier is deliberately **structural, not content-derived**. Rewording a
criterion must not change its identity, or the ledger would lose the history of
the promise every time its wording was improved. Detecting the reword is the
content hash's job, and that separation is what makes the `STALE` verdict
possible: same ID plus different hash means the evidence no longer applies.

**Content hash.** SHA-256 over the criterion text with runs of whitespace
collapsed to single spaces and leading and trailing whitespace stripped. Case is
**preserved**, because the keyword-case rule makes case semantically
significant — lower-casing before hashing would erase the difference between a
logical operator and a prose conjunction.

The full hex digest is stored; only display truncates, to twelve characters.

## Diagnostics

Diagnostics are values, not exceptions. `ParseResult` carries both the criteria
that were understood and the problems encountered, so one malformed line cannot
abort a run.

| Code | Severity | Condition |
|---|---|---|
| `E001` | error | no recognisable modality; criterion unparseable |
| `E002` | error | clause keyword present with an empty body |
| `W001` | warning | lower-case modality found and no upper-case modality present |
| `W002` | warning | numbered item found outside any Acceptance Criteria heading |
| `W003` | warning | requirement heading carries no number; ordinal position assigned |

Where a criterion is partially understood it is still emitted, so that its
identity stays stable across the fix (REQ-5.5).

## Markdown extraction

A line-oriented scanner holding a small explicit state machine, tracking the
byte offset of every line so spans stay accurate.

States: `SEEKING_REQUIREMENT` → `IN_REQUIREMENT` → `IN_CRITERIA`.

- Requirement heading: any ATX heading whose text matches
  `Requirement\s+(\d+)` with an optional `:` and title. A heading without a
  number gets its ordinal position plus a `W003`.
- `#### Acceptance Criteria` (at any heading depth) enters `IN_CRITERIA`.
- A numbered item `^\s*\d+[.)]\s+` begins a criterion. Subsequent indented,
  non-blank, non-item lines are continuations and are joined with a single space.
- `**User Story:**` is captured as prose.
- Fenced code blocks are tracked and skipped entirely, so a numbered list inside
  a fence is never mistaken for a criterion.
- Any other content is ignored.

Deliberately **not** a general Markdown parser. The grammar of a Kiro
requirements document is narrow, a real Markdown dependency would pull an AST we
do not need, and character-accurate offsets are easier to guarantee with a line
scanner than to recover from a syntax tree.

## Determinism

- Output is ordered by requirement number, then criterion position (REQ-6.2).
- JSON serialisation uses sorted keys and no timestamps (REQ-6.5, REQ-6.6).
- Paths are made repository-relative with forward slashes at the boundary in
  `loader.py`, so no absolute path can reach an artefact (REQ-6.3).
- Nothing in the front end reads a clock or a random source.

## Testing strategy

- **Lexer:** token kinds, offsets, the case rule, comma separation, single EOF.
- **Parser:** one test per EARS pattern; complex ordering; `THEN` handling;
  every modality; conjunction extraction for upper case versus lower case; both
  error codes.
- **Classification and normativity:** tested as pure functions on constructed
  clause tuples, without the parser.
- **Identity:** insertion and reordering leave other requirements untouched;
  whitespace-only differences hash identically; single-character edits do not.
- **Markdown:** multi-line criteria, unnumbered headings, fenced code blocks
  containing numbered lists, numbered items outside a criteria heading.
- **Span accuracy:** for each extracted criterion, slicing the original file with
  the recorded span returns text equal to the criterion's raw text.
- **Self-hosting:** this document's own `requirements.md` parses with zero
  errors, and the count of extracted criteria is asserted. The spec is the
  parser's first fixture.
- **Determinism:** parsing twice yields equal IR and byte-identical JSON.
