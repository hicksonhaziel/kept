# What kept is not

## Not Kiro's property-based testing

The resemblance is the most obvious objection to the project, so here it is
directly. Kiro *generates* the oracle. kept *audits and enforces* it.

| | Kiro's correctness features | kept |
|---|---|---|
| What it produces | a property-based test for code you point it at | a verdict per acceptance criterion, and the evidence behind it |
| Where it runs | in the IDE, while you work | in CI, on every commit, and locally |
| Who writes the oracle | Kiro | you already did; kept never writes one |
| What it asks | "what property should hold here?" | "would the tests bound to this promise notice if the code broke?" |
| How it decides | a model proposes the property | mutation of the covered lines, then the criterion's own tests. No model, at any point |
| What you keep | a test file | a commit-pinned ledger and `EVIDENCE.md` |
| Failure it catches | missing test cases | tests that pass while the implementation is broken, and criteria nothing verifies |

They compose. Kiro writes the property; kept tells you whether that property
actually constrains the implementation, and fails the build when it stops doing so.
kept consumes the requirement-to-test link as input — the `@verifies` marker
connects a criterion to a test, whoever wrote the test.

If you already have tests, kept needs no new ones to start. It tells you which of
your existing tests are load-bearing and which are decoration.

## Not a documentation-claims checker

There is a family of tools that read prose promises — a README, a changelog — and
exercise the *running product* against them. That is a different question, and a
useful one.

| | Documentation-claim checkers | kept |
|---|---|---|
| Source of promises | prose, usually a README | acceptance criteria with a normative modality |
| What is exercised | the deployed product, often through a browser | the test suite that claims to verify each criterion |
| Question answered | does the live product still do what the docs say? | would your tests notice if it stopped? |
| Needs to run | a live target, a runner, usually credentials | the repository |
| Reproducible by a stranger | if they can reach your deployment | byte-for-byte, offline, from the commit |

Neither subsumes the other. A tool that drives the real product can catch a
regression no unit test covers; kept can tell you that the unit test you *do* have
would sleep through it.

## Not a coverage tool

Coverage is an input, never a verdict. It answers "did this line run", which is the
question kept starts from, not the one it ends on. A line can be covered by a test
that asserts nothing at all — that promise reports UNPROVEN, and coverage would
have reported 100%.

## Not a whole-suite mutation tool

Conventional mutation testing scores the suite. kept scores each promise
*separately*, using only the oracles bound to it. The numbers are deliberately not
comparable: a mutant caught by an unrelated test still counts as surviving here.
See [ADR-0003](adr/0003-a-criterion-kills-only-with-its-own-oracles.md).

## Not formal verification, and not an opinion

kept produces **evidence, not proof**. A killed mutant is a strong negative signal
about a test's weakness; a dead mutant is not a guarantee of correctness. And no
language model participates in reaching a verdict — not to classify, not to
summarise, not behind a flag — because a verdict backed by a model is an opinion,
and the entire value of the ledger is that it is not one.

The honest boundaries are in the [threat model](THREAT-MODEL.md), including the two
defects that made kept's own output untrustworthy for three days.
