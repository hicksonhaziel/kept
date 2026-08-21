"""Project configuration: what a project may state once, and what precedence wins.

Unbound on purpose: `.kept/config.toml` has no acceptance criteria yet, and binding
these to a criterion they do not verify would be the misattribution kept detects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kept import cli, config


def _write(root: Path, body: str) -> Path:
    directory = root / ".kept"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_project_with_no_config_file_gets_no_defaults_and_no_complaint(
    tmp_path: Path,
) -> None:
    loaded = config.load(tmp_path)

    assert loaded.values == ()
    assert loaded.diagnostics == ()
    assert loaded.path is None


def test_values_are_read_and_typed_for_the_command_line(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """
        spec = ["docs/criteria.md", "other.md"]
        source = "myapp"
        python = "/usr/bin/python3"
        cap = 20
        timeout = 30
        threshold = 0.8
        """,
    )

    defaults = config.load(tmp_path).defaults_for("verify")

    assert defaults["specs"] == [Path("docs/criteria.md"), Path("other.md")]
    assert defaults["source"] == "myapp"
    assert defaults["python"] == Path("/usr/bin/python3")
    assert defaults["cap"] == 20
    assert defaults["timeout"] == pytest.approx(30.0)
    assert isinstance(defaults["timeout"], float)
    assert defaults["threshold"] == pytest.approx(0.8)


def test_a_key_reaches_only_the_commands_that_understand_it(tmp_path: Path) -> None:
    _write(tmp_path, 'threshold = 0.5\nspec = ["a.md"]\n')

    loaded = config.load(tmp_path)

    assert "threshold" in loaded.defaults_for("verify")
    assert "threshold" not in loaded.defaults_for("observe")
    assert "specs" in loaded.defaults_for("prompt")
    assert loaded.defaults_for("parse") == {}


def test_a_misspelled_key_is_an_error_rather_than_a_silent_no_op(tmp_path: Path) -> None:
    _write(tmp_path, "treshold = 0.5\n")

    loaded = config.load(tmp_path)

    assert [diagnostic.code for diagnostic in loaded.errors] == ["C001"]
    assert "threshold" in loaded.diagnostics[0].message
    assert loaded.values == ()


def test_a_value_of_the_wrong_type_is_refused_with_the_type_it_needed(
    tmp_path: Path,
) -> None:
    _write(tmp_path, 'cap = "lots"\n')

    loaded = config.load(tmp_path)

    assert [diagnostic.code for diagnostic in loaded.errors] == ["C002"]
    assert "int" in loaded.diagnostics[0].message


def test_a_boolean_is_not_accepted_as_a_number(tmp_path: Path) -> None:
    _write(tmp_path, "cap = true\n")

    assert [diagnostic.code for diagnostic in config.load(tmp_path).errors] == ["C002"]


def test_a_future_schema_version_is_refused_rather_than_guessed(tmp_path: Path) -> None:
    _write(tmp_path, "version = 99\nthreshold = 0.5\n")

    loaded = config.load(tmp_path)

    assert [diagnostic.code for diagnostic in loaded.errors] == ["C004"]
    assert loaded.values == ()


def test_a_malformed_file_raises_rather_than_being_half_read(tmp_path: Path) -> None:
    _write(tmp_path, "spec = [unclosed\n")

    with pytest.raises(config.ConfigError, match="not valid TOML"):
        config.load(tmp_path)


def test_the_config_file_beats_the_built_in_default(tmp_path: Path) -> None:
    _write(tmp_path, "threshold = 0.5\ncap = 3\n")

    parser = cli.build_parser(config.load(tmp_path))
    args = parser.parse_args(["verify"])

    assert args.threshold == pytest.approx(0.5)
    assert args.cap == 3


def test_an_explicit_flag_beats_the_config_file(tmp_path: Path) -> None:
    _write(tmp_path, "threshold = 0.5\n")

    parser = cli.build_parser(config.load(tmp_path))
    args = parser.parse_args(["verify", "--threshold", "0.9"])

    assert args.threshold == pytest.approx(0.9)


def test_the_built_in_default_still_applies_where_the_file_is_silent(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "cap = 3\n")

    args = cli.build_parser(config.load(tmp_path)).parse_args(["verify"])

    assert args.gate == "no-regression"


def test_a_malformed_config_file_is_a_usage_error_not_a_crash(tmp_path: Path) -> None:
    _write(tmp_path, "cap = [\n")

    assert cli.main(["parse", "--root", str(tmp_path)]) == cli.EXIT_USAGE


def test_an_unknown_key_stops_the_run_before_any_work_happens(tmp_path: Path) -> None:
    _write(tmp_path, "nonsense = 1\n")

    assert cli.main(["verify", "--root", str(tmp_path)]) == cli.EXIT_USAGE


def test_the_root_is_found_before_argparse_runs(tmp_path: Path) -> None:
    assert cli._peek_root(["verify", "--root", str(tmp_path)]) == tmp_path
    assert cli._peek_root([f"--root={tmp_path}", "verify"]) == tmp_path
    assert cli._peek_root(["verify"]) == Path.cwd()
