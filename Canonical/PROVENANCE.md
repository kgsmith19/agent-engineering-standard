# Capability Registry — Provenance

Owner research input (outside this repository; safekeeping copy on Desktop):

- Source file: `agent-engineering-v5-capability-registry.json`
- Package: `agent-engineering-v5-final-sdvfd-package`
- Package SHA256 of source: `521076b7e7663147655e0a5fb35389df765296e3ac16ce628ab827cee0753dbc`
- Records: 264 (234 preserved v4.2 IDs + 30 final research additions)
- Fields (14): Capability ID, Category, Capability, Current Repo Status,
  v4 Action, Normative Home, Machine Enforcement, Template/Schema,
  Test/Canary, Metric, Fail-Closed Behavior, Evidence,
  External Support Grade/Source, Eject/Override

Normalization into `Canonical/capabilities.json`:

- Sorted by Capability ID (byte order), LF newlines, 2-space JSON indent,
  single trailing newline, UTF-8.
- Canonical SHA256: `8478ac78d16a8b6c14dafbf5780ba2d9228a35bfbeb91df86b94c321ada3aff0`

Preservation matrix:

- Source file: `agent-engineering-v4.2-to-v5-preservation-matrix.csv`
- Package SHA256 of source: `6251a50b9e8ca686d97eead6e83cbc6299f38e7d584aad87e3146769ea1e614b`
- Rows: 264 data rows; 234 rows have v4.2 Status PRESENT; ID set equals
  the registry ID set exactly.

Status: audit metadata only. Normative policy remains in `AGENTS.md`
and `AGENTS/*.md`. This registry is never loaded by normal bootstrap
context.
