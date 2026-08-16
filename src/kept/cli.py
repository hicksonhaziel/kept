"""Command-line entry point. The only module that calls `sys.exit`."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from kept import __version__, bindings
from kept.diagnostics import Diagnostic
from kept.ids import SCHEMA_VERSION, display_hash
from kept.loader import LoadResult, SpecNotFoundError, load_all, load_document
from kept.observe import DiscoveryError, discover_bindings

EXIT_OK = 0
EXIT_GATE_VIOLATED = 1
EXIT_USAGE = 2
EXIT_INTERNAL = 3


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
    root: Path = args.root

    try:
        spec = load_all(root)
        discovery = discover_bindings(root, tests=args.tests)
        manual = bindings.load(bindings.bindings_path(root))
    except (DiscoveryError, bindings.BindingsError) as error:
        print(f"kept: {error}", file=sys.stderr)
        return EXIT_USAGE

    merged = bindings.merge(discovery.bindings, manual.human_authored())
    criteria = [criterion.id for criterion in spec.criteria if criterion.is_normative]
    unbound = merged.unbound(criteria)
    orphaned = merged.orphaned(criterion.id for criterion in spec.criteria)

    if args.write:
        bindings.save(merged, bindings.bindings_path(root))

    report = {
        "schema_version": SCHEMA_VERSION,
        "promises": len(criteria),
        "bound": len([c for c in criteria if c in merged.bound_criteria]),
        "unbound": list(unbound),
        "orphaned": list(orphaned),
        "unverifiable": [entry.to_dict() for entry in merged.unverifiable],
        "oracles": len(merged.all_oracles),
        "tests_collected": discovery.collected,
        "malformed": [{"oracle": o, "problem": p} for o, p in discovery.malformed],
    }

    if args.as_json:
        print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False))
        return EXIT_GATE_VIOLATED if unbound or orphaned or discovery.malformed else EXIT_OK

    write = sys.stdout.write
    for binding in merged.bindings:
        if binding.criterion in orphaned:
            continue
        write(f"\n  {binding.criterion}  ({binding.origin})\n")
        for oracle in binding.oracles:
            write(f"      {oracle}\n")

    if unbound:
        write("\nunbound promises (nothing claims to verify these)\n")
        for criterion in unbound:
            write(f"      {criterion}\n")

    if orphaned:
        write("\norphaned bindings (criterion no longer exists in the spec)\n")
        for criterion in orphaned:
            write(f"      {criterion}\n")

    for oracle, problem in discovery.malformed:
        write(f"\n  WARNING {oracle}\n      {problem}\n")

    write(
        f"\n{report['promises']} promises · "
        f"{report['bound']} bound · "
        f"{len(unbound)} unbound · "
        f"{report['oracles']} oracles across {report['tests_collected']} collected tests\n"
    )
    if args.write:
        write(f"\nwrote {bindings.bindings_path(root)}\n")

    # Unbound promises are not a crash: kept reported honestly. They are a gate
    # violation, because an unbound promise cannot be verified.
    return EXIT_GATE_VIOLATED if unbound or orphaned or discovery.malformed else EXIT_OK


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
