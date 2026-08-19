"""Command-line entry point. The only module that calls `sys.exit`."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from kept import __version__, attack, bindings, ledger, pipeline, report, verdict
from kept.diagnostics import Diagnostic
from kept.ids import SCHEMA_VERSION, display_hash
from kept.ir import Criterion
from kept.loader import LoadResult, SpecNotFoundError, load, load_all, load_document
from kept.observe import ObservationError

#: Every failure mode that is the user's input rather than a defect in kept.
_INPUT_ERRORS = (
    ObservationError,
    SpecNotFoundError,
    bindings.BindingsError,
    ledger.LedgerError,
)

EXIT_OK = 0
EXIT_GATE_VIOLATED = 1
EXIT_USAGE = 2
EXIT_INTERNAL = 3


def _report_spec_errors(errors: tuple[Diagnostic, ...]) -> bool:
    """Print specification errors and report whether any were found.

    These block the run. Ambiguous input cannot produce a trustworthy verdict, and
    guessing which reading was meant is exactly what kept must not do.
    """
    for diagnostic in errors:
        print(f"kept: {diagnostic.code} {diagnostic.message}", file=sys.stderr)
    return bool(errors)


def _add_spec_option(command: argparse.ArgumentParser) -> None:
    """Let the user point at requirements that do not live in `.kiro/specs`."""
    command.add_argument(
        "--spec",
        action="append",
        type=Path,
        dest="specs",
        metavar="PATH",
        help=(
            "a requirements document to read. Repeatable. Any markdown file with "
            "numbered criteria under an 'Acceptance Criteria' heading works. "
            "Defaults to every .kiro/specs/*/requirements.md"
        ),
    )


def _add_python_option(command: argparse.ArgumentParser) -> None:
    """Let the user name the interpreter that owns the project's dependencies."""
    command.add_argument(
        "--python",
        type=Path,
        metavar="PATH",
        help=(
            "interpreter used to run the project's tests. Defaults to the active "
            "virtual environment, else the nearest .venv, else kept's own"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kept",
        description=(
            "An evidence ledger for agent-written code. Reports, per acceptance "
            "criterion, which promises your code actually keeps. Evidence, not proof."
        ),
    )
    parser.add_argument("--version", action="version", version=f"kept {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    parse_command = subcommands.add_parser(
        "parse",
        help="show the acceptance criteria kept can read, with identifiers and hashes",
        description="Parse specifications and print what was understood. No verdicts.",
    )
    parse_command.add_argument(
        "path",
        nargs="?",
        type=Path,
        help="a requirements.md file. Omit to parse everything under .kiro/specs",
    )
    parse_command.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="repository root used to relativise paths (default: current directory)",
    )
    parse_command.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit machine-readable JSON with sorted keys",
    )
    parse_command.add_argument("--quiet", action="store_true", help="print only the summary")
    parse_command.set_defaults(handler=_handle_parse)

    bind_command = subcommands.add_parser(
        "bind",
        help="show which criteria are bound to tests, and which are not",
        description=(
            "Harvest @pytest.mark.verifies markers, merge them over any hand-written "
            "bindings, and report what is bound. Reaches no verdicts."
        ),
    )
    bind_command.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="project root holding .kiro/specs and .kept (default: current directory)",
    )
    bind_command.add_argument(
        "--tests",
        help="restrict test collection to this path",
    )
    _add_python_option(bind_command)
    _add_spec_option(bind_command)
    bind_command.add_argument(
        "--write",
        action="store_true",
        help="write the merged result to .kept/bindings.toml for review",
    )
    bind_command.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit machine-readable JSON with sorted keys",
    )
    bind_command.set_defaults(handler=_handle_bind)

    observe_command = subcommands.add_parser(
        "observe",
        help="run the suite and show which lines each promise actually exercises",
        description=(
            "Run the test suite under per-test coverage and gather evidence for each "
            "promise: which oracles ran, whether they assert anything, and exactly "
            "which lines of code they touched. Reaches no verdicts."
        ),
    )
    observe_command.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="project root holding .kiro/specs and .kept (default: current directory)",
    )
    observe_command.add_argument("--tests", help="restrict the test run to this path")
    _add_python_option(observe_command)
    _add_spec_option(observe_command)
    observe_command.add_argument(
        "--source",
        default=".",
        help="path coverage should measure, relative to the root (default: .)",
    )
    observe_command.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit machine-readable JSON with sorted keys",
    )
    observe_command.set_defaults(handler=_handle_observe)

    attack_command = subcommands.add_parser(
        "attack",
        help="break the covered lines and report which oracles fail to notice",
        description=(
            "For each promise, mutate the lines its own oracles executed and rerun "
            "only those oracles. A mutant that survives means the implementation can "
            "be broken while the promise still reports success."
        ),
    )
    attack_command.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="project root holding .kiro/specs and .kept (default: current directory)",
    )
    attack_command.add_argument("--tests", help="restrict the test run to this path")
    _add_python_option(attack_command)
    _add_spec_option(attack_command)
    attack_command.add_argument(
        "--source",
        default=".",
        help="path coverage should measure, relative to the root (default: .)",
    )
    attack_command.add_argument(
        "--cap",
        type=int,
        default=attack.DEFAULT_CAP,
        metavar="N",
        help=f"mutants per promise (default: {attack.DEFAULT_CAP})",
    )
    attack_command.add_argument(
        "--workers",
        type=int,
        default=attack.DEFAULT_WORKERS,
        metavar="N",
        help=f"parallel test processes (default: {attack.DEFAULT_WORKERS})",
    )
    attack_command.add_argument(
        "--timeout",
        type=float,
        default=attack.MIN_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help="seconds allowed per mutant before it counts as killed",
    )
    attack_command.add_argument(
        "--no-cache",
        action="store_false",
        dest="use_cache",
        help="ignore and do not write the mutation cache",
    )
    attack_command.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit machine-readable JSON with sorted keys",
    )
    attack_command.set_defaults(handler=_handle_attack)

    verify_command = subcommands.add_parser(
        "verify",
        help="reach a verdict on every promise and write the evidence ledger",
        description=(
            "Run the whole pipeline and rule on each promise: KEPT, WEAK, UNPROVEN, "
            "or BROKEN. Compares against the committed ledger to report drift and "
            "regressions. Produces evidence, not proof."
        ),
    )
    verify_command.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="project root holding .kiro/specs and .kept (default: current directory)",
    )
    verify_command.add_argument("--tests", help="restrict the test run to this path")
    _add_python_option(verify_command)
    _add_spec_option(verify_command)
    verify_command.add_argument(
        "--source",
        default=".",
        help="path coverage should measure, relative to the root (default: .)",
    )
    verify_command.add_argument(
        "--threshold",
        type=float,
        default=verdict.DEFAULT_THRESHOLD,
        metavar="RATIO",
        help=(
            "share of detectable breakages a promise's own oracles must catch to be "
            f"KEPT (default: {verdict.DEFAULT_THRESHOLD}, meaning all of them)"
        ),
    )
    verify_command.add_argument(
        "--cap",
        type=int,
        default=attack.DEFAULT_CAP,
        metavar="N",
        help=f"mutants per promise (default: {attack.DEFAULT_CAP})",
    )
    verify_command.add_argument(
        "--workers",
        type=int,
        default=attack.DEFAULT_WORKERS,
        metavar="N",
        help=f"parallel test processes (default: {attack.DEFAULT_WORKERS})",
    )
    verify_command.add_argument(
        "--timeout",
        type=float,
        default=attack.MIN_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help="seconds allowed per mutant before it counts as killed",
    )
    verify_command.add_argument(
        "--gate",
        choices=("none", "no-regression", "no-broken", "all-kept"),
        default="no-regression",
        help=(
            "what makes this run fail with exit 1. Defaults to no-regression, which "
            "is adoptable on an existing codebase from day one"
        ),
    )
    verify_command.add_argument(
        "--write",
        action="store_true",
        help="write .kept/ledger.json, EVIDENCE.md, and .kept/badge.svg",
    )
    verify_command.add_argument(
        "--show-unpinned",
        type=int,
        default=10,
        metavar="N",
        help="how many unpinned lines to list (default: 10)",
    )
    verify_command.add_argument(
        "--no-cache",
        action="store_false",
        dest="use_cache",
        help="ignore and do not write the mutation cache",
    )
    verify_command.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit machine-readable JSON with sorted keys",
    )
    verify_command.set_defaults(handler=_handle_verify)

    prompt_command = subcommands.add_parser(
        "prompt",
        help="emit a remediation brief for one promise, from the committed ledger",
        description=(
            "Restate the recorded evidence for one promise and name the change that "
            "would answer it. Reads the ledger; runs no tests and reaches no "
            "verdict. The output is a suggestion for a human or an agent to review, "
            "rendered deterministically with no model involved."
        ),
    )
    prompt_command.add_argument(
        "criterion",
        help="the promise to brief on, as it appears in the ledger (for example REQ-2.1)",
    )
    prompt_command.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="project root holding .kept and the specification (default: current directory)",
    )
    _add_spec_option(prompt_command)
    prompt_command.set_defaults(handler=_handle_prompt)

    return parser


