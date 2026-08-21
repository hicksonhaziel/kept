<div align="center">

# kept

### Promises, proven.

**Per-criterion verification evidence for agent-written code.**

[Quickstart](docs/QUICKSTART.md) · [Verdicts](docs/VERDICTS.md) · [Commands](docs/COMMANDS.md) · [CI](docs/CI.md) · [Agents & MCP](docs/AGENTS.md) · [Threat model](docs/THREAT-MODEL.md) · [Public evidence](EVIDENCE.md)

</div>

kept reads your acceptance criteria, binds each one to the tests that claim to verify it, breaks the code those tests guard, and records — per criterion — whether they noticed. Parsing, binding, observation, mutation, and the verdict rules are deterministic Python; no model participates in the verification path.

> [!IMPORTANT]
> **Truthful public status:** kept 0.1.0 is published on PyPI and installs cleanly from a fresh environment. It publishes its own ledger in CI, and that ledger currently reads 4 kept · 45 weak · 2 unproven of 51 promises. It has been run against three projects: this repository and its two bundled fixtures. No claim is made about large codebases, no verdict is a proof of correctness, and two defects that made kept's own output untrustworthy were found and fixed on 2026-08-21 — both are documented rather than quietly patched.

## Why kept

An agent writes the implementation and its tests in the same breath. The suite is green, coverage is high, and the work looks finished — but the same author produced both the code and its oracle, so a green suite may only prove the code agrees with itself.

| Property | kept behaviour |
|---|---|
| Per-promise verdicts | One of KEPT, WEAK, UNPROVEN, BROKEN, STALE for every normative criterion |
| Oracle-strength evidence | Mutates the lines a criterion's own tests execute, then reruns only those tests |
| Human-owned mapping | Bindings are authored and reviewed by people, in a committed file kept never rewrites silently |
| No model in the path | Not to classify, not to summarise, not behind a flag. A verdict backed by a model is an opinion |
| Deterministic | Same commit, same seed, same ledger, byte for byte. Repository-relative paths, no timestamps in the payload |
| Offline | No network, no account, no API key, at any point |
| Self-attesting | kept publishes its own verdicts, weak spots included, regenerated in CI |

## What a run looks like

```console
$ kept verify
  REQ-1.1    KEPT          9/9
  REQ-1.2    WEAK          6/7   1 of 7 detectable breakages went unnoticed
      missed  refund.py:122  <= to <   (caught by REQ-1.3)
  REQ-1.4    UNPROVEN        -   no oracle claims to verify this promise

25 promises · 4 kept · 20 weak · 1 unproven
```

`WEAK` is the verdict that earns the tool: those tests passed, and they would have passed anyway. `REQ-1.3`'s tests catching the same change is the proof it was detectable.

## Pipeline

```text
.kiro/specs/*/requirements.md
   │
   ├── parse ──────── EARS grammar → typed IR, stable IDs, content hashes
   │
   ├── bind ───────── @pytest.mark.verifies markers → .kept/bindings.toml
   │
   ├── observe ────── pytest under per-test coverage → criterion ↔ line map
   │
   ├── attack ─────── libcst mutants on covered lines, in a temporary worktree
   │                  rerun ONLY that criterion's own bound tests
   │
   └── rule ───────── pure function: evidence → verdict
                          │
                          ▼
              .kept/ledger.json · EVIDENCE.md · badge
```

`parse`, `bind` and `rule` are pure. `observe` and `attack` are adapters at the edge. The rule engine is unit-tested with hand-built evidence and no I/O, because a verdict you cannot test without running a suite is a verdict you cannot trust. See [Commands](docs/COMMANDS.md) for the stage-by-stage surface.

## Install

```bash
uv add --dev kept-cli     # or: pip install kept-cli
```

> [!WARNING]
> Install it into the environment your tests run in. The `@pytest.mark.verifies` marker comes from a pytest plugin kept ships via an entry point; a global-only install leaves your project's pytest not knowing the marker exists, and `--strict-markers` will then fail on every one.

Then, once:

```bash
kept parse            # which criteria kept can read
kept bind --write     # after marking tests; writes .kept/bindings.toml to review
kept verify --write   # writes .kept/ledger.json and EVIDENCE.md to commit
```

After that, forever: `kept verify`. In a Kiro project no flags are needed — `--root` defaults to the working directory and specs are discovered. Anything else belongs in [`.kept/config.toml`](docs/CONFIGURATION.md).

## Try it without installing anything

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

```bash
git clone https://github.com/hicksonhaziel/kept.git && cd kept
uv sync --all-extras

uv run kept verify --root fixtures/refund_engine               # a Kiro project
uv run kept verify --root fixtures/slug --spec ACCEPTANCE.md    # no .kiro at all
uv run kept prompt REQ-1.1 --root fixtures/refund_engine        # what to do about a WEAK
```

## kept, on kept

```
51 promises · 4 kept · 45 weak · 2 unproven
```

Two promises have no test at all and say so. Forty-five have tests that pass without noticing a change kept made to the code they cover. That is an uncomfortable number to publish and it is the number: [EVIDENCE.md](EVIDENCE.md).

Pointing kept at itself for the first time also found two defects in its own verification path — mutants that were never imported, and mutants counted as killed without ever running. Before the fix, kept called 26 of its own promises KEPT. That figure was fiction. The post-mortem is in [the journal](docs/journal/2026-08-21.md); [ADR-0006](docs/adr/0006-cross-scope-detectability.md) explains why most of the remaining 45 are honest.

## Documentation

| | |
|---|---|
| [Quickstart](docs/QUICKSTART.md) | install, bind, verify — five minutes |
| [Verdicts](docs/VERDICTS.md) | the five verdicts, and the asymmetry behind WEAK |
| [Commands](docs/COMMANDS.md) | every command and flag, and the exit-code contract |
| [Configuration](docs/CONFIGURATION.md) | `.kept/config.toml`, so `kept verify` stays the whole command |
| [CI](docs/CI.md) | the action, the four gates, runtime |
| [Agents & MCP](docs/AGENTS.md) | `kept serve`, the four tools, Kiro hooks |
| [Comparison](docs/COMPARISON.md) | why this is not Kiro's property-based testing |
| [Threat model](docs/THREAT-MODEL.md) | every way a verdict could be wrong, including two that were |
| [ADRs](docs/adr/INDEX.md) | the decisions, including the uncomfortable ones |
| [Journal](docs/journal/) | the build log: what broke, and how it was found |
| [Releasing](docs/RELEASE.md) | how a version reaches PyPI |

## Scope

- **Python and pytest only.** Not JavaScript, not Go.
- Needs written acceptance criteria — Kiro's `.kiro/specs/*/requirements.md`, or any markdown file passed with `--spec`.
- Criteria must carry a normative modality (`SHALL`, `MUST`). `SHOULD` and `MAY` parse but are advisory and carry no verdict.
- A criterion no test could reasonably automate belongs in the bindings file as an explicit exclusion with a reason, not left silently unbound.
- Produces **evidence, not proof**.

## Licence

[MIT](LICENSE).
