# ADR-0007: A binding names a test, and covers every parametrisation of it

**Status:** accepted
**Date:** 2026-08-22

## Context

Found by running kept against Starlette, whose suite parametrises almost every
test over two async backends. Its node IDs look like
`tests/test_routing.py::test_router[asyncio]`.

A binding written as `tests/test_routing.py::test_router` matched nothing, so the
oracle was reported **missing** and the promise UNPROVEN. The author had named a
real test, correctly, and kept told them it did not exist.

Worse, the parameters also broke the vacuity scan. Shapes are keyed by the
function a source file defines, so a lookup for `test_router[asyncio]` found
nothing, and an oracle whose shape cannot be found is treated as asserting
nothing. **Every parametrised oracle in every project was reported vacuous**,
which is most oracles in most real suites.

## Decision

A bound node ID that names a test function covers every parametrisation of that
test. Naming one variant explicitly binds only that variant.

Shape lookups fall back to the unparametrised node ID, so a parametrised test is
judged by the assertions its function body contains.

## Consequences

This is what `pytest path::test_router` already means, so the binding file now
reads the way a Python developer expects. It also means a criterion's evidence
grows automatically when a maintainer adds a parameter to a bound test — which is
correct: the promise is still verified by that test, under more conditions.

Accepted costs:

- Two parametrisations of one test count as two oracles in the ledger. The counts
  are honest but a reader may expect one.
- If a maintainer parametrises a bound test in a way that makes some variants
  skip, those variants report `skipped` and drag the criterion toward UNPROVEN.
  That is the correct signal — a skipped oracle verifies nothing — but it will
  look surprising the first time.
- kept cannot tell a deliberately narrow binding from a stale one. Naming
  `test_router[trio]` binds only trio, forever, silently, if asyncio is added
  later. The bindings file is reviewed by humans for exactly this reason.

## Rejected

**Matching by substring or fuzzily.** A binding must name a test exactly or name a
function exactly. Anything looser would let a rename silently rebind a criterion to
a different test, which is the misattribution the whole tool exists to prevent.
