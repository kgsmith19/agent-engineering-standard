# AGENTS.md

This repository follows `kgsmith19/agent-engineering-standard`, pinned in `.agent/standard.lock`.

## Product truth

- `PRD.md` — what/why/outcomes/requirements
- `specs/` — implementation contract only when behavior is nontrivial
- `docs/adr/` — consequential, hard-to-reverse architecture decisions only

## Work

GitHub Issues are the durable work-item source.

`Issue → SPEC if needed → thin slice → evidence → RED/minimum GREEN when appropriate → PR → PR Gate → merge/release`

Work one thin slice at a time. Keep PRs coherent and reviewable. Keep PRs draft while still iterating; make them ready only after local verification.

## Quality

Use the cheapest evidence sufficient for the change. Do not weaken tests, evaluators, policies, or security boundaries to obtain GREEN. Verify before claiming completion.

## Risk

Use the shared R0–R4 scale. The implementing agent may raise risk, never lower it. R3/R4 and control-plane changes require fresh independent semantic review before merge.

## Code Review Rules

- Flag requirement/spec mismatches even when tests pass.
- Flag tests that can pass without proving the behavior they claim to prove.
- Flag weakened authority/security/evaluator boundaries and unnecessary scope/complexity.
- For UI changes, confirm important user-visible behavior is covered by an appropriate Playwright journey or explicitly justified stronger evidence.
