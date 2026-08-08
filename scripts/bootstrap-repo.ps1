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

$exists = & gh repo view $repo --json nameWithOwner 2>$null
if ($LASTEXITCODE -ne 0) {
  $visibilityFlag = if ($Visibility -eq 'public') { '--public' } else { '--private' }
  $args = @('repo','create',$repo,$visibilityFlag,'--clone')
  if ($Description) { $args += @('--description',$Description) }
  Push-Location $Destination
  try { & gh @args | Out-Host } finally { Pop-Location }
  if ($LASTEXITCODE -ne 0) { throw "Could not create $repo" }
} elseif (-not (Test-Path $target)) {
  Push-Location $Destination
  try { & gh repo clone $repo | Out-Host } finally { Pop-Location }
  if ($LASTEXITCODE -ne 0) { throw "Could not clone $repo" }
}

New-Item -ItemType Directory -Force (Join-Path $target '.agent') | Out-Null
New-Item -ItemType Directory -Force (Join-Path $target 'specs') | Out-Null
New-Item -ItemType Directory -Force (Join-Path $target 'docs/adr') | Out-Null
New-Item -ItemType Directory -Force (Join-Path $target '.github/ISSUE_TEMPLATE') | Out-Null

Copy-Item (Join-Path $standardRoot 'templates/AGENTS.md') (Join-Path $target 'AGENTS.md') -Force
Copy-Item (Join-Path $standardRoot 'templates/PRD.md') (Join-Path $target 'PRD.md') -Force
Copy-Item (Join-Path $standardRoot 'templates/ISSUE.md') (Join-Path $target '.github/ISSUE_TEMPLATE/work-item.md') -Force
Copy-Item (Join-Path $standardRoot 'templates/PULL_REQUEST.md') (Join-Path $target '.github/PULL_REQUEST_TEMPLATE.md') -Force

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

# Add only verified repo-specific commands/risk paths after the initial scaffold exists.
"@ | Set-Content (Join-Path $target '.agent/project.yaml') -Encoding utf8

@"
@AGENTS.md
"@ | Set-Content (Join-Path $target 'CLAUDE.md') -Encoding utf8

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

Write-Host "`nBOOTSTRAPPED: $repo" -ForegroundColor Green
Write-Host 'Next: have the first coding agent inspect the scaffold, fill only verified project commands/risk paths, create the first GitHub Issue, and add the repo-specific PR Gate before feature work.'
