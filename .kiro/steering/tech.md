# Technology constraints

## Runtime

- **Python 3.13** is the pinned development and CI version (`.python-version`).
  The package supports 3.11+. The pin exists because `coverage.py` dynamic
  contexts are load-bearing for criterion-scoped coverage, and 3.13 is the
  best-trodden version for that tracer path.
- **uv** is the only supported toolchain. Every documented command is `uv run …`
  so a judge gets a byte-identical environment from a clean clone with no
  virtualenv ceremony.

## Dependencies

The verification core is **stdlib-only**. Third-party packages appear only in
adapters at the edges:

| Package | Used for | Layer |
|---|---|---|
| `coverage` | per-test dynamic contexts → criterion ↔ line map | adapter |
| `libcst` | concrete-syntax-tree mutation with formatting preserved | adapter |
| `pytest` | executing bound oracles in the target project | adapter (subprocess) |
| `hypothesis` | reading property-test statistics and seeds | adapter |
| `mcp` | optional MCP server | optional extra |

Rules for adding a dependency:

- It must not require network access at runtime.
- It must not be a model client, an HTTP client, or a telemetry package.
- Pin a lower bound; never an open upper bound that lets CI drift.
- If the core needs it, the core is wrong. Push it to an adapter.

## Determinism requirements

Restated from `verification-integrity.md` because they constrain
implementation choices directly:

- Sort collections before serialising. `set` and `dict` iteration order must
  never reach an artefact.
- Seed every random choice and record the seed in the ledger.
- Use a derandomised Hypothesis profile for ledger runs.
- Repository-relative POSIX paths only, in every artefact.
- No wall-clock values inside a compared verdict payload.

## Command surface

```
kept parse     # show parsed criteria and IDs (diagnostic)
kept bind      # inspect and validate bindings
kept verify    # the main event: produce verdicts and write the ledger
kept report    # render EVIDENCE.md, badge, HTML evidence map
kept prompt    # emit a remediation brief for one criterion
kept demo      # run the whole story on the bundled fixture, offline
kept serve     # MCP server (optional extra)
```

`kept verify` exit codes are a contract, not an implementation detail:

| Code | Meaning |
|---|---|
| 0 | Gate satisfied |
| 1 | Gate violated (e.g. a criterion regressed from KEPT) |
| 2 | Usage or configuration error |
| 3 | Internal error; ledger not written |

## Artefacts and where they live

| Path | Committed | Purpose |
|---|---|---|
| `.kept/bindings.toml` | yes | human-owned criterion → oracle map |
| `.kept/ledger.json` | yes | commit-pinned verdicts; the repo attests to itself |
| `.kept/cache/` | no | mutation result cache, keyed by (mutant hash, test-set hash) |
| `EVIDENCE.md` | yes | rendered human-readable ledger |

Every serialised artefact carries a `schema_version`. Changing a field's
meaning without bumping it is a defect.

## Performance budget

The demo lives or dies on runtime. `kept verify` on the bundled fixture must
finish in **under 30 seconds** on a laptop. This is why mutants are scoped to a
criterion's covered lines and executed against only that criterion's bound
tests, and why results are cached. Benchmark this as soon as the mutation engine
exists, not at the end.
