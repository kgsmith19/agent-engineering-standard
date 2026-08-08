param(
  [switch]$Remote,
  [string]$ConfigPath = (Join-Path $PSScriptRoot "..\policy\github-defaults.json")
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$required = @(
  "README.md",
  "LIFECYCLE.md",
  "AGENT_RULES.md",
  "QUALITY_RULES.md",
  "SECURITY_RISK_AUTONOMY.md",
  "DELIVERY_GITHUB.md",
  "EVIDENCE_LEARNING.md",
  "AGENTS.md",
  "policy/github-defaults.json",
  "scripts/apply-github-standard.ps1",
  "scripts/sync-agentic-project.ps1",
  "scripts/codex-review.ps1",
  ".github/workflows/ci.yml",
  "templates/PRD.md",
  "templates/SPEC.md",
  "templates/ADR.md",
  "templates/ISSUE.md",
  "templates/PULL_REQUEST.md"
)

foreach ($relative in $required) {
  $path = Join-Path $root $relative
  if (-not (Test-Path $path)) { throw "Missing required file: $relative" }
}

$config = Get-Content (Join-Path $root "policy/github-defaults.json") -Raw | ConvertFrom-Json
if ($config.required_status_context -ne "PR Gate") { throw "required_status_context must be 'PR Gate'" }
if ($config.required_approving_review_count -ne 0) { throw "Default approval count must remain 0; R3/R4 review is risk-driven, not universal." }

foreach ($relative in @("scripts/apply-github-standard.ps1", "scripts/sync-agentic-project.ps1", "scripts/codex-review.ps1", "scripts/doctor.ps1")) {
  $tokens = $null
  $errors = $null
  [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root $relative), [ref]$tokens, [ref]$errors) | Out-Null
  if ($errors.Count -gt 0) { throw "PowerShell parse failed: $relative :: $($errors[0].Message)" }
}

Write-Host "LOCAL: READY" -ForegroundColor Green

if (-not $Remote) { exit 0 }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "gh is required for -Remote." }

foreach ($name in $config.repositories) {
  $repo = "$($config.owner)/$name"
  $meta = ((& gh api "repos/$repo") -join "`n") | ConvertFrom-Json
  if ($LASTEXITCODE -ne 0) { throw "Cannot read $repo" }

  $problems = @()
  if (-not $meta.allow_auto_merge) { $problems += "auto-merge off" }
  if (-not $meta.delete_branch_on_merge) { $problems += "delete-branch off" }
  if (-not $meta.allow_squash_merge) { $problems += "squash off" }
  if ($meta.allow_merge_commit) { $problems += "merge commits enabled" }
  if ($meta.allow_rebase_merge) { $problems += "rebase enabled" }

  $actions = ((& gh api "repos/$repo/actions/permissions") -join "`n") | ConvertFrom-Json
  if (-not $actions.enabled) { $problems += "actions disabled" }

  $rulesets = ((& gh api "repos/$repo/rulesets") -join "`n") | ConvertFrom-Json
  $ruleset = $rulesets | Where-Object { $_.name -eq $config.ruleset_name } | Select-Object -First 1
  if (-not $ruleset) { $problems += "ruleset missing" }

  if ($problems.Count -eq 0) {
    Write-Host "$repo : READY" -ForegroundColor Green
  } else {
    Write-Host "$repo : $($problems -join ', ')" -ForegroundColor Yellow
  }

  if ($config.merge_queue.desired -and $meta.owner.type -ne "Organization") {
    Write-Host "  merge queue: waiting on transfer to a supported GitHub organization" -ForegroundColor DarkYellow
  }
}
