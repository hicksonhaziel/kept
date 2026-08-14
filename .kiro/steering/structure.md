# Repository structure and architecture

## Shape: functional core, imperative shell

The verdict pipeline is a pure function. Everything that touches the filesystem,
spawns a process, or reads a clock lives at the edge and is injected.

```
parse  →  bind  →  observe  →  attack  →  rule
```

- `parse`, `bind`, `rule` are **pure**: data in, data out, no I/O, no clock, no
  randomness that is not passed in explicitly.
- `observe` and `attack` are **adapters**: they run pytest, read coverage
  databases, rewrite syntax trees. They return plain data structures.
- The rule engine must be testable with hand-built inputs and zero I/O. If you
  cannot unit-test a verdict without running pytest, the layering is wrong.

## Layout

```
src/kept/
  ir.py              # typed intermediate representation; no I/O
  ids.py             # stable criterion IDs and content hashing; pure
  ears/
    tokens.py        # token kinds and Token
    lexer.py         # source text → tokens; pure
    parser.py        # recursive descent → IR; pure
    errors.py        # diagnostics with source spans
  markdown.py        # requirements.md → raw criteria with spans; pure
  loader.py          # spec discovery + parse orchestration (thin adapter)
  bindings.py        # .kept/bindings.toml read/validate; criterion → oracles
  observe/           # adapters: pytest run, coverage contexts, hypothesis stats
  attack/            # adapters: libcst operators, mutant selection, execution
  rule.py            # pure: evidence → verdict
  ledger.py          # schema, serialisation, diffing, staleness detection
  report/            # EVIDENCE.md, badge, HTML
  cli.py             # argparse entry point; the only place that calls sys.exit
tests/               # mirrors src/kept
fixtures/            # sample projects under audit; deliberately imperfect
docs/
  adr/               # architecture decision records
  journal/           # daily build log: what the agent got wrong, how it was corrected
.kiro/
  steering/
  specs/
  hooks/
```

## Dependency direction

`cli` → `loader`/`report` → `rule`/`ledger` → `ir`/`ids`

Arrows never reverse. Specifically:

- `ir.py` and `ids.py` import nothing from `kept` except each other.
- `rule.py` imports no adapter and no third-party package.
- `ears/` never reads a file. It receives strings.
- Only `cli.py` calls `sys.exit`. Library code raises.

## Source spans everywhere

Every criterion, clause, and diagnostic carries a byte-accurate span back to its
origin file. This is what lets the report link a verdict to the exact line of
`requirements.md` that made the promise. Do not drop spans for convenience; they
are re-derived only at great cost.

## Testing conventions

- Unit tests mirror module paths: `tests/ears/test_parser.py`.
- The rule engine is tested with constructed evidence, never by running a suite.
- Parser tests assert on the full IR, including spans, not just a happy-path field.
- `kept`'s own specs live in `.kiro/specs/` and its own tests carry `@verifies`
  annotations, because `kept` is dogfooded on itself and publishes the result.
- Fixtures under `fixtures/` are excluded from lint, type-checking, and coverage.
  They are subjects, not source.
