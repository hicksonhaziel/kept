# Requirements Document

## Introduction

`kept` cannot make claims about promises it has misread. Every verdict, every
binding, and every line of the ledger is downstream of this component, so the
parser is the foundation the rest of the tool stands on.

This spec covers the front end: turning a `requirements.md` file into a typed,
immutable intermediate representation in which every acceptance criterion has a
stable identity, a classified EARS pattern, structured clauses, and a
byte-accurate span back to its source.

Two design commitments shape the requirements below.

**A real grammar, not pattern matching.** A regular expression over requirement
text cannot distinguish the logical operator in "WHEN the cart is empty AND the
user is anonymous" from the ordinary conjunction in "WHEN the user submits a name
and email address". `kept` resolves this with a lexer that recognises structural
keywords only in upper case, feeding a recursive-descent parser. The rule is
mechanical, documented, and testable.

**Malformed input is a diagnostic, not a crash.** Real specifications contain
prose, headings, tables, and half-finished sentences. One unparseable line must
never prevent the other two hundred criteria from being verified.

## Requirements

### Requirement 1: Lexical analysis of criterion text

**User Story:** As a developer whose requirements mix EARS keywords with ordinary
prose, I want the tokeniser to distinguish structure from description
unambiguously, so that my criteria are never silently misread.

#### Acceptance Criteria

1. WHEN the lexer encounters the word `WHEN`, `WHILE`, `IF`, `WHERE`, `THEN`, `SHALL`, `SHOULD`, `MAY`, `MUST`, `NOT`, `AND`, or `OR` written entirely in upper case THEN the system SHALL emit a structural keyword token for that word.
2. WHEN the lexer encounters any of those same words in lower case or mixed case THEN the system SHALL emit an ordinary word token, because prose conjunctions must not be mistaken for grammar.
3. THE lexer SHALL record the start offset and end offset of every token as a character index into the original criterion text.
4. WHEN the lexer encounters a comma THEN the system SHALL emit a separator token rather than attaching the comma to an adjacent word.
5. THE lexer SHALL preserve the original spelling of every word token without normalising case, so that reports can quote the source exactly.
6. WHEN the lexer reaches the end of the input THEN the system SHALL emit exactly one end-of-input token.
7. WHEN the criterion text contains a lower-case modality such as "shall" and contains no upper-case modality THEN the system SHALL report a diagnostic advising that EARS modalities are written in upper case.
8. WHEN a span of text is enclosed in backtick characters THEN the system SHALL emit it as a single ordinary word token even where the enclosed text is an upper-case keyword or contains spaces, because an author quoting a keyword is describing it rather than using it.

### Requirement 2: Recursive-descent parsing of EARS patterns

**User Story:** As a developer auditing traceability, I want each criterion
classified by its EARS pattern with its parts separated, so that `kept` can
reason about triggers and conditions rather than treating a requirement as an
opaque string.

#### Acceptance Criteria

1. WHEN a criterion consists of a subject, a modality, and a response with no preceding clause THEN the system SHALL classify it as the ubiquitous pattern.
2. WHEN a criterion begins with a `WHEN` clause followed by a response THEN the system SHALL classify it as the event-driven pattern and SHALL record the clause as the trigger.
3. WHEN a criterion begins with a `WHILE` clause followed by a response THEN the system SHALL classify it as the state-driven pattern and SHALL record the clause as the state.
4. WHEN a criterion begins with an `IF` clause followed by a response THEN the system SHALL classify it as the unwanted-behaviour pattern and SHALL record the clause as the condition.
5. WHEN a criterion begins with a `WHERE` clause followed by a response THEN the system SHALL classify it as the optional-feature pattern and SHALL record the clause as the feature.
6. WHEN a criterion contains two or more leading clauses THEN the system SHALL classify it as the complex pattern and SHALL preserve every clause in source order.
7. THE parser SHALL treat an optional `THEN` keyword between the final clause and the subject as a separator and SHALL exclude it from the recorded response.
8. THE parser SHALL record the modality of every criterion as one of `SHALL`, `SHALL NOT`, `SHOULD`, `SHOULD NOT`, `MAY`, `MUST`, or `MUST NOT`.
9. WHEN the modality is `SHALL`, `SHALL NOT`, `MUST`, or `MUST NOT` THEN the system SHALL mark the criterion as normative.
10. WHEN the modality is `SHOULD`, `SHOULD NOT`, or `MAY` THEN the system SHALL mark the criterion as advisory, because a criterion that does not oblige the implementation cannot be held to a verdict.
11. WHEN a clause body contains an upper-case `AND` or `OR` between two phrases THEN the system SHALL record the individual conjuncts and the operator joining them.
12. WHEN a clause body contains only a lower-case "and" or "or" THEN the system SHALL record the body as a single conjunct.
13. IF a criterion contains no recognisable modality THEN THE system SHALL report a diagnostic identifying the criterion as unparseable and SHALL continue processing the remaining criteria.
14. IF a criterion contains a clause keyword with an empty body THEN THE system SHALL report a diagnostic naming the offending keyword.
15. THE parser SHALL record a source span for every clause it produces.

