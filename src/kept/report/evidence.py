"""Render a ledger as EVIDENCE.md. Pure: text in, text out."""

from __future__ import annotations

from kept.ids import display_hash
from kept.ledger import Ledger
from kept.verdict import Ruling, Verdict

_SYMBOL = {
    Verdict.KEPT: "kept",
    Verdict.WEAK: "weak",
    Verdict.UNPROVEN: "unproven",
    Verdict.BROKEN: "broken",
    Verdict.STALE: "stale",
}

_MEANING = {
    Verdict.KEPT: (
        "Bound oracles passed, assert something, and caught every breakage of the "
        "covered lines that any bound oracle proved detectable."
    ),
    Verdict.WEAK: (
        "Bound oracles passed, but missed a breakage that another bound oracle "
        "caught. The implementation can be broken while this promise still reports "
        "success."
    ),
    Verdict.UNPROVEN: "Nothing was actually checked. See the reason on each row.",
    Verdict.BROKEN: "A bound oracle failed or errored.",
    Verdict.STALE: (
        "Recorded evidence refers to different criterion text or different code "
        "than the current commit."
    ),
}


def render(ledger: Ledger) -> str:
    lines: list[str] = [
        "# Evidence",
        "",
        f"**{ledger.headline()}**",
        "",
    ]

    if ledger.commit:
        lines += [f"Commit `{ledger.commit}`, kept {ledger.kept_version}.", ""]

    lines += [
        "Produced by `kept verify`. This is **evidence, not proof**: mutation "
        "survival is a strong negative signal, but a killed mutant is not a "
        "guarantee of correctness.",
        "",
        f"Settings: threshold {ledger.settings.threshold}, "
        f"cap {ledger.settings.cap} mutants per promise.",
        "",
        "## Verdicts",
        "",
        "| Promise | Verdict | Caught | Oracles | Note |",
        "|---|---|---|---|---|",
    ]

    for ruling in ledger.rulings:
        lines.append(_row(ruling))

    present = [verdict for verdict in Verdict if ledger.counts[str(verdict)]]
    if present:
        lines += ["", "## What the verdicts mean", ""]
        for verdict in present:
            lines += [f"**{_SYMBOL[verdict]}** — {_MEANING[verdict]}", ""]

    weak = [r for r in ledger.rulings if r.verdict is Verdict.WEAK]
    if weak:
        lines += ["## Missed breakages", "", _missed_intro(), ""]
        for ruling in weak:
            lines += [f"### {ruling.criterion}", ""]
            for missed in ruling.evidence.missed:
                caught = ", ".join(missed.caught_by)
                lines.append(
                    f"- `{missed.path}:{missed.line}` {missed.description} "
                    f"— caught by {caught}"
                )
            lines.append("")

    if ledger.unpinned:
        lines += [
            "## Unpinned lines",
            "",
            "Breakages that **no** bound oracle noticed. These are charged to the "
            "suite rather than to any one promise: if nothing detects them, blaming "
            "a single promise would be misattribution.",
            "",
            "| Location | Breakage | Covered by |",
            "|---|---|---|",
        ]
        for entry in ledger.unpinned:
            covered = f"{len(entry.covered_by)} promises" if entry.covered_by else "none"
            lines.append(
                f"| `{entry.path}:{entry.line}` | {entry.description} | {covered} |"
            )
        lines.append("")

    if ledger.excluded:
        lines += [
            "## Excluded",
            "",
            "Promises deliberately kept out of the verdicts, with the stated reason.",
            "",
            "| Promise | Reason |",
            "|---|---|",
        ]
        for criterion, reason in ledger.excluded:
            lines.append(f"| {criterion} | {reason} |")
        lines.append("")

    if ledger.sources:
        lines += [
            "## Sources judged",
            "",
            "| File | SHA-256 |",
            "|---|---|",
        ]
        for path, digest in ledger.sources:
            lines.append(f"| `{path}` | `{display_hash(digest)}` |")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _row(ruling: Ruling) -> str:
    evidence = ruling.evidence
    score = evidence.score
    caught = (
        f"{evidence.discriminating - len(evidence.missed)}/{evidence.discriminating}"
        if score is not None
        else "n/a"
    )
    note = ruling.reason or ""
    return (
        f"| {ruling.criterion} | {_SYMBOL[ruling.verdict]} | {caught} "
        f"| {len(evidence.oracles)} | {note} |"
    )


def _missed_intro() -> str:
    return (
        "Each line below is a change to the implementation that this promise's own "
        "oracles did not notice, but another promise's oracle did. That another "
        "oracle caught it is the proof the breakage is detectable, which is why it "
        "counts against this one."
    )
