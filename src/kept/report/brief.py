"""Render one recorded verdict as a remediation brief. Pure: evidence in, text out.

A brief is a *suggestion*, not a verdict. It restates recorded evidence and names
the change that would answer it. Nothing here participates in reaching a verdict,
and no model is consulted: the text is a deterministic function of the ledger.
See docs/adr/0005.
"""

from __future__ import annotations

from kept.ids import display_hash
from kept.ir import Criterion
from kept.ledger import Ledger
from kept.verdict import Missed, Ruling, Unproven, Verdict

#: Printed on every brief. The brief sits outside the verification path, and the
#: reader has to know that acting on it changes nothing until kept re-runs.
DISCLAIMER = (
    "Rendered by `kept prompt` from recorded evidence in `.kept/ledger.json`. "
    "This is a **suggestion for a human or an agent to act on** — not a verdict, "
    "and not verified advice. No language model produced it, here or anywhere in "
    "kept. Only re-running `kept verify` can change a verdict."
)


class UnknownCriterionError(LookupError):
    """Raised when the ledger holds no ruling for the requested criterion."""


def render(
    ledger: Ledger,
    criterion_id: str,
    *,
    criterion: Criterion | None = None,
    command: str = "kept verify --write",
    at_commit: str | None = None,
) -> str:
    """Render the remediation brief for one criterion.

    Args:
        ledger: The recorded verdicts to read. Not re-verified.
        criterion_id: Which promise to brief on. Must exist in the ledger.
        criterion: The parsed criterion, when the spec still defines it, so the
            brief can quote the promise rather than only its identifier.
        command: The invocation that would re-check this promise.
        at_commit: The commit the reader is on, so a brief built from evidence
            gathered elsewhere says so.
    """
    ruling = ledger.get(criterion_id)
    if ruling is None:
        known = ", ".join(entry.criterion for entry in ledger.rulings) or "none"
        msg = (
            f"the ledger holds no verdict for {criterion_id}. "
            f"Run `kept verify --write` first, or pick one of: {known}"
        )
        raise UnknownCriterionError(msg)

    lines = [
        f"# Remediation brief — {ruling.criterion}",
        "",
        f"Verdict **{ruling.verdict}**.",
        "",
    ]
    lines += _provenance(ledger, at_commit=at_commit)
    lines += _promise(ruling, criterion)
    lines += _evidence(ruling)
    lines += _actions(ruling)
    lines += _how_to_check(command)
    lines += ["---", "", DISCLAIMER]

    return "\n".join(lines).rstrip() + "\n"


def _provenance(ledger: Ledger, *, at_commit: str | None) -> list[str]:
    lines: list[str] = []
    if ledger.commit:
        lines += [f"Evidence gathered at commit `{ledger.commit}`, kept {ledger.kept_version}.", ""]
    if at_commit is not None and ledger.commit is not None and at_commit != ledger.commit:
        lines += [
            f"> This evidence describes commit `{ledger.commit}`, but you are on "
            f"`{at_commit}`. It may no longer apply. Re-run `kept verify` before "
            f"trusting the detail below.",
            "",
        ]
    return lines


def _promise(ruling: Ruling, criterion: Criterion | None) -> list[str]:
    lines = ["## The promise", ""]
    if criterion is not None:
        lines += [f"> {criterion.text}", ""]
        lines += [
            f"`{criterion.id}` · {criterion.pattern} · {criterion.modality} · "
            f"content hash `{display_hash(criterion.content_hash)}` · "
            f"{criterion.span.source}",
            "",
        ]
    else:
        lines += [
            f"`{ruling.criterion}` · content hash `{display_hash(ruling.content_hash)}`",
            "",
            "The specification no longer defines this identifier, so the wording "
            "above cannot be quoted. Either the criterion was renumbered or the "
            "ledger is out of date.",
            "",
        ]
    return lines


def _evidence(ruling: Ruling) -> list[str]:
    evidence = ruling.evidence
    lines = ["## What the evidence says", ""]

    if ruling.reason:
        lines += [str(ruling.reason), ""]

    if evidence.oracles:
        lines += [f"Bound oracles ({len(evidence.oracles)}):", ""]
        lines += [f"- `{nodeid}` — {status}" for nodeid, status in evidence.oracles]
        lines.append("")
    else:
        lines += ["No oracle is bound to this promise.", ""]

    if evidence.covered:
        lines += ["Lines under audit:", ""]
        lines += [f"- `{path}`: {line_ranges(lines_)}" for path, lines_ in evidence.covered]
        lines.append("")

    if evidence.probed:
        score = evidence.score
        share = "n/a" if score is None else f"{score:.0%}"
        lines += [
            f"Breakages probed: {evidence.probed} · killed by this promise's own "
            f"oracles: {evidence.killed} · detectable: {evidence.discriminating} · "
            f"missed: {len(evidence.missed)} · caught by nothing at all: "
            f"{evidence.unpinned}. Share of detectable breakages caught: {share}.",
            "",
        ]

    return lines


def _actions(ruling: Ruling) -> list[str]:
    return ["## What to change", "", *_action_body(ruling)]


