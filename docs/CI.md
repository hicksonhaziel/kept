# Continuous integration

kept ships a composite action. It installs kept from the action's own checkout, so
the version that runs is the version you pinned — not whatever an index happens to
hold that day.

```yaml
- uses: hicksonhaziel/kept@v0.1.0
  with:
    root: .
    gate: no-regression
```

## Gates

Choose what breaks the build.

| Gate | Fails when | Use it |
|---|---|---|
| `none` | never | reporting only, first week |
| `no-regression` | a promise loses ground against the committed ledger | **default** — adoptable on day one |
| `no-broken` | any bound oracle fails | once nothing is BROKEN |
| `all-kept` | any promise is not KEPT | on a control fixture, or a codebase you have finished |

`no-regression` is the one that makes this usable on an existing project: today's
WEAK verdicts are reported rather than failed, and the build only breaks when a
promise that was verified stops being verified. It compares against the ledger you
committed, which is why committing it matters.

## Inputs

| Input | Default | Notes |
|---|---|---|
| `root` | `.` | project root |
| `spec` | discovered | one path per line, for projects without `.kiro/specs` |
| `tests` | whole suite | restrict collection |
| `source` | `.` | what coverage measures — point this at your package |
| `gate` | `no-regression` | see above |
| `cap` | `12` | mutants per promise |
| `threshold` | `1.0` | share required for KEPT |
| `python` | nearest venv | interpreter owning your test dependencies |
| `write` | `false` | write the ledger into the workspace |
| `summary` | `true` | append the verdict table to the job summary |

## Outputs

```yaml
- uses: hicksonhaziel/kept@v0.1.0
  id: kept
  with: { root: ., gate: no-regression }

- run: echo "${{ steps.kept.outputs.headline }}"
```

`headline`, `promises`, `kept`, `weak`, `unproven`, `broken`, `regressions`,
`ledger`.

## What kept's own CI does

Two jobs, both in [`ci.yml`](../.github/workflows/ci.yml):

```text
verify   lint → format → mypy --strict → pytest
         → kept parse            (can kept still read its own spec?)
         → kept verify --root .  (gate: no-regression, against its own ledger)
         → kept verify fixtures/slug          (gate: all-kept)
         → kept verify fixtures/refund_engine (gate: no-regression)
         → kept prompt REQ-1.1

action   runs this repository's own action against fixtures/slug
         and asserts its outputs
```

The control fixture is gated at `all-kept` deliberately: if an honest
implementation ever stops reaching KEPT, kept is crying wolf and the build should
say so. The demo fixture publishes real WEAK verdicts, so it is gated at
`no-regression` — the number is reported, not suppressed.

> [!TIP]
> Commit `.kept/ledger.json` and `EVIDENCE.md`. Without a committed ledger there is
> nothing for `no-regression` to compare against, and the gate silently has no
> teeth.

## Runtime

kept re-runs a promise's own tests once per mutant, so cost scales with test
*duration*, not test count.

| Project | Promises | Cold |
|---|---|---|
| `fixtures/slug` | 5 | under 2s |
| `fixtures/refund_engine` | 25 | ~10s |
| kept itself | 51 | 31.6s |

Millisecond unit tests are cheap. Database-backed tests at seconds each are not:
scope with `--tests`, point `--source` at your package, and lower `--cap`. Results
are cached under `.kept/cache/`, which is gitignored — a shared cache is not part of
the trust chain.
