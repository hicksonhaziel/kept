"""The MCP adapter: payloads, tool surface, and the guardrails around it.

Unbound on purpose: `kept serve` has no acceptance criteria yet, and binding these
to a criterion they do not verify would be the misattribution kept exists to catch.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

from kept import serve
from kept.report import UnknownCriterionError

SLUG = Path("fixtures/slug")


@pytest.fixture
def slug(repo_root: Path) -> serve.Config:
    return serve.Config(root=repo_root / SLUG, specs=(Path("ACCEPTANCE.md"),))


def _tools(config: serve.Config) -> dict[str, Any]:
    listed = asyncio.run(serve.build_server(config).list_tools())
    return {tool.name: tool for tool in listed}


def test_list_promises_reports_each_criterion_with_its_recorded_verdict(
    slug: serve.Config,
) -> None:
    payload = serve.list_promises(slug)

    identifiers = [promise["criterion"] for promise in payload["promises"]]
    assert identifiers == ["REQ-1.1", "REQ-1.2", "REQ-1.3", "REQ-1.4", "REQ-1.5"]
    assert all(promise["recorded_verdict"] == "kept" for promise in payload["promises"])
    assert "may predate the current code" in payload["note"]


def test_read_ledger_returns_the_committed_evidence_without_running_anything(
    slug: serve.Config,
) -> None:
    payload = serve.read_ledger(slug)

    assert payload["headline"] == "5 promises · 5 kept · 0 weak"
    assert payload["ledger"]["schema_version"] >= 1


def test_read_ledger_says_so_plainly_when_no_ledger_has_been_committed(tmp_path: Path) -> None:
    payload = serve.read_ledger(serve.Config(root=tmp_path))

    assert payload["ledger"] is None
    assert "no evidence to read" in payload["note"]


def test_a_brief_is_served_for_a_promise_in_the_ledger(slug: serve.Config) -> None:
    brief = serve.remediation_brief(slug, "REQ-1.1")

    assert brief.startswith("# Remediation brief — REQ-1.1")
    assert "Only re-running `kept verify` can change a verdict." in brief


def test_a_brief_is_refused_rather_than_invented_when_there_is_no_ledger(
    tmp_path: Path,
) -> None:
    with pytest.raises(UnknownCriterionError, match="invents none"):
        serve.remediation_brief(serve.Config(root=tmp_path), "REQ-1.1")


def test_the_server_exposes_exactly_the_four_documented_tools(slug: serve.Config) -> None:
    assert set(_tools(slug)) == {
        "list_promises",
        "read_ledger",
        "remediation_brief",
        "verify",
    }


def test_only_verify_is_allowed_to_change_anything(slug: serve.Config) -> None:
    tools = _tools(slug)

    for name in ("list_promises", "read_ledger", "remediation_brief"):
        assert tools[name].annotations is not None
        assert tools[name].annotations.read_only_hint is True
    assert tools["verify"].annotations.read_only_hint is False


def test_no_tool_accepts_a_filesystem_path_from_the_client(slug: serve.Config) -> None:
    """The root is fixed at startup, so an agent cannot redirect kept elsewhere."""
    for tool in _tools(slug).values():
        properties = (tool.input_schema or {}).get("properties", {})
        assert not {"root", "path", "spec", "specs", "python"} & set(properties), tool.name


def test_every_tool_description_states_whether_it_can_move_a_verdict(
    slug: serve.Config,
) -> None:
    tools = _tools(slug)

    assert "Runs no tests." in " ".join(tools["read_ledger"].description.split())
    assert "only verify can" in tools["remediation_brief"].description
    assert "only tool that can move a verdict" in tools["verify"].description


def test_the_instructions_tell_a_client_it_cannot_set_a_verdict() -> None:
    assert "You cannot set a verdict" in serve.INSTRUCTIONS
    assert "deterministic and offline" in serve.INSTRUCTIONS


def test_without_the_optional_extra_the_server_refuses_to_start(
    slug: serve.Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "mcp.server", None)

    with pytest.raises(serve.MissingExtraError, match="uv sync --extra mcp"):
        serve.build_server(slug)
