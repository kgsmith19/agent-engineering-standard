# Seven-Surface `harness:` Contract Audit [T01]

Parent program: `kgsmith19/agent-engineering-standard#99`.
Amendment epic: `#196`. Work item: `#198` (T01).
Status: audit only — **zero behavior change**. GitHub sentences remain
authoritative for the GitHub rendering. `CLAUDE.md`/`GEMINI.md`
import-only exception-adapter status preserved. No file under
`TEMPLATES/**` modified.

Read-back date: 2026-09-21. Base: `origin/main` at claim time.
Classification vocabulary (plan §8): `generic-core` |
`harness-capability` | `exception-adapter`.

## Contract table

Exactly 7 surfaces (plan Q3 locked). Each row records: (a) the native
binding in use today, (b) the generic `harness:` capability contract
(declarative required capabilities, never the environment), (c) the
GitHub shipped rendering, (d) the §8 classification, (e) ownership.

| # | Surface | Native binding today | Generic `harness:` capability contract | GitHub shipped rendering | Class | Owner |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | tracker | GitHub Issues: thin Issues carry one observable outcome; labels `status:*` / `risk:R*`; `issue/<n>-<slug>` branches; one worktree + one PR per Issue | `harness: {tracker: <binding>}` — work tracker offering: thin work items with acceptance criteria, state labels, branch/worktree linkage, PR linkage, close-by-merge receipt | GitHub Issues + `TEMPLATES/ISSUE.md` + claim protocol (`AGENTS/work.md`) | harness-capability | TBD — candidate: T05 (#202) tracker/pipeline/gate contracts |
| 2 | pipeline | GitHub Actions: `pr-gate.yml` (sole required check aggregator), `merge-policy.yml` (metadata automation), `llm-review.yml` + comment delivery, dev/reviewer post workflows | `harness: {pipeline: <binding>}` — CI pipeline offering: required-check aggregation, metadata-only merge policy, review-result delivery, artifact upload | `.github/workflows/pr-gate.yml` + `merge-policy.yml` + `llm-review*.yml` + `dev-agent-post*.yml` | harness-capability | TBD — candidate: T05 (#202) tracker/pipeline/gate contracts |
| 3 | gate | Single fail-closed aggregator `Agent Engineering Standard PR Gate`; `verify` + unittest + `llm_review` strictness feed it; flags-off jobs deleted from render, never stubbed (Q13) | `harness: {gate: <binding>}` — merge gate offering: exact-head verification, fail-closed aggregation, no-bypass except owner override | `Agent Engineering Standard PR Gate` job + `tools/standardctl.py verify` + `check_gate_noop_stages` | generic-core | TBD — candidate: T05 (#202); gate topology owned by standard core |
| 4 | secrets/identity | Infisical (project `hyperbolic-core`, env `prod`, machine identity `ai-coding-harness`); dev-agent + review-agent GitHub Apps; refs only in repo, never values | `harness: {secrets: <store-ref>, identity: <role-map>}` — secret store offering: named refs (never values), short-lived identity tokens, role separation (builder vs reviewer) | `~/.config` harness docs + `fetch-agent-secrets.ps1` adapter + `AGENTS/governance.md` agent identities | harness-capability | TBD — candidate: T04 (#201) secret-store/identity contracts; native links T22 (#216) |
| 5 | filesystem/runtime | Local repo at `C:\code\<repo>`; isolated work in `.worktrees/`; gitignored runtime `.superpowers/` + `.agent-runtime/`; ledger per Issue; zero-compaction target (Q4) | `harness: {filesystem: <binding>, runtime: <binding>}` — filesystem/runtime offering: isolated per-task worktrees, restart-safe ledger, governed rotation, no silent compaction | `.worktrees/` pattern (`project.yaml`) + `AGENTS/work.md` worktrees/ledger + `tools/standardctl.py worktrees` | harness-capability | TBD — candidate: T06 (#203) ledger/runtime contracts |
| 6 | extensions | `agent-extensions` sibling repo via `Canonical/sibling-contract.json` v1.0.0; catalog/profile schemas; `TEMPLATES/manifest.yaml` distribution | `harness: {extensions: <binding>}` — extension supply offering: versioned catalog, capability refs, additive-only compatibility gate, offline bootstrap | `Canonical/sibling-contract.json` + `Canonical/schemas/extension-*.schema.json` + `TEMPLATES/manifest.yaml` | harness-capability | TBD — candidate: T07 (#204) registry validation; native links agent-extensions#35–#37 |
| 7 | UX/commands | `python tools/standardctl.py verify/doctor/...` (stdlib-only, single file); `python -m unittest discover -s tests -p "test_*.py"`; `worktrees reconcile` | `harness: {commands: <binding>}` — command UX offering: deterministic verify, live-settings doctor, worktree reconcile, evidence validate/index | `tools/standardctl.py` + `project.yaml` commands + `README.md` lifecycle | generic-core | TBD — candidate: T08 (#205) edition-aware standardctl |

Exception-adapter note (not an 8th surface): `CLAUDE.md`/`GEMINI.md`
are import-only pointers (`@AGENTS.md`), classified
`exception-adapter`, preserved as-is. They are the existing
exception-adapters referenced by the issue Context; no new adapter is
declared here.

## Assumption audit

Every assumption behind the surface inventory, marked
verified / unknown / missing-input. Unknowns stay named; nothing is
invented.

| # | Assumption | Status | Evidence / note |
| --- | --- | --- | --- |
| A1 | Tracker surface = GitHub Issues with the claim protocol as the native binding | verified | `project.yaml` `work.tracker: github-issues`; `AGENTS/work.md` claim protocol; branch pattern `issue/<n>-<slug>` |
| A2 | Pipeline surface = GitHub Actions workflows listed in `.github/workflows/` | verified | `pr-gate.yml`, `merge-policy.yml`, `llm-review.yml`, `llm-review-comment.yml`, `dev-agent-post*.yml`, `reviewer-*.yml`, `post-work-state.yml` read back 2026-09-21 |
| A3 | Gate surface = single aggregator `Agent Engineering Standard PR Gate` | verified | `project.yaml` `ci.required_check`; `AGENTS/boundaries.md` sole-gate rule |
| A4 | Secrets native binding = Infisical + dev/reviewer GitHub Apps | verified | `AGENTS/governance.md` agent identities (App IDs 4656454/4656330); harness secret-provider docs; **values never read or recorded — refs only** |
| A5 | Filesystem native binding = `C:\code\<repo>` + `.worktrees/` + gitignored runtime dirs | verified | `project.yaml` `work.worktree_pattern`; `.gitignore` (`.worktrees/`, `.superpowers/`, `.agent-runtime/`, `.evidence/`); `AGENTS/work.md` |
| A6 | Extensions native binding = sibling contract v1.0.0 + catalog/profile schemas | verified | `Canonical/sibling-contract.json` (`contract_version: 1.0.0`); `Canonical/schemas/extension-*.schema.json`; `TEMPLATES/manifest.yaml` |
| A7 | UX/commands native binding = `standardctl.py` subcommands + unittest discovery | verified | `project.yaml` commands; `tools/standardctl.py --help` subcommand list; `README.md` lifecycle |
| A8 | `CLAUDE.md`/`GEMINI.md` are import-only exception adapters | verified | Both files contain only `@AGENTS.md` plus a heading; read back 2026-09-21 |
| A9 | Exact plan §8 classification wording per surface (which surfaces are generic-core vs harness-capability) | unknown | Plan source documents are owner-held (not in this repo); classification above follows the issue Context cues (gate/commands core-like, rest harness-bound) and is **input to T02, not a final verdict** |
| A10 | Ownership of each surface beyond TBD candidates | missing input | Owning repo/issue per surface is not yet decided; cells stay `TBD` with candidate pointers per the issue's Must-never-happen rule |
| A11 | Live GitHub settings (protection ruleset, required checks) match `TEMPLATES/` declarations | unknown | Not read back in this audit; `doctor --live` path owns that verification, untouched here |
| A12 | Sibling-repo surface state (agent-extensions / hyperbolic-core bindings) | missing input | Native-link issues (agent-extensions#35–#37, hyperbolic-core#396–#397) own those bindings; this audit covers the standard repo only |

## Sensitivity demonstration

Per the issue test strategy (docs-only R1; `verify` + unittest output
identical pre/post; diff is docs-only):

- Completeness: this document covers exactly the 7 Q3 surfaces —
  tracker, pipeline, gate, secrets/identity, filesystem/runtime,
  extensions, UX/commands. A removed row is detectable by counting the
  table rows (7 data rows) against the Q3 list; the assumption audit
  (A1–A8) gives one verified anchor per surface, so a dropped surface
  loses its anchor.
- No invented facts: every native-binding cell cites a repo path read
  back 2026-09-21; assumptions that could not be verified are marked
  unknown/missing-input (A9–A12), never filled in.
- No behavior change: the change adds exactly one new file under
  `Canonical/`; `python tools/standardctl.py verify` and
  `python -m unittest discover -s tests -p "test_*.py"` run identically
  before and after (receipts in the PR).

## T02 handoff

T02 (#199) finalizes the `harness:`/`edition:`/`flags:` schema keys
against these contracts: each surface row's generic contract maps to
one `harness:` key (`tracker`, `pipeline`, `gate`, `secrets` +
`identity`, `filesystem` + `runtime`, `extensions`, `commands`);
classification (generic-core | harness-capability) guides which keys
are edition-scoped; exception-adapters (`CLAUDE.md`/`GEMINI.md`) stay
out of the schema per Q8 (`adapters:` reserved).
