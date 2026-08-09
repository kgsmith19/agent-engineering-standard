# Change

## Work
Issue:
Spec:
Slice(s):
<<<<<<< HEAD
Implementer: claude / copilot / codex / human

> Agent-created PRs must use a recognized provider author/prefix or `agent/<provider>/...`; `AI Review` fails closed on unknown implementation provenance.
=======
Implementer: chatgpt / claude / copilot / codex / human

> The Implementer line is descriptive, not trusted agent identity. Controlled agent work should use `agent/<provider>/...` (for example `agent/chatgpt/42-fix`). Ordinary/user-authored branches are treated as ambiguous and require both Codex + Copilot for unattended merge.
>>>>>>> origin/main

## What Changed
-

## Evidence
- [ ] Required `PR Gate` passes on the latest head
- [ ] Required `AI Review` passes on the latest head
- [ ] Acceptance satisfied
- [ ] Risk/security evidence passes when applicable

## Risk
R0 / R1 / R2 / R3 / R4

## Not Included
-

## Integrity
- [ ] Tests/policies were not weakened
- [ ] Scope was not unnecessarily widened
- [ ] Repeated manual work was automated in-scope or logged as one bounded automation/research candidate

## Manual Gate (only when actually required)
None, or state all four:
- Failure class prevented:
- Why automation is insufficient today:
- Decision owner:
- Gate removal condition:
