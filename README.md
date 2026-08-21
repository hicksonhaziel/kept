# kept

**Your spec is a list of promises. `kept` proves, per promise, which ones your code actually keeps — and it does not take a test suite's word for it.**

An offline, deterministic CLI that reads your acceptance criteria, binds each one to the tests that claim to verify it, then breaks the code those tests guard to find out whether they actually notice.

```
25 promises · 4 kept · 21 weak
```

## kept, on kept

kept audits its own promises in CI and publishes the result, weak spots included:

```
51 promises · 4 kept · 45 weak · 2 unproven
```

See [EVIDENCE.md](EVIDENCE.md). Two of those promises have no test at all and say
so; forty-five have tests that pass without noticing a change kept made to the code
they cover. That is an uncomfortable number to publish, and it is the number.

Pointing kept at itself for the first time also found two defects that had made the
tool's own output untrustworthy — mutants that were never imported, and mutants that
were counted as killed without ever running. Before the fix kept reported 26 of its
own promises as KEPT. That figure was fiction. See
[the journal](docs/journal/2026-08-21.md).

## This is not Kiro's property-based testing

The resemblance is the most obvious objection to the project, so here it is
directly. Kiro *generates* the oracle. kept *audits and enforces* it.

| | Kiro's correctness features | kept |
|---|---|---|
| What it produces | a property-based test for code you point it at | a verdict per acceptance criterion, and the evidence behind it |
| Where it runs | in the IDE, while you work | in CI, on every commit, and locally |
| Who writes the oracle | Kiro | you already did; kept never writes one |
| What it asks | "what property should hold here?" | "would the tests bound to this promise notice if the code broke?" |
| How it decides | a model proposes the property | mutation of the covered lines, then the criterion's own tests. No model, at any point |
| What you keep | a test file | a committed, commit-pinned ledger and `EVIDENCE.md` |
| Failure it catches | missing test cases | tests that pass while the implementation is broken, and criteria nothing verifies |

They compose: Kiro writes the property, kept tells you whether that property
actually constrains the implementation, and fails the build when it stops doing so.
kept consumes Kiro's requirement-to-test links as input — the `@verifies` marker is
how a criterion and a test are connected, whoever wrote the test.

If you already have tests, kept needs no new ones to start. It will tell you which
of your existing tests are load-bearing and which are decoration.

### And compared with tools that check documentation claims

There is a family of tools that read prose promises — a README, a changelog — and
exercise the running product against them. That is a different question, and a
useful one. It asks *does the deployed product still do what the docs say*. kept
asks *would your test suite notice if it stopped*.

The practical difference is what a reader needs to reproduce the answer: those
tools need a live target, a browser runner, and usually credentials. kept needs the
repository. No network, no account, no API key, and the same ledger byte-for-byte
on any machine.

## Documentation

| | |
|---|---|
| [EVIDENCE.md](EVIDENCE.md) | kept's own verdicts, regenerated in CI |
| [Threat model](docs/threat-model.md) | every way a verdict could be wrong, including two that were |
| [ADRs](docs/adr/) | the decisions, including the ones that are uncomfortable |
| [Journal](docs/journal/) | the build log: what went wrong, and how it was found |
| [Releasing](docs/release.md) | how a version reaches PyPI |

## Install it in your own project

kept has to be installed into the environment your tests run in, because the
`@pytest.mark.verifies` marker is registered by a pytest plugin kept ships. So it is
a dev dependency, not a standalone tool:

```bash
uv add --dev kept-cli
# or: pip install kept-cli
```

Then, once:

```bash
kept parse            # the criteria kept can read
# mark the tests that verify each one: @pytest.mark.verifies("REQ-1.1")
kept bind --write     # writes .kept/bindings.toml to review and commit
kept verify --write   # writes .kept/ledger.json and EVIDENCE.md to commit
```

After that, forever:

```bash
kept verify
```

