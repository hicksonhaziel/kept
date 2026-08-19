# Evidence

**25 promises · 4 kept · 21 weak**

Commit `68ff7bdcacc7652f33fb908050767ec82baf35ed`, kept 0.1.0.

Produced by `kept verify`. This is **evidence, not proof**: mutation survival is a strong negative signal, but a killed mutant is not a guarantee of correctness.

Settings: threshold 1.0, cap 12 mutants per promise.

## Verdicts

| Promise | Verdict | Caught | Oracles | Note |
|---|---|---|---|---|
| REQ-1.1 | weak | 6/9 | 1 | 3 of 9 detectable breakages went unnoticed by this promise's own oracles |
| REQ-1.2 | weak | 6/7 | 1 | 1 of 7 detectable breakages went unnoticed by this promise's own oracles |
| REQ-1.3 | weak | 6/7 | 1 | 1 of 7 detectable breakages went unnoticed by this promise's own oracles |
| REQ-1.4 | weak | 7/10 | 1 | 3 of 10 detectable breakages went unnoticed by this promise's own oracles |
| REQ-1.5 | weak | 8/10 | 1 | 2 of 10 detectable breakages went unnoticed by this promise's own oracles |
| REQ-2.1 | weak | 6/11 | 1 | 5 of 11 detectable breakages went unnoticed by this promise's own oracles |
| REQ-2.2 | weak | 8/11 | 1 | 3 of 11 detectable breakages went unnoticed by this promise's own oracles |
| REQ-2.3 | weak | 7/11 | 1 | 4 of 11 detectable breakages went unnoticed by this promise's own oracles |
| REQ-2.4 | weak | 6/10 | 1 | 4 of 10 detectable breakages went unnoticed by this promise's own oracles |
| REQ-3.1 | weak | 1/6 | 1 | 5 of 6 detectable breakages went unnoticed by this promise's own oracles |
| REQ-3.2 | kept | 1/1 | 1 |  |
| REQ-3.3 | kept | 8/8 | 1 |  |
| REQ-3.4 | weak | 1/6 | 1 | 5 of 6 detectable breakages went unnoticed by this promise's own oracles |
| REQ-4.1 | weak | 4/7 | 1 | 3 of 7 detectable breakages went unnoticed by this promise's own oracles |
| REQ-4.2 | kept | 8/8 | 1 |  |
| REQ-4.3 | weak | 6/8 | 1 | 2 of 8 detectable breakages went unnoticed by this promise's own oracles |
| REQ-4.4 | weak | 3/8 | 1 | 5 of 8 detectable breakages went unnoticed by this promise's own oracles |
| REQ-4.5 | weak | 3/8 | 1 | 5 of 8 detectable breakages went unnoticed by this promise's own oracles |
| REQ-5.1 | kept | 7/7 | 1 |  |
| REQ-5.2 | weak | 4/6 | 1 | 2 of 6 detectable breakages went unnoticed by this promise's own oracles |
| REQ-5.3 | weak | 3/7 | 1 | 4 of 7 detectable breakages went unnoticed by this promise's own oracles |
| REQ-5.4 | weak | 2/5 | 1 | 3 of 5 detectable breakages went unnoticed by this promise's own oracles |
| REQ-6.1 | weak | 7/11 | 1 | 4 of 11 detectable breakages went unnoticed by this promise's own oracles |
| REQ-6.2 | weak | 7/10 | 1 | 3 of 10 detectable breakages went unnoticed by this promise's own oracles |
| REQ-6.3 | weak | 7/11 | 1 | 4 of 11 detectable breakages went unnoticed by this promise's own oracles |

## What the verdicts mean

**kept** — Bound oracles passed, assert something, and caught every breakage of the covered lines that any bound oracle proved detectable.

**weak** — Bound oracles passed, but missed a breakage that another bound oracle caught. The implementation can be broken while this promise still reports success.

## Missed breakages

Each line below is a change to the implementation that this promise's own oracles did not notice, but another promise's oracle did. That another oracle caught it is the proof the breakage is detectable, which is why it counts against this one.

### REQ-1.1

- `refund.py:105` - to + — caught by REQ-1.4, REQ-1.5
- `refund.py:122` <= to < — caught by REQ-1.3
- `refund.py:124` > to >= — caught by REQ-1.5

### REQ-1.2

- `refund.py:122` <= to < — caught by REQ-1.3

### REQ-1.3

- `refund.py:122` <= to >= — caught by REQ-1.2

### REQ-1.4

- `refund.py:122` <= to < — caught by REQ-1.3
- `refund.py:124` > to >= — caught by REQ-1.5
- `refund.py:130` return None instead — caught by REQ-2.2

### REQ-1.5

- `refund.py:122` <= to < — caught by REQ-1.3
- `refund.py:130` return None instead — caught by REQ-2.2

### REQ-2.1

- `refund.py:105` - to + — caught by REQ-1.4, REQ-1.5
- `refund.py:120` return None instead — caught by REQ-2.2
- `refund.py:122` <= to < — caught by REQ-1.3
- `refund.py:124` > to >= — caught by REQ-1.5
- `refund.py:130` return None instead — caught by REQ-2.2

### REQ-2.2

- `refund.py:105` - to + — caught by REQ-1.4, REQ-1.5
- `refund.py:122` <= to < — caught by REQ-1.3
- `refund.py:124` > to >= — caught by REQ-1.5

### REQ-2.3

- `refund.py:105` - to + — caught by REQ-1.4, REQ-1.5
- `refund.py:122` <= to < — caught by REQ-1.3
- `refund.py:124` > to >= — caught by REQ-1.5
- `refund.py:130` return None instead — caught by REQ-2.2

### REQ-2.4

