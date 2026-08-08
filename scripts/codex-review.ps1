param(
  [string]$Base = "origin/main",
  [string]$Model = "gpt-5.4-mini",
  [string]$Output = ".agent/codex-review.md"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
  throw "Codex CLI is required. Install/authenticate Codex before running this review."
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  throw "git is required."
}

$root = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { throw "Run from inside a Git repository." }
Set-Location $root

& git fetch origin --quiet
if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin." }

$dir = Split-Path -Parent $Output
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }

$prompt = @"
Act as an independent software reviewer. You did not participate in implementation and must not modify files.

Review the current branch against $Base. Inspect only the relevant repository context needed to judge the change, including:
- AGENTS.md
- the PRD / source of product truth
- the active SPEC or linked Issue when present
- the diff against $Base
- tests/evaluators that claim to prove the change
- nearby implementation and security/authority boundaries

Prioritize only material findings:
P0 catastrophic/security/data-loss
P1 likely correctness, requirement, security, or false-green defect
P2 meaningful maintainability/reliability/test gap likely to cause rework

Explicitly check:
1. Did implementation match the stated requirement/spec rather than merely the tests?
2. Could tests pass while the requirement is still wrong or incomplete?
3. Are acceptance, property, integration/contract, E2E, security, or migration tests missing where the risk calls for them?
4. Did the change weaken or bypass an evaluator, permission boundary, CI gate, or invariant?
5. Did scope/complexity expand without concrete benefit?
6. For UI work, do Playwright journeys exercise the important user-visible flow rather than only implementation details?

Do not report formatting/style nits that deterministic tooling can catch. Do not disagree for the sake of disagreement. If there are no P0-P2 findings, say exactly: NO MATERIAL FINDINGS.

For each finding give: priority, file/location, concrete failure scenario, why existing evidence misses it, and smallest credible fix.
"@

& codex exec --ephemeral --ignore-user-config --sandbox read-only -m $Model -o $Output $prompt
if ($LASTEXITCODE -ne 0) { throw "Codex review failed." }

Get-Content $Output
