# Code and process conventions

## Typing

- Full annotations on every function, including private helpers. `mypy --strict`
  passes with no `# type: ignore` unless the ignore carries a comment naming the
  upstream cause.
- IR types are `@dataclass(frozen=True, slots=True)`. The IR is immutable;
  transformations return new values.
- Prefer `tuple[...]` over `list[...]` in IR fields so values stay hashable and
  ordering is explicit.
- Use `StrEnum` for values that appear in serialised artefacts, so the wire
  format is readable and stable.
- `from __future__ import annotations` at the top of every module.

## Errors and diagnostics

- Library code raises; it never prints and never exits. Only `cli.py` calls
  `sys.exit`.
- Parse problems are **diagnostics**, not exceptions. A malformed criterion must
  not abort a run over 200 good ones. Collect diagnostics with source spans and
  report them alongside results.
- Every diagnostic carries a stable machine-readable code (`E001`) plus a
  message that says what to do about it, not merely what went wrong.
- Exception types live close to their layer: `ears/errors.py` for grammar
  problems.

## Naming

Follow the vocabulary in `product.md` exactly: criterion, promise, oracle,
binding, evidence, ledger, verdict. Do not introduce "requirement" where
"criterion" is meant, or "check" where "oracle" is meant. The words are the
product.

## Comments and docstrings

Keep the code lean. Long rationale belongs in `docs/adr/` and `docs/journal/`,
not in the middle of a module.

- Module docstring: one or two lines saying what the module is for.
- Function docstring: one line. Add `Args:` only where a parameter has a
  non-obvious contract.
- Inline comments: only where a reader would otherwise "tidy" the code and break
  it. A comment that restates the line below it is noise.
- When a design decision needs explaining, write the ADR and point at it in one
  short line. Do not inline the argument.

The test is whether the file reads like code or like an essay. It should read like
code.

## Tests

- `pytest`. No test touches the network. No test depends on wall-clock time.
- Name tests for the behaviour asserted, not the function called:
  `test_uppercase_and_is_a_logical_operator_but_lowercase_and_is_prose`.
- Bind kept's own tests to its own criteria with the `@verifies` marker, since
  kept is dogfooded and publishes its own ledger.
- Property tests use a derandomised profile in CI.
- A bug fix starts with a failing test that reproduces it.

## Commits

- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`,
  `spec:` (for `.kiro/specs` changes), `adr:`.
- Reference the criterion when a commit implements one: `feat(ears): parse
  complex multi-clause criteria (REQ-1.6)`.
- Commit `.kiro/` changes as their own commits so the spec history is legible as
  a workflow record. The git history is submission evidence; treat it as a
  deliverable.
- Small, honest commits over tidy rewrites. Do not rewrite history to look
  cleaner than the work was.

## Documentation duties that ride along with code

- A new verdict rule or scoring decision requires an ADR in `docs/adr/`.
- A new CLI flag requires a README update in the same commit.
- Any deliberate limitation gets written down in the honest-scope section rather
  than left for a judge to discover.
