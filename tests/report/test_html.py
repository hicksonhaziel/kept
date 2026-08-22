"""The HTML evidence map: a pure renderer, and the diffs handed to it.

Unbound on purpose: `kept report` has no acceptance criteria yet.
"""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from kept import pipeline
from kept.ledger import Ledger, Settings
from kept.report.html import MutationDiff, render
from kept.verdict import Evidence, Missed, Ruling, Verdict

SETTINGS = Settings(threshold=1.0, cap=12)


def _ruling(
    verdict: Verdict = Verdict.WEAK,
    *,
    missed: tuple[Missed, ...] = (),
    oracles: tuple[tuple[str, str], ...] = (("tests/test_a.py::test_it", "passed"),),
) -> Ruling:
    return Ruling(
        criterion="REQ-1.1",
        content_hash="a" * 64,
        verdict=verdict,
        evidence=Evidence(
            oracles=oracles,
            covered=(("app.py", (3, 4, 5)),),
            probed=2,
            killed=1,
            discriminating=2,
            missed=missed,
        ),
        reason="1 of 2 detectable breakages went unnoticed by this promise's own oracles",
    )


def _ledger(*rulings: Ruling) -> Ledger:
    return Ledger(
        kept_version="0.1.0",
        settings=SETTINGS,
        rulings=rulings or (_ruling(),),
        commit="c0ffee1234567890",
        sources=(("app.py", "b" * 64),),
    )


MISS = Missed(
    path="app.py",
    line=4,
    operator="comparison",
    description="<= to <",
    caught_by=("REQ-1.3",),
)


class _WellFormed(HTMLParser):
    """Enough of a check to catch an unclosed element in a hand-built template."""

    VOID = frozenset({"meta", "br", "hr", "img", "input", "path", "circle", "link"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.problems: list[str] = []

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in self.VOID:
            return
        if not self.stack:
            self.problems.append(f"</{tag}> with nothing open")
        elif self.stack[-1] != tag:
            self.problems.append(f"</{tag}> closes <{self.stack[-1]}>")
            self.stack.pop()
        else:
            self.stack.pop()


def test_the_document_is_well_formed() -> None:
    parser = _WellFormed()
    parser.feed(render(_ledger()))

    assert parser.problems == []
    assert parser.stack == [], f"never closed: {parser.stack}"


def test_the_report_references_nothing_outside_itself() -> None:
    """kept claims to work offline. A CDN font would break that claim quietly, the
    first time somebody opened the report without a network."""
    page = render(_ledger(_ruling(missed=(MISS,))))

    external = re.findall(r"""(?:src|href)\s*=\s*["'](?!#)([^"']+)""", page)

    assert external == [], f"external references: {external}"
    assert "http://" not in page
    assert "https://" not in page


def test_every_promise_appears_with_its_verdict_and_wording() -> None:
    page = render(_ledger(), texts={"REQ-1.1": "THE system SHALL refund no more than was paid."})

    assert "REQ-1.1" in page
    assert 'class="pill v-weak"' in page
    assert "THE system SHALL refund no more than was paid." in page


def test_a_missed_breakage_is_shown_as_a_red_and_green_diff() -> None:
    diff = MutationDiff(
        path="app.py",
        line=4,
        operator="comparison",
        description="<= to <",
        before="    if total <= limit:",
        after="    if total < limit:",
    )

    page = render(_ledger(_ruling(missed=(MISS,))), diffs={diff.key: diff})

    assert 'class="line del"' in page
    assert 'class="line ins"' in page
    assert "if total &lt;= limit:" in page
    assert "if total &lt; limit:" in page
    assert 'class="caught">REQ-1.3' in page


def test_a_changed_source_is_admitted_rather_than_guessed_at() -> None:
    stale = MutationDiff(
        path="app.py", line=4, operator="comparison", description="<= to <", stale=True
    )

    page = render(_ledger(_ruling(missed=(MISS,))), diffs={stale.key: stale})

    assert "The source has changed since this evidence was recorded" in page
    assert 'class="line del"' not in page


def test_a_missing_diff_shows_no_diff_at_all() -> None:
    page = render(_ledger(_ruling(missed=(MISS,))))

    assert 'class="line del"' not in page
    assert "app.py:4" in page


def test_criterion_wording_is_escaped_not_executed() -> None:
    page = render(_ledger(), texts={"REQ-1.1": "<script>alert('x')</script>"})

    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_only_the_verdicts_present_get_a_filter() -> None:
    page = render(_ledger(_ruling(Verdict.KEPT)))

    assert 'data-verdict="kept"' in page
    assert 'data-verdict="broken"' not in page


def test_the_page_says_evidence_not_proof_and_names_no_model() -> None:
    page = render(_ledger())

    assert "Evidence, not proof." in page
    assert "No model produced any part of this page." in page


def test_the_same_ledger_renders_the_same_page() -> None:
    stored = _ledger(_ruling(missed=(MISS,)))

    assert render(stored) == render(stored)


def test_reduced_motion_and_print_are_both_handled() -> None:
    page = render(_ledger())

    assert "prefers-reduced-motion" in page
    assert "@media print" in page


def _project(tmp_path: Path, source: str) -> tuple[Path, str]:
    target = tmp_path / "app.py"
    target.write_text(source, encoding="utf-8")
    return target, hashlib.sha256(target.read_bytes()).hexdigest()


SOURCE = """def charge(total, limit):
    if total <= limit:
        return total
    return limit
"""


def test_a_diff_is_recomputed_from_the_source_the_ledger_judged(tmp_path: Path) -> None:
    _, digest = _project(tmp_path, SOURCE)
    missed = Missed(
        path="app.py", line=2, operator="comparison", description="<= to <", caught_by=("REQ-9.9",)
    )
    stored = Ledger(
        kept_version="0.1.0",
        settings=SETTINGS,
        rulings=(_ruling(missed=(missed,)),),
        sources=(("app.py", digest),),
    )

    diffs = pipeline.mutation_diffs(tmp_path, stored)

    diff = diffs[missed.path, missed.line, missed.operator, missed.description]
    assert not diff.stale
    assert diff.before == "    if total <= limit:"
    assert diff.after == "    if total < limit:"


def test_a_source_that_moved_since_the_ledger_yields_no_diff(tmp_path: Path) -> None:
    _project(tmp_path, SOURCE)
    missed = Missed(
        path="app.py", line=2, operator="comparison", description="<= to <", caught_by=("REQ-9.9",)
    )
    stored = Ledger(
        kept_version="0.1.0",
        settings=SETTINGS,
        rulings=(_ruling(missed=(missed,)),),
        sources=(("app.py", "0" * 64),),
    )

    diffs = pipeline.mutation_diffs(tmp_path, stored)

    assert diffs[missed.path, 2, "comparison", "<= to <"].stale


def test_a_breakage_no_operator_can_reproduce_is_marked_stale(tmp_path: Path) -> None:
    _, digest = _project(tmp_path, SOURCE)
    missed = Missed(
        path="app.py",
        line=2,
        operator="invented",
        description="nothing kept generates",
        caught_by=(),
    )
    stored = Ledger(
        kept_version="0.1.0",
        settings=SETTINGS,
        rulings=(_ruling(missed=(missed,)),),
        sources=(("app.py", digest),),
    )

    diffs = pipeline.mutation_diffs(tmp_path, stored)

    assert diffs[missed.path, 2, "invented", "nothing kept generates"].stale


@pytest.mark.parametrize("verdict", list(Verdict))
def test_every_verdict_renders(verdict: Verdict) -> None:
    page = render(_ledger(_ruling(verdict)))

    assert f'class="pill v-{verdict}"' in page
