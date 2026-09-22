# Capability compiler corpus (Stage 54a, #145)

Frozen, hand-adjudicated capability actions. Every entry's
`expected_rule` must equal `tools/capability_compiler.check(entry.action).rule`
and `expected_verdict` the verdict.
`standardctl capability-compiler` validates the set on every run.

## What the compiler proves

Stage 54a (Standard half) compiles role/phase/task profiles
into concrete capability bounds — read/write roots, execute
and network allowlists, secret handles, owner-gated ops:

- `foreign-read` / `foreign-write` — outside roots DENY.
- `frozen-mold` / `direct-main` — regenerations and PRs only.
- `secret-mount` / `arbitrary-egress` — handles and
  allowlists only.
- `focused-edit` / `test-command` — routine work ALLOWs.
- `mcp-research-write` — research stays read-only.
- `no-sandbox` — ESCALATE dry-run/report.
- `owner-escalation` — owner approval ALLOWs with record.

## Dry-run first

Sharp edges deny immediately; full hard enforcement waits for
false-block and approval-reduction data. Provider sandbox
mechanics belong to the 54b agent-extensions half.
