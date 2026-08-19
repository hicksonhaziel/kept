# ADR-0004: No arbitrary pass mark. Only detectable breakages count

**Status:** accepted
**Date:** 2026-08-19

## Context

The first run of the mutation engine flagged **every** promise as weak: 25 of 25,
with 157 surviving breakages. A tool that flags everything is as useless as one
that flags nothing, so the raw survivor count could not drive a verdict.

Inspecting the survivors showed two different things mixed together.

**Genuinely loose oracles.** `test_amounts_are_integers` asserts only
`isinstance(calculate_discount(25_000), int)`. It would pass if the discount were
always zero, or negative, or wrong by a factor of ten. It caught 1 breakage in 12.
That is exactly what kept exists to find.

**Breakages nothing could detect.** `RefundLedger(10_000)` executes
`if amount_paid < 0`. Mutating `<` to `<=` changes nothing when the input is
10000, so the mutant is equivalent under that test's inputs. Reporting it as a
survivor is literally true and says nothing whatever about the oracle's quality.
Worse, it was charged to every promise whose oracle happened to construct a
ledger.

The obvious fix is a pass mark: KEPT above some kill ratio. But any number is
arbitrary, and an arbitrary number in the verdict path is the sort of thing this
project spent two ADRs avoiding.

## Decision

A breakage counts against a promise **only if some bound oracle proved it
detectable**.

- If any bound oracle anywhere killed a mutant, that mutant is *discriminating*.
  A promise whose own oracles missed a discriminating mutant has a real gap: a
  sibling test caught it, so it was catchable.
- If no bound oracle killed it, the mutant is *unpinned*. It is reported at suite
  level as a gap in the tests as a whole, and charged to nobody.

A promise's score is therefore: of the breakages proven detectable on its covered
lines, how many did its own oracles catch?

The default threshold is **1.0**, which is not a tuned number but the absence of
one. KEPT means "your oracle caught everything that was catchable". WEAK means
"another test in your own suite catches something yours misses". Both are claims
about the evidence, not about a chosen bar.

## Consequences

On the refund fixture this moved the result from 25 of 25 flagged, which was
noise, to 4 KEPT and 21 WEAK, with 23 unpinned lines reported separately. Every
one of the 21 now carries a proof of detectability naming the sibling oracle that
caught the breakage.

- The threshold remains configurable with `--threshold`, for a team that wants to
  adopt kept gradually. Lowering it admits promises whose oracles are weaker than
  their siblings'.
- A promise with no discriminating mutants is **UNPROVEN**, not KEPT. Absence of
  evidence is not evidence: if nothing on its covered lines could be shown
  breakable, kept has learned nothing about the oracle either way.
- Weakening the *only* oracle that detects something converts a discriminating
  mutant into an unpinned one. The promise then falls from KEPT to UNPROVEN
  rather than to WEAK. That is still a regression, and the gate catches it.
- The unpinned list is genuinely useful output in its own right: it is the set of
  behaviours no bound test constrains anywhere.

## Rejected alternatives

- **A tuned pass mark**, such as 0.8. Indefensible under questioning, and the
  number would have had to change per project.
- **Excluding lines covered by many promises.** Would have removed the noise, but
  by a heuristic about "centrality" that no one could justify.
- **Reporting the raw survivor count.** Honest but unusable, as the first run
  demonstrated.
