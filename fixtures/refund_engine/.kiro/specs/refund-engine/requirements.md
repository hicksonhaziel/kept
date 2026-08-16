# Requirements Document

## Introduction

A refund and invoice engine. Money, rounding, idempotency, and monotonicity: a
domain that is property-rich and legible without background knowledge.

All monetary amounts are integers in minor units (cents). No floating point.

## Requirements

### Requirement 1: Refund limits

**User Story:** As a merchant, I want refunds bounded by what was actually paid, so that the business cannot lose money to a bad request.

#### Acceptance Criteria

1. WHEN a refund is requested for an order THEN the system SHALL refund no more than the amount paid for that order.
2. WHEN a refund is requested with a negative amount THEN the system SHALL reject the request.
3. WHEN a refund is requested with an amount of zero THEN the system SHALL reject the request.
4. THE system SHALL NOT allow the total of all refunds against an order to exceed the amount paid for that order.
5. WHEN an order has already been refunded in full THEN the system SHALL reject any further refund against it.

### Requirement 2: Idempotency

**User Story:** As an engineer handling payment webhooks, I want repeated requests to be safe, so that a retry cannot double-refund a customer.

#### Acceptance Criteria

1. WHEN two refunds are requested with the same reference THEN the system SHALL record only one refund.
2. WHEN a refund is requested twice with the same reference THEN the system SHALL return an equal result both times.
3. WHEN two refunds are requested with different references THEN the system SHALL treat them as distinct refunds.
4. WHEN a refund is retried with the same reference but a different amount THEN the system SHALL reject the retry.

### Requirement 3: Money and rounding

**User Story:** As an accountant, I want every amount to be an exact whole number of cents, so that the books reconcile.

#### Acceptance Criteria

1. THE system SHALL express every monetary amount as an integer number of minor units.
2. WHEN a computed amount falls exactly halfway between two minor units THEN the system SHALL round away from zero.
3. WHEN an amount is split across several lines THEN the system SHALL ensure the parts sum exactly to the total.
4. THE system SHALL NOT return a monetary amount that is not an integer.

### Requirement 4: Discounts

**User Story:** As a customer, I want the advertised discount applied consistently, so that a larger order is never penalised.

#### Acceptance Criteria

1. WHEN an order subtotal is below 10000 minor units THEN the system SHALL apply no discount.
2. WHEN an order subtotal is at least 10000 minor units AND below 50000 minor units THEN the system SHALL apply a discount of 10 percent.
3. WHEN an order subtotal is at least 50000 minor units THEN the system SHALL apply a discount of 15 percent.
4. WHEN one subtotal is greater than another THEN the system SHALL NOT compute a smaller discount for the greater subtotal.
5. THE system SHALL NOT compute a discount greater than the subtotal.

### Requirement 5: Tax proration

**User Story:** As a merchant, I want tax refunded in proportion to the goods returned, so that the tax return is correct.

#### Acceptance Criteria

1. WHEN a partial refund is issued THEN the system SHALL prorate the tax in the same ratio as the goods refunded.
2. WHEN a full refund is issued THEN the system SHALL refund the entire tax charged.
3. THE system SHALL NOT prorate tax to an amount greater than the tax originally charged.
4. WHEN no goods are refunded THEN the system SHALL prorate no tax.

### Requirement 6: Audit trail

**User Story:** As an auditor, I want every decision recorded, so that a dispute can be reconstructed.

#### Acceptance Criteria

1. THE system SHALL record a reference for every accepted refund.
2. WHEN a refund is rejected THEN the system SHALL record the reason for the rejection.
3. THE system SHALL preserve refunds in the order they were accepted.
