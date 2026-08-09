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
if ($LASTEXITCODE -ne 0 -or $standardSha -notmatch '^[0-9a-fA-F]{40}$') { throw 'Could not resolve the full standards commit SHA.' }
$config = Get-Content (Join-Path $standardRoot 'policy/github-defaults.json') -Raw | ConvertFrom-Json
$owner = $config.owner
$repo = "$owner/$Name"
$target = Join-Path $Destination $Name

& gh repo view $repo --json nameWithOwner 1>$null 2>$null
if ($LASTEXITCODE -ne 0) {
  $visibilityFlag = if ($Visibility -eq 'public') { '--public' } else { '--private' }
  $ghArgs = @('repo','create',$repo,$visibilityFlag,'--clone')
  if ($Description) { $ghArgs += @('--description',$Description) }
  Push-Location $Destination
  try { & gh @ghArgs | Out-Host } finally { Pop-Location }
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

$gitignorePath = Join-Path $target '.gitignore'
if (-not (Test-Path $gitignorePath)) {
  Copy-Item (Join-Path $standardRoot 'templates/.gitignore') $gitignorePath -Force
}
else {
  $gitignoreText = Get-Content $gitignorePath -Raw
  foreach ($entry in @('.worktrees/','.superpowers/')) {
    if ($gitignoreText -notmatch "(?m)^$([regex]::Escape($entry))\s*$") {
      Add-Content $gitignorePath $entry -Encoding utf8
      $gitignoreText += "`n$entry"
    }
  }
}

$dependabotPath = Join-Path $target '.github/dependabot.yml'
if (-not (Test-Path $dependabotPath)) {
  Copy-Item (Join-Path $standardRoot 'templates/dependabot.yml') $dependabotPath -Force
}

Copy-Item (Join-Path $standardRoot 'templates/AGENTS.md') (Join-Path $target 'AGENTS.md') -Force
Copy-Item (Join-Path $standardRoot 'templates/PRD.md') (Join-Path $target 'PRD.md') -Force
Copy-Item (Join-Path $standardRoot 'templates/ISSUE.md') (Join-Path $target '.github/ISSUE_TEMPLATE/work-item.md') -Force
Copy-Item (Join-Path $standardRoot 'templates/PULL_REQUEST.md') (Join-Path $target '.github/PULL_REQUEST_TEMPLATE.md') -Force
Copy-Item (Join-Path $standardRoot 'templates/PR_GATE.yml') (Join-Path $target '.github/workflows/pr-gate.yml') -Force

$aiReview = (Get-Content (Join-Path $standardRoot 'templates/AI_REVIEW.yml') -Raw).Replace('__STANDARD_SHA__',$standardSha)
Set-Content (Join-Path $target '.github/workflows/ai-review.yml') $aiReview -Encoding utf8 -NoNewline
$prAutomation = (Get-Content (Join-Path $standardRoot 'templates/PR_AUTOMATION.yml') -Raw).Replace('__STANDARD_SHA__',$standardSha)
Set-Content (Join-Path $target '.github/workflows/pr-automation.yml') $prAutomation -Encoding utf8 -NoNewline

# Native CODEOWNERS can automatically request Kyle and create an accidental
# human bottleneck. Path sensitivity is enforced by machine policy instead.
Remove-Item (Join-Path $target '.github/CODEOWNERS') -Force -ErrorAction SilentlyContinue

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
  automation_workflow: "PR Automation"
  gate_profile: bootstrap-only

# Before product code lands, replace the bootstrap-only PR Gate with the cheapest
# repo-specific objective build/test/acceptance evidence for the detected stack.
# Keep AI Review and PR Automation pinned to standard.sha.
"@ | Set-Content (Join-Path $target '.agent/project.yaml') -Encoding utf8

'@AGENTS.md' | Set-Content (Join-Path $target 'CLAUDE.md') -Encoding utf8

Push-Location $target
try {
  & git add -A -- .gitignore AGENTS.md CLAUDE.md PRD.md specs docs/adr .agent .github
  & git commit -m 'chore: bootstrap lean autonomous engineering standard'
  if ($LASTEXITCODE -ne 0) { throw 'Initial bootstrap commit failed.' }
  & git push origin HEAD
  if ($LASTEXITCODE -ne 0) { throw 'Initial bootstrap push failed.' }
}
finally { Pop-Location }

& pwsh -NoProfile -File (Join-Path $PSScriptRoot 'apply-github-standard.ps1') -Repositories $Name
if ($LASTEXITCODE -ne 0) { throw 'GitHub policy bootstrap failed.' }

$copilotRaw = & gh api -H 'X-GitHub-Api-Version: 2026-03-10' "repos/$repo/copilot/cloud-agent/configuration" 2>&1
if ($LASTEXITCODE -eq 0) {
  $copilot = ($copilotRaw -join "`n") | ConvertFrom-Json
  if ([bool]$copilot.require_actions_workflow_approval) {
    Write-Warning "ONE-TIME GITHUB UI SETTING: Settings > Copilot > Coding agent > Require approval for workflows must be OFF for $repo. GitHub currently exposes this setting read-only through the public REST API."
  }
}
else { Write-Warning 'Could not verify Copilot cloud-agent workflow approval setting.' }

$issueBody = @"
## Outcome
Replace the bootstrap-only PR Gate with the smallest objective gate appropriate to this repository's real stack before product code lands.

## Acceptance
- Detect and record verified build/test/type/lint/E2E commands in `.agent/project.yaml`.
- Replace `.github/workflows/pr-gate.yml` so workflow name and required job context remain exactly `PR Gate`.
- Preserve exact-SHA-pinned `.github/workflows/ai-review.yml` and `.github/workflows/pr-automation.yml`.
- Extend `.github/dependabot.yml` only with package ecosystems this repo actually uses; group patch/minor updates when it reduces CI/review noise.
- Keep native `.github/CODEOWNERS` absent so Kyle is never auto-requested as a routine reviewer.
- Keep draft iteration quiet; `status:ready` promotes a coherent draft, then `PR Gate` + exact-head `AI Review` govern auto-merge.
- Add only tests/tools justified by actual product risk; do not invent a framework for conformity.
- Update `ci.gate_profile` away from `bootstrap-only`.

## Risk
R3 — initial control-plane finalization.
"@
& gh issue create --repo $repo --title 'Finalize repo-specific objective PR Gate before product code' --body $issueBody | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Could not create initial control-plane Issue.' }

Write-Host "`nBOOTSTRAPPED: $repo" -ForegroundColor Green
Write-Host 'Run doctor.ps1 -Remote after the generated PR-Gate Issue is complete.'