def _action_body(ruling: Ruling) -> list[str]:
    verdict = ruling.verdict

    if verdict is Verdict.WEAK:
        return _weak_actions(ruling)
    if verdict is Verdict.BROKEN:
        return _broken_actions(ruling)
    if verdict is Verdict.UNPROVEN:
        return _unproven_actions(ruling)
    if verdict is Verdict.STALE:
        return [
            "The recorded evidence was gathered against different criterion text or "
            "different code. Re-run `kept verify --write` to judge the current "
            "commit, then read the new brief.",
            "",
        ]

    return [
        "Nothing. Every breakage that any bound oracle proved detectable was caught "
        "by this promise's own oracles.",
        "",
        "This is evidence, not proof. A killed mutant does not guarantee the "
        "implementation is correct — only that these oracles notice the breakages "
        "kept was able to generate on the lines they cover.",
        "",
    ]


def _weak_actions(ruling: Ruling) -> list[str]:
    missed = ruling.evidence.missed
    lines = [
        "Each change below was applied to the implementation, one at a time, and "
        "this promise's own oracles still passed. Another bound oracle did notice "
        "each one, which is how kept knows the change is detectable rather than "
        "equivalent to the original.",
        "",
        "Strengthen this promise's own oracles so each change makes one of them "
        "fail. Do not bind another promise's test to this one, and do not weaken "
        "the implementation to suit a test.",
        "",
    ]
    for position, entry in enumerate(missed, start=1):
        lines += _missed_entry(position, entry)
    return lines


def _missed_entry(position: int, missed: Missed) -> list[str]:
    caught = ", ".join(f"`{criterion}`" for criterion in missed.caught_by)
    return [
        f"{position}. `{missed.path}:{missed.line}` — {missed.description} ({missed.operator})",
        f"   Noticed by the oracles of: {caught}",
        "",
    ]


def _broken_actions(ruling: Ruling) -> list[str]:
    failing = [nodeid for nodeid, status in ruling.evidence.oracles if status in _FAILED]
    lines = [
        "A bound oracle is failing, so no mutation evidence applies yet. Decide "
        "which side is wrong — the implementation or the oracle — and fix that one. "
        "Do not delete or skip the oracle to clear the verdict; a skipped oracle "
        "reports UNPROVEN, which is not an improvement.",
        "",
    ]
    if failing:
        lines += ["Failing oracles:", ""]
        lines += [f"- `{nodeid}`" for nodeid in failing]
        lines.append("")
    return lines


#: Oracle statuses that mean the oracle did not pass. Mirrors observation.OracleStatus
#: by value rather than importing it, because a stored ledger carries strings.
_FAILED = frozenset({"failed", "error"})


_UNPROVEN_ADVICE: dict[str, tuple[str, ...]] = {
    str(Unproven.NO_BINDING): (
        "Nothing claims to verify this promise. Bind a test to it, then re-run.",
        "",
        "Mark the test that already covers this behaviour:",
        "",
        "```python",
        '@pytest.mark.verifies("{criterion}")',
        "def test_...():",
        "    ...",
        "```",
        "",
        "Or record the binding in `.kept/bindings.toml`, which is the reviewable, "
        "human-owned file. If no test could reasonably automate this promise, say "
        "so there as an explicit exclusion with a reason rather than leaving it "
        "silently unbound.",
        "",
    ),
    str(Unproven.NO_USABLE_ORACLE): (
        "Every bound oracle was skipped, could not be collected, or asserts "
        "nothing. An oracle that asserts nothing passes for any implementation, so "
        "it constrains nothing. Add the assertion that would fail if the promise "
        "were broken, or remove the skip.",
        "",
    ),
    str(Unproven.NO_COVERAGE): (
        "The bound oracles ran, but executed no source line attributable to this "
        "promise. Usually the test exercises a different module than the one that "
        "implements the promise, or `--source` points somewhere the implementation "
        "is not. Check that the oracle really drives the code this promise is "
        "about.",
        "",
    ),
    str(Unproven.NO_MUTANTS): (
        "No breakage could be generated on the covered lines, so there is no "
        "evidence either way. This is common when the covered lines are only "
        "definitions or constants. Broaden what the oracle exercises so the "
        "promise's actual logic is under audit.",
        "",
    ),
    str(Unproven.NOT_DISCRIMINATING): (
        "Every breakage kept generated on these lines survived *every* bound "
        "oracle in the suite, so kept cannot tell a weak oracle from an "
        "unbreakable line. This is a signal about the suite as a whole rather than "
        "about this promise alone: see the unpinned lines in EVIDENCE.md, and add "
        "an assertion that pins the behaviour of the covered lines.",
        "",
    ),
}


def _unproven_actions(ruling: Ruling) -> list[str]:
    advice = _UNPROVEN_ADVICE.get(str(ruling.reason or ""))
    if advice is None:
        return [
            "Nothing was actually checked for this promise, and the ledger records "
            "no reason. Re-run `kept verify --write` to regenerate the evidence.",
            "",
        ]
    return [line.replace("{criterion}", ruling.criterion) for line in advice]


def _how_to_check(command: str) -> list[str]:
    return [
        "## How to check the work",
        "",
        "```bash",
        command,
        "```",
        "",
        "The verdict moves only when kept re-runs. Editing this brief changes "
        "nothing, and neither does asserting that the promise is now kept.",
        "",
    ]


def line_ranges(lines: tuple[int, ...]) -> str:
    """Render line numbers compactly: 3-5, 9, 12-14."""
    if not lines:
        return "none"
    groups: list[tuple[int, int]] = []
    start = previous = lines[0]
    for line in lines[1:]:
        if line == previous + 1:
            previous = line
            continue
        groups.append((start, previous))
        start = previous = line
    groups.append((start, previous))
    return ", ".join(str(a) if a == b else f"{a}-{b}" for a, b in groups)