def _handle_parse(args: argparse.Namespace) -> int:
    try:
        result = (
            load_document(args.path, root=args.root)
            if args.path is not None
            else load_all(args.root)
        )
    except SpecNotFoundError as error:
        print(f"kept: {error}", file=sys.stderr)
        return EXIT_USAGE

    if args.as_json:
        print(_render_json(result))
    else:
        _render_text(result, quiet=args.quiet, stream=sys.stdout)

    # Parse errors mean kept could not read a promise it was asked about: a gate
    # violation, not a crash.
    return EXIT_GATE_VIOLATED if result.errors else EXIT_OK


def _handle_bind(args: argparse.Namespace) -> int:
    try:
        stage = pipeline.bind(
            args.root, tests=args.tests, python=args.python, specs=args.specs
        )
    except _INPUT_ERRORS as error:
        print(f"kept: {error}", file=sys.stderr)
        return EXIT_USAGE

    if _report_spec_errors(stage.errors):
        return EXIT_USAGE

    merged = stage.bindings
    unbound, orphaned = stage.unbound, stage.orphaned
    malformed = stage.report.malformed

    if args.write:
        bindings.save(merged, bindings.bindings_path(args.root))

    summary = {
        "schema_version": SCHEMA_VERSION,
        "promises": len(stage.promise_ids),
        "bound": sum(1 for c in stage.promise_ids if c in merged.bound_criteria),
        "unbound": list(unbound),
        "orphaned": list(orphaned),
        "unverifiable": [entry.to_dict() for entry in merged.unverifiable],
        "oracles": len(merged.all_oracles),
        "tests_collected": stage.report.collected,
        "malformed": [{"oracle": o, "problem": p} for o, p in malformed],
    }

    if args.as_json:
        print(json.dumps(summary, sort_keys=True, indent=2, ensure_ascii=False))
        return EXIT_GATE_VIOLATED if unbound or orphaned or malformed else EXIT_OK

    write = sys.stdout.write
    for binding in merged.bindings:
        if binding.criterion in orphaned:
            continue
        write(f"\n  {binding.criterion}  ({binding.origin})\n")
        for oracle in binding.oracles:
            write(f"      {oracle}\n")

    _write_list(write, "unbound promises (nothing claims to verify these)", unbound)
    _write_list(write, "orphaned bindings (criterion no longer exists in the spec)", orphaned)

    for oracle, problem in malformed:
        write(f"\n  WARNING {oracle}\n      {problem}\n")

    write(
        f"\n{summary['promises']} promises · "
        f"{summary['bound']} bound · "
        f"{len(unbound)} unbound · "
        f"{summary['oracles']} oracles across {summary['tests_collected']} collected tests\n"
    )
    if args.write:
        write(f"\nwrote {bindings.bindings_path(args.root)}\n")

    # Unbound promises are not a crash: kept reported honestly. They are a gate
    # violation, because an unbound promise cannot be verified.
    return EXIT_GATE_VIOLATED if unbound or orphaned or malformed else EXIT_OK


