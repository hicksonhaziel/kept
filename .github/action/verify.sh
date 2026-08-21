#!/usr/bin/env bash
# The body of the kept action. Kept as a script rather than inline YAML so it can
# be read, reviewed, and run by hand.
#
# Exit status is kept's own: 0 gate satisfied, 1 gate violated, 2 usage or
# configuration error, 3 internal error.

set -uo pipefail

arguments=(verify --root "${KEPT_ROOT}" --gate "${KEPT_GATE}" --cap "${KEPT_CAP}"
  --threshold "${KEPT_THRESHOLD}" --source "${KEPT_SOURCE}" --json)

while IFS= read -r specification; do
  [ -n "${specification}" ] && arguments+=(--spec "${specification}")
done <<<"${KEPT_SPEC}"

[ -n "${KEPT_TESTS}" ] && arguments+=(--tests "${KEPT_TESTS}")
[ -n "${KEPT_PYTHON}" ] && arguments+=(--python "${KEPT_PYTHON}")
[ "${KEPT_WRITE}" = "true" ] && arguments+=(--write)

payload="$(mktemp)"
kept "${arguments[@]}" >"${payload}"
status=$?

if [ ! -s "${payload}" ]; then
  echo "kept produced no output; exit status ${status}" >&2
  exit "${status}"
fi

# Read the ledger with python rather than jq: the runner is guaranteed to have the
# interpreter kept itself needs, and this keeps the action dependency-free.
python3 - "${payload}" <<'PYTHON'
import json
import os
import pathlib
import sys

payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
ledger = payload["ledger"]
summary = ledger["summary"]
regressions = payload.get("regressions", [])

counts = " · ".join(
    f"{summary[name]} {name}"
    for name in ("kept", "weak", "unproven", "broken", "stale")
    if summary.get(name)
)
headline = f"{summary['promises']} promises · {counts}" if counts else f"{summary['promises']} promises"

outputs = {
    "headline": headline,
    "promises": summary["promises"],
    "kept": summary.get("kept", 0),
    "weak": summary.get("weak", 0),
    "unproven": summary.get("unproven", 0),
    "broken": summary.get("broken", 0),
    "stale": summary.get("stale", 0),
    "regressions": len(regressions),
    "ledger": os.path.join(os.environ["KEPT_ROOT"], ".kept", "ledger.json"),
}

with pathlib.Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as handle:
    for name, value in outputs.items():
        handle.write(f"{name}={value}\n")

print(f"kept: {headline}")
for regression in regressions:
    print(f"kept: {regression['criterion']} regressed {regression['was']} -> {regression['now']}")

if os.environ.get("KEPT_SUMMARY") != "true":
    sys.exit(0)

rows = [
    "## kept",
    "",
    f"**{headline}**",
    "",
    "Evidence, not proof: a killed mutant is not a guarantee of correctness.",
    "",
    "| Promise | Verdict | Caught | Note |",
    "|---|---|---|---|",
]
for entry in ledger["criteria"]:
    evidence = entry.get("evidence") or {}
    mutants = evidence.get("mutants") or {}
    detectable = mutants.get("discriminating", 0)
    missed = len(evidence.get("missed") or ())
    caught = f"{detectable - missed}/{detectable}" if detectable else "—"
    rows.append(
        f"| {entry['criterion']} | {entry['verdict']} | {caught} | {entry.get('reason') or ''} |"
    )

if regressions:
    rows += ["", "### Regressed against the committed ledger", ""]
    rows += [f"- `{r['criterion']}` {r['was']} → {r['now']}" for r in regressions]

step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
if step_summary:
    with pathlib.Path(step_summary).open("a", encoding="utf-8") as handle:
        handle.write("\n".join(rows) + "\n")
PYTHON

rm -f "${payload}"
exit "${status}"
