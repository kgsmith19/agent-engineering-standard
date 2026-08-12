$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("gate-result-arming-" + [guid]::NewGuid().ToString('N'))
$oldPath = $env:PATH
$oldLog = $env:GH_FAKE_LOG

function Assert-True {
  param([string]$Name,$Condition)
  if (-not $Condition) { throw "$Name failed." }
}

# One-pass arming: after PR Gate success on an armable PR (open, ready, R2,
# non-control-plane, unblocked), a single gate-result invocation must arm
# auto-merge — no second event and no watchdog pass required, and no machine
# review evaluation is a precondition (AI Review removed — ADR-0004).
try {
  New-Item -ItemType Directory -Path $temp | Out-Null
  $log = Join-Path $temp 'gh.log'

  $head = 'ffffffffffffffffffffffffffffffffffffffff'
  $fakeGh = Join-Path $temp 'gh'
  @'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$GH_FAKE_LOG"
HEAD="ffffffffffffffffffffffffffffffffffffffff"
case "$*" in
  "pr view 23"*)
    printf '%s\n' '{"number":23,"state":"OPEN","isDraft":false,"labels":[{"name":"risk:R2"}],"headRefOid":"'"$HEAD"'","headRefName":"agent/23-arm","headRepository":{"name":"example"},"headRepositoryOwner":{"login":"kgsmith19"},"baseRefName":"main","author":{"login":"kgsmith19"},"autoMergeRequest":null,"mergeable":"MERGEABLE","title":"t","updatedAt":"2026-08-09T00:00:00Z"}' ;;
  *"requested_reviewers"*) printf '%s\n' '{"users":[]}' ;;
  *"issues/23/comments"*) printf '%s\n' '[[]]' ;;
  *"pulls/23/files"*) printf '%s\n' 'src/app.ts' ;;
  *"check-runs?check_name=PR%20Gate"*) printf '%s\n' '{"check_runs":[{"id":31,"name":"PR Gate","app":{"slug":"github-actions"},"conclusion":"success","output":{"summary":"deterministic"}}]}' ;;
  "api repos/kgsmith19/example/pulls/23") printf '%s\n' '{"number":23,"state":"open","draft":false,"node_id":"PR_z","head":{"sha":"'"$HEAD"'","repo":{"full_name":"kgsmith19/example"}},"base":{"sha":"1111111111111111111111111111111111111111","repo":{"owner":{"login":"kgsmith19"}}},"user":{"login":"kgsmith19"},"labels":[{"name":"risk:R2"}]}' ;;
  "api repos/kgsmith19/example") printf '%s\n' '{"default_branch":"main","allow_auto_merge":true,"allow_update_branch":true,"allow_squash_merge":true,"allow_merge_commit":false,"allow_rebase_merge":false}' ;;
  "api /apps/github-actions") printf '%s\n' '{"id":15368}' ;;
  *"repos/kgsmith19/example/rulesets?per_page=100") printf '%s\n' '[[{"id":77,"name":"Lean PR Gate","target":"branch","enforcement":"active"}]]' ;;
  *"rules/branches/main?per_page=100") printf '%s\n' '[[{"ruleset_id":77,"type":"pull_request"}]]' ;;
  "api repos/kgsmith19/example/rulesets/77") printf '%s\n' '{"id":77,"enforcement":"active","bypass_actors":[],"conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"]}},"rules":[{"type":"pull_request","parameters":{"required_approving_review_count":0,"require_code_owner_review":false,"require_last_push_approval":false,"dismiss_stale_reviews_on_push":true,"required_review_thread_resolution":false,"allowed_merge_methods":["squash"]}},{"type":"required_status_checks","parameters":{"required_status_checks":[{"context":"PR Gate","integration_id":15368}]}}]}' ;;
  "pr merge 23"*|"pr comment 23"*|"pr edit 23"*) : ;;
  *) printf 'unexpected fake gh call: %s\n' "$*" >&2; exit 91 ;;
esac
'@ | Set-Content $fakeGh -Encoding utf8 -NoNewline
  & chmod +x $fakeGh
  if ($LASTEXITCODE -ne 0) { throw 'Could not make fake gh executable.' }

  $pwshDir = Split-Path -Parent ([System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName)
  $env:GH_FAKE_LOG = $log
  $env:PATH = "$temp$([System.IO.Path]::PathSeparator)$pwshDir$([System.IO.Path]::PathSeparator)$oldPath"

  & (Join-Path $root 'scripts/pr-orchestrator.ps1') -Mode gate-result -Repo 'kgsmith19/example' -Pr 23 `
    -GateConclusion success -GateHeadSha $head -GateRunId 88

  $calls = Get-Content $log -Raw
  $mergeIndex = $calls.IndexOf('pr merge 23 --repo kgsmith19/example --auto --squash')
  Assert-True 'auto-merge armed in the gate-result pass' ($mergeIndex -ge 0)
}
finally {
  $env:PATH = $oldPath
  $env:GH_FAKE_LOG = $oldLog
  Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
}

Write-Host 'gate-result-arming tests: PASS' -ForegroundColor Green
