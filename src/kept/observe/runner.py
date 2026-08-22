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


def resolve_interpreter(root: Path, explicit: str | Path | None = None) -> Path:
    """Find the interpreter that can run the target project's tests.

    kept must never run a project's tests with its own interpreter. kept may be
    installed as an isolated tool, and even when it is not, the project's tests
    need the project's dependencies, which only the project's environment has.

    Search order, first hit wins:

    1. an interpreter given explicitly
    2. the currently activated virtual environment
    3. `.venv` in the project root
    4. `.venv` in the nearest ancestor directory that has one
    5. the interpreter running kept, as a last resort

    The result is always absolute. A relative path would resolve against whatever
    directory the caller happens to be in, and the mutation stage runs from a
    temporary worktree, where `.venv/bin/python` means nothing.
    """
    if explicit is not None:
        candidate = Path(explicit)
        if not candidate.is_absolute():
            # Interpret against the project root first, then the caller's own
            # directory, so both `--python .venv/bin/python` and a path the user
            # can see in their shell work.
            for base in (root, Path.cwd()):
                resolved_candidate = (base / candidate).resolve()
                if resolved_candidate.exists():
                    return resolved_candidate
        elif candidate.exists():
            return candidate

        msg = (
            f"no interpreter at {explicit}. Give --python a path to the python "
            f"executable inside your project's virtual environment, for example "
            f"{root / '.venv' / 'bin' / 'python'}"
        )
        raise ObservationError(msg)

    activated = os.environ.get("VIRTUAL_ENV")
    if activated:
        found = _interpreter_in(Path(activated))
        if found is not None:
            return found

    resolved = root.resolve()
    for directory in (resolved, *resolved.parents):
        found = _interpreter_in(directory / ".venv")
        if found is not None:
            return found

    return Path(sys.executable)


