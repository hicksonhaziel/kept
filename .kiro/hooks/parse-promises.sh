#!/usr/bin/env bash
# Guard the specification after a write: if kept can no longer read a criterion,
# say so immediately rather than at the end of the task.
#
# Registered as a `postToolUse` hook on write in .kiro/agents/kept.json. Cheap by
# design: parsing is pure and runs in well under a second, so it can afford to run
# on every edit. It reaches no verdict.

set -euo pipefail

cat >/dev/null # drain the hook event

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

if output="$(uv run kept parse --quiet 2>&1)"; then
  printf 'kept: %s\n' "$(printf '%s\n' "${output}" | tail -1 | sed 's/^ *//')"
  exit 0
fi

{
  printf 'kept: the specification no longer parses cleanly\n'
  printf '%s\n' "${output}"
} >&2
exit 1