`--root` defaults to the current directory and specifications are discovered from
`.kiro/specs/*/requirements.md`, so a Kiro project needs no flags at all.

### Configure it once

If your project does need non-default settings, state them in `.kept/config.toml`
and stop repeating them:

```toml
version = 1
spec = ["docs/acceptance.md"]   # projects without .kiro/specs
source = "myapp"                # what coverage should measure
tests = "tests/unit"
gate = "no-regression"
threshold = 1.0
cap = 12
```

Precedence is explicit flag, then this file, then the built-in default. An unknown
key or a value of the wrong type stops the run with exit 2 rather than being
ignored: a misspelled `treshold` that quietly did nothing would be worse than a
refusal. The settings that can change a verdict — `threshold` and `cap` — are still
recorded in the ledger, so a published number stays reproducible without this file.

## Try it on the bundled fixtures

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/). No API key, no account, no network.

```bash
git clone https://github.com/hicksonhaziel/kept.git
cd kept
uv sync --all-extras

# a Kiro project, specs discovered automatically
uv run kept verify --root fixtures/refund_engine

# a plain Python project with no .kiro directory at all
uv run kept verify --root fixtures/slug --spec ACCEPTANCE.md
```

## Commands

```
kept parse     the promises kept can read, with identifiers and content hashes
kept bind      which test claims to verify each promise
kept observe   which lines each promise's tests actually execute
kept attack    which breakages those tests fail to notice
kept verify    the verdict on every promise, plus the evidence ledger
kept prompt    a remediation brief for one promise, rendered from the ledger
```

`kept prompt REQ-1.1` restates the recorded evidence for one promise and names the
change that would answer it — for a human, or for an agent to act on:

```bash
uv run kept verify --root fixtures/refund_engine --write
uv run kept prompt REQ-1.1 --root fixtures/refund_engine
```

It reads the ledger, runs no tests, reaches no verdict, and consults no model. It
is a suggestion, and it says so in its own text. Only `kept verify` moves a
verdict. See [ADR-0005](docs/adr/0005-the-brief-is-outside-the-verification-path.md).

## Use it from an agent

`kept serve` speaks [MCP](https://modelcontextprotocol.io) over stdio, so an agent
can read the evidence and act on it:

```bash
uv sync --extra mcp
uv run kept serve --root fixtures/refund_engine
```

| Tool | Does |
|---|---|
| `list_promises` | every criterion, with the verdict recorded for it |
| `read_ledger` | the committed ledger and the evidence behind each verdict |
| `remediation_brief` | what one promise's evidence says, and the change it asks for |
| `verify` | run the pipeline; the only tool that can move a verdict |

The root and the specification are fixed by the flags you start the server with,
not chosen by the client, so an agent cannot point kept at a different project. The
first three tools are read-only. No model participates in a verdict, in this path
or any other.

## Use it in CI

```yaml
- uses: hicksonhaziel/kept@v0
  with:
    root: .
    gate: no-regression
```

The gate defaults to `no-regression`, which is adoptable on an existing codebase on
day one: today's WEAK verdicts are reported, not failed, and the build breaks only
when a promise loses ground against the committed ledger. Use `all-kept` once you
are clean, or `no-broken` in between.

Outputs: `headline`, `promises`, `kept`, `weak`, `unproven`, `broken`,
`regressions`, `ledger`. The verdict table is appended to the job summary. The exit
status is kept's own contract: 0 gate satisfied, 1 gate violated, 2 usage error, 3
internal error.

kept's own CI runs this action against the fixtures in this repository, so the
action is covered by the same evidence as the tool.

## Scope

- **Python and pytest only.** Not JavaScript, not Go.
- Needs written acceptance criteria: Kiro's `.kiro/specs/*/requirements.md`, or any markdown file passed with `--spec`.
- Produces **evidence, not proof.** A killed mutant is not a guarantee of correctness.

## Licence

MIT.
