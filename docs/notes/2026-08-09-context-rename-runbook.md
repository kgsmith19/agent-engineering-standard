# Context-rename runbook: `PR Gate` → `Gate: Deterministic CI`

The pipeline taxonomy rename (`Gate:` / `Orchestrator:` / `Advisory:` / `Ops:`) ships with a
zero-unmergeable-window bridge: every gate workflow keeps a `pr-gate-bridge` job named exactly
`PR Gate` (`needs: [gate]`, `exit 0`), so the ruleset's required `PR Gate` context stays green
until the owner flips it. Fail-closed: a gate failure skips the bridge, the required context
goes missing, and the merge stays blocked. Nothing in this runbook is executable by automation —
ruleset writes are owner authority.

## 1. Per-repo owner checklist (ruleset flip)

For each repository below, in the GitHub UI:

1. Settings → Rules → Rulesets → **Lean PR Gate** → Edit.
2. Under **Require status checks to pass**, add `Gate: Deterministic CI` (source: GitHub Actions).
3. Remove `PR Gate` from the required list.
4. Save. Open PRs re-evaluate on their next check event; the six-hourly watchdog converges stragglers.

Repositories (currently managed set):

- [ ] agent-engineering-standard
- [ ] agentic-command-center
- [ ] agentic-command-center-ui
- [ ] prompt-organizer
- [ ] toolbelt
- [ ] lifeos
- [ ] lifeos-ui
- [ ] network-checker

(The five phase-4 repositories — 2048Game, ShaesChicDesignsWeb, PitchRandomizer, AutoHit,
AccountPortal — get the new names at bootstrap time and never need the flip.)

## 2. Cleanup PR (after every ruleset is flipped)

One standard-side PR, plus the pinned rollout to products:

- Remove the `pr-gate-bridge` job from `.github/workflows/ci.yml` and `templates/PR_GATE.yml`.
- Set `policy/github-defaults.json` `required_status_context` to the `required_status_context_next`
  value (`Gate: Deterministic CI`) and delete `required_status_context_next`.
- Drop doctor's transition assertions (the either-context acceptance and the bridge requirement);
  pin `required_status_context` to `Gate: Deterministic CI` exactly.
- In each product `.agent/project.yaml`, replace `required_check` with the `required_check_next`
  value and delete `required_check_next`.
- No script changes are needed: gate check-run readers already resolve the context from
  `required_status_context`.

## 3. Standing admin blockers (unchanged by this rename)

- `agentic-command-center-ui` has repository setting **Allow auto-merge OFF**; arming fails there
  until the owner enables it (Settings → General → Pull Requests) or provisions
  `AUTOMATION_TOKEN` with Administration:write.
- `AUTOMATION_TOKEN` (fine-grained PAT: Administration:read + Contents:write + Pull requests:write)
  must be installed as an Actions secret — and made available to Dependabot-triggered runs — in
  every managed repository for arming and the Ops lane to work end-to-end.
- Audit the ruleset history for any window in which failed-Gate Dependabot merges were possible;
  the canonical ruleset must be the sole active default-branch authority everywhere.
- Optional: a scoped GitHub App to replace the PAT remains an owner authority item; nothing in
  this repo mints App tokens.