def _handle_observe(args: argparse.Namespace) -> int:
    try:
        stage = pipeline.observe(
            args.root,
            tests=args.tests,
            source=args.source,
            python=args.python,
            specs=args.specs,
        )
    except _INPUT_ERRORS as error:
        print(f"kept: {error}", file=sys.stderr)
        return EXIT_USAGE

    if _report_spec_errors(stage.bind.errors):
        return EXIT_USAGE

    observations = stage.observations.criteria
    problems = {
        "unbound": list(stage.bind.unbound),
        "failing": [o.criterion for o in observations if o.failing],
        "vacuous": [o.criterion for o in observations if o.vacuous and not o.usable],
        "uncovered": [
            o.criterion
            for o in observations
            if o.usable and not o.covered and o.excluded_reason is None
        ],
        "missing_oracles": sorted(
            {
                oracle.nodeid
                for o in observations
                for oracle in o.oracles
                if str(oracle.status) == "missing"
            }
        ),
    }

    if args.as_json:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "observations": stage.observations.to_dict(),
                    "problems": problems,
                },
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
            )
        )
        return EXIT_GATE_VIOLATED if any(problems.values()) else EXIT_OK

    write = sys.stdout.write
    for entry in observations:
        if entry.excluded_reason is not None:
            write(f"\n  {entry.criterion}  excluded: {entry.excluded_reason}\n")
            continue

        write(f"\n  {entry.criterion}  {entry.covered_line_count} lines under audit\n")
        for oracle in entry.oracles:
            note = "" if oracle.has_assertion else "  [asserts nothing]"
            write(f"      {oracle.status:<8} {oracle.nodeid}{note}\n")
        for path, lines in entry.covered:
            write(f"        {path}: {report.line_ranges(lines)}\n")

    for label, criteria in problems.items():
        _write_list(write, label.replace("_", " "), tuple(criteria))

    audited = sum(1 for entry in observations if entry.covered)
    total_lines = sum(entry.covered_line_count for entry in observations)
    write(
        f"\n{len(observations)} promises · "
        f"{audited} with observed coverage · "
        f"{total_lines} criterion-line pairs to attack\n"
    )
    write("\nObservation only. No verdicts yet: nothing has been attacked.\n")

    return EXIT_GATE_VIOLATED if any(problems.values()) else EXIT_OK


