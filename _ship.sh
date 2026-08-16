#!/usr/bin/env bash
set -x
cd /home/hickson/kept || exit 1

rm -f mk.txt mk2.txt k1.txt gate.log gate.txt g1.log _out.txt bind_out.txt fixture_out.txt

uv run kept bind --root fixtures/refund_engine --write --json | tail -20

cat > /tmp/msg15.txt <<'EOF'
feat(bindings): map criteria to the tests that claim to verify them

Third pipeline stage. A criterion with no oracle cannot be verified, so the map
from criterion to test has to exist before any verdict can.

Bindings are harvested from @pytest.mark.verifies markers by a pytest plugin
loaded through a pytest11 entry point, so a target project needs no conftest
change and never imports kept. Harvesting is opt-in via an environment variable
and uses --collect-only, so no test body runs and a normal test run is untouched.

Hand-written bindings in .kept/bindings.toml are merged over the harvested ones
and win on conflict. The human owns the mapping; kept only verifies it. An
[[unverifiable]] entry must state a reason, so excluding a criterion is a visible
choice a reviewer can challenge rather than a silent omission.

kept bind reports unbound promises and orphaned bindings, and exits 1 on either.
An unbound promise is not a crash, it is a gate violation.

Also adds the refund-engine fixture: a spec of 25 EARS criteria plus a one-pass
implementation and its tests, committed as written. It is self-contained, with its
own .kiro and pytest config, so its promises stay separate from kept's own.
Currently 25 promises, 25 bound, 25 tests passing. What those tests are actually
worth is the next stage's question.
EOF

git add -A
git commit -q -F /tmp/msg15.txt
git log --oneline -3
git push 2>&1 | tail -3
git status --short
