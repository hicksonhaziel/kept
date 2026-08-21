# Implementation Plan

> **Status: complete.** Every task below was implemented between 2026-08-14 and
> 2026-08-19, and re-verified against the implementation on 2026-08-21. The
> component is dogfooded: `kept parse` reads this very specification, and
> `tests/test_self_hosting.py` asserts it parses with zero error diagnostics and
> the expected criterion count.
>
> **One deviation from the plan as written.** Task 3.1 places `Diagnostic` and the
> code registry in `src/kept/ears/errors.py`. They live in
> `src/kept/diagnostics.py` instead, because diagnostics are not specific to the
> EARS grammar — the loader, the markdown scanner and the configuration reader all
> emit them. `ears/errors.py` holds the grammar's diagnostic *factories*, so each
> code is worded identically wherever it is raised. The codes are exactly as
> specified: E001, E002, W001, W002, W003.
>
> Scope note: this specification covers the front end only — parse and the IR.
> `bind`, `observe`, `attack` and the verdict rules were built without a
> specification of their own, which is recorded honestly rather than backfilled.

- [x] 1. Establish the identity primitives
- [x] 1.1 Implement text normalisation and content hashing in `src/kept/ids.py`
  - Collapse whitespace runs to single spaces, strip the ends, preserve case
  - SHA-256 hex digest, full digest stored, twelve characters for display
  - Expose the algorithm name as a constant and a schema version
  - _Requirements: REQ-3.3, REQ-3.4, REQ-3.5, REQ-3.6, REQ-3.7_

- [x] 1.2 Implement structural identifier construction
  - `REQ-<n>` for requirements, `REQ-<n>.<i>` for criteria, both one-based
  - Pure functions with no knowledge of documents
  - _Requirements: REQ-3.1, REQ-3.2_

- [x] 2. Define the intermediate representation
- [x] 2.1 Write the IR dataclasses in `src/kept/ir.py`
  - `Span`, `Condition`, `Clause`, `Criterion`, `Requirement`, `SpecDocument`
  - Frozen, slotted, tuple-valued sequence fields
  - `EarsPattern`, `ClauseKind`, `Modality`, `LogicalOperator`, `Severity` as string enums
  - _Requirements: REQ-2.8, REQ-3.7_

- [x] 2.2 Implement pattern classification and normativity as pure functions
  - Classification from the clause tuple alone
  - Normativity from the modality alone
  - _Requirements: REQ-2.1, REQ-2.2, REQ-2.3, REQ-2.4, REQ-2.5, REQ-2.6, REQ-2.9, REQ-2.10_

- [x] 2.3 Implement deterministic JSON serialisation of the IR
  - Sorted keys, no timestamps, repository-relative POSIX paths
  - _Requirements: REQ-6.1, REQ-6.3, REQ-6.5, REQ-6.6_

- [x] 3. Build the diagnostics facility
- [x] 3.1 Implement `Diagnostic` and the diagnostic code registry in `src/kept/ears/errors.py`
  - Stable codes `E001`, `E002`, `W001`, `W002`, `W003`
  - Optional span, severity, and a message phrased as corrective action
  - _Requirements: REQ-5.2, REQ-5.3, REQ-5.4, REQ-5.6_

- [x] 4. Build the lexer
- [x] 4.1 Define `TokenKind` and `Token` in `src/kept/ears/tokens.py`
  - _Requirements: REQ-1.3, REQ-1.5_

- [x] 4.2 Implement the lexer in `src/kept/ears/lexer.py`
  - Structural keywords recognised only in upper case
  - Character offsets on every token, original spelling preserved
  - Comma as its own separator token, exactly one EOF token
  - _Requirements: REQ-1.1, REQ-1.2, REQ-1.3, REQ-1.4, REQ-1.5, REQ-1.6_

- [x] 4.3 Implement the lower-case modality warning
  - Emit `W001` when a lower-case modality appears and no upper-case one does
  - _Requirements: REQ-1.7_

