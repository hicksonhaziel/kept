# kept

**Your spec is a list of promises. `kept` proves, per promise, which ones your code actually keeps — and it does not take a test suite's word for it.**

An agent writes the code and the tests in the same breath. The suite is green, coverage is high, so the work looks finished. But the agent authored both the implementation and its own oracle, so a green suite may only prove the code agrees with itself.

`kept` reads the acceptance criteria in your `.kiro/specs/*/requirements.md`, binds each one to the tests that claim to verify it, then **attacks those tests** to find out whether they actually constrain behaviour. It emits a commit-pinned evidence ledger with one verdict per criterion.

```
23 promises · 14 kept · 4 weak · 4 unproven · 1 broken
```

Offline. No API key. Deterministic. No language model anywhere in the verification path.

> **Status: in development.** This README documents what is built and working today. Anything not listed under "What works today" is not yet implemented, and `kept` will tell you so rather than pretend otherwise.

---

## Quickstart

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/). Nothing else — no account, no key, no network.

```bash
git clone https://github.com/hicksonhaziel/kept.git
cd kept
uv run kept parse
```

That parses `kept`'s own specification and prints every promise it found, with a stable identifier and content hash for each. The tool is dogfooded on itself, so its own spec is the first thing it reads.

For machine-readable output:

```bash
uv run kept parse --json
```

## What works today

| Capability | State |
|---|---|
| EARS parsing (all five patterns plus complex) | working |
| Stable criterion identifiers and content hashes | working |
| Extraction from `.kiro/specs/*/requirements.md` | working |
| Diagnostics with source spans | working |
| `kept parse`, human and JSON output | working |
| Bindings, coverage observation, mutation, verdicts | not yet implemented |

## The five verdicts

| Verdict | Meaning |
|---|---|
| **KEPT** | A bound oracle exists, passes, is non-vacuous, and every generated mutant on the criterion's covered lines was killed by that criterion's own bound tests |
| **WEAK** | The oracles pass, but at least one mutant survived them. The implementation can be silently broken and the criterion still reports success |
| **UNPROVEN** | No binding, no covered lines, or the oracle was skipped or is vacuous. Nothing was actually checked |
| **BROKEN** | A bound oracle fails, with a shrunk minimal counterexample where available |
| **STALE** | Recorded evidence refers to different criterion text or different code than the current commit |

### Why WEAK is stricter than it looks

A mutant counts as surviving if **the criterion's own bound tests** fail to kill it, even when some unrelated test elsewhere in the suite would have caught it. That is deliberate. The claim under audit is not "the suite is adequate", it is "*this criterion is independently verified*". Traceability is worthless if a criterion's verdict silently depends on tests that were never bound to it.

## Why this is not Kiro's property-based testing

Kiro ships spec correctness via property-based testing: it extracts properties from EARS acceptance criteria, generates tests, and links requirement to property to task. `kept` is not a reimplementation of that. It consumes it.

Kiro's own documentation is candid about three limits, and `kept` addresses exactly those:

| | Kiro's PBT | `kept` |
|---|---|---|
| Where it runs | IDE only, per its published capability matrix | CLI, CI, MCP |
| What it does | *generates* the oracle | *audits and enforces* the oracle |
| A too-weak property | documented as able to pass while behaviour is wrong | detected, as WEAK, via mutation |
| Enforcement | interactive | exit-code gate on regression |

Kiro generates the oracle. `kept` asks whether that oracle is worth anything, and blocks the merge when it is not. *(Kiro's documentation is paraphrased here; content was rephrased for compliance with licensing restrictions. See [kiro.dev/docs/specs/correctness](https://kiro.dev/docs/specs/correctness.md).)*

## Honest scope

- **Python and pytest only** in this release.
- `kept` produces **evidence, not proof.** It is not formal verification. A surviving mutant is a strong negative signal; a dead mutant is not a correctness guarantee.
- Criteria written with `SHOULD` or `MAY` are parsed and identified but marked advisory. A criterion that does not oblige the implementation cannot fairly be given a verdict.
- The grammar requires EARS keywords in **upper case**. This is what makes `WHEN a AND b` distinguishable from `WHEN a name and address`. A criterion in all lower case is reported with a diagnostic telling you what to capitalise, not silently misread.

## How Kiro was used

This project was built with Kiro, spec-first. The `.kiro/` directory is committed at the repository root and contains the real working history, not a retrofit.

- **Steering** (`.kiro/steering/`) — six files establishing the product vocabulary, the verdict taxonomy, the architecture, the conventions, and one non-negotiable rule: *no model in the verification path*. These were written before any implementation code, so every subsequent agent turn inherited them. One uses conditional `fileMatch` inclusion so that the rules for `fixtures/` apply only when working there.
- **Specs** (`.kiro/specs/`) — each component gets requirements in EARS, a design document, and a task list with every task tracing back to specific criteria.
- **A defect found by dogfooding** — the parser's own `requirements.md` broke the parser. REQ-1.1 enumerates the EARS keywords in order to specify how they are recognised, and the parser read those enumerated keywords as grammar. The fix was to honour a convention authors already follow: a backtick-quoted span is literal text. The spec, the design, and the tests were all updated. `docs/journal/` records this and everything like it.

## Development

```bash
uv sync --all-extras   # install
uv run pytest          # test
uv run ruff check .    # lint
uv run mypy            # type-check
```

## Third-party dependencies

| Package | Licence | Used for |
|---|---|---|
| [coverage](https://github.com/nedbat/coveragepy) | Apache-2.0 | per-test dynamic contexts |
| [libcst](https://github.com/Instagram/LibCST) | MIT / PSF | syntax-tree mutation |
| [pytest](https://github.com/pytest-dev/pytest) | MIT | executing bound oracles |
| [hypothesis](https://github.com/HypothesisWorks/hypothesis) | MPL-2.0 | property-test statistics and seeds |

The verification core itself is stdlib-only. No package in the tree is a model client, an HTTP client, or a telemetry package.

## Costs and limits

None. `kept` makes no network requests, calls no paid API, and requires no credentials. There is nothing to rate-limit.

## Licence

MIT.
