"""Adapters that observe a target project by collecting and running its tests."""

from __future__ import annotations

from kept.observe.runner import (
    CoverageResult,
    ObservationError,
    Report,
    RunResult,
    TestRecord,
    collect,
    resolve_interpreter,
    run,
)
from kept.observe.vacuity import OracleShape, scan_files

__all__ = [
    "CoverageResult",
    "ObservationError",
    "OracleShape",
    "Report",
    "RunResult",
    "TestRecord",
    "collect",
    "resolve_interpreter",
    "run",
    "scan_files",
]
