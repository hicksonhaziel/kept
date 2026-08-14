# kept — product definition

## One sentence

Your spec is a list of promises. `kept` proves, per promise, which ones your code
actually keeps — and it does not take a test suite's word for it.

## The problem

An agent writes code and a test suite in the same breath. The suite is green and
coverage is high, so the work looks finished. But the agent authored both the
implementation and its own oracle, so a green suite may only prove that the code
agrees with itself. Two failure modes matter:

1. **Memorised behaviour.** The implementation returns the values the tests
   expect, without implementing the rule. A hard-coded lookup table keyed to the
   fixtures passes every test.
2. **Vacuous oracles.** The test exists, is bound to a requirement, and passes,
   but constrains nothing — no assertion, a precondition so tight that almost no
   input survives it, or an invariant that is true of any implementation.

Coverage cannot see either one. Both are invisible to the agent that produced
them. `kept` exists to make them visible, per requirement, in CI.

## What kept does

Reads acceptance criteria from `.kiro/specs/*/requirements.md` (EARS) and from
Gherkin, binds each criterion to the tests that claim to verify it, then
**attacks those tests** to find out whether they actually constrain behaviour.
Emits a commit-pinned evidence ledger with one verdict per criterion.

## Vocabulary

Use these words precisely, in code, docs, and output. Do not invent synonyms.

| Term | Meaning |
|---|---|
| **criterion** | One parsed acceptance criterion with a stable ID (`REQ-3.2`) and a content hash |
| **promise** | The user-facing name for a normative criterion. Headline counts speak in promises |
| **oracle** | A test that claims to verify a criterion. Example-based or property-based |
| **binding** | The mapping from criterion to oracles. Reviewable, committed, human-owned |
| **evidence** | The receipts behind a verdict: test IDs, covered lines, surviving mutants, counterexamples, seeds |
| **ledger** | The commit-pinned, machine-readable record of all verdicts |
| **verdict** | One of the five values below |

## The five verdicts

| Verdict | Definition |
|---|---|
| **KEPT** | A bound oracle exists, passes, is non-vacuous, and every generated mutant on the criterion's covered lines was killed by that criterion's own bound tests |
| **WEAK** | Bound oracles pass, but at least one mutant on the criterion's covered lines survived them. The implementation can be silently broken and the criterion still reports success |
| **UNPROVEN** | No binding, no covered lines, or the bound oracle was skipped or is vacuous. Nothing was actually checked |
| **BROKEN** | A bound oracle fails. Carries a shrunk minimal counterexample where available |
| **STALE** | Recorded evidence refers to different criterion text or different code than the current commit. The evidence exists but no longer applies |

### The WEAK asymmetry — a deliberate decision

A mutant counts as surviving if **the criterion's own bound tests** fail to kill
it, even when some unrelated test elsewhere in the suite would have caught it.
This is intentional. The claim under audit is not "the suite is adequate", it is
"**this criterion is independently verified**". Traceability is worthless if a
criterion's verdict silently depends on tests that were never bound to it.

This is the single most likely design decision to be challenged. It is recorded
as an ADR and it must be stated plainly in the docs, not buried.

## Non-negotiable claims

These are load-bearing. Any change that weakens one is a breaking change.

- **Offline.** No network access, no API key, no account, at any point.
- **Deterministic.** Same commit plus same seed yields the same ledger, byte for byte.
- **Model-free verification.** No language model participates in reaching a verdict. See `verification-integrity.md`.
- **Self-attesting.** The repository publishes its own ledger, generated in CI, for the current commit.

## Honest scope

State these boundaries plainly rather than implying generality:

- Python and pytest only in this release.
- `kept` produces **evidence, not proof**. It is not formal verification. Mutation
  survival is a strong negative signal; mutation death is not a correctness
  guarantee. The tool's own output must say so.
- A criterion that no test could reasonably automate (visual design, external
  service behaviour) should be marked as such in the bindings rather than
  reported as a failure of the code.

## Relationship to Kiro's property-based testing

Complementary, not competing. Kiro *generates* the oracle inside the IDE.
`kept` *audits and enforces* the oracle, in CI, which is where Kiro's
correctness feature does not reach (its documented capability matrix lists
property-based testing as IDE-only). `kept` consumes Kiro's requirement ↔
property links as an input. The README must carry a capability table making
this distinction explicit, because the resemblance is the most obvious
objection to the project.

## Non-goals

- Not a spec-to-test generator. That is Kiro's feature; do not rebuild it.
- Not a documentation drift linter based on model opinion.
- Not a coverage tool. Coverage is an input, never a verdict.
- Not a dashboard. The primary interface is a CLI and a committed artefact.
