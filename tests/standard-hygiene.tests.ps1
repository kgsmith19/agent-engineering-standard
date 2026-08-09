$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-True {
  param([string]$Name, $Condition)
  if (-not $Condition) { throw "$Name failed." }
}

foreach ($relative in @(
  '.gitignore',
  'scripts/prune-portfolio.ps1',
  'templates/.gitignore',
  'templates/dependabot.yml',
  'templates/PR_AUTOMATION.yml'
)) {
  Assert-True "required file $relative" (Test-Path (Join-Path $root $relative))
}

$textExtensions = @('.md','.ps1','.yml','.yaml','.json','.txt')
$conflicts = Get-ChildItem $root -Recurse -File | Where-Object {
  $_.FullName -notmatch '[\\/]\.git[\\/]' -and $textExtensions -contains $_.Extension.ToLowerInvariant()
} | Select-String -Pattern '^(<<<<<<< .+|=======|>>>>>>> .+)$'
if ($conflicts) {
  throw "Raw merge-conflict markers found:`n$($conflicts -join "`n")"
}

$ignore = Get-Content (Join-Path $root 'templates/.gitignore') -Raw
foreach ($entry in @('.worktrees/','.superpowers/')) {
  Assert-True "gitignore contains $entry" ($ignore -match "(?m)^$([regex]::Escape($entry))\s*$")
}

$dependabot = Get-Content (Join-Path $root 'templates/dependabot.yml') -Raw
Assert-True 'Dependabot v2' ($dependabot -match '(?m)^version:\s*2\s*$')
Assert-True 'Dependabot GitHub Actions ecosystem' ($dependabot -match 'package-ecosystem:\s*github-actions')
Assert-True 'Dependabot groups minor updates' ($dependabot -match '(?m)^\s*-\s*minor\s*$')
Assert-True 'Dependabot groups patch updates' ($dependabot -match '(?m)^\s*-\s*patch\s*$')

$agentsLines = @(Get-Content (Join-Path $root 'templates/AGENTS.md')).Count
if ($agentsLines -gt 120) { throw "templates/AGENTS.md exceeded lean 120-line budget: $agentsLines" }

$bootstrap = Get-Content (Join-Path $root 'scripts/bootstrap-repo.ps1') -Raw
Assert-True 'bootstrap manages scratch ignore' ($bootstrap -match 'templates/\.gitignore')
Assert-True 'bootstrap installs Dependabot default' ($bootstrap -match 'templates/dependabot\.yml')

$prAutomation = Get-Content (Join-Path $root 'templates/PR_AUTOMATION.yml') -Raw
Assert-True 'PR automation reacts to formal reviews' ($prAutomation -match '(?m)^\s*pull_request_review:\s*$')
Assert-True 'PR automation reacts to structured review comments' ($prAutomation -match '(?m)^\s*issue_comment:\s*$')
Assert-True 'PR automation chains only follow-up reviews' ($prAutomation -match '-FollowupOnly')
Assert-True 'PR automation rejects stale gate heads' ($prAutomation -match 'gateRun\.head_sha\s+-ne\s+\$pr\.head\.sha')
Assert-True 'PR automation reconciles draft conversion' ($prAutomation -match 'converted_to_draft')
Assert-True 'PR automation reconciles external auto-merge arming' ($prAutomation -match 'auto_merge_enabled')

$autoMerge = Get-Content (Join-Path $root 'scripts/auto-merge.ps1') -Raw
Assert-True 'auto-merge actively disarms ineligible PRs' ($autoMerge -match '--disable-auto')
Assert-True 'auto-merge pins the validated head when arming' ($autoMerge -match '--match-head-commit\s+\$pr\.headRefOid')
Assert-True 'auto-merge validates multiple risk labels itself' ($autoMerge -match 'multiple risk labels')

$requestReview = Get-Content (Join-Path $root 'scripts/request-independent-review.ps1') -Raw
Assert-True 'review router exposes follow-up-only mode' ($requestReview -match '\[switch\]\$FollowupOnly')
Assert-True 'review router stops on current-head failure' ($requestReview -match 'CURRENT-HEAD REQUIRED REVIEW FAILED')
Assert-True 'review router requires a prior pass for follow-up' ($requestReview -match 'passedRequiredCount')

$doctor = Get-Content (Join-Path $root 'scripts/doctor.ps1') -Raw
Assert-True 'doctor validates configured Project title per repo' ($doctor -match 'work-tracking Project title drift')
Assert-True 'doctor validates Issues backing record per repo' ($doctor -match 'work-tracking backing record drift')

$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Join-Path $root 'scripts/prune-portfolio.ps1'), [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count -gt 0) { throw "prune-portfolio.ps1 parse failed: $($errors[0].Message)" }

Write-Host 'standard-hygiene tests: PASS' -ForegroundColor Green
