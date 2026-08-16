"""A refund and invoice engine. All amounts are integer minor units (cents)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

# Highest threshold first, so the first match wins.
DISCOUNT_TIERS: tuple[tuple[int, Decimal], ...] = (
    (50_000, Decimal("0.15")),
    (10_000, Decimal("0.10")),
)


class RefundRejected(Exception):
    """Raised when a refund request cannot be accepted."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def round_minor(value: Decimal) -> int:
    """Round a decimal amount to a whole minor unit, half away from zero."""
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def calculate_discount(subtotal: int) -> int:
    """Return the discount for a subtotal, in minor units."""
    if subtotal <= 0:
        return 0
    for threshold, rate in DISCOUNT_TIERS:
        if subtotal >= threshold:
            return round_minor(Decimal(subtotal) * rate)
    return 0


def prorate_tax(tax_charged: int, goods_refunded: int, goods_total: int) -> int:
    """Return the share of tax to refund alongside `goods_refunded`."""
    if goods_total <= 0 or goods_refunded <= 0:
        return 0
    if goods_refunded >= goods_total:
        return tax_charged
    return round_minor(Decimal(tax_charged) * Decimal(goods_refunded) / Decimal(goods_total))


def allocate(total: int, weights: tuple[int, ...]) -> tuple[int, ...]:
    """Split `total` across `weights` so the parts sum exactly to the total."""
    weight_sum = sum(weights)
    if weight_sum <= 0:
        return tuple(0 for _ in weights)

    floors = [total * weight // weight_sum for weight in weights]
    remainder = total - sum(floors)

    # Hand the leftover minor units to the largest fractional parts first.
    fractions = sorted(
        range(len(weights)),
        key=lambda index: (total * weights[index]) % weight_sum,
        reverse=True,
    )
    for index in fractions[:remainder]:
        floors[index] += 1
    return tuple(floors)


@dataclass(frozen=True, slots=True)
class Refund:
    reference: str
    amount: int


@dataclass(frozen=True, slots=True)
class Rejection:
    reference: str
    reason: str


class RefundLedger:
    """Tracks refunds against a single order."""

    def __init__(self, amount_paid: int) -> None:
        if amount_paid < 0:
            msg = "amount paid cannot be negative"
            raise ValueError(msg)
        self.amount_paid = amount_paid
        self._refunds: list[Refund] = []
        self._by_reference: dict[str, Refund] = {}
        self._rejections: list[Rejection] = []

    @property
    def refunds(self) -> tuple[Refund, ...]:
        return tuple(self._refunds)

    @property
    def rejections(self) -> tuple[Rejection, ...]:
        return tuple(self._rejections)

    @property
    def total_refunded(self) -> int:
        return sum(refund.amount for refund in self._refunds)

    @property
    def remaining(self) -> int:
        return self.amount_paid - self.total_refunded

    @property
    def is_fully_refunded(self) -> bool:
        return self.remaining == 0

    def refund(self, reference: str, amount: int) -> Refund:
        """Record a refund, or raise `RefundRejected`.

        Requesting the same reference twice returns the original refund.
        """
        existing = self._by_reference.get(reference)
        if existing is not None:
            if existing.amount != amount:
                self._reject(reference, "reference reused with a different amount")
            return existing

        if amount <= 0:
            self._reject(reference, "refund amount must be positive")
        if amount > self.remaining:
            self._reject(reference, "refund exceeds the remaining refundable balance")

        refund = Refund(reference=reference, amount=amount)
        self._refunds.append(refund)
        self._by_reference[reference] = refund
        return refund

    def _reject(self, reference: str, reason: str) -> None:
        self._rejections.append(Rejection(reference=reference, reason=reason))
        raise RefundRejected(reason)
