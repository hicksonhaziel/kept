# Agents and MCP

kept is built to sit inside an agent loop without a model ever entering the
verification path. The agent proposes; the ledger disposes.

## The MCP server

```bash
uv add --dev "kept-cli[mcp]"
kept serve --root .
```

In `.kiro/agents/<name>.json`:

```json
{
  "mcpServers": {
    "kept": { "command": "kept", "args": ["serve", "--root", "."] }
  }
}
```

`/tools` should then list four `@kept/` tools.

| Tool | Does | Read-only |
|---|---|---|
| `list_promises` | every criterion, with the verdict recorded for it | yes |
| `read_ledger` | the committed ledger and the evidence behind each verdict | yes |
| `remediation_brief` | what one promise's evidence says, and the change it asks for | yes |
| `verify` | runs the pipeline — the only tool that can move a verdict | no |

> [!IMPORTANT]
> No tool accepts a filesystem path. The root and the specification are fixed by the
> flags the server starts with, so a client cannot redirect kept at another project.
> A test asserts that no tool's input schema ever grows one.

The server's instructions tell the client, in as many words, that it cannot set a
verdict and neither can the server. `remediation_brief` is a suggestion rendered
deterministically from recorded evidence — see
[ADR-0005](adr/0005-the-brief-is-outside-the-verification-path.md) for why a
`--suggest` flag that drafts the missing assertion was rejected.

## Kiro hooks

Two hooks, in `.kiro/agents/<name>.json`:

```json
{
  "hooks": {
    "postToolUse": [
      { "matcher": "write", "command": ".kiro/hooks/parse-promises.sh", "timeout_ms": 60000 }
    ],
    "stop": [
      { "command": ".kiro/hooks/verify-promises.sh", "timeout_ms": 900000 }
    ]
  }
}
```

**`postToolUse` on write** runs `kept parse`. Pure and sub-second, so it can afford
to run on every edit: a criterion the parser can no longer read is reported at the
edit rather than at the end of the task.

**`stop`** runs `kept verify --gate no-regression` once the turn is over, and exits
non-zero with the regressed promises on stderr. It skips silently when no `.py` or
`.md` file moved, so a documentation turn does not pay for a mutation run.

Two environment variables: `KEPT_HOOK_ROOT` (default `.`) and `KEPT_HOOK_GATE`
(default `no-regression`).

> [!NOTE]
> The Kiro IDE calls this trigger PostTaskExec. The CLI documents `agentSpawn`,
> `userPromptSubmit`, `preToolUse`, `postToolUse` and `stop`, and `stop` is the one
> that means the turn is over.

## The loop this enables

```text
agent writes code and tests
        │
        ▼
kept verify ──── WEAK ────► remediation_brief ────► agent strengthens the oracle
        │                                                     │
        │                                                     ▼
        └──────────────────── kept verify again ◄─────────────┘
                                    │
                                    ▼
                              KEPT, or a better reason
```

The agent can read evidence and act on a brief. It cannot mark its own work as
verified, because nothing in that path produces a verdict except `verify`, and
`verify` runs the same deterministic pipeline the CLI runs. That is
[rule 1](../.kiro/steering/verification-integrity.md), and it does not bend for
convenience.
