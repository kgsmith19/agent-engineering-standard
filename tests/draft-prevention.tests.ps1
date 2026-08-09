$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("draft-prevention-" + [guid]::NewGuid().ToString('N'))
$oldPath = $env:PATH
$oldLog = $env:GH_FAKE_LOG

function Assert-True {
  param([string]$Name,$Condition)
  if (-not $Condition) { throw "$Name failed." }
}

try {
  New-Item -ItemType Directory -Path $temp | Out-Null
  $log = Join-Path $temp 'gh.log'
  $fakeGh = Join-Path $temp 'gh'
  @'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$GH_FAKE_LOG"

if [[ "$1 $2" == "pr view" ]]; then
  printf '%s\n' '{"number":17,"state":"OPEN","isDraft":true,"labels":[{"name":"status:ready"}],"headRefOid":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","headRefName":"agent/17-test","baseRefName":"main","author":{"login":"kgsmith19"},"autoMergeRequest":null,"mergeable":"MERGEABLE","title":"draft contract test","updatedAt":"2026-08-09T00:00:00Z"}'
elif [[ "$1" == "api" && "$*" == *"requested_reviewers"* ]]; then
  printf '%s\n' '{"users":[]}'
elif [[ "$1" == "api" && "$*" == *"issues/17/comments"* ]]; then
  printf '%s\n' '[[]]'
elif [[ "$1 $2" == "pr edit" || "$1 $2" == "pr comment" ]]; then
  :
else
  printf 'unexpected fake gh call: %s\n' "$*" >&2
  exit 91
fi
'@ | Set-Content $fakeGh -Encoding utf8 -NoNewline
  & chmod +x $fakeGh
  if ($LASTEXITCODE -ne 0) { throw 'Could not make fake gh executable.' }

  $env:GH_FAKE_LOG = $log
  $env:PATH = "$temp$([System.IO.Path]::PathSeparator)$oldPath"

  $failure = $null
  try {
    & (Join-Path $root 'scripts/pr-orchestrator.ps1') -Mode pr-event -Repo 'kgsmith19/example' -Pr 17
  }
  catch { $failure = $_.Exception.Message }

  Assert-True 'draft PR fails the workflow contract' ($failure -match 'ready-at-creation')
  $calls = Get-Content $log -Raw
  Assert-True 'draft PR is visibly blocked' ($calls -match 'pr edit 17 --repo kgsmith19/example --add-label status:blocked')
  Assert-True 'draft PR receives one actionable diagnostic' ($calls -match 'pr comment 17 --repo kgsmith19/example')
  Assert-True 'draft PR is never auto-converted' ($calls -notmatch 'pr ready 17')
  Assert-True 'draft PR never reaches auto-merge' ($calls -notmatch 'pr merge 17 .* --auto')

  $fixture = Join-Path $temp 'lint-fixture'
  New-Item -ItemType Directory -Path (Join-Path $fixture 'scripts') | Out-Null
  Set-Content (Join-Path $fixture 'scripts/good.ps1') 'gh pr create --repo owner/repo --base main --head agent/17-test --title test --body ok' -NoNewline
  Set-Content (Join-Path $fixture 'scripts/bad.ps1') 'gh pr create --repo owner/repo --base main --head agent/18-test --draft --title test --body bad' -NoNewline

  $lintFailure = $null
  try { & (Join-Path $root 'scripts/lint-pr-creation.ps1') -Root $fixture }
  catch { $lintFailure = $_.Exception.Message }
  Assert-True 'PR creation lint rejects --draft' ($lintFailure -match 'bad\.ps1')

  Remove-Item (Join-Path $fixture 'scripts/bad.ps1')
  & (Join-Path $root 'scripts/lint-pr-creation.ps1') -Root $fixture
  Assert-True 'PR creation lint accepts Ready gh creation' ($LASTEXITCODE -eq 0)
}
finally {
  $env:PATH = $oldPath
  $env:GH_FAKE_LOG = $oldLog
  Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
}

Write-Host 'draft-prevention tests: PASS' -ForegroundColor Green