def _handle_attack(args: argparse.Namespace) -> int:
    try:
        stage = pipeline.attack_project(
            args.root,
            tests=args.tests,
            source=args.source,
            cap=args.cap,
            workers=args.workers,
            timeout=args.timeout,
            use_cache=args.use_cache,
            python=args.python,
            specs=args.specs,
        )
    except _INPUT_ERRORS as error:
        print(f"kept: {error}", file=sys.stderr)
        return EXIT_USAGE

    result = stage.result
    criteria = [entry.criterion for entry in stage.observe.observations.criteria]
    weak = [c for c in criteria if result.survivors_for(c)]

    if args.as_json:
        print(
            json.dumps(
                {
                    "schema_version": SCHEMA_VERSION,
                    "cap": result.cap,
                    "mutants_available": stage.mutants_available,
                    "mutants_run": len(result.outcomes),
                    "weak": weak,
                    "per_criterion": {
                        c: {
                            "probed": result.probed(c),
                            "killed": len(result.killed_for(c)),
                            "survived": [o.mutant.to_dict() for o in result.survivors_for(c)],
                        }
                        for c in criteria
                        if result.probed(c)
                    },
                },
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
            )
        )
        return EXIT_GATE_VIOLATED if weak else EXIT_OK

    write = sys.stdout.write
    for criterion in criteria:
        probed = result.probed(criterion)
        if not probed:
            continue
        survivors = result.survivors_for(criterion)
        killed = probed - len(survivors)
        write(f"\n  {criterion}  {killed}/{probed} mutants killed\n")
        for outcome in survivors:
            # The site index disambiguates two mutation sites on one line, such as
            # both comparisons in `a <= 0 or b <= 0`.
            location = f"{outcome.mutant.path}:{outcome.mutant.line}#{outcome.mutant.index}"
            write(f"      survived  {location:<28} {outcome.mutant.description}\n")

    unprobed = [c for c in criteria if not result.probed(c)]
    _write_list(write, "not probed (no usable oracle, or no covered lines)", tuple(unprobed))

    total_probed = sum(result.probed(c) for c in criteria)
    total_survived = sum(len(result.survivors_for(c)) for c in criteria)
    write(
        f"\n{len(result.outcomes)} mutants run of {stage.mutants_available} available "
        f"(cap {result.cap} per promise, {result.workers} workers)\n"
    )
    write(
        f"{total_probed} criterion-mutant pairs · "
        f"{total_probed - total_survived} killed · "
        f"{total_survived} survived · "
        f"{len(weak)} of {len(criteria)} promises have at least one survivor\n"
    )
    write(
        "\nFacts only, no verdicts. Whether a survivor count makes a promise WEAK is "
        "decided by the rule stage, against a declared threshold.\n"
    )

    return EXIT_OK


