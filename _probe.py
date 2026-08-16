"""Probe: what do coverage.py dynamic contexts actually look like?"""

import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURE = Path("/home/hickson/kept/fixtures/refund_engine")

rc = """
[run]
branch = True
dynamic_context = test_function
source = .
relative_files = True

[report]
include = refund.py
"""

with tempfile.TemporaryDirectory() as scratch:
    rcfile = Path(scratch) / "cov.rc"
    rcfile.write_text(rc)
    datafile = Path(scratch) / "cdata"

    result = subprocess.run(
        [sys.executable, "-m", "coverage", "run", f"--rcfile={rcfile}",
         f"--data-file={datafile}", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=FIXTURE, capture_output=True, text=True, check=False,
    )
    print("pytest exit:", result.returncode)
    print((result.stdout or "")[-400:])

    from coverage.sqldata import CoverageData

    data = CoverageData(basename=str(datafile))
    data.read()

    files = sorted(data.measured_files())
    print("\nMEASURED FILES:")
    for f in files:
        print("  ", f)

    contexts = sorted(data.measured_contexts())
    print(f"\nCONTEXTS ({len(contexts)}):")
    for c in contexts[:8]:
        print("  ", repr(c))

    target = next((f for f in files if f.endswith("refund.py")), None)
    print("\nTARGET:", target)

    if target:
        for ctx in ["test_refund.test_refund_cannot_exceed_amount_paid",
                    "test_refund.test_ten_percent_discount_in_the_first_tier"]:
            data.set_query_contexts([ctx])
            lines = data.lines(target)
            print(f"\n  context {ctx!r}")
            print(f"    lines: {sorted(lines) if lines else None}")

    print("\nARCS SUPPORTED:", data.has_arcs())