- `refund.py:105` - to + — caught by REQ-1.4, REQ-1.5
- `refund.py:122` <= to < — caught by REQ-1.3
- `refund.py:124` > to >= — caught by REQ-1.5
- `refund.py:130` return None instead — caught by REQ-2.2

### REQ-3.1

- `refund.py:30` <= to >= — caught by REQ-4.2, REQ-4.3
- `refund.py:33` >= to > — caught by REQ-4.2, REQ-4.3
- `refund.py:33` >= to <= — caught by REQ-4.1, REQ-4.2, REQ-4.4
- `refund.py:34` * to / — caught by REQ-4.2, REQ-4.3, REQ-4.5
- `refund.py:44` * to / — caught by REQ-5.1

### REQ-3.4

- `refund.py:30` <= to >= — caught by REQ-4.2, REQ-4.3
- `refund.py:33` >= to > — caught by REQ-4.2, REQ-4.3
- `refund.py:33` >= to <= — caught by REQ-4.1, REQ-4.2, REQ-4.4
- `refund.py:34` * to / — caught by REQ-4.2, REQ-4.3, REQ-4.5
- `refund.py:44` * to / — caught by REQ-5.1

### REQ-4.1

- `refund.py:30` <= to >= — caught by REQ-4.2, REQ-4.3
- `refund.py:30` condition forced to True — caught by REQ-4.2, REQ-4.3
- `refund.py:33` >= to > — caught by REQ-4.2, REQ-4.3

### REQ-4.3

- `refund.py:33` >= to <= — caught by REQ-4.1, REQ-4.2, REQ-4.4
- `refund.py:33` condition forced to True — caught by REQ-4.1, REQ-4.2

### REQ-4.4

- `refund.py:30` <= to >= — caught by REQ-4.2, REQ-4.3
- `refund.py:30` condition forced to True — caught by REQ-4.2, REQ-4.3
- `refund.py:33` >= to > — caught by REQ-4.2, REQ-4.3
- `refund.py:33` condition forced to True — caught by REQ-4.1, REQ-4.2
- `refund.py:34` * to / — caught by REQ-4.2, REQ-4.3, REQ-4.5

### REQ-4.5

- `refund.py:30` <= to >= — caught by REQ-4.2, REQ-4.3
- `refund.py:30` condition forced to True — caught by REQ-4.2, REQ-4.3
- `refund.py:33` >= to > — caught by REQ-4.2, REQ-4.3
- `refund.py:33` >= to <= — caught by REQ-4.1, REQ-4.2, REQ-4.4
- `refund.py:33` condition forced to True — caught by REQ-4.1, REQ-4.2

### REQ-5.2

- `refund.py:42` >= to <= — caught by REQ-5.1
- `refund.py:42` condition forced to True — caught by REQ-5.1

### REQ-5.3

- `refund.py:40` <= to >= — caught by REQ-5.1, REQ-5.2
- `refund.py:42` >= to <= — caught by REQ-5.1
- `refund.py:42` condition forced to True — caught by REQ-5.1
- `refund.py:44` * to / — caught by REQ-5.1

### REQ-5.4

- `refund.py:40` <= to >= — caught by REQ-5.1, REQ-5.2
- `refund.py:40` <= to >= — caught by REQ-5.2
- `refund.py:40` condition forced to True — caught by REQ-5.2

### REQ-6.1

- `refund.py:105` - to + — caught by REQ-1.4, REQ-1.5
- `refund.py:122` <= to < — caught by REQ-1.3
- `refund.py:124` > to >= — caught by REQ-1.5
- `refund.py:130` return None instead — caught by REQ-2.2

### REQ-6.2

- `refund.py:105` - to + — caught by REQ-1.4, REQ-1.5
- `refund.py:122` <= to < — caught by REQ-1.3
- `refund.py:124` > to >= — caught by REQ-1.5

### REQ-6.3

- `refund.py:105` - to + — caught by REQ-1.4, REQ-1.5
- `refund.py:122` <= to < — caught by REQ-1.3
- `refund.py:124` > to >= — caught by REQ-1.5
- `refund.py:130` return None instead — caught by REQ-2.2

## Unpinned lines

Breakages that **no** bound oracle noticed. These are charged to the suite rather than to any one promise: if nothing detects them, blaming a single promise would be misattribution.

| Location | Breakage | Covered by |
|---|---|---|
| `refund.py:19` | body of __init__ replaced by return None | 7 promises |
| `refund.py:25` | 1 to 0 | 9 promises |
| `refund.py:25` | 1 to 2 | 9 promises |
| `refund.py:30` | <= to < | 7 promises |
| `refund.py:30` | condition forced to False | 5 promises |
| `refund.py:30` | 0 to 1 | 1 promises |
| `refund.py:33` | condition forced to False | 1 promises |
| `refund.py:40` | or to and | 6 promises |
| `refund.py:40` | <= to < | 6 promises |
| `refund.py:40` | <= to < | 2 promises |
| `refund.py:40` | condition forced to False | 2 promises |
| `refund.py:40` | 0 to 1 | 1 promises |
| `refund.py:40` | 0 to 1 | 1 promises |
| `refund.py:42` | >= to > | 5 promises |
| `refund.py:42` | condition forced to False | 1 promises |
| `refund.py:50` | <= to < | 1 promises |
| `refund.py:59` | % to * | 1 promises |
| `refund.py:59` | * to / | 1 promises |
| `refund.py:60` | True to False | 1 promises |
| `refund.py:83` | < to <= | 12 promises |
| `refund.py:83` | condition forced to False | 2 promises |
| `refund.py:117` | condition forced to False | 3 promises |
| `refund.py:122` | condition forced to True | 2 promises |

## Sources judged

| File | SHA-256 |
|---|---|
| `refund.py` | `f66ddc49ffbf` |
