# Configuration

In a Kiro project, `kept verify` needs no flags: `--root` defaults to the working
directory and specifications are discovered from `.kiro/specs/*/requirements.md`.

If your project needs something else, say it once in `.kept/config.toml` instead of
repeating it on every run and in CI.

```toml
version = 1

spec = ["docs/acceptance.md"]   # for projects without .kiro/specs
source = "myapp"                # what coverage should measure
tests = "tests/unit"            # restrict collection
gate = "no-regression"
threshold = 1.0
cap = 12
```

Commit it. `kept verify` is then the whole command again.

## Every key

| Key | Type | Applies to | Default |
|---|---|---|---|
| `spec` | list of paths | bind, observe, attack, verify, prompt, serve | discovered from `.kiro/specs` |
| `tests` | path | bind, observe, attack, verify, serve | whole suite |
| `source` | path | observe, attack, verify, serve | `.` |
| `python` | path | bind, observe, attack, verify, serve | active venv, else nearest `.venv` |
| `cap` | integer | attack, verify | 12 mutants per promise |
| `workers` | integer | attack, verify | 8 |
| `timeout` | number | attack, verify | 10.0 seconds per mutant |
| `threshold` | number | verify | 1.0 |
| `gate` | string | verify | `no-regression` |
| `show_unpinned` | integer | verify | 10 |

`--root` is deliberately **not** configurable: the file lives under the root, so the
root has to be known before the file can be read.

## Precedence

```
explicit flag  →  .kept/config.toml  →  built-in default
```

## Mistakes are refused, not ignored

> [!WARNING]
> An unknown key or a value of the wrong type stops the run with exit code 2.

```console
$ kept verify
kept: C001 .kept/config.toml sets unknown key 'treshold'. Remove it or correct the
spelling. Known keys: cap, gate, python, show_unpinned, source, spec, tests,
threshold, timeout, workers.
```

A misspelled `treshold` that was silently ignored would leave you believing a
threshold had been applied. Refusing the run is the kinder failure. Likewise
`cap = true` is rejected: a boolean is an integer in Python, and it is never what
was meant.

| Code | Problem |
|---|---|
| `C001` | unknown key |
| `C002` | value is not of the type the key requires |
| `C004` | file declares a `version` this kept cannot read |

Malformed TOML raises before any work happens, also exit 2.

## Reproducibility

The settings that can change a verdict — `threshold` and `cap` — are recorded in
the ledger, so a published number stays reproducible by someone who never sees your
config file.

```json
"settings": { "cap": 12, "seed": 0, "threshold": 1.0 }
```

Two ledgers are only comparable if those agree. Check them before reading a
difference in verdicts as a change in quality.
