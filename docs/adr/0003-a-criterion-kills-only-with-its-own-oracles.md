# ADR-0003: A criterion kills a mutant only through its own bound oracles

**Status:** accepted
**Date:** 2026-08-17

## Context

When kept mutates a line, several tests in the suite may fail. Which of those
failures should count as evidence that a particular criterion is verified?

The permissive reading is that any failing test kills the mutant, so the mutant
counts as killed for every criterion covering that line. The strict reading is
that only the criterion's own bound oracles count.

## Decision

Only the criterion's own bound oracles. A mutant that some unrelated test would
have caught still counts as **surviving** for a criterion whose oracles missed it.

## Consequences

The claim under audit is not "the suite is adequate". It is "**this criterion is
independently verified**". Traceability is worth nothing if a criterion's verdict
silently depends on tests nobody ever bound to it: the promise would appear proven
because of an accident of the suite, and would quietly become unproven the day
that unrelated test was deleted.

The strict reading also produces the more useful report. "REQ-4.5 has no test that
would notice this break" is actionable. "Something somewhere failed" is not.

Accepted costs:

- Mutation counts are lower than a whole-suite mutation tool would report on the
  same code. This is not a bug and the numbers are not comparable. kept measures
  per-promise verification, not suite adequacy.
- A well-tested project with sparse annotations will look weak. That is honest:
  unbound tests are not traceable evidence. The remedy is to bind them.
- The same mutant may be killed for one criterion and survive for another. The
  ledger records it per criterion for exactly that reason.

Only oracles that passed and provably assert something are used. A failing oracle
would "notice" every mutant and manufacture a perfect score, and a vacuous one
would notice none.

This is the single most likely design decision to be challenged, which is why it
is recorded rather than buried in the executor.
