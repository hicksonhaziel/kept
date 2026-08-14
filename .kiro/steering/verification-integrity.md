# Verification integrity — the rules that cannot bend

`kept` is a tool that detects code which only appears to work. It has no
standing to make that claim unless it holds itself to a stricter standard than
it applies to others. These rules override convenience, schedule, and elegance.

## Rule 1 — No model in the verification path

No language model, remote service, or non-deterministic heuristic may
participate in producing a verdict. Not to classify, not to summarise, not to
"help decide" a borderline case, not behind a feature flag that defaults on.

The verification path is: parse → bind → observe → attack → rule.

Every step must be reproducible from the repository contents alone, by a reader
with no API key and no network connection. If a proposed feature cannot meet
that bar, it does not belong in the verification path. It may live in a clearly
labelled convenience command **outside** it, and the docs must say that its
output is a suggestion a human must review, never trusted input.

Rationale: a verdict backed by a model is an opinion. The entire value of the
ledger is that it is not an opinion.

## Rule 2 — Never simulate, stub, or hard-code a feature and present it as working

The failure mode `kept` detects is exactly this failure mode. Committing it
would be self-refuting, and it is independently prohibited by the hackathon
rules.

Therefore:

- No placeholder that returns a plausible constant.
- No demo path that special-cases the demo fixture.
- No `TODO` behind a function that reports success.
- If something is not implemented, it must fail loudly or be absent from the
  CLI surface entirely. `NotImplementedError` is acceptable; a fake result is not.
- Any capability shown in the README or the demo video must work on a clean
  clone, by the documented command, with no hidden setup.

Corollary: `kept` runs against itself in CI, and its own WEAK verdicts are
published rather than suppressed. An honest weak spot is evidence of integrity;
a hidden one is fraud.

## Rule 3 — Determinism is a feature, not a detail

Same commit plus same seed must yield the same ledger, byte for byte.

- Sort everything before it reaches output: criteria by ID, mutants by a stable
  key, test IDs lexicographically. Never let set or dict iteration order reach
  a serialised artefact.
- Record the seed in the ledger. Use a derandomised Hypothesis profile for
  ledger runs so property tests are reproducible.
- Mutant generation and selection must be a pure function of (source, covered
  lines, operator set, seed, cap). No wall-clock, no PID, no randomness that
  is not seeded and recorded.
- No absolute paths in the ledger. All paths are repository-relative with
  forward slashes, so a ledger produced on one machine compares cleanly against
  one produced on another.
- Timestamps are metadata, never part of the compared verdict payload.

## Rule 4 — Claim precisely

The tool's own language must not overstate. Say "evidence", not "proof". Say
"no surviving mutants", not "correct". Say "unproven", not "wrong", when nothing
was checked. Mirroring the careful phrasing that Kiro's own documentation uses
about property-based testing is the correct register.

Overclaiming is both a scoring risk and, more importantly, the thing this tool
was built to oppose.

## Rule 5 — The human owns the mapping, the machine owns the verification

Bindings are authored and reviewed by people, stored in a readable committed
file. The machine never silently invents a binding and then grades itself
against it. Automatic binding *suggestions* are permitted only as a separate,
explicitly optional command that writes reviewable output a human must commit.
