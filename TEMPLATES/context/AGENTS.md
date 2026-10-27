# <name> context

Context-local rules only. Repository rules live in the root `AGENTS.md` and
`AGENTS/*.md`: link to them, never copy them. Budget: 120 lines.

Root rules: `<path to repository root>/AGENTS.md`, `<path to repository root>/AGENTS/contexts.md`.

## Purpose

<One sentence, matching the `purpose` in context.yaml.>

## Invariants

- <Rule that must always hold inside this context.>

## Public Interface

Other contexts may use only these paths (the `public` list in context.yaml):

- `<relative/path>`: <what it provides>

## Scoped Commands

Run from the repository root:

- Test: `<command>`
- Lint: `<command>` (optional)

## Do Not Touch

- `<path>`: <owner or generator; change it through that owner>

## Layering

Dependencies point inward: domain (pure rules) -> application (use cases) -> interface/infrastructure (CLI, storage, network).
