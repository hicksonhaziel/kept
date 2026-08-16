"""Pytest plugin that registers the `verifies` marker and harvests bindings.

Loaded automatically through the `pytest11` entry point, so a target project needs
no conftest changes and never imports kept.

Harvesting is opt-in: it happens only when KEPT_BINDINGS_OUT names a file to write.
A normal test run is unaffected.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

MARKER_NAME = "verifies"
OUTPUT_ENV_VAR = "KEPT_BINDINGS_OUT"

_MARKER_HELP = (
    "verifies(*criterion_ids): bind this test to one or more acceptance criteria, "
    "for example @pytest.mark.verifies('REQ-3.2')"
)


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", _MARKER_HELP)


def pytest_collection_modifyitems(session: Any, config: Any, items: list[Any]) -> None:
    destination = os.environ.get(OUTPUT_ENV_VAR)
    if not destination:
        return

    discovered: dict[str, set[str]] = {}
    malformed: list[dict[str, str]] = []

    for item in items:
        for marker in item.iter_markers(name=MARKER_NAME):
            if not marker.args:
                malformed.append(
                    {
                        "oracle": item.nodeid,
                        "problem": (
                            "verifies marker has no criterion identifier. "
                            "Pass at least one, as @pytest.mark.verifies('REQ-1.1')."
                        ),
                    }
                )
                continue
            for argument in marker.args:
                if not isinstance(argument, str) or not argument.strip():
                    malformed.append(
                        {
                            "oracle": item.nodeid,
                            "problem": f"criterion identifier {argument!r} is not a string",
                        }
                    )
                    continue
                discovered.setdefault(argument.strip(), set()).add(item.nodeid)

    payload = {
        "bindings": [
            {"criterion": criterion, "oracles": sorted(oracles)}
            for criterion, oracles in sorted(discovered.items())
        ],
        "malformed": sorted(malformed, key=lambda entry: (entry["oracle"], entry["problem"])),
        "collected": len(items),
    }

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
