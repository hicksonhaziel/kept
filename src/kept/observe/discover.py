"""Harvest bindings by collecting a target project's tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from kept.bindings import Binding, BindingSet, Origin
from kept.observe.plugin import OUTPUT_ENV_VAR

# Collection only. No test body runs, so discovery cannot be slowed down or
# broken by the suite it is inspecting.
_COLLECT_ARGS = ("--collect-only", "-q", "-p", "no:cacheprovider")


class DiscoveryError(RuntimeError):
    """Raised when a target project's tests could not be collected."""


@dataclass(frozen=True, slots=True)
class Discovery:
    bindings: BindingSet
    collected: int
    malformed: tuple[tuple[str, str], ...] = ()


def discover_bindings(root: Path, *, tests: str | None = None) -> Discovery:
    """Collect `root`'s tests and read every `verifies` marker found.

    Args:
        root: The target project's root directory.
        tests: Optional path to restrict collection to.
    """
    if not root.is_dir():
        msg = f"no such directory: {root}"
        raise DiscoveryError(msg)

    with tempfile.TemporaryDirectory() as scratch:
        output = Path(scratch) / "bindings.json"
        environment = {**os.environ, OUTPUT_ENV_VAR: str(output)}

        command = [sys.executable, "-m", "pytest", *_COLLECT_ARGS]
        if tests is not None:
            command.append(tests)

        # Fixed argv, no shell, so the command cannot be injected into.
        result = subprocess.run(
            command,
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        if not output.is_file():
            detail = (result.stderr or result.stdout or "").strip()
            msg = (
                f"pytest collected nothing in {root} (exit {result.returncode}). "
                f"Check that the project has tests and that pytest can import them."
                + (f"\n{detail[-2000:]}" if detail else "")
            )
            raise DiscoveryError(msg)

        payload = json.loads(output.read_text(encoding="utf-8"))

    bindings = tuple(
        Binding(
            criterion=entry["criterion"],
            oracles=tuple(entry["oracles"]),
            origin=Origin.ANNOTATION,
        )
        for entry in payload["bindings"]
    )
    malformed = tuple((entry["oracle"], entry["problem"]) for entry in payload["malformed"])

    return Discovery(
        bindings=BindingSet(bindings=bindings),
        collected=int(payload["collected"]),
        malformed=malformed,
    )
