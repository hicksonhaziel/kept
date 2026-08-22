"""Parametrised tests, and a suite that could not run at all.

Every case here came from running kept against Starlette, whose suite parametrises
almost everything over asyncio and trio. Before these fixes, every parametrised
oracle in every project was reported as asserting nothing.

Unbound on purpose: no acceptance criterion covers binding resolution yet.
"""

from __future__ import annotations

import pytest

from kept.bindings import Binding, BindingSet, Origin
from kept.observation import CriterionObservation, OracleStatus, build
from kept.observe.runner import Report
from kept.observe.runner import TestRecord as Record
from kept.observe.vacuity import OracleShape, scan_source, shape_for

SOURCE = """
import pytest


@pytest.mark.parametrize("backend", ["asyncio", "trio"])
def test_redirect_sets_location(backend):
    assert location() == "/target"


def test_asserts_nothing():
    build_the_thing()
"""


def _shapes() -> dict[str, OracleShape]:
    return scan_source(SOURCE, path="tests/test_web.py")


def test_a_parametrised_node_id_finds_the_function_that_defines_it() -> None:
    shapes = _shapes()

    found = shape_for(shapes, "tests/test_web.py::test_redirect_sets_location[asyncio]")

    assert found is not None
    assert found.has_assertion


def test_an_unparametrised_lookup_still_works() -> None:
    found = shape_for(_shapes(), "tests/test_web.py::test_asserts_nothing")

    assert found is not None
    assert not found.has_assertion


def test_a_node_id_from_another_file_is_not_invented() -> None:
    assert shape_for(_shapes(), "tests/other.py::test_redirect_sets_location[asyncio]") is None


def _report(*nodeids: str) -> Report:
    return Report(
        tests=tuple(
            Record(nodeid=nodeid, outcome="passed", context=f"m.{nodeid}") for nodeid in nodeids
        )
    )


def _built(bound: str, *collected: str) -> CriterionObservation:
    bindings = BindingSet(
        bindings=(Binding(criterion="REQ-1.1", oracles=(bound,), origin=Origin.MANUAL),)
    )
    return build(
        criteria=["REQ-1.1"],
        bindings=bindings,
        report=_report(*collected),
        coverage={},
        shapes={},
        test_files=frozenset(),
    ).criteria[0]


def test_binding_a_test_by_name_covers_every_parametrisation_of_it() -> None:
    """`pytest path::test_it` already means all of its parameters. A binding that
    named the function used to report the oracle as missing."""
    observation = _built(
        "tests/test_web.py::test_redirect",
        "tests/test_web.py::test_redirect[asyncio]",
        "tests/test_web.py::test_redirect[trio]",
    )

    assert [oracle.nodeid for oracle in observation.oracles] == [
        "tests/test_web.py::test_redirect[asyncio]",
        "tests/test_web.py::test_redirect[trio]",
    ]
    assert all(oracle.status is OracleStatus.PASSED for oracle in observation.oracles)


def test_naming_one_parametrisation_binds_only_that_one() -> None:
    observation = _built(
        "tests/test_web.py::test_redirect[trio]",
        "tests/test_web.py::test_redirect[asyncio]",
        "tests/test_web.py::test_redirect[trio]",
    )

    assert [o.nodeid for o in observation.oracles] == ["tests/test_web.py::test_redirect[trio]"]


def test_a_binding_that_matches_nothing_is_still_reported_missing() -> None:
    observation = _built("tests/test_web.py::test_gone", "tests/test_web.py::test_other")

    assert observation.oracles[0].status is OracleStatus.MISSING


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (2, "collection was interrupted"),
        (3, "internal error"),
        (4, "command line was rejected"),
        (5, "no tests were collected"),
    ],
)
def test_a_suite_that_never_ran_is_named_as_such(code: int, expected: str) -> None:
    """Reporting every promise as unverified would blame the tests for a broken
    environment."""
    from kept.observe.runner import _did_not_run_message

    message = _did_not_run_message(__import__("pathlib").Path("/tmp/project"), code, "boom")

    assert expected in message
    assert "kept reports no verdict" in message


def test_test_failures_are_not_treated_as_a_suite_that_did_not_run() -> None:
    from kept.observe.runner import _SUITE_DID_NOT_RUN

    assert 1 not in _SUITE_DID_NOT_RUN, "exit 1 is failing tests, which become BROKEN verdicts"
    assert 0 not in _SUITE_DID_NOT_RUN
