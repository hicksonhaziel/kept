"""Run a target project's tests and read back coverage and outcomes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kept.observe.plugin import REPORT_ENV_VAR

# Collection only: no test body runs, so binding discovery cannot be slowed down
# or broken by the suite it is inspecting.
_COLLECT_ARGS = ("--collect-only", "-q", "-p", "no:cacheprovider")

_COVERAGE_RC = """
[run]
branch = True
dynamic_context = test_function
relative_files = True
source = {source}

[report]
show_missing = False
"""


class ObservationError(RuntimeError):
    """Raised when a target project's tests could not be collected or run."""


@dataclass(frozen=True, slots=True)
class TestRecord:
    """One test as pytest saw it."""

    nodeid: str
    context: str | None
    outcome: str

    @property
    def passed(self) -> bool:
        return self.outcome == "passed"

    @property
    def ran(self) -> bool:
        return self.outcome in {"passed", "failed"}


@dataclass(frozen=True, slots=True)
class Report:
    """What the pytest plugin reported."""

    bindings: tuple[tuple[str, tuple[str, ...]], ...] = ()
    malformed: tuple[tuple[str, str], ...] = ()
    tests: tuple[TestRecord, ...] = ()
    collected: int = 0

    def by_nodeid(self) -> dict[str, TestRecord]:
        return {record.nodeid: record for record in self.tests}


@dataclass(frozen=True, slots=True)
class CoverageResult:
    """Per-test line coverage, keyed by coverage context then by source file."""

    lines: dict[str, dict[str, tuple[int, ...]]] = field(default_factory=dict)
    measured_files: tuple[str, ...] = ()

    def for_context(self, context: str) -> dict[str, tuple[int, ...]]:
        return self.lines.get(context, {})


@dataclass(frozen=True, slots=True)
class RunResult:
    report: Report
    coverage: CoverageResult
    exit_code: int
    output: str


@dataclass(frozen=True, slots=True)
class TestRun:
    """One targeted test run, as used when probing a mutant."""

    report: Report
    timed_out: bool = False
    exit_code: int = 0


def run_tests(
    root: Path,
    nodeids: Sequence[str],
    *,
    timeout: float | None = None,
) -> TestRun:
    """Run exactly the given tests, with no coverage instrumentation.

    A timeout is reported rather than raised: a mutant that makes the suite hang
    has changed behaviour observably, which is a kill, not a failure of kept.
    """
    if not nodeids:
        return TestRun(report=Report())

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "--no-header",
        *nodeids,
    ]

    with tempfile.TemporaryDirectory() as scratch:
        destination = Path(scratch) / "report.json"
        environment = {**os.environ, REPORT_ENV_VAR: str(destination)}

        try:
            # Fixed argv and no shell, so the command cannot be injected into.
            completed = subprocess.run(
                command,
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return TestRun(report=Report(), timed_out=True, exit_code=-1)

        if not destination.is_file():
            return TestRun(report=Report(), exit_code=completed.returncode)

        payload = json.loads(destination.read_text(encoding="utf-8"))

    return TestRun(report=_parse_report(payload), exit_code=completed.returncode)


def collect(root: Path, *, tests: str | None = None) -> Report:
    """Collect tests without running them, to harvest bindings."""
    command = [sys.executable, "-m", "pytest", *_COLLECT_ARGS]
    if tests is not None:
        command.append(tests)
    return _invoke(root, command, expect_report=True).report


def run(root: Path, *, tests: str | None = None, source: str = ".") -> RunResult:
    """Run the suite under coverage with per-test contexts."""
    with tempfile.TemporaryDirectory() as scratch:
        rcfile = Path(scratch) / "coverage.rc"
        rcfile.write_text(_COVERAGE_RC.format(source=source), encoding="utf-8")
        datafile = Path(scratch) / "coverage.data"

        command = [
            sys.executable,
            "-m",
            "coverage",
            "run",
            f"--rcfile={rcfile}",
            f"--data-file={datafile}",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
        ]
        if tests is not None:
            command.append(tests)

        result = _invoke(root, command, expect_report=True)
        coverage = _read_coverage(datafile)

    return RunResult(
        report=result.report,
        coverage=coverage,
        exit_code=result.exit_code,
        output=result.output,
    )


def _invoke(root: Path, command: list[str], *, expect_report: bool) -> RunResult:
    if not root.is_dir():
        msg = f"no such directory: {root}"
        raise ObservationError(msg)

    with tempfile.TemporaryDirectory() as scratch:
        destination = Path(scratch) / "report.json"
        environment = {**os.environ, REPORT_ENV_VAR: str(destination)}

        # Fixed argv and no shell, so the command cannot be injected into.
        completed = subprocess.run(
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (completed.stdout or "") + (completed.stderr or "")

        if expect_report and not destination.is_file():
            msg = (
                f"pytest produced no report in {root} (exit {completed.returncode}). "
                f"Check that the project has tests and that pytest can import them."
                + (f"\n{output.strip()[-2000:]}" if output.strip() else "")
            )
            raise ObservationError(msg)

        payload = json.loads(destination.read_text(encoding="utf-8"))

    return RunResult(
        report=_parse_report(payload),
        coverage=CoverageResult(),
        exit_code=completed.returncode,
        output=output,
    )


def _parse_report(payload: Mapping[str, Any]) -> Report:
    raw_bindings = payload.get("bindings") or []
    raw_malformed = payload.get("malformed") or []
    raw_tests = payload.get("tests") or {}

    return Report(
        bindings=tuple(
            (entry["criterion"], tuple(entry["oracles"]))
            for entry in raw_bindings
            if isinstance(entry, dict)
        ),
        malformed=tuple(
            (entry["oracle"], entry["problem"])
            for entry in raw_malformed
            if isinstance(entry, dict)
        ),
        tests=tuple(
            TestRecord(
                nodeid=nodeid,
                context=record.get("context"),
                outcome=record.get("outcome", "notrun"),
            )
            for nodeid, record in sorted(raw_tests.items())
            if isinstance(record, dict)
        ),
        collected=int(payload.get("collected", 0) or 0),
    )


def _read_coverage(datafile: Path) -> CoverageResult:
    """Read per-context line data out of the coverage database."""
    from coverage.sqldata import CoverageData

    data = CoverageData(basename=str(datafile))
    data.read()

    files = tuple(sorted(data.measured_files()))
    lines: dict[str, dict[str, tuple[int, ...]]] = {}

    for context in sorted(data.measured_contexts()):
        if not context:
            # The empty context holds import-time execution, which belongs to no
            # test and must never be attributed to a criterion.
            continue
        data.set_query_contexts([context])
        per_file = {
            path: tuple(sorted(measured))
            for path in files
            if (measured := data.lines(path))
        }
        if per_file:
            lines[context] = per_file

    return CoverageResult(lines=lines, measured_files=files)
