"""Project defaults from `.kept/config.toml`, so a flag is stated once, not per run.

An input, not an artefact: nothing here reaches a verdict. Values that could change
a verdict — threshold and cap — are still recorded in the ledger, so a reader can
reproduce a number without seeing this file.

Precedence is explicit flag, then this file, then the built-in default.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kept.diagnostics import Diagnostic, Severity

CONFIG_FILENAME = "config.toml"
KEPT_DIRECTORY = ".kept"
SUPPORTED_VERSION = 1


class ConfigError(ValueError):
    """Raised when the configuration file cannot be read at all."""


#: Every key a project may set, and the type it must hold. The argparse
#: destination differs from the key where the flag is repeatable or renamed.
_KEYS: dict[str, tuple[type, str]] = {
    "spec": (list, "specs"),
    "tests": (str, "tests"),
    "source": (str, "source"),
    "python": (str, "python"),
    "cap": (int, "cap"),
    "workers": (int, "workers"),
    "timeout": (float, "timeout"),
    "threshold": (float, "threshold"),
    "gate": (str, "gate"),
    "show_unpinned": (int, "show_unpinned"),
}

#: Which keys each command understands. Explicit rather than derived from the
#: parser, so a key silently applying to the wrong command is impossible.
_BY_COMMAND: dict[str, tuple[str, ...]] = {
    "parse": (),
    "bind": ("spec", "tests", "python"),
    "observe": ("spec", "tests", "python", "source"),
    "attack": ("spec", "tests", "python", "source", "cap", "workers", "timeout"),
    "verify": (
        "spec",
        "tests",
        "python",
        "source",
        "cap",
        "workers",
        "timeout",
        "threshold",
        "gate",
        "show_unpinned",
    ),
    "prompt": ("spec",),
    "serve": ("spec", "tests", "python", "source"),
}


@dataclass(frozen=True, slots=True)
class Config:
    """What a project asked for, and anything wrong with the asking."""

    path: str | None = None
    values: tuple[tuple[str, Any], ...] = field(default_factory=tuple)
    diagnostics: tuple[Diagnostic, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> tuple[Diagnostic, ...]:
        return tuple(diagnostic for diagnostic in self.diagnostics if diagnostic.is_error)

    def defaults_for(self, command: str) -> dict[str, Any]:
        """The argparse defaults this command should adopt from the file."""
        allowed = _BY_COMMAND.get(command, ())
        return {_KEYS[key][1]: value for key, value in self.values if key in allowed}


def config_path(root: Path) -> Path:
    return root / KEPT_DIRECTORY / CONFIG_FILENAME


def load(root: Path) -> Config:
    """Read `.kept/config.toml`. A missing file is absence, not an error."""
    path = config_path(root)
    if not path.is_file():
        return Config()

    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        msg = f"{path} is not valid TOML: {error}"
        raise ConfigError(msg) from error
    except OSError as error:
        msg = f"{path} could not be read: {error}"
        raise ConfigError(msg) from error

    return _interpret(payload, source=path.as_posix())


def _interpret(payload: Mapping[str, Any], *, source: str) -> Config:
    diagnostics: list[Diagnostic] = []
    values: list[tuple[str, Any]] = []

    version = payload.get("version", SUPPORTED_VERSION)
    if version != SUPPORTED_VERSION:
        diagnostics.append(
            _problem(
                "C004",
                f"{source} declares version {version!r}, which this kept cannot read. "
                f"Set version = {SUPPORTED_VERSION}, or upgrade kept.",
            )
        )
        return Config(path=source, diagnostics=tuple(diagnostics))

    for key in sorted(payload):
        if key == "version":
            continue
        if key not in _KEYS:
            known = ", ".join(sorted(_KEYS))
            diagnostics.append(
                _problem(
                    "C001",
                    f"{source} sets unknown key {key!r}. Remove it or correct the "
                    f"spelling. Known keys: {known}.",
                )
            )
            continue

        expected, _ = _KEYS[key]
        raw = payload[key]
        try:
            values.append((key, _coerce(key, raw, expected)))
        except (TypeError, ValueError):
            diagnostics.append(
                _problem(
                    "C002",
                    f"{source} sets {key} = {raw!r}, which is not a "
                    f"{expected.__name__}. Correct the value.",
                )
            )

    return Config(
        path=source,
        values=tuple(sorted(values)),
        diagnostics=tuple(diagnostics),
    )


def _coerce(key: str, raw: Any, expected: type) -> Any:
    """Turn a TOML value into what the CLI expects, or raise."""
    if expected is list:
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            msg = f"{key} must be a list of strings"
            raise TypeError(msg)
        return [Path(item) for item in raw]
    if expected is str:
        if not isinstance(raw, str):
            msg = f"{key} must be a string"
            raise TypeError(msg)
        return Path(raw) if key == "python" else raw
    if isinstance(raw, bool):
        # bool is an int in Python, and `cap = true` is never what was meant.
        msg = f"{key} must be a number"
        raise TypeError(msg)
    if expected is int:
        if not isinstance(raw, int):
            msg = f"{key} must be an integer"
            raise TypeError(msg)
        return raw
    if not isinstance(raw, int | float):
        msg = f"{key} must be a number"
        raise TypeError(msg)
    return float(raw)


def _problem(code: str, message: str) -> Diagnostic:
    """Configuration problems are errors: a key that does nothing is a trap.

    A misspelled `treshold` that is silently ignored would leave the reader
    believing a threshold was applied. Better to refuse the run.
    """
    return Diagnostic(code=code, severity=Severity.ERROR, message=message)
