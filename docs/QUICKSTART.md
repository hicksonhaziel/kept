# Quickstart

Five minutes, from installed to a committed ledger. Nothing here needs a network
connection, an account, or an API key.

## 1. Install into your test environment

```bash
uv add --dev kept-cli     # or: pip install kept-cli
```

> [!IMPORTANT]
> This has to be the same environment your tests run in. The
> `@pytest.mark.verifies` marker comes from a pytest plugin kept ships via an
> entry point, so a global-only install leaves your project's pytest not knowing
> the marker exists — and `--strict-markers` will then fail on every one.

Check it took:

```console
$ kept --version
kept 0.1.0
```

## 2. See what kept can read

```console
$ kept parse

pricing  (.kiro/specs/pricing/requirements.md)

  REQ-1  Discounting
      REQ-1.1    event_driven       SHALL      668fa5b83995
      REQ-1.2    unwanted_behaviour SHALL      528eddc264c2
      REQ-1.3    ubiquitous         SHALL      31c4e3d7dd04

3 criteria · 3 promises · 0 advisory · 0 errors · 0 warnings
```

Criteria need a normative modality — `SHALL`, `SHALL NOT`, `MUST`, `MUST NOT` — to
carry a verdict. `SHOULD` and `MAY` parse and are marked advisory. Anything kept
cannot read produces a diagnostic that says what to change, and never stops the
run.

<details>
<summary>What a readable criterion looks like</summary>

```markdown
## Requirement 1 - Discounting

**User Story:** As a shopper, I want discounts applied correctly, so that I am
charged a fair price.

#### Acceptance Criteria

1. WHEN a discount percentage is applied THEN the system SHALL reduce the total by
   that percentage.
2. IF the percentage is outside the range 0 to 100 THEN the system SHALL reject it.
3. THE system SHALL never return a total below zero.
```

Kiro writes this shape by default. Any markdown file with numbered items under an
"Acceptance Criteria" heading works, wherever it lives — pass it with `--spec`.

</details>

## 3. Say which test verifies what

kept never invents this mapping. You write it, review it, and commit it.

```python
import pytest

@pytest.mark.verifies("REQ-1.1")
def test_a_ten_percent_discount_reduces_the_total_by_a_tenth():
    assert discounted(1000, 10) == 900
```

Then harvest the markers into a reviewable file:

```console
$ kept bind --write

  REQ-1.1  (annotation)
      tests/test_pricing.py::test_a_ten_percent_discount_reduces_the_total_by_a_tenth

unbound promises (nothing claims to verify these)
      REQ-1.3

3 promises · 2 bound · 1 unbound · 2 oracles across 3 collected tests

wrote .kept/bindings.toml
```

Commit `.kept/bindings.toml`. An unbound promise is not a failure of your code — it
is a promise nothing checks, stated out loud.

## 4. Get the verdicts

```console
$ kept verify --write

  REQ-1.3    WEAK          4/9  5 of 9 detectable breakages went unnoticed by this promise's own oracles
      missed  pricing.py:5   * to /   (caught by REQ-1.1)
      missed  pricing.py:6   - to +   (caught by REQ-1.1)

4 promises · 0 kept · 3 weak · 1 unproven

wrote .kept/ledger.json, EVIDENCE.md, .kept/badge.svg
```

Commit all three. Your repository now attests to itself: anyone can see which
promises are independently verified, at which commit, under which settings.

> [!TIP]
> Expect a first run heavy on WEAK and UNPROVEN. kept's own first honest run was
> 4 kept and 45 weak out of 51. That gap is the difference between "the suite is
> green" and "this promise is independently verified".

## 5. Act on a finding

```bash
kept prompt REQ-1.3
```

You get the promise's wording, the tests bound to it, the lines under audit, and
every breakage those tests missed — with the promise whose tests *did* catch it,
which is how kept knows the breakage is detectable rather than harmless.

Strengthen the assertion, run `kept verify` again, watch the verdict move. That is
the loop.

## 6. Keep it from sliding back

```yaml
- uses: hicksonhaziel/kept@v0.1.0
  with:
    root: .
    gate: no-regression
```

`no-regression` is adoptable on day one: today's WEAK verdicts are reported, not
failed, and the build breaks only when a promise loses ground against the committed
ledger. See [CI](CI.md).

## Where to go next

- [Verdicts](VERDICTS.md) — what each of the five actually claims
- [Configuration](CONFIGURATION.md) — put your flags in a file and forget them
- [Threat model](THREAT-MODEL.md) — how a verdict could still mislead you