def _handle_verify(args: argparse.Namespace) -> int:
    try:
        stage = pipeline.verify(
            args.root,
            tests=args.tests,
            source=args.source,
            cap=args.cap,
            workers=args.workers,
            timeout=args.timeout,
            use_cache=args.use_cache,
            python=args.python,
            threshold=args.threshold,
            specs=args.specs,
        )
    except _INPUT_ERRORS as error:
        print(f"kept: {error}", file=sys.stderr)
        return EXIT_USAGE

    if _report_spec_errors(stage.attack.observe.bind.errors):
        return EXIT_USAGE

    fresh = stage.ledger
    written: list[str] = []

    if args.write:
        ledger.save(fresh, ledger.ledger_path(args.root))
        written.append(str(ledger.ledger_path(args.root)))

        evidence_path = args.root / "EVIDENCE.md"
        evidence_path.write_text(report.render_evidence(fresh), encoding="utf-8")
        written.append(str(evidence_path))

        badge_path = args.root / ".kept" / "badge.svg"
        badge_path.parent.mkdir(parents=True, exist_ok=True)
        badge_path.write_text(report.render_badge(fresh), encoding="utf-8")
        written.append(str(badge_path))

    if args.as_json:
        print(
            json.dumps(
                {
                    "ledger": fresh.to_dict(),
                    "drift": stage.drift.to_dict(),
                    "regressions": [r.to_dict() for r in stage.regressions],
                    "written": written,
                },
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
            )
        )
        return _gate(args.gate, stage)

    write = sys.stdout.write
    for ruling in fresh.rulings:
        evidence = ruling.evidence
        score = evidence.score
        caught = (
            f"{evidence.discriminating - len(evidence.missed)}/{evidence.discriminating}"
            if score is not None
            else "  -  "
        )
        write(f"\n  {ruling.criterion:<10} {str(ruling.verdict).upper():<9} {caught:>7}  ")
        write(f"{ruling.reason or ''}\n")
        for missed in evidence.missed:
            write(
                f"      missed  {missed.path}:{missed.line:<5} {missed.description}"
                f"  (caught by {', '.join(missed.caught_by)})\n"
            )

    if fresh.unpinned:
        write(f"\n{len(fresh.unpinned)} unpinned lines: no bound oracle noticed these\n")
        for entry in fresh.unpinned[: args.show_unpinned]:
            write(f"      {entry.path}:{entry.line:<5} {entry.description}\n")
        if len(fresh.unpinned) > args.show_unpinned:
            write(f"      ... and {len(fresh.unpinned) - args.show_unpinned} more\n")

    _write_drift(write, stage)

    write(f"\n{fresh.headline()}\n")
    if written:
        write("\nwrote " + ", ".join(written) + "\n")
    write("\nEvidence, not proof. A killed mutant is not a guarantee of correctness.\n")

    return _gate(args.gate, stage)


def _handle_prompt(args: argparse.Namespace) -> int:
    path = ledger.ledger_path(args.root)
    try:
        stored = ledger.load(path)
    except ledger.LedgerError as error:
        print(f"kept: {error}", file=sys.stderr)
        return EXIT_USAGE

    if stored is None:
        print(
            f"kept: no ledger at {path}. Run `kept verify --write` first: a brief "
            f"restates recorded evidence and invents none.",
            file=sys.stderr,
        )
        return EXIT_USAGE

    try:
        rendered = report.render_brief(
            stored,
            args.criterion,
            criterion=_criterion_text(args),
            command=_recheck_command(args),
            at_commit=ledger.current_commit(args.root),
        )
    except report.UnknownCriterionError as error:
        print(f"kept: {error}", file=sys.stderr)
        return EXIT_USAGE

    print(rendered, end="")
    return EXIT_OK


def _criterion_text(args: argparse.Namespace) -> Criterion | None:
    """The parsed criterion, so the brief can quote the promise.

    Absence is not fatal. A brief built only from the ledger is still honest; it
    just cannot show the wording.
    """
    try:
        result = load(args.root, specs=args.specs)
    except (SpecNotFoundError, OSError):
        return None
    for criterion in result.criteria:
        if criterion.id == args.criterion:
            return criterion
    return None


