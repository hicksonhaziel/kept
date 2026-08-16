"""Pytest plugin: registers the `verifies` marker and reports what kept needs.

Loaded automatically through the `pytest11` entry point, so a target project needs
no conftest change and never imports kept.

Reporting is opt-in: it happens only when KEPT_REPORT_OUT names a file to write.
A normal test run is unaffected.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

MARKER_NAME = "verifies"
REPORT_ENV_VAR = "KEPT_REPORT_OUT"

_MARKER_HELP = (
    "verifies(*criterion_ids): bind this test to one or more acceptance criteria, "
    "for example @pytest.mark.verifies('REQ-3.2')"
)

# Outcome precedence when a test reports at several phases. A collapse in setup or
# teardown outranks a passing call phase: a test whose fixtures exploded has not
# verified anything.
_PRECEDENCE = {"passed": 0, "skipped": 1, "failed": 2, "error": 3}

_bindings: dict[str, set[str]] = {}
_malformed: set[tuple[str, str]] = set()
_contexts: dict[str, str | None] = {}
_outcomes: dict[str, str] = {}
_collected = 0


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", _MARKER_HELP)
    _bindings.clear()
    _malformed.clear()
    _contexts.clear()
    _outcomes.clear()


def pytest_collection_modifyitems(session: Any, config: Any, items: list[Any]) -> None:
    # A pytest plugin is a per-process singleton, so module state is the simplest
    # correct place to accumulate this.
    global _collected
    _collected = len(items)

    for item in items:
        _contexts[item.nodeid] = _coverage_context(item)
        for marker in item.iter_markers(name=MARKER_NAME):
            if not marker.args:
                _malformed.add(
                    (
                        item.nodeid,
                        "verifies marker has no criterion identifier. Pass at least "
                        "one, as @pytest.mark.verifies('REQ-1.1').",
                    )
                )
                continue
            for argument in marker.args:
                if not isinstance(argument, str) or not argument.strip():
                    _malformed.add(
                        (item.nodeid, f"criterion identifier {argument!r} is not a string")
                    )
                    continue
                _bindings.setdefault(argument.strip(), set()).add(item.nodeid)


def pytest_runtest_logreport(report: Any) -> None:
    if report.when == "call":
        outcome = "passed" if report.passed else "skipped" if report.skipped else "failed"
    elif report.failed:
        outcome = "error"
    elif report.when == "setup" and report.skipped:
        outcome = "skipped"
    else:
        return

    existing = _outcomes.get(report.nodeid)
    if existing is None or _PRECEDENCE[outcome] > _PRECEDENCE[existing]:
        _outcomes[report.nodeid] = outcome


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    destination = os.environ.get(REPORT_ENV_VAR)
    if not destination:
        return

    payload = {
        "bindings": [
            {"criterion": criterion, "oracles": sorted(oracles)}
            for criterion, oracles in sorted(_bindings.items())
        ],
        "malformed": [
            {"oracle": oracle, "problem": problem} for oracle, problem in sorted(_malformed)
        ],
        "collected": _collected,
        "tests": {
            nodeid: {
                "context": _contexts.get(nodeid),
                "outcome": _outcomes.get(nodeid, "notrun"),
            }
            for nodeid in sorted(_contexts)
        },
    }

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _coverage_context(item: Any) -> str | None:
    """Compute the context name coverage.py will record for this test.

    Coverage's `dynamic_context = test_function` names a context after the running
    function's module and qualified name. Deriving the same string here, from the
    same objects, avoids reconstructing it from the node ID later: node IDs are file
    paths and depend on package layout, whereas this is exact.
    """
    try:
        return f"{item.module.__name__}.{item.obj.__qualname__}"
    except (AttributeError, ImportError):
        return None