def _interpreter_in(environment: Path) -> Path | None:
    for relative in ("bin/python", "bin/python3", "Scripts/python.exe"):
        candidate = environment / relative
        if candidate.is_file():
            return candidate
    return None


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
    python: Path | None = None,
    import_roots: Sequence[Path] = (),
) -> TestRun:
    """Run exactly the given tests, with no coverage instrumentation.

    A timeout is reported rather than raised: a mutant that makes the suite hang
    has changed behaviour observably, which is a kill, not a failure of kept.

    Args:
        import_roots: Directories to put ahead of everything else on the import
            path. Load-bearing when the project under audit is installed into the
            environment: without them a mutated copy is never imported and every
            mutant looks harmless.
    """
    if not nodeids:
        return TestRun(report=Report())

    interpreter = python if python is not None else resolve_interpreter(root)
    command = [
        str(interpreter),
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
        if import_roots:
            existing = environment.get("PYTHONPATH")
            entries = [str(path) for path in import_roots]
            if existing:
                entries.append(existing)
            environment["PYTHONPATH"] = os.pathsep.join(entries)

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
        except OSError as error:
            # A missing or unexecutable interpreter is the user's environment, not
            # a defect in kept, so it must not surface as a traceback.
            msg = f"could not run {command[0]}: {error}"
            raise ObservationError(msg) from error

        if not destination.is_file():
            return TestRun(report=Report(), exit_code=completed.returncode)

        payload = json.loads(destination.read_text(encoding="utf-8"))

    return TestRun(report=_parse_report(payload), exit_code=completed.returncode)


def collect(root: Path, *, tests: str | None = None, python: Path | None = None) -> Report:
    """Collect tests without running them, to harvest bindings."""
    interpreter = python if python is not None else resolve_interpreter(root)
    command = [str(interpreter), "-m", "pytest", *_COLLECT_ARGS]
    if tests is not None:
        command.append(tests)
    return _invoke(root, command, interpreter, expect_report=True).report


def run(
    root: Path,
    *,
    tests: str | None = None,
    source: str = ".",
    python: Path | None = None,
) -> RunResult:
    """Run the suite under coverage with per-test contexts."""
    interpreter = python if python is not None else resolve_interpreter(root)

    with tempfile.TemporaryDirectory() as scratch:
        rcfile = Path(scratch) / "coverage.rc"
        rcfile.write_text(_COVERAGE_RC.format(source=source), encoding="utf-8")
        datafile = Path(scratch) / "coverage.data"

        command = [
            str(interpreter),
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

        result = _invoke(root, command, interpreter, expect_report=True)
        coverage = _read_coverage(datafile)

    return RunResult(
        report=result.report,
        coverage=coverage,
        exit_code=result.exit_code,
        output=result.output,
    )


def _invoke(
    root: Path,
    command: list[str],
    interpreter: Path,
    *,
    expect_report: bool,
) -> RunResult:
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
            raise ObservationError(_failure_message(root, interpreter, completed, output))

        # pytest: 2 interrupted (a collection error), 3 internal, 4 usage, 5 no
        # tests. Test *failures* are exit 1 and expected — they become BROKEN
        # verdicts. The rest mean the suite never ran, and proceeding would report
        # every oracle as notrun, which reads like a verdict about the tests.
        if completed.returncode in _SUITE_DID_NOT_RUN:
            raise ObservationError(_did_not_run_message(root, completed.returncode, output))

        payload = json.loads(destination.read_text(encoding="utf-8"))

    return RunResult(
        report=_parse_report(payload),
        coverage=CoverageResult(),
        exit_code=completed.returncode,
        output=output,
    )


#: pytest exit codes that mean the suite never ran, so there is nothing to observe.
_SUITE_DID_NOT_RUN = frozenset({2, 3, 4, 5})

_DID_NOT_RUN_CAUSE = {
    2: "collection was interrupted, usually an import error in a test module",
    3: "pytest reported an internal error",
    4: "the pytest command line was rejected",
    5: "no tests were collected",
}


def _did_not_run_message(root: Path, code: int, output: str) -> str:
    trimmed = output.strip()
    tail = "\n\n" + "\n".join(trimmed.splitlines()[-12:]) if trimmed else ""
    return (
        f"the test suite in {root} did not run: {_DID_NOT_RUN_CAUSE.get(code, 'unknown')} "
        f"(pytest exit {code}). Fix the suite so `pytest` runs on its own, then try "
        f"again. kept reports no verdict rather than reporting every promise as "
        f"unverified, which would misattribute a broken environment to your tests."
        f"{tail}"
    )


def _failure_message(
    root: Path,
    interpreter: Path,
    completed: subprocess.CompletedProcess[str],
    output: str,
) -> str:
    """Explain a failed run in terms of the fix, not the symptom."""
    trimmed = output.strip()

    if "No module named 'pytest'" in trimmed or "No module named pytest" in trimmed:
        return (
            f"The interpreter kept chose cannot import pytest:\n"
            f"    {interpreter}\n\n"
            f"kept runs your project's tests with your project's interpreter, because "
            f"the tests need your project's dependencies. Pick one:\n"
            f"    kept ... --python /path/to/your/.venv/bin/python\n"
            f"    activate the project's virtual environment first\n"
            f"    run from a directory whose .venv has pytest installed"
        )

    if "No module named 'coverage'" in trimmed:
        return (
            f"The interpreter kept chose cannot import coverage:\n"
            f"    {interpreter}\n\n"
            f"Install coverage into that environment, or point kept at one that has "
            f"it with --python."
        )

    return (
        f"pytest produced no report in {root} (exit {completed.returncode}).\n"
        f"    interpreter: {interpreter}\n\n"
        f"Check that the project has tests, that pytest can import them, and that "
        f"the interpreter above is the one your project uses. Override it with "
        f"--python if not." + (f"\n\n{trimmed[-2000:]}" if trimmed else "")
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
            path: tuple(sorted(measured)) for path in files if (measured := data.lines(path))
        }
        if per_file:
            lines[context] = per_file

    return CoverageResult(lines=lines, measured_files=files)
