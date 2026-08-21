# Architecture decision records

The decisions that shape what a verdict means. Each one states the context, the
call, and the cost accepted — including the calls that are uncomfortable.

| | Decision | Why it needed writing down |
|---|---|---|
| [0001](0001-uppercase-keywords.md) | EARS keywords are recognised only in upper case | `WHEN a AND b` is a logical operator; `WHEN a name and address` is prose. No regular expression separates them reliably |
| [0002](0002-identity-versus-change-detection.md) | Identity is structural, change detection is content-based | Rewording a criterion must not discard its history, and must still invalidate its evidence. That needs two mechanisms, not one |
| [0003](0003-a-criterion-kills-only-with-its-own-oracles.md) | A criterion kills a mutant only through its own bound oracles | The most likely decision to be challenged. A verdict that leans on unbound tests is not traceable evidence |
| [0004](0004-no-arbitrary-pass-mark.md) | No arbitrary pass mark: a mutant counts only once some bound oracle proved it detectable | Removes the need for a magic percentage, and separates a weak oracle from an unbreakable line |
| [0005](0005-the-brief-is-outside-the-verification-path.md) | `kept prompt` is a suggestion, rendered from the ledger, outside the verdict path | Once an agent can call kept, the tempting next feature is a model-written patch. This is where that line is drawn |
| [0006](0006-cross-scope-detectability.md) | A breakage detectable only through another promise's inputs still counts | Explains most of kept's own 45 WEAK verdicts, and refuses three easier answers that would have flattered the number |

Anything that changes what a verdict means requires a new record here. That rule is
in [conventions.md](../../.kiro/steering/conventions.md).
