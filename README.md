# kept

**Your spec is a list of promises. `kept` proves, per promise, which ones your code actually keeps — and it does not take a test suite's word for it.**

An offline, deterministic CLI that reads your acceptance criteria, binds each one to the tests that claim to verify it, then breaks the code those tests guard to find out whether they actually notice.

```
25 promises · 4 kept · 21 weak
```

> **This README is a placeholder.** Full documentation is being written. What is here is accurate; it is just not complete.

## Try it

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

## Scope

- **Python and pytest only.** Not JavaScript, not Go.
- Needs written acceptance criteria: Kiro's `.kiro/specs/*/requirements.md`, or any markdown file passed with `--spec`.
- Produces **evidence, not proof.** A killed mutant is not a guarantee of correctness.

## Licence

MIT.