### Requirement 3: Stable identity and change detection

**User Story:** As a developer whose ledger must survive edits to the
specification, I want every criterion to carry an identity that is stable across
unrelated changes and a hash that changes when its meaning changes, so that
recorded evidence can be matched to the promise it was gathered for.

#### Acceptance Criteria

1. THE system SHALL assign every criterion an identifier of the form REQ-<requirement number>.<criterion position>.
2. WHEN a criterion is inserted, removed, or reordered within a requirement THEN the system SHALL leave the identifiers of criteria in other requirements unchanged.
3. THE system SHALL compute a content hash for every criterion using SHA-256 over its whitespace-normalised text.
4. WHEN two criteria differ only in surrounding whitespace or line wrapping THEN the system SHALL compute the same content hash for both.
5. WHEN the wording of a criterion changes in any way that alters a non-whitespace character THEN the system SHALL compute a different content hash.
6. THE system SHALL record the hash algorithm name alongside every hash, so that a future change of algorithm cannot be mistaken for a change of meaning.
7. THE system SHALL include a schema version in every serialised representation of the intermediate representation.

### Requirement 4: Extraction from specification documents

**User Story:** As a developer using Kiro's spec workflow, I want `kept` to read
the `requirements.md` files I already have, so that adopting the tool costs me no
new bookkeeping.

#### Acceptance Criteria

1. THE system SHALL locate specifications by reading every `requirements.md` file directly beneath a directory in `.kiro/specs`.
2. THE system SHALL derive the name of each specification from the name of its containing directory.
3. WHEN a heading matches the form "Requirement <number>" optionally followed by a colon and a title THEN the system SHALL begin a new requirement using that number and title.
4. WHEN a numbered list item appears beneath an "Acceptance Criteria" heading THEN the system SHALL extract that item as one criterion.
5. WHEN a criterion spans more than one line in the source THEN the system SHALL join the continuation lines into a single criterion text.
6. THE system SHALL record the file path, start offset, and end offset of every extracted criterion.
7. WHEN a user story line is present in a requirement THEN the system SHALL record it as prose without attempting to parse it as a criterion.
8. WHEN a requirement heading carries no number THEN the system SHALL assign the requirement its ordinal position among the requirements in that document.
9. THE system SHALL ignore prose, tables, and code blocks that do not appear as numbered items beneath an Acceptance Criteria heading.

### Requirement 5: Diagnostics

**User Story:** As a developer with an imperfect specification, I want problems
reported with enough precision to fix them, so that a single bad line does not
block a whole verification run.

#### Acceptance Criteria

1. WHEN the system cannot parse a criterion THEN the system SHALL record a diagnostic and SHALL continue with the remaining criteria.
2. THE system SHALL give every diagnostic a stable machine-readable code.
3. THE system SHALL include a source span in every diagnostic that refers to a specific location.
4. THE system SHALL phrase every diagnostic message to state the corrective action, not merely the symptom.
5. WHERE a diagnostic concerns a criterion that was nonetheless partially understood THE system SHALL still emit the criterion so that its identity remains stable.
6. THE system SHALL classify each diagnostic by severity as either an error or a warning.

### Requirement 6: Deterministic and inspectable output

**User Story:** As a judge or reviewer reproducing a published result, I want the
parser's output to be identical on my machine, so that the numbers in the
repository can be trusted.

#### Acceptance Criteria

1. WHEN the same document is parsed twice THEN the system SHALL produce identical output both times.
2. THE system SHALL order criteria by requirement number and then by criterion position in all output.
3. THE system SHALL express every file path in output as a repository-relative path using forward slashes.
4. THE system SHALL provide a command that prints the parsed criteria with their identifiers, patterns, and content hashes.
5. WHERE machine-readable output is requested THE system SHALL emit JSON with sorted object keys.
6. THE system SHALL exclude wall-clock timestamps from parser output, because a timestamp would make two identical parses appear different.
