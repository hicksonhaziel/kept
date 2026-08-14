---
inclusion: fileMatch
fileMatchPattern: 'fixtures/**'
---

# Working inside `fixtures/`

Files under `fixtures/` are **subjects under audit**, not product source. The
normal conventions are suspended here, and different rules apply.

## What these are

`fixtures/` holds small, self-contained sample projects that `kept` runs
against. They exist to demonstrate and to test the verdict engine end to end.

The primary fixture is a refund and invoice engine: money, rounding,
idempotency, monotonicity. The domain is chosen because it is property-rich and
instantly legible to a viewer with no context.

Two variants:

- `fixtures/refund_engine/honest/` — a faithful implementation. Every normative
  criterion should reach KEPT. This is the control, and it is how we prove kept
  does not simply cry wolf.
- `fixtures/refund_engine/agent_generated/` — the unedited output of asking Kiro
  to implement the spec in a single pass, committed verbatim at a recorded
  commit. **Do not clean this up. Do not fix its bugs. Do not improve its
  tests.** Its value is entirely that it is authentic. If it needs to change,
  regenerate it and record the new provenance.

## Rules

- Excluded from lint, `mypy`, and coverage. Configured in `pyproject.toml`; keep
  it that way.
- Fixtures must never import from `kept`. They are ordinary projects that happen
  to be examined.
- No network, no clock, no randomness without a fixed seed. Fixture test runs
  must be reproducible or the demo is not reproducible.
- Each fixture carries a `PROVENANCE.md` recording exactly how it was produced:
  the prompt or spec used, the date, the Kiro version, and whether a human edited
  it afterwards. For the agent-generated variant the honest answer must be "no".

## The rule that matters most here

Do not tune a fixture until it fails in an interesting way. That inverts the
whole argument: a strawman authored to be caught proves nothing, and this panel
will notice. The demo's power comes from the finding being genuine.

If the agent-generated fixture turns out to be *good*, that is a real result and
it gets reported as one. Say so in the journal and in the video. A tool that
reports KEPT across the board on honest code, and finds real weakness where it
exists, is more credible than one that always finds something.