- [x] 4.4 Write lexer tests
  - Include the case rule for `AND` used as operator versus prose
  - _Requirements: REQ-1.1, REQ-1.2, REQ-1.3, REQ-1.4, REQ-1.5, REQ-1.6, REQ-1.7_

- [x] 5. Build the parser
- [x] 5.1 Implement clause parsing in `src/kept/ears/parser.py`
  - All four clause openers, optional comma separators, spans per clause
  - `E002` for an empty clause body
  - _Requirements: REQ-2.2, REQ-2.3, REQ-2.4, REQ-2.5, REQ-2.6, REQ-2.14, REQ-2.15_

- [x] 5.2 Implement condition and conjunction parsing
  - Split on upper-case `AND`/`OR` only, record operator and conjuncts
  - Lower-case conjunctions yield a single conjunct
  - _Requirements: REQ-2.11, REQ-2.12_

- [x] 5.3 Implement response parsing
  - Optional `THEN` consumed as a separator and excluded from the response
  - Subject consumed up to the modality; all seven modalities including negations
  - `E001` when no modality is found
  - _Requirements: REQ-2.7, REQ-2.8, REQ-2.13_

- [x] 5.4 Assemble criteria with pattern, normativity, hash, and span
  - _Requirements: REQ-2.1, REQ-2.9, REQ-2.10, REQ-3.1, REQ-3.3_

- [x] 5.5 Write parser tests
  - One per pattern, complex ordering, every modality, both error codes
  - _Requirements: REQ-2.1 through REQ-2.15_

- [x] 6. Build markdown extraction
- [x] 6.1 Implement the line scanner in `src/kept/markdown.py`
  - Explicit state machine, per-line byte offsets, fenced code block skipping
  - _Requirements: REQ-4.3, REQ-4.4, REQ-4.9_

- [x] 6.2 Implement multi-line criterion joining and user story capture
  - _Requirements: REQ-4.5, REQ-4.7_

- [x] 6.3 Implement requirement numbering including the unnumbered fallback
  - Ordinal position plus `W003` when a heading carries no number
  - _Requirements: REQ-4.8_

- [x] 6.4 Record file path and offsets for every extracted criterion
  - _Requirements: REQ-4.6_

- [x] 6.5 Write markdown extraction tests
  - Multi-line criteria, unnumbered headings, numbered lists inside code fences,
    numbered items outside any criteria heading
  - _Requirements: REQ-4.3 through REQ-4.9, REQ-5.5_

- [x] 7. Build spec discovery and the loader
- [x] 7.1 Implement discovery of `.kiro/specs/*/requirements.md` in `src/kept/loader.py`
  - Specification name from the containing directory, deterministic ordering
  - _Requirements: REQ-4.1, REQ-4.2, REQ-6.2_

- [x] 7.2 Convert absolute paths to repository-relative POSIX paths at the boundary
  - _Requirements: REQ-6.3_

- [x] 8. Expose the parser through the CLI
- [x] 8.1 Implement `kept parse` in `src/kept/cli.py`
  - Human-readable table of identifier, pattern, modality, and hash
  - `--json` for machine-readable output with sorted keys
  - Exit code 2 on usage error; `sys.exit` called only here
  - _Requirements: REQ-6.4, REQ-6.5_

- [x] 9. Verify span accuracy and self-hosting
- [x] 9.1 Write a span round-trip test
  - Slicing the source file with each recorded span reproduces the raw text
  - _Requirements: REQ-4.6, REQ-2.15_

- [x] 9.2 Parse this component's own `requirements.md` as a fixture
  - Assert zero error-severity diagnostics and assert the criterion count
  - _Requirements: REQ-5.1, REQ-6.1_

- [x] 9.3 Write a determinism test
  - Two parses yield equal IR and byte-identical JSON
  - _Requirements: REQ-6.1_

- [x] 10. Record the decisions
- [x] 10.1 Write ADR-0001 on the upper-case keyword rule
  - State the ambiguity, the rule, and the accepted consequences
- [x] 10.2 Write ADR-0002 on structural identifiers versus content hashes
  - Explain why identity is positional and change detection is hash-based, and
    how the pair makes the `STALE` verdict possible
