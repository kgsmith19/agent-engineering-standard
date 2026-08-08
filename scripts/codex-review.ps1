param(
  [string]$Base = "origin/main",
  [string]$Model = "gpt-5.4-mini",
  [string]$Output = ".agent/codex-review.md"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) { throw "Codex CLI is required. Install/authenticate Codex before running this review." }
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "git is required." }

$root = (& git rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0) { throw "Run from inside a Git repository." }
Set-Location $root

& git fetch origin --quiet
if ($LASTEXITCODE -ne 0) { throw "Could not fetch origin." }

$dir = Split-Path -Parent $Output
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Force $dir | Out-Null }

$prompt = @"
Act as ONE independent review agent performing a batched multi-lens review. You did not participate in implementation, have no implementation-session context, and must not modify files.

Review the current branch against $Base. Read only the minimum relevant context: AGENTS.md, product truth/PRD, linked Issue/SPEC/slice when present, the diff, claimed test evidence, and nearby security/authority boundaries.

Use these four lenses in one pass to minimize model cost:

1. SOFTWARE / SECURITY
   - requirement/spec correctness versus merely satisfying tests
   - false-green tests, missing evidence, regressions, security/authority boundary weakening
   - data loss, migration, auth, PII, secrets, concurrency, failure/recovery risk when relevant

2. BUSINESS / PRODUCT
   - does this change solve the stated user/business outcome?
   - is there scope that adds cost or complexity without measurable value?
   - did implementation miss the highest-ROI or simplest acceptable outcome?
   - flag only material product mismatch, not taste

3. SYSTEMS / OPTIMIZATION
   - unnecessary layers, dependencies, state, files, jobs, services, model calls, or repeated manual work
   - opportunities to replace recurring manual effort with a small deterministic automation
   - CI/runtime/cost waste introduced by the change
   - preserve maintainability; do not optimize into cleverness

4. LEANNESS
   - smallest correct implementation, low LOC/complexity, reuse before abstraction
   - dead code, stale branches/config, duplicated process, speculative framework-building
   - modern idiomatic approach without novelty for novelty's sake

Prioritize only material findings:
P0 catastrophic/security/data-loss
P1 likely correctness, requirement, security, authority, or false-green defect
P2 meaningful business-value, maintainability, reliability, complexity, cost, or test gap likely to cause rework

For each finding give: priority, lens, file/location, concrete failure/cost scenario, why current evidence misses it, and the smallest credible fix.

If you discover a repeated manual workaround or missing automation that is OUTSIDE this PR's approved scope, do not widen the PR. Report it as:
AUTOMATION CANDIDATE: problem | evidence | expected ROI | smallest experiment | research needed

Do not report formatting/style nits deterministic tooling can catch. Do not disagree for the sake of disagreement. If there are no P0-P2 findings, say exactly: NO MATERIAL FINDINGS.
"@

& codex exec --ephemeral --ignore-user-config --sandbox read-only -m $Model -o $Output $prompt
if ($LASTEXITCODE -ne 0) { throw "Codex review failed." }

Get-Content $Output
