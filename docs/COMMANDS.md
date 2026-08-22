# Commands

Seven commands. In a Kiro project every one of them runs with no flags: `--root`
defaults to the working directory and specifications are discovered from
`.kiro/specs/*/requirements.md`.

| Command | Does | Reaches a verdict? |
|---|---|---|
| `kept parse` | prints the criteria kept understood, with IDs and content hashes | no |
| `kept bind` | harvests `@verifies` markers, reports what is bound and what is not | no |
| `kept observe` | runs the suite under per-test coverage, shows the lines each promise executes | no |
| `kept attack` | mutates those lines and reports which oracles fail to notice | no — facts only |
| `kept verify` | the whole pipeline, one verdict per promise, writes the ledger | **yes** |
| `kept prompt` | a remediation brief for one promise, rendered from the ledger | no |
| `kept report` | renders the ledger as `EVIDENCE.md`, a badge, and an HTML evidence map | no |
| `kept serve` | MCP server over stdio for an agent | only through `verify` |

The pipeline is `parse → bind → observe → attack → rule`. The first four commands
each stop after their own stage, so you can inspect any layer in isolation.

## Shared flags

| Flag | Applies to | Default |
|---|---|---|
| `--root PATH` | all | current directory |
| `--spec PATH` | all but `parse` | discovered from `.kiro/specs` |
| `--tests PATH` | bind, observe, attack, verify, serve | whole suite |
| `--source PATH` | observe, attack, verify, serve | `.` |
| `--python PATH` | bind, observe, attack, verify, serve | active venv, else nearest `.venv` |
| `--json` | parse, bind, observe, attack, verify | human-readable output |

`--spec` is repeatable. Anything here can live in
[`.kept/config.toml`](CONFIGURATION.md) instead.

## kept verify

```bash
kept verify [--write] [--gate GATE] [--threshold RATIO] [--cap N]
            [--workers N] [--timeout SECONDS] [--no-cache] [--show-unpinned N]
```

| Flag | Default | Notes |
|---|---|---|
| `--write` | off | writes `.kept/ledger.json`, `EVIDENCE.md`, `.kept/badge.svg` |
| `--gate` | `no-regression` | `none`, `no-regression`, `no-broken`, `all-kept` |
| `--threshold` | `1.0` | share of detectable breakages required for KEPT |
| `--cap` | `12` | mutants per promise |
| `--workers` | `8` | parallel test processes |
| `--timeout` | `10.0` | seconds per mutant; a timeout counts as noticed |
| `--no-cache` | off | ignore and do not write `.kept/cache/` |
| `--show-unpinned` | `10` | how many unpinned lines to list |

> [!NOTE]
> `--threshold` and `--cap` are recorded in the ledger, because both change what a
> verdict means. Two ledgers are comparable only if they agree.

## kept bind

```bash
kept bind [--write]
```

`--write` merges harvested markers over any hand-written entries and saves
`.kept/bindings.toml` for review. Markers win over the file for the same criterion,
so deleting a marker cannot be masked by a stale entry.

Exits 1 when a promise is unbound, a binding is orphaned, or a marker is malformed —
each of those is a traceability gap rather than a crash.

## kept prompt

```bash
kept prompt REQ-1.1
```

Reads the committed ledger. Runs no tests, reaches no verdict, consults no model.
Says so in its own output, because a brief travels away from the tool that made it.

## kept report

```bash
kept report [--html PATH] [--open]
```

Renders what the ledger already records — no tests, no verdict, nothing changed.
Writes `EVIDENCE.md`, `.kept/badge.svg`, and `.kept/report.html`.

The evidence map is one self-contained file: no CDN font, no external stylesheet, no
script pointing anywhere. kept claims to work offline, and a report that fetched a
typeface would break that claim the first time someone opened it on a plane.

Each breakage a promise missed is shown as a diff of the exact line, red for what
was there and green for what kept put in its place. Those lines are **recomputed**
from the source by the same operators, then checked against the content hash the
ledger recorded: a file that has changed since gets no diff rather than a plausible
one.

`--open` opens the file in your browser. `/` focuses the filter, `Escape` clears it.

## kept serve

```bash
kept serve            # needs the mcp extra: uv add --dev "kept-cli[mcp]"
```

See [Agents & MCP](AGENTS.md).

## Exit codes

A contract, not an implementation detail.

| Code | Meaning |
|---|---|
| `0` | gate satisfied |
| `1` | gate violated — a promise regressed, or a diagnostic-level gate failed |
| `2` | usage or configuration error |
| `3` | internal error; **no ledger was written** |

The distinction that matters in CI: `1` means kept ran and you did not like the
answer. `2` means kept never got as far as an answer.
