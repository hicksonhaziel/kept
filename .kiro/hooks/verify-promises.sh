#!/usr/bin/env bash
# Re-verify the promises after the agent finishes a turn.
#
# Registered as a `stop` hook in .kiro/agents/kept.json. The build plan called
# this PostTaskExec, which is the IDE's name; the CLI's documented triggers are
# agentSpawn, userPromptSubmit, preToolUse, postToolUse and stop, and stop is the
# one that means "the turn is over".
#
# Exits 0 when nothing regressed, 1 with a message on stderr when something did.
# The agent does not get to decide that: this runs kept, and kept rules.

set -euo pipefail

cat >/dev/null # drain the hook event; this hook needs no field from it

root_directory="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "${root_directory}"

# Which project to verify. Defaults to this repository's demo fixture, because
# kept's own bindings are not written yet.
target="${KEPT_HOOK_ROOT:-fixtures/refund_engine}"
gate="${KEPT_HOOK_GATE:-no-regression}"

if [ ! -d "${target}" ]; then
  echo "kept hook: no such root: ${target}" >&2
  exit 1
fi

# Nothing to re-verify if no Python or criteria moved. Keeps a documentation turn
# from paying for a mutation run.
if git diff --quiet HEAD -- '*.py' '*.md' 2>/dev/null &&
  [ -z "$(git ls-files --others --exclude-standard -- '*.py' '*.md')" ]; then
  exit 0
fi

output="$(uv run kept verify --root "${target}" --gate "${gate}" 2>&1)" && status=0 || status=$?

headline="$(printf '%s\n' "${output}" | grep -E '^[0-9]+ promises' | tail -1)"
printf 'kept: %s (%s, gate %s)\n' "${headline:-no verdicts}" "${target}" "${gate}"

if [ "${status}" -ne 0 ]; then
  {
    printf 'kept: gate %s violated in %s\n' "${gate}" "${target}"
    printf '%s\n' "${output}" | grep -A20 -E 'REGRESSED|STALE:' || true
    printf 'Run: uv run kept prompt <PROMISE> --root %s\n' "${target}"
  } >&2
  exit 1
fi

exit 0
