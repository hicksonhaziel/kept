# The five verdicts

One per promise, per commit. Every verdict carries its evidence in
`.kept/ledger.json`: the test IDs, the lines under audit, the mutants that
survived, and the settings in force.

| Verdict | Means | Read it as |
|---|---|---|
| **KEPT** | A bound oracle exists, passes, asserts something, and every breakage kept generated on the criterion's covered lines was noticed by that criterion's own tests | This promise is independently verified, within the bounds recorded |
| **WEAK** | The bound oracles pass, but at least one breakage went unnoticed | The implementation can be silently broken while this promise still reports success |
| **UNPROVEN** | No binding, no coverage, or the oracle was skipped or asserts nothing | Nothing was actually checked. Not wrong — unknown |
| **BROKEN** | A bound oracle fails or errors | Fix the code or the test; no mutation evidence applies yet |
| **STALE** | Recorded evidence describes different criterion text or different code | The evidence exists but no longer applies to this commit |

## Why WEAK is the interesting one

A green suite tells you the tests passed. WEAK tells you they would have passed
anyway. It is the verdict that separates a test which constrains behaviour from one
that merely runs it.

```
  REQ-1.2    WEAK          6/7   1 of 7 detectable breakages went unnoticed
      missed  refund.py:122  <= to <   (caught by REQ-1.3)
```

Read that as: kept changed `<=` to `<` on line 122, REQ-1.2's own tests still
passed, and REQ-1.3's tests caught it. The last part is what makes it evidence
rather than noise — another oracle proving the change is detectable is how kept
knows the code really did break.

## The asymmetry, stated plainly

> [!WARNING]
> A mutant counts as surviving if **the criterion's own bound tests** miss it, even
> when some unrelated test elsewhere in the suite would have caught it.

This is deliberate, and it is the design decision most likely to be challenged. The
claim under audit is not *the suite is adequate*. It is *this criterion is
independently verified*.

Traceability is worthless if a promise's verdict silently depends on tests nobody
bound to it: the promise would look proven by accident, and would quietly become
unproven the day that unrelated test was deleted.

Two consequences worth knowing before you read your first ledger:

1. **Mutation counts are lower than a whole-suite mutation tool would report.** The
   numbers are not comparable. kept measures per-promise verification, not suite
   adequacy.
2. **A well-tested project with sparse annotations will look weak.** That is
   honest — unbound tests are not traceable evidence. The remedy is to bind them.

Recorded as [ADR-0003](adr/0003-a-criterion-kills-only-with-its-own-oracles.md).

## Why there is no pass mark

A mutant only counts as evidence about a promise once *some* bound oracle proved it
detectable. A breakage nobody in the suite notices says something about the code,
not about this promise's test, so it is reported separately as an **unpinned line**
and charged to the suite rather than to any one promise.

That distinction removes the need for an arbitrary percentage. KEPT means every
detectable breakage was caught, not "enough of them were". See
[ADR-0004](adr/0004-no-arbitrary-pass-mark.md).

## What KEPT does not mean

KEPT is bounded by four things the word hides, all of which are in the ledger:

- which lines the criterion's tests actually executed,
- which mutations kept can generate,
- how many it ran (`--cap`, default 12 per promise),
- which oracles you bound.

A killed mutant is not proof of correctness. See the
[threat model](THREAT-MODEL.md).
