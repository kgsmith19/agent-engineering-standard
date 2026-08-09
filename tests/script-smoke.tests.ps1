$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("script-smoke-" + [guid]::NewGuid().ToString('N'))
$oldPath = $env:PATH
$oldLog = $env:GH_FAKE_LOG

function Assert-True {
  param([string]$Name,$Condition)
  if (-not $Condition) { throw "$Name failed." }
}

# End-to-end smoke: auto-merge.ps1 and request-machine-review.ps1 must run their
# full happy path against a fake gh. A typed-numeric-param collision ($pr under
# [int]$Pr) crashes both before any logic runs, which no structural test catches.
try {
  New-Item -ItemType Directory -Path $temp | Out-Null
  $log = Join-Path $temp 'gh.log'

  $config = Get-Content (Join-Path $root 'policy/github-defaults.json') -Raw | ConvertFrom-Json
  $config.independent_review.dispatch_mode = 'enabled'
  $configPath = Join-Path $temp 'policy.json'
  $config | ConvertTo-Json -Depth 10 | Set-Content $configPath -Encoding utf8

  $fakeGh = Join-Path $temp 'gh'
  @'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$GH_FAKE_LOG"
HEAD="dddddddddddddddddddddddddddddddddddddddd"
case "$*" in
  "pr view 22"*)
    printf '%s\n' '{"number":22,"state":"OPEN","isDraft":false,"labels":[{"name":"risk:R2"}],"headRefOid":"'"$HEAD"'","headRefName":"agent/22-smoke","headRepository":{"name":"example"},"headRepositoryOwner":{"login":"kgsmith19"},"baseRefName":"main","author":{"login":"kgsmith19"},"autoMergeRequest":null,"mergeable":"MERGEABLE","title":"t","updatedAt":"2026-08-09T00:00:00Z"}' ;;
  *"requested_reviewers"*) printf '%s\n' '{"users":[]}' ;;
  *"pulls/22/files"*) printf '%s\n' 'src/app.ts' ;;
  *"pulls/22/commits"*) printf '%s\n' '[[{"author":{"login":"kgsmith19"},"committer":{"login":"kgsmith19"}}]]' ;;
  *"pulls/22/reviews"*) printf '%s\n' '[[]]' ;;
  *"pulls/22/comments"*) printf '%s\n' '[[]]' ;;
  *"issues/22/comments"*) printf '%s\n' '[[]]' ;;
  *"check-runs?check_name=PR%20Gate"*) printf '%s\n' '{"check_runs":[{"id":31,"name":"PR Gate","app":{"slug":"github-actions"},"conclusion":"success","output":{"summary":"deterministic"}}]}' ;;
  *"check-runs?check_name="*) printf '%s\n' '{"check_runs":[{"id":32,"name":"AI Review","app":{"slug":"github-actions"},"conclusion":"neutral","output":{"summary":"dispatch-evidence repo=kgsmith19/example pr=22 head='"$HEAD"' base=e policy_version=1"}}]}' ;;
  "api /apps/github-actions") printf '%s\n' '{"id":15368}' ;;
  *"repos/kgsmith19/example/rulesets?per_page=100") printf '%s\n' '[[{"id":77,"name":"Lean PR Gate","target":"branch","enforcement":"active"}]]' ;;
  *"rules/branches/main?per_page=100") printf '%s\n' '[[{"ruleset_id":77,"type":"pull_request"}]]' ;;
  "api repos/kgsmith19/example/rulesets/77") printf '%s\n' '{"id":77,"enforcement":"active","bypass_actors":[],"conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"]}},"rules":[{"type":"pull_request","parameters":{"required_approving_review_count":0,"require_code_owner_review":false,"require_last_push_approval":false,"dismiss_stale_reviews_on_push":true,"required_review_thread_resolution":false,"allowed_merge_methods":["squash"]}},{"type":"required_status_checks","parameters":{"required_status_checks":[{"context":"PR Gate","integration_id":15368}]}}]}' ;;
  "api repos/kgsmith19/example/pulls/22") printf '%s\n' '{"number":22,"state":"open","draft":false,"node_id":"PR_y","head":{"sha":"'"$HEAD"'","repo":{"full_name":"kgsmith19/example"}},"base":{"sha":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","repo":{"owner":{"login":"kgsmith19"}}},"user":{"login":"kgsmith19"},"labels":[{"name":"risk:R2"}]}' ;;
  "api repos/kgsmith19/example") printf '%s\n' '{"default_branch":"main","allow_auto_merge":true,"allow_update_branch":true,"allow_squash_merge":true,"allow_merge_commit":false,"allow_rebase_merge":false}' ;;
  "pr merge 22"*|"pr comment 22"*|"pr edit 22"*) : ;;
  *) printf 'unexpected fake gh call: %s\n' "$*" >&2; exit 91 ;;
esac
'@ | Set-Content $fakeGh -Encoding utf8 -NoNewline
  & chmod +x $fakeGh
  if ($LASTEXITCODE -ne 0) { throw 'Could not make fake gh executable.' }

  $pwshDir = Split-Path -Parent ([System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName)
  $env:GH_FAKE_LOG = $log
  $env:PATH = "$temp$([System.IO.Path]::PathSeparator)$pwshDir$([System.IO.Path]::PathSeparator)$oldPath"

  $armOutput = & pwsh -NoProfile -File (Join-Path $root 'scripts/auto-merge.ps1') -Repo 'kgsmith19/example' -Pr 22 -Risk R2 2>&1 | Out-String
  Assert-True "auto-merge smoke run exits clean (output: $armOutput)" ($LASTEXITCODE -eq 0)
  $calls = Get-Content $log -Raw
  Assert-True 'auto-merge armed the squash merge' ($calls -match '(?m)^pr merge 22 --repo kgsmith19/example --auto --squash')

  Set-Content $log '' -NoNewline
  $reviewOutput = & pwsh -NoProfile -File (Join-Path $root 'scripts/request-machine-review.ps1') -Repo 'kgsmith19/example' -Pr 22 -Provider auto -ConfigPath $configPath 2>&1 | Out-String
  Assert-True "review request smoke run exits clean (output: $reviewOutput)" ($LASTEXITCODE -eq 0)
  $calls = Get-Content $log -Raw
  Assert-True 'review requester posted the reviewer comment' ($calls -match '(?m)^pr comment 22 --repo kgsmith19/example')
}
finally {
  $env:PATH = $oldPath
  $env:GH_FAKE_LOG = $oldLog
  Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
}

Write-Host 'script-smoke tests: PASS' -ForegroundColor Green
