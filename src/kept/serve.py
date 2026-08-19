"""MCP server: hand an agent kept's evidence, over stdio, offline.

An adapter, not a verdict path. Every tool either reads the committed ledger or
runs the same pipeline `kept verify` runs. Nothing here decides anything, and the
server accepts no filesystem paths from the caller: the project root and the
specification are fixed when the server starts, so an agent cannot point kept at
somewhere else.

Behind the optional `mcp` extra. Absent, `kept serve` fails loudly rather than
degrading into something that only looks like a server.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from kept import __version__, attack, pipeline, report
from kept import ledger as ledger_module
from kept.loader import load as load_specs

if TYPE_CHECKING:  # pragma: no cover - import only for the annotation
    from mcp.server import MCPServer

SERVER_NAME = "kept"

INSTRUCTIONS = """\
kept reports, per acceptance criterion, which promises the code actually keeps.

Verdicts come only from `verify`, which parses the criteria, runs the bound tests
under coverage, mutates the lines those tests cover, and reruns them. It is
deterministic and offline. You cannot set a verdict, and neither can this server.

`remediation_brief` restates recorded evidence and names the change that would
answer it. It is a suggestion for you to act on, not a verdict and not verified
advice. After acting on one, call `verify` again: that is the only thing that
moves a verdict.
"""


class MissingExtraError(RuntimeError):
    """Raised when the optional MCP dependency is not installed."""


@dataclass(frozen=True, slots=True)
class Config:
    """What the server is allowed to look at. Fixed at startup, never per call."""

    root: Path
    specs: tuple[Path, ...] = ()
    tests: str | None = None
    source: str = "."
    python: Path | None = None

    @property
    def spec_paths(self) -> tuple[Path, ...] | None:
        return self.specs or None


def list_promises(config: Config) -> dict[str, Any]:
    """Every criterion in the specification, with its recorded verdict if any."""
    result = load_specs(config.root, specs=config.spec_paths)
    stored = ledger_module.load(ledger_module.ledger_path(config.root))

    promises = []
    for criterion in result.criteria:
        ruling = stored.get(criterion.id) if stored is not None else None
        promises.append(
            {
                "criterion": criterion.id,
                "text": criterion.text,
                "normative": criterion.is_normative,
                "pattern": str(criterion.pattern),
                "modality": str(criterion.modality),
                "content_hash": criterion.content_hash,
                "source": criterion.span.source,
                "recorded_verdict": str(ruling.verdict) if ruling is not None else None,
            }
        )

    return {
        "promises": promises,
        "diagnostics": [diagnostic.to_dict() for diagnostic in result.diagnostics],
        "note": (
            "A recorded verdict comes from the committed ledger and may predate the "
            "current code. Call verify to judge the working tree."
        ),
    }


def read_ledger(config: Config) -> dict[str, Any]:
    """The committed ledger, as recorded. Runs nothing."""
    path = ledger_module.ledger_path(config.root)
    stored = ledger_module.load(path)
    if stored is None:
        return {
            "ledger": None,
            "note": (
                f"No ledger at {path.name}. Call verify with write=true to produce "
                f"one; there is no evidence to read until then."
            ),
        }
    return {
        "ledger": stored.to_dict(),
        "headline": stored.headline(),
        "note": (
            "Evidence as committed. It describes the commit recorded in it, not necessarily HEAD."
        ),
    }


def remediation_brief(config: Config, criterion: str) -> str:
    """The brief for one promise: recorded evidence and the change it asks for."""
    path = ledger_module.ledger_path(config.root)
    stored = ledger_module.load(path)
    if stored is None:
        msg = (
            f"no ledger at {path}. Call verify with write=true first: a brief "
            f"restates recorded evidence and invents none"
        )
        raise report.UnknownCriterionError(msg)

    parsed = load_specs(config.root, specs=config.spec_paths)
    match = next((c for c in parsed.criteria if c.id == criterion), None)

    return report.render_brief(
        stored,
        criterion,
        criterion=match,
        command=f"kept verify --root {config.root} --write",
        at_commit=ledger_module.current_commit(config.root),
    )


def verify(
    config: Config,
    *,
    cap: int = attack.DEFAULT_CAP,
    write: bool = False,
) -> dict[str, Any]:
    """Run the whole pipeline and return fresh verdicts."""
    stage = pipeline.verify(
        config.root,
        tests=config.tests,
        source=config.source,
        cap=cap,
        python=config.python,
        specs=config.spec_paths,
    )

    written: list[str] = []
    if write:
        ledger_module.save(stage.ledger, ledger_module.ledger_path(config.root))
        written.append(ledger_module.ledger_path(config.root).name)
        evidence = config.root / "EVIDENCE.md"
        evidence.write_text(report.render_evidence(stage.ledger), encoding="utf-8")
        written.append(evidence.name)

    return {
        "ledger": stage.ledger.to_dict(),
        "headline": stage.ledger.headline(),
        "drift": stage.drift.to_dict(),
        "regressions": [regression.to_dict() for regression in stage.regressions],
        "written": written,
        "note": (
            "Evidence, not proof. A killed mutant is not a guarantee of correctness, "
            "and a KEPT verdict is bounded by the mutation operators kept applied."
        ),
    }


def build_server(config: Config) -> MCPServer:
    """Register the tools. Raises MissingExtraError without the `mcp` extra."""
    try:
        from mcp.server import MCPServer
        from mcp.types import ToolAnnotations
    except ImportError as error:  # pragma: no cover - depends on the environment
        msg = (
            "kept serve needs the optional MCP dependency. Install it with "
            "`uv sync --extra mcp`, or `pip install 'kept-cli[mcp]'`."
        )
        raise MissingExtraError(msg) from error

    server = MCPServer(
        name=SERVER_NAME,
        version=__version__,
        instructions=INSTRUCTIONS,
    )

    read_only = ToolAnnotations(read_only_hint=True, open_world_hint=False)

    @server.tool(
        name="list_promises",
        description=(
            "List every acceptance criterion kept can read, with its identifier, "
            "wording, and the verdict recorded in the committed ledger. Reads files "
            "only."
        ),
        annotations=read_only,
    )
    def _list_promises() -> dict[str, Any]:
        return list_promises(config)

    @server.tool(
        name="read_ledger",
        description=(
            "Return the committed evidence ledger: one verdict per promise, with the "
            "test identifiers, covered lines, and surviving mutants behind it. Runs "
            "no tests."
        ),
        annotations=read_only,
    )
    def _read_ledger() -> dict[str, Any]:
        return read_ledger(config)

    @server.tool(
        name="remediation_brief",
        description=(
            "Explain what one promise's recorded evidence says and name the change "
            "that would answer it. A suggestion to act on, rendered from the ledger "
            "with no model involved. It cannot change a verdict; only verify can."
        ),
        annotations=read_only,
    )
    def _remediation_brief(criterion: str) -> str:
        return remediation_brief(config, criterion)

    @server.tool(
        name="verify",
        description=(
            "Reach a verdict on every promise: parse the criteria, run the bound "
            "tests under coverage, mutate the lines they cover, and rerun them. "
            "Deterministic and offline. Slow: it executes the test suite many times. "
            "This is the only tool that can move a verdict."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False, destructive_hint=False, open_world_hint=False
        ),
    )
    def _verify(cap: int = attack.DEFAULT_CAP, write: bool = False) -> dict[str, Any]:
        return verify(config, cap=cap, write=write)

    return server


def serve(config: Config) -> None:
    """Serve over stdio until the client disconnects."""
    build_server(config).run(transport="stdio")
