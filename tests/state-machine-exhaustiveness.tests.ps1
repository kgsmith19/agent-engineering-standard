$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Read-Text { param([string]$Path) Get-Content (Join-Path $root $Path) -Raw }
function Assert-Contains {
  param([string]$Name,[string]$Path,[string]$Pattern)
  if ((Read-Text $Path) -notmatch $Pattern) { throw "$Name failed." }
}

# Material PR mutations must wake authority reconciliation immediately.
foreach ($path in @('templates/PR_AUTOMATION.yml','.github/workflows/pr-automation.yml')) {
  Assert-Contains "$path handles PR edited" $path '(?s)pull_request_target:.*?types:\s*\[[^\]]*\bedited\b'
  Assert-Contains "$path handles auto-merge enabled" $path '(?s)pull_request_target:.*?types:\s*\[[^\]]*\bauto_merge_enabled\b'
  Assert-Contains "$path handles auto-merge disabled" $path '(?s)pull_request_target:.*?types:\s*\[[^\]]*\bauto_merge_disabled\b'
  Assert-Contains "$path handles edited formal reviews" $path '(?s)pull_request_review:.*?types:\s*\[[^\]]*\bedited\b'
  Assert-Contains "$path handles inline review lifecycle" $path '(?s)pull_request_review_comment:.*?types:\s*\[[^\]]*created[^\]]*edited[^\]]*deleted'
  Assert-Contains "$path handles structured comment deletion" $path '(?s)issue_comment:.*?types:\s*\[[^\]]*\bdeleted\b'
}

# Semantic gate must retract stale evidence immediately when review artifacts mutate.
foreach ($path in @('templates/AI_REVIEW.yml','.github/workflows/ai-review.yml')) {
  Assert-Contains "$path handles edited formal reviews" $path '(?s)pull_request_review:.*?types:\s*\[[^\]]*\bedited\b'
  Assert-Contains "$path handles structured comment deletion" $path '(?s)issue_comment:.*?types:\s*\[[^\]]*\bdeleted\b'
}

# PR metadata edits can change the effective base/diff, so deterministic evidence must rerun.
Assert-Contains 'PR Gate template reruns on edited PR metadata' 'templates/PR_GATE.yml' '(?s)pull_request:.*?types:\s*\[[^\]]*\bedited\b'

Write-Host 'state-machine exhaustiveness event tests: PASS' -ForegroundColor Green
