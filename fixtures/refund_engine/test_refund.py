"""Tests for the refund engine, bound to acceptance criteria."""

from __future__ import annotations

from decimal import Decimal

import pytest

from refund import (
    Refund,
    RefundLedger,
    RefundRejected,
    allocate,
    calculate_discount,
    prorate_tax,
    round_minor,
)


@pytest.mark.verifies("REQ-1.1")
def test_refund_cannot_exceed_amount_paid():
    ledger = RefundLedger(10_000)
    with pytest.raises(RefundRejected):
        ledger.refund("r1", 10_001)


@pytest.mark.verifies("REQ-1.2")
def test_negative_refund_is_rejected():
    ledger = RefundLedger(10_000)
    with pytest.raises(RefundRejected):
        ledger.refund("r1", -500)


@pytest.mark.verifies("REQ-1.3")
def test_zero_refund_is_rejected():
    ledger = RefundLedger(10_000)
    with pytest.raises(RefundRejected):
        ledger.refund("r1", 0)


@pytest.mark.verifies("REQ-1.4")
def test_refunds_cannot_total_more_than_paid():
    ledger = RefundLedger(10_000)
    ledger.refund("r1", 6_000)
    with pytest.raises(RefundRejected):
        ledger.refund("r2", 5_000)
    assert ledger.total_refunded == 6_000


@pytest.mark.verifies("REQ-1.5")
def test_no_further_refund_after_full_refund():
    ledger = RefundLedger(10_000)
    ledger.refund("r1", 10_000)
    assert ledger.is_fully_refunded
    with pytest.raises(RefundRejected):
        ledger.refund("r2", 1)


@pytest.mark.verifies("REQ-2.1")
def test_same_reference_records_one_refund():
    ledger = RefundLedger(10_000)
    ledger.refund("r1", 2_500)
    ledger.refund("r1", 2_500)
    assert len(ledger.refunds) == 1


@pytest.mark.verifies("REQ-2.2")
def test_same_reference_returns_an_equal_result():
    ledger = RefundLedger(10_000)
    first = ledger.refund("r1", 2_500)
    second = ledger.refund("r1", 2_500)
    assert first == second


@pytest.mark.verifies("REQ-2.3")
def test_different_references_are_distinct_refunds():
    ledger = RefundLedger(10_000)
    ledger.refund("r1", 2_500)
    ledger.refund("r2", 2_500)
    assert len(ledger.refunds) == 2
    assert ledger.total_refunded == 5_000


@pytest.mark.verifies("REQ-2.4")
def test_reused_reference_with_a_different_amount_is_rejected():
    ledger = RefundLedger(10_000)
    ledger.refund("r1", 2_500)
    with pytest.raises(RefundRejected):
        ledger.refund("r1", 3_000)


@pytest.mark.verifies("REQ-3.1", "REQ-3.4")
def test_amounts_are_integers():
    assert isinstance(calculate_discount(25_000), int)
    assert isinstance(prorate_tax(500, 250, 1_000), int)


@pytest.mark.verifies("REQ-3.2")
def test_half_rounds_away_from_zero():
    assert round_minor(Decimal("2.5")) == 3
    assert round_minor(Decimal("3.5")) == 4


@pytest.mark.verifies("REQ-3.3")
def test_allocation_parts_sum_to_the_total():
    parts = allocate(100, (1, 1, 1))
    assert sum(parts) == 100


@pytest.mark.verifies("REQ-4.1")
def test_no_discount_below_the_first_tier():
    assert calculate_discount(9_999) == 0


@pytest.mark.verifies("REQ-4.2")
def test_ten_percent_discount_in_the_first_tier():
    assert calculate_discount(10_000) == 1_000
    assert calculate_discount(20_000) == 2_000


@pytest.mark.verifies("REQ-4.3")
def test_fifteen_percent_discount_in_the_top_tier():
    assert calculate_discount(50_000) == 7_500


@pytest.mark.verifies("REQ-4.4")
def test_discount_does_not_shrink_as_the_subtotal_grows():
    assert calculate_discount(20_000) >= calculate_discount(10_000)
    assert calculate_discount(60_000) >= calculate_discount(50_000)


@pytest.mark.verifies("REQ-4.5")
def test_discount_never_exceeds_the_subtotal():
    assert calculate_discount(10_000) <= 10_000


@pytest.mark.verifies("REQ-5.1")
def test_partial_refund_prorates_tax():
    assert prorate_tax(1_000, 500, 1_000) == 500


@pytest.mark.verifies("REQ-5.2")
def test_full_refund_returns_all_tax():
    assert prorate_tax(1_000, 1_000, 1_000) == 1_000


@pytest.mark.verifies("REQ-5.3")
def test_prorated_tax_never_exceeds_tax_charged():
    assert prorate_tax(1_000, 900, 1_000) <= 1_000


@pytest.mark.verifies("REQ-5.4")
def test_no_goods_refunded_prorates_no_tax():
    assert prorate_tax(1_000, 0, 1_000) == 0


@pytest.mark.verifies("REQ-6.1")
def test_accepted_refund_records_its_reference():
    ledger = RefundLedger(10_000)
    ledger.refund("r1", 1_000)
    assert ledger.refunds[0].reference == "r1"


@pytest.mark.verifies("REQ-6.2")
def test_rejection_records_a_reason():
    ledger = RefundLedger(10_000)
    with pytest.raises(RefundRejected):
        ledger.refund("r1", 20_000)
    assert ledger.rejections[0].reason


@pytest.mark.verifies("REQ-6.3")
def test_refunds_are_kept_in_order():
    ledger = RefundLedger(10_000)
    ledger.refund("r1", 1_000)
    ledger.refund("r2", 2_000)
    assert [r.reference for r in ledger.refunds] == ["r1", "r2"]


def test_refund_is_hashable_value_object():
    assert Refund("r1", 100) == Refund("r1", 100)
