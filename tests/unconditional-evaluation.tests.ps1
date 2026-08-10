$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("unconditional-eval-" + [guid]::NewGuid().ToString('N'))
$oldPath = $env:PATH
$oldLog = $env:GH_FAKE_LOG

function Assert-True {
  param([string]$Name,$Condition)
  if (-not $Condition) { throw "$Name failed." }
}

# F2: the advisory evaluator must run on the gate-result path even when
# dispatch_mode=enabled and solicit_reviews=false — evaluation is unconditional;
# solicit_reviews gates only reviewer solicitation.
try {
  New-Item -ItemType Directory -Path $temp | Out-Null
  $log = Join-Path $temp 'gh.log'

  $config = Get-Content (Join-Path $root 'policy/github-defaults.json') -Raw | ConvertFrom-Json
  $config.independent_review.dispatch_mode = 'enabled'
  $configPath = Join-Path $temp 'policy.json'
  $config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding utf8
  Assert-True 'fixture keeps solicit_reviews off' (-not [bool]$config.independent_review.solicit_reviews)

  $head = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
  $fakeGh = Join-Path $temp 'gh'
  @'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$GH_FAKE_LOG"
HEAD="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
case "$*" in
  "pr view 21"*)
    printf '%s\n' '{"number":21,"state":"OPEN","isDraft":false,"labels":[{"name":"risk:R2"}],"headRefOid":"'"$HEAD"'","headRefName":"agent/21-test","headRepository":{"name":"example"},"headRepositoryOwner":{"login":"kgsmith19"},"baseRefName":"main","author":{"login":"kgsmith19"},"autoMergeRequest":null,"mergeable":"MERGEABLE","title":"t","updatedAt":"2026-08-09T00:00:00Z"}' ;;
  *"requested_reviewers"*) printf '%s\n' '{"users":[]}' ;;
  *"issues/21/comments"*) printf '%s\n' '[[]]' ;;
  *"pulls/21/files"*) printf '%s\n' 'src/app.ts' ;;
  *"pulls/21/commits"*) printf '%s\n' '[[{"author":{"login":"kgsmith19"},"committer":{"login":"kgsmith19"}}]]' ;;
  *"pulls/21/reviews"*) printf '%s\n' '[[]]' ;;
  *"pulls/21/comments"*) printf '%s\n' '[[]]' ;;
  *"check-runs?check_name=PR%20Gate"*) printf '%s\n' '{"check_runs":[{"id":11,"name":"PR Gate","app":{"slug":"github-actions"},"conclusion":"success","output":{"summary":"deterministic"}}]}' ;;
  *"check-runs?check_name="*) printf '%s\n' '{"check_runs":[]}' ;;
  "api --method POST repos/kgsmith19/example/check-runs"*) printf '%s\n' '{}' ;;
  "api repos/kgsmith19/example/pulls/21") printf '%s\n' '{"number":21,"state":"open","draft":false,"node_id":"PR_x","head":{"sha":"'"$HEAD"'","repo":{"full_name":"kgsmith19/example"}},"base":{"sha":"cccccccccccccccccccccccccccccccccccccccc","repo":{"owner":{"login":"kgsmith19"}}},"user":{"login":"kgsmith19"},"labels":[{"name":"risk:R2"}]}' ;;
  "pr edit 21"*|"pr comment 21"*|"pr merge 21"*) : ;;
  *) printf 'unexpected fake gh call: %s\n' "$*" >&2; exit 91 ;;
esac
'@ | Set-Content $fakeGh -Encoding utf8 -NoNewline
  & chmod +x $fakeGh
  if ($LASTEXITCODE -ne 0) { throw 'Could not make fake gh executable.' }

  $pwshDir = Split-Path -Parent ([System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName)
  $env:GH_FAKE_LOG = $log
  $env:PATH = "$temp$([System.IO.Path]::PathSeparator)$pwshDir$([System.IO.Path]::PathSeparator)$oldPath"

  & (Join-Path $root 'scripts/pr-orchestrator.ps1') -Mode gate-result -Repo 'kgsmith19/example' -Pr 21 `
    -GateConclusion success -GateHeadSha $head -GateRunId 99 -ConfigPath $configPath

  $calls = Get-Content $log -Raw
  Assert-True 'evaluator ran and wrote an exact-head conclusion' ($calls -match '(?m)^api --method POST repos/kgsmith19/example/check-runs')
  Assert-True 'no reviewer was solicited without solicit_reviews' ($calls -notmatch 'codex review' -and $calls -notmatch 'Independently review')
  Assert-True 'no forbidden human reviewer interaction occurred' ($calls -notmatch 'pr ready 21')
}
finally {
  $env:PATH = $oldPath
  $env:GH_FAKE_LOG = $oldLog
  Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
}

Write-Host 'unconditional-evaluation tests: PASS' -ForegroundColor Green
