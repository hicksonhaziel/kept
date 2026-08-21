# ADR-0006: A breakage detectable only through another promise's inputs still counts

**Status:** accepted
**Date:** 2026-08-21

## Context

Running kept against itself produced 46 WEAK verdicts out of 51 promises, and the
misses concentrated hard: five distinct mutants accounted for most of them. One
mutant alone was charged against 33 promises.

That mutant changes `if char == BACKTICK` to `!=` in the lexer's main loop. It
looks devastating and is almost inert, because the function it wrongly calls falls
back to ordinary word lexing when it finds no closing backtick. For any input
without a backtick — which is nearly every test input in the suite — the token
stream is unchanged.

It is not fully equivalent, though. REQ-1.8's oracles lex backticked text, and they
fail immediately. So kept has proof the change is detectable, and charges every
other promise whose covered lines include that branch for not noticing it.

The question this raises: should a promise be marked WEAK for missing a breakage
that can only be observed through inputs belonging to a *different* promise?

## Decision

Yes. The rule stands unchanged: if any bound oracle proved a breakage detectable,
every promise whose covered lines include it and whose own oracles missed it is
WEAK.

## Consequences

The verdict is answering the question kept actually asks, which is not "is this
line tested somewhere" but "would this promise's own oracles notice if this line
broke". For the 33 promises above the honest answer is no. Their oracles execute
that branch and constrain nothing about it. If REQ-1.8's tests were deleted
tomorrow, the branch would be unguarded and 33 promises would still report success.

Accepted costs, stated plainly because they are large:

- A promise can be WEAK for reasons outside its own subject matter. REQ-4.3 is
  about markdown headings, and it is marked WEAK partly for not noticing a lexer
  change. That reads oddly and it is not a defect.
- A shared helper on a hot path inflates the count. `normalise_text` and
  `criterion_id` are executed by almost every test, so a mutant on either is
  charged to almost every promise. Nine files produced 46 WEAK verdicts.
- The remedy is real work, not a flag: either the oracle asserts more of what it
  executes, or the criterion's covered surface shrinks. Both are improvements;
  neither is quick.

## What was rejected

**Scoping mutants to the module a criterion "belongs to".** There is no
machine-checkable notion of belonging that is not a guess, and guessing which
lines a criterion is really about is the kind of inference that would put a
heuristic in the verification path.

**Discarding mutants killed by fewer than N promises.** This would silently drop
exactly the mutants that expose narrow oracles, which is the signal, not the noise.

**Tuning the threshold below 1.0 to make the number look better.** The threshold
exists so a reader can see what standard was applied; moving it to flatter a
result would make the ledger an opinion. See ADR-0004.

## Note for readers of kept's own ledger

kept's 46 WEAK verdicts are not a claim that kept is badly tested by conventional
measures — 186 tests pass, and the suite as a whole kills most of these mutants.
They are a claim that per-promise, most of kept's criteria are guarded by oracles
narrower than the code they touch. That is the distinction the tool exists to draw,
and it applies to its author's code as much as anyone's.
