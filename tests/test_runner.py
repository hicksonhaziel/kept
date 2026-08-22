"""Interpreter resolution and the process-boundary exit-code contract.

Both cases here were found by running kept against a real project — a relative
`--python` crashed with a traceback once the mutation stage changed directory.

Unbound on purpose: neither has an acceptance criterion yet.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

from kept import cli
from kept.observe import ObservationError, resolve_interpreter


def _parser_raising(handler: object) -> argparse.ArgumentParser:
    """A parser whose only job is to hand main() a handler that misbehaves."""
    parser = argparse.ArgumentParser()
    parser.set_defaults(handler=handler)
    return parser


def _fake_interpreter(root: Path, relative: str = ".venv/bin/python") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def test_a_relative_interpreter_is_resolved_against_the_project_root(tmp_path: Path) -> None:
    """The mutation stage runs from a temporary worktree, where `.venv/bin/python`
    would otherwise mean nothing."""
    expected = _fake_interpreter(tmp_path)

    resolved = resolve_interpreter(tmp_path, ".venv/bin/python")

    assert resolved == expected.resolve()
    assert resolved.is_absolute()


def test_an_absolute_interpreter_is_taken_as_given(tmp_path: Path) -> None:
    expected = _fake_interpreter(tmp_path)

    assert resolve_interpreter(tmp_path, expected) == expected


def test_an_interpreter_that_does_not_exist_is_refused_with_advice(tmp_path: Path) -> None:
    with pytest.raises(ObservationError, match="no interpreter at"):
        resolve_interpreter(tmp_path, "does/not/exist/python")


def test_the_current_interpreter_is_the_last_resort(tmp_path: Path) -> None:
    assert resolve_interpreter(tmp_path).is_absolute()


def test_an_unexpected_failure_exits_three_and_says_no_ledger_was_written(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 3 is a contract: an internal error, and no ledger written. A traceback
    on the way out would break both halves of that promise."""

    def explode(_: argparse.Namespace) -> int:
        raise RuntimeError("something nobody predicted")

    monkeypatch.setattr(cli, "build_parser", lambda *_, **__: _parser_raising(explode))

    assert cli.main([]) == cli.EXIT_INTERNAL

    captured = capsys.readouterr()
    assert "internal error: RuntimeError: something nobody predicted" in captured.err
    assert "no ledger was written" in captured.err
    assert "Traceback" not in captured.err


def test_a_keyboard_interrupt_is_not_reported_as_an_internal_defect(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def interrupt(_: argparse.Namespace) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "build_parser", lambda *_, **__: _parser_raising(interrupt))

    assert cli.main([]) == cli.EXIT_INTERNAL
    assert "interrupted" in capsys.readouterr().err


def test_parse_accepts_spec_like_every_other_command(tmp_path: Path) -> None:
    spec = tmp_path / "ACCEPTANCE.md"
    spec.write_text(
        "## Requirement 1 - Thing\n\n#### Acceptance Criteria\n\n"
        "1. THE system SHALL do the thing.\n",
        encoding="utf-8",
    )

    assert cli.main(["parse", "--root", str(tmp_path), "--spec", "ACCEPTANCE.md"]) == cli.EXIT_OK


if sys.platform == "win32":  # pragma: no cover - kept is tested on POSIX
    pytest.skip("interpreter layout differs", allow_module_level=True)
