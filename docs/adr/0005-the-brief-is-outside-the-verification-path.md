# ADR-0005: The remediation brief sits outside the verification path

**Status:** accepted
**Date:** 2026-08-19

## Context

A WEAK verdict is a finding, not a fix. The reader still has to work out which
assertion would have caught the surviving change. That work is mechanical, and it
is exactly the kind of task an agent is good at — which is the temptation: ask a
model to read the evidence and propose the missing assertion.

`kept serve` sharpens the temptation. Once an agent can call kept over MCP, the
obvious next step is a tool that returns a suggested patch.

## Decision

`kept prompt` renders a brief for one promise: the recorded evidence, the wording
of the promise, and the change that would answer it. It is a **pure function of
the committed ledger**. Same ledger, same brief, byte for byte.

It does not run tests, does not reach a verdict, and does not consult a model. It
cannot alter a verdict, and neither can anything an agent does with its output.
The only thing that moves a verdict is `kept verify` re-running the pipeline.

Every brief carries that statement in its own text, because the brief travels
away from the tool that produced it — into a pull request comment, an agent's
context window, a terminal scrollback — and has to remain honest out of context.

## Consequences

kept is now usable inside an agent loop without a model entering the verification
path. The division holds: the agent may act on a brief, and kept then judges the
result exactly as it judges any other commit. The agent proposes; the ledger
disposes.

Accepted costs:

- The brief is less helpful than a generated patch would be. It names the line,
  the breakage, and the promise whose oracle caught it, then stops. Writing the
  assertion is left to the reader.
- The advice is templated per verdict and per UNPROVEN reason, so it can read
  mechanically. Mechanical is the point: a brief that reads like insight invites
  the trust that only the ledger has earned.

Rejected alternative: a `--suggest` flag that calls a model to draft the missing
assertion. It fails Rule 1 of `verification-integrity.md` on the letter — the
draft is not a verdict — but it fails the spirit too. A tool built to expose
oracles that agree with the code they were written from should not ship a feature
that writes oracles from the code.

The brief's own weakness is worth stating plainly: it is only as good as the
mutation operators that produced the evidence. It tells you an oracle missed a
change; it cannot tell you the promise is otherwise well tested.
