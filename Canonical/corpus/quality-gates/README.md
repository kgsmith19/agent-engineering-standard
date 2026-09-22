# Quality and architecture gates corpus (Stage 37, #128)

Frozen, hand-adjudicated fixture outcomes for stack-native
quality gates. Every entry's `expected_class` must equal the
rule of the single finding from
`tools/quality_gates.classify(entry.fixture)` (empty when
`expected_ok` is true); `expected_ok` must equal the ok flag.
`standardctl quality-gates` validates the set on every run.

## What the gates prove

Stage 37 declares portable repository-selected linters,
analyzers, dead-code, duplication, dependency, and
architecture tests — without forcing one universal tool
choice, without a global LOC/coverage/mutation gate, and
without enforcing the exhaustive CI matrix locally:

- `lint` — mutual exclusion (Biome vs ESLint), Ruff
  correctness, Roslyn correctness, no-op rejection, seeded
  bad-import detection, scanner-synthetic issues, generated
  exclusion.
- `types` — Pyright correctness on the Python stack.
- `dead-code` — dead-export detection.
- `duplication` — duplicated-block detection.
- `dependency` — invalid dependency direction rejected.
- `architecture` — Roslyn/NetArchTest boundary correctness.

## Local vs CI

Fast affected checks stay local; the exhaustive matrix stays
in CI. This module validates declarations and classifies
fixture outcomes — it never executes the tools themselves.
