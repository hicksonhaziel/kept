"""Command-line entry point. The only module that calls `sys.exit`."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from kept import __version__
from kept.diagnostics import Diagnostic
from kept.ids import SCHEMA_VERSION, display_hash
from kept.loader import LoadResult, SpecNotFoundError, load_all, load_document

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