def _recheck_command(args: argparse.Namespace) -> str:
    parts = ["kept verify", f"--root {args.root}"]
    parts += [f"--spec {spec}" for spec in (args.specs or ())]
    parts.append("--write")
    return " ".join(parts)


def _write_drift(write: Callable[[str], int], stage: pipeline.VerifyStage) -> None:
    drift = stage.drift
    if drift.stale:
        write("\nSTALE: the committed ledger judged different wording for these\n")
        for criterion in drift.stale:
            write(f"      {criterion}\n")
    if drift.vanished:
        write("\nvanished since the committed ledger\n")
        for criterion in drift.vanished:
            write(f"      {criterion}\n")
    if stage.regressions:
        write("\nREGRESSED against the committed ledger\n")
        for regression in stage.regressions:
            write(f"      {regression.criterion}  {regression.was} -> {regression.now}\n")


def _gate(gate: str, stage: pipeline.VerifyStage) -> int:
    """Apply the requested gate. Exit codes are a contract, not a detail."""
    counts = stage.ledger.counts
    if gate == "none":
        return EXIT_OK
    if gate == "no-regression":
        return EXIT_GATE_VIOLATED if stage.regressions else EXIT_OK
    if gate == "no-broken":
        return EXIT_GATE_VIOLATED if counts[str(verdict.Verdict.BROKEN)] else EXIT_OK
    if gate == "all-kept":
        shortfall = stage.ledger.promises - counts[str(verdict.Verdict.KEPT)]
        return EXIT_GATE_VIOLATED if shortfall else EXIT_OK
    return EXIT_USAGE


def _write_list(write: Callable[[str], int], heading: str, items: tuple[str, ...]) -> None:
    if not items:
        return
    write(f"\n{heading}\n")
    for item in items:
        write(f"      {item}\n")


def _render_json(result: LoadResult) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "documents": [document.to_dict() for document in result.documents],
        "diagnostics": [diagnostic.to_dict() for diagnostic in result.diagnostics],
        "summary": _summary(result),
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)


def _summary(result: LoadResult) -> dict[str, int]:
    criteria = result.criteria
    promises = sum(1 for criterion in criteria if criterion.is_normative)
    return {
        "documents": len(result.documents),
        "criteria": len(criteria),
        "promises": promises,
        "advisory": len(criteria) - promises,
        "errors": len(result.errors),
        "warnings": len(result.diagnostics) - len(result.errors),
    }


def _render_text(result: LoadResult, *, quiet: bool, stream: TextIO) -> None:
    write = stream.write

    if not quiet:
        for document in result.documents:
            write(f"\n{document.name}  ({document.path})\n")
            for requirement in document.requirements:
                write(f"\n  {requirement.id}  {requirement.title or '(untitled)'}\n")
                for criterion in requirement.criteria:
                    marker = " " if criterion.is_normative else "~"
                    write(
                        f"    {marker} {criterion.id:<10} "
                        f"{criterion.pattern:<18} "
                        f"{criterion.modality:<10} "
                        f"{display_hash(criterion.content_hash)}\n"
                    )

        if result.diagnostics:
            write("\ndiagnostics\n")
            for diagnostic in result.diagnostics:
                write(f"  {_format_diagnostic(diagnostic)}\n")

    summary = _summary(result)
    write(
        f"\n{summary['criteria']} criteria · "
        f"{summary['promises']} promises · "
        f"{summary['advisory']} advisory · "
        f"{summary['errors']} errors · "
        f"{summary['warnings']} warnings\n"
    )
    if not quiet and summary["advisory"]:
        write("\n~ marks advisory criteria (SHOULD or MAY). These carry no verdict.\n")


def _format_diagnostic(diagnostic: Diagnostic) -> str:
    location = ""
    if diagnostic.span is not None:
        location = f"{diagnostic.span.source}:{diagnostic.span.start} "
    return f"{diagnostic.severity.upper():<7} {diagnostic.code}  {location}{diagnostic.message}"


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except KeyboardInterrupt:
        print("kept: interrupted", file=sys.stderr)
        return EXIT_INTERNAL


def run() -> None:
    sys.exit(main())


if __name__ == "__main__":
    run()
