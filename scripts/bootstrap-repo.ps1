param(
  [Parameter(Mandatory)][string]$Name,
  [ValidateSet('private','public')][string]$Visibility = 'private',
  [string]$Description = '',
  [string]$Destination = (Get-Location).Path
)

$ErrorActionPreference = 'Stop'
foreach ($cmd in @('gh','git')) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$cmd is required." }
}
& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'gh is not authenticated.' }

$standardRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$standardSha = (& git -C $standardRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the standards commit.' }
$owner = ((Get-Content (Join-Path $standardRoot 'policy/github-defaults.json') -Raw | ConvertFrom-Json).owner)
$repo = "$owner/$Name"
$target = Join-Path $Destination $Name

& gh repo view $repo --json nameWithOwner 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
  $visibilityFlag = if ($Visibility -eq 'public') { '--public' } else { '--private' }
  $args = @('repo','create',$repo,$visibilityFlag,'--clone')
  if ($Description) { $args += @('--description',$Description) }
  Push-Location $Destination
  try { & gh @args | Out-Host } finally { Pop-Location }
  if ($LASTEXITCODE -ne 0) { throw "Could not create $repo" }
}
elseif (-not (Test-Path $target)) {
  Push-Location $Destination
  try { & gh repo clone $repo | Out-Host } finally { Pop-Location }
  if ($LASTEXITCODE -ne 0) { throw "Could not clone $repo" }
}

New-Item -ItemType Directory -Force (Join-Path $target '.agent') | Out-Null
New-Item -ItemType Directory -Force (Join-Path $target 'specs') | Out-Null
New-Item -ItemType Directory -Force (Join-Path $target 'docs/adr') | Out-Null
New-Item -ItemType Directory -Force (Join-Path $target '.github/ISSUE_TEMPLATE') | Out-Null
New-Item -ItemType Directory -Force (Join-Path $target '.github/workflows') | Out-Null

# Dependabot config: install only if the repository does not already have one
# so that stack-specific customisations (e.g. Python enabled) are preserved.
$dependabotDest = Join-Path $target '.github/dependabot.yml'
if (-not (Test-Path $dependabotDest)) {
    Copy-Item (Join-Path $standardRoot 'templates/dependabot.yml') $dependabotDest -Force
}

Copy-Item (Join-Path $standardRoot 'templates/AGENTS.md') (Join-Path $target 'AGENTS.md') -Force
Copy-Item (Join-Path $standardRoot 'templates/PRD.md') (Join-Path $target 'PRD.md') -Force
Copy-Item (Join-Path $standardRoot 'templates/ISSUE.md') (Join-Path $target '.github/ISSUE_TEMPLATE/work-item.md') -Force
Copy-Item (Join-Path $standardRoot 'templates/PULL_REQUEST.md') (Join-Path $target '.github/PULL_REQUEST_TEMPLATE.md') -Force
Copy-Item (Join-Path $standardRoot 'templates/PR_GATE.yml') (Join-Path $target '.github/workflows/pr-gate.yml') -Force
Copy-Item (Join-Path $standardRoot 'templates/AI_REVIEW.yml') (Join-Path $target '.github/workflows/ai-review.yml') -Force
Copy-Item (Join-Path $standardRoot 'templates/CODEOWNERS') (Join-Path $target '.github/CODEOWNERS') -Force

@"
standard: $owner/agent-engineering-standard
commit: $standardSha
pinned_at: "$(Get-Date -Format yyyy-MM-dd)"
pinned_by: bootstrap-repo.ps1
"@ | Set-Content (Join-Path $target '.agent/standard.lock') -Encoding utf8

@"
project:
  name: $Name

standard:
  repo: $owner/agent-engineering-standard
  sha: $standardSha

work_tracking:
  system: github-issues

ci:
  required_check: "PR Gate"
  ai_review_check: "AI Review"
  gate_profile: bootstrap-only

# Before product code lands, replace the bootstrap-only PR Gate with the cheapest
# repo-specific objective build/test/acceptance evidence for the detected stack.
# Keep the shared AI Review caller intact unless the control-plane design changes.
"@ | Set-Content (Join-Path $target '.agent/project.yaml') -Encoding utf8

'@AGENTS.md' | Set-Content (Join-Path $target 'CLAUDE.md') -Encoding utf8

Push-Location $target
try {
  & git add AGENTS.md CLAUDE.md PRD.md specs docs/adr .agent .github
  & git commit -m 'chore: bootstrap lean agent engineering standard'
  if ($LASTEXITCODE -ne 0) { throw 'Initial bootstrap commit failed.' }
  & git push origin HEAD
  if ($LASTEXITCODE -ne 0) { throw 'Initial bootstrap push failed.' }
} finally { Pop-Location }

& pwsh -NoProfile -File (Join-Path $PSScriptRoot 'apply-github-standard.ps1') -Repositories $Name
if ($LASTEXITCODE -ne 0) { throw 'GitHub policy bootstrap failed.' }

$issueBody = @"
## Outcome
Replace the bootstrap-only PR Gate with the smallest objective gate appropriate to this repository's real stack before product code lands.

## Acceptance
- Detect and record verified build/test/type/lint/E2E commands in `.agent/project.yaml`.
- Replace `.github/workflows/pr-gate.yml` so `PR Gate` executes the cheapest sufficient independent evidence.
- Preserve `.github/workflows/ai-review.yml` so the required exact-head `AI Review` context continues to run.
- Extend `.github/CODEOWNERS` with the small repo-specific gate entrypoints whose weakening could make `PR Gate` falsely green; keep the canonical control-plane ownership rules as the final non-comment rules.
- Keep draft iteration local; ready PR and `merge_group` must produce the real `PR Gate`.
- Add only tests/tools justified by actual product risk; do not invent a framework just for conformity.
- Update `ci.gate_profile` away from `bootstrap-only`.

## Risk
R3 — initial control-plane finalization.
"@
& gh issue create --repo $repo --title 'Finalize repo-specific objective PR Gate before product code' --body $issueBody | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Could not create initial control-plane Issue.' }

Write-Host "`nBOOTSTRAPPED: $repo" -ForegroundColor Green
Write-Host 'The repo is protected immediately. Complete the generated PR-Gate Issue before adding product code.'
