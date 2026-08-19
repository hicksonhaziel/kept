# Evidence

**5 promises · 5 kept · 0 weak**

Commit `a3727462d620596942675f07279372429f57b2b3`, kept 0.1.0.

Produced by `kept verify`. This is **evidence, not proof**: mutation survival is a strong negative signal, but a killed mutant is not a guarantee of correctness.

Settings: threshold 1.0, cap 12 mutants per promise.

## Verdicts

| Promise | Verdict | Caught | Oracles | Note |
|---|---|---|---|---|
| REQ-1.1 | kept | 2/2 | 1 |  |
| REQ-1.2 | kept | 2/2 | 1 |  |
| REQ-1.3 | kept | 2/2 | 1 |  |
| REQ-1.4 | kept | 2/2 | 1 |  |
| REQ-1.5 | kept | 2/2 | 1 |  |

## What the verdicts mean

**kept** — Bound oracles passed, assert something, and caught every breakage of the covered lines that any bound oracle proved detectable.

## Sources judged

| File | SHA-256 |
|---|---|
| `slug.py` | `1759252e937c` |
