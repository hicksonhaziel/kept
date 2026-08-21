# Threat model

kept exists to detect code that only appears to work. This document is the same
scrutiny turned on kept: every way a KEPT verdict could be wrong, or read as
saying more than it does.

Nothing here is hypothetical for its own sake. Two of these were live defects,
found on 2026-08-21 by pointing kept at itself, and both are marked as such.

## What a verdict actually claims

**KEPT** claims exactly this: for the lines this criterion's own bound oracles
executed, every mutation kept generated and ran was noticed by those oracles.

It does not claim the code is correct, that the criterion is fully tested, or that
no bug remains. The claim is bounded by four things a reader cannot see in the
word "kept": which lines were covered, which mutations exist, how many were run,
and which oracles were bound. All four are in the ledger. This is why the tool says
evidence, not proof.

## 1. The mutant that never reached the code

**Was live until 2026-08-21.** kept mutates a copy of the project in a temporary
worktree. If the package under audit is installed into the environment — every
src-layout project, kept included — `import yourpackage` resolves to the installed
original and the mutated copy is never read. Every mutant survives being noticed,
which paradoxically produced *flattering* verdicts through the next weakness.

Fixed by putting the worktree's import root ahead of anything installed.
Regression-tested in `tests/test_verdict.py`.

**Residual risk.** A project that imports its code by some other route — a
`.pth` file of its own, a compiled extension, a plugin loaded from an absolute
path — could still shadow the copy. The signature is a suspiciously high KEPT
count with many unpinned lines. If you see that, distrust it and tell us.

## 2. The mutant that was counted without running

**Was live until 2026-08-21.** A mutant that failed to build, or that came out
textually identical to the original, was recorded as *killed*. Because the score
is killed over detectable, a criterion whose every mutant was a no-op scored 1.0
and reported KEPT on an empty probe.

Fixed: such mutants are marked as not executed and excluded from every count, so
the criterion reports UNPROVEN with no mutants.

**Why it matters beyond the fix.** This is the exact failure kept was built to
find, and it lived in kept for three days, invisible to a green suite and to
coverage. It is the strongest argument in this document for auditing the auditor.

## 3. Equivalent mutants inflate WEAK

A mutant can be syntactically different and behaviourally identical for the inputs
a test uses. kept has no way to prove semantic equivalence — nobody does, it is
undecidable in general — so an equivalent mutant that some *other* criterion's
oracles happen to detect is charged as a miss.

This is the largest single distortion in kept's own published ledger: one mutant,
which flips `char == BACKTICK` to `!=` and is inert for any input without a
backtick, is charged against 33 of 51 promises. Documented in
[ADR-0006](adr/0006-cross-scope-detectability.md), which also records why the
easier answers were refused.

**Direction of the error:** it makes results look *worse*, never better. A WEAK
verdict may be pessimistic. A KEPT verdict is not affected.

## 4. The cap hides survivors

`--cap` bounds mutants per promise (default 12). Mutant selection is a
deterministic function of source, covered lines, operator set, seed and cap, so it
is reproducible — but a promise with 200 mutable sites is judged on 12 of them.
KEPT means "the twelve kept chose were all noticed", not "nothing survives".

The cap is recorded in the ledger's settings for exactly this reason. Raising it
strictly increases what is checked. A reader comparing two ledgers must compare
caps first.

## 5. Coverage attribution is broader than a criterion's subject

Lines under audit come from what a criterion's oracles *executed*, not from what
the criterion is *about*. A test that exercises a promise about invoice rounding
also runs the logger, the config loader, and any shared helper on the path.
Mutants land there too.

Consequence: a promise can be WEAK for missing a change in code that has nothing
to do with it. Shared helpers on hot paths inflate the count across every promise
at once. Accepted deliberately: the alternative is inferring which lines a
criterion is "really" about, and a heuristic guess has no place in a verification
path.

## 6. A wrong binding produces a confident wrong answer

Bindings are authored by humans. Bind `REQ-3.2` to a test that verifies something
else and kept will faithfully report evidence about the wrong thing. The machine
never invents a binding, and it also cannot tell that yours is mistaken.

Mitigation is procedural, not technical: `.kept/bindings.toml` is a reviewable
committed file, and binding changes belong in code review like any other change.
This is [rule 5](../.kiro/steering/verification-integrity.md) and it is a
deliberate limit on what automation is trusted to do.

## 7. Gaming it

Every one of these makes the ledger say less, and all are visible in the artefact:

- **Bind a stronger test to a weak criterion.** Works, and the ledger names the
  oracles for every verdict, so a reviewer sees which test is claimed where.
- **Raise `--threshold` above 1.0 or lower it.** Recorded in the ledger settings;
  a published number without its threshold is meaningless and kept refuses to
  print one that way.
- **Lower `--cap` to 1.** Recorded. A one-mutant KEPT is visibly thin.
- **Delete a failing oracle.** Turns BROKEN into UNPROVEN, which is not an
  improvement and is reported as its own verdict.
- **Mark criteria unverifiable in the bindings file.** Legitimate for a criterion
  no test could automate, and listed in `EVIDENCE.md` under Excluded with the
  stated reason, so it cannot be quiet.
- **Commit a stale ledger.** Content hashes of both criteria and sources are
  recorded; kept reports STALE and drift when either moved.

There is no way to make kept report KEPT for a promise whose oracles do not notice
a breakage. That is the one property the whole design protects.

## 8. The cache

Mutation results are cached under `.kept/cache/`, keyed by mutant and test set,
and the directory is gitignored — a shared cache is not part of the trust chain.
A hand-edited cache could fabricate kills. The defence is that it is local, never
committed, never fetched, and `--no-cache` reproduces any run from scratch.

The cache carries a version, and version 1 is discarded wholesale because entries
written before the two fixes above recorded results that are now known to be
wrong. A cache that outlived a semantic change is a real hazard, and versioning is
the only honest answer to it.

## 9. Executing the code under audit

kept runs your test suite, including under mutation. A mutant can turn a loop
infinite (bounded by `--timeout`, and a timeout counts as noticed) or make a test
delete files, since a mutated test is still arbitrary code. Mutation happens in a
copy under a temporary directory, never in your working tree, so the blast radius
is that copy — but a test that reaches outside its own tree can still do damage.

kept opens no network connection, reads no credentials, and requires no account.
The mutation worktree excludes `.git` and `.venv`, so a mutant cannot corrupt
repository history.

## 10. Misreading the headline

`4 kept · 45 weak` invites two wrong conclusions: that the code is bad, or that
the tests are bad. Neither follows. It means that per promise, most criteria are
guarded by oracles narrower than the code they touch. kept's own suite is 200
tests and passes; the suite as a whole kills most of these mutants. The claim
under audit is independent verification per promise, not suite adequacy.

The trap in the other direction is worse: a repository that reports all-KEPT and
stops reading. The cap, the operator set, and the covered-line scope all bound
that result, and they are all in the ledger.

## What kept does not attempt

- Formal verification or proof of correctness.
- Any statement about performance, security, or accessibility.
- Any judgement of the wording of a criterion. If prose is ambiguous, kept reports
  a diagnostic and refuses to guess.
- Any verdict influenced by a language model, anywhere, under any flag.
