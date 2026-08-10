$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("automation-entrypoints-" + [guid]::NewGuid().ToString('N'))
$oldPath = $env:PATH
$oldLog = $env:GH_FAKE_LOG
$oldScenario = $env:GH_FAKE_SCENARIO

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

if [[ "$GH_FAKE_SCENARIO" == "auto-merge-fork" ]]; then
  if [[ "$1 $2" == "pr view" ]]; then
    printf '%s\n' '{"state":"OPEN","isDraft":false,"labels":[{"name":"risk:R2"}],"baseRefName":"main","headRefName":"patch-1","headRefOid":"1717171717171717171717171717171717171717","author":{"login":"attacker"},"headRepositoryOwner":{"login":"attacker"},"headRepository":{"name":"example"}}'
  else
    printf 'unexpected auto-merge-fork fake gh call: %s\n' "$*" >&2
    exit 91
  fi
elif [[ "$GH_FAKE_SCENARIO" == "auto-merge-drift" || "$GH_FAKE_SCENARIO" == "auto-merge-ready" ]]; then
  if [[ "$1 $2" == "pr view" ]]; then
    printf '%s\n' '{"state":"OPEN","isDraft":false,"labels":[{"name":"risk:R2"}],"baseRefName":"main","headRefName":"dependabot/npm_and_yarn/example","headRefOid":"1717171717171717171717171717171717171717","author":{"login":"dependabot[bot]"},"headRepositoryOwner":{"login":"kgsmith19"},"headRepository":{"name":"example"}}'
  elif [[ "$1" == "api" && "$*" == *"check-runs?check_name=PR%20Gate"* ]]; then
    printf '%s\n' '{"check_runs":[{"id":41,"name":"PR Gate","app":{"slug":"github-actions"},"conclusion":"success","output":{"summary":"deterministic"}}]}'
  elif [[ "$1" == "api" && "$*" == *"check-runs?check_name="* ]]; then
    printf '%s\n' '{"check_runs":[{"id":42,"name":"Advisory: AI Review","app":{"slug":"github-actions"},"conclusion":"neutral","output":{"summary":"dispatch-evidence repo=kgsmith19/example pr=17 head=1717171717171717171717171717171717171717 base=e risk=R2 mode=disabled_pending_e2e policy_version=1"}}]}'
  elif [[ "$*" == "api repos/kgsmith19/example/pulls/17" ]]; then
    printf '%s\n' '{"number":17,"state":"open","draft":false,"node_id":"PR_x","head":{"sha":"1717171717171717171717171717171717171717","repo":{"full_name":"kgsmith19/example"}},"base":{"sha":"eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","repo":{"owner":{"login":"kgsmith19"}}},"user":{"login":"dependabot[bot]"},"labels":[{"name":"risk:R2"}]}'
  elif [[ "$1" == "api" && "$*" == *"requested_reviewers"* ]]; then
    printf '%s\n' '{"users":[]}'
  elif [[ "$1" == "api" && "$*" == *"pulls/17/files"* ]]; then
    printf '%s\n' 'package-lock.json'
  elif [[ "$*" == "api repos/kgsmith19/example" ]]; then
    if [[ "$GH_FAKE_SCENARIO" == "auto-merge-drift" ]]; then
      printf '%s\n' '{"default_branch":"main","allow_auto_merge":false,"allow_update_branch":true,"allow_squash_merge":true,"allow_merge_commit":false,"allow_rebase_merge":false}'
    else
      printf '%s\n' '{"default_branch":"main","allow_auto_merge":true,"allow_update_branch":true,"allow_squash_merge":true,"allow_merge_commit":false,"allow_rebase_merge":false}'
    fi
  elif [[ "$*" == "api /apps/github-actions" ]]; then
    printf '%s\n' '{"id":15368}'
  elif [[ "$1" == "api" && "$*" == *"rules/branches/main"* ]]; then
    printf '%s\n' '[[{"ruleset_id":101}]]'
  elif [[ "$1" == "api" && "$*" == *"rulesets?per_page=100"* ]]; then
    printf '%s\n' '[[{"id":101,"name":"Lean PR Gate","target":"branch","enforcement":"active"}]]'
  elif [[ "$*" == "api repos/kgsmith19/example/rulesets/101" ]]; then
    printf '%s\n' '{"enforcement":"active","bypass_actors":[],"conditions":{"ref_name":{"include":["~DEFAULT_BRANCH"]}},"rules":[{"type":"pull_request","parameters":{"required_approving_review_count":0,"require_code_owner_review":false,"require_last_push_approval":false,"dismiss_stale_reviews_on_push":true,"required_review_thread_resolution":false,"allowed_merge_methods":["squash"]}},{"type":"required_status_checks","parameters":{"required_status_checks":[{"context":"PR Gate","integration_id":15368}]}}]}'
  elif [[ "$1 $2" == "pr merge" && "$*" == *"--auto --squash"* ]]; then
    :
  else
    printf 'unexpected auto-merge fake gh call: %s\n' "$*" >&2
    exit 91
  fi
elif [[ "$GH_FAKE_SCENARIO" == "review-request" ]]; then
  if [[ "$*" == "api repos/kgsmith19/example/pulls/17" ]]; then
    printf '%s\n' '{"state":"open","draft":false,"head":{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","repo":{"full_name":"kgsmith19/example"}},"user":{"login":"dependabot[bot]"}}'
  elif [[ "$1" == "api" && "$*" == *"pulls/17/commits"* ]]; then
    printf '%s\n' '[[{"author":{"login":"dependabot[bot]"},"committer":{"login":"dependabot[bot]"}}]]'
  elif [[ "$1" == "api" && "$*" == *"pulls/17/reviews"* ]]; then
    printf '%s\n' '[[]]'
  elif [[ "$1" == "api" && "$*" == *"pulls/17/comments"* ]]; then
    printf '%s\n' '[[]]'
  elif [[ "$1" == "api" && "$*" == *"issues/17/comments"* ]]; then
    printf '%s\n' '[[]]'
  elif [[ "$1 $2" == "pr comment" ]]; then
    :
  else
    printf 'unexpected review-request fake gh call: %s\n' "$*" >&2
    exit 92
  fi
else
  printf 'unknown fake gh scenario: %s\n' "$GH_FAKE_SCENARIO" >&2
  exit 93
fi
'@ | Set-Content $fakeGh -Encoding utf8 -NoNewline
  & chmod +x $fakeGh
  if ($LASTEXITCODE -ne 0) { throw 'Could not make fake gh executable.' }

  $env:GH_FAKE_LOG = $log
  $env:PATH = "$temp$([System.IO.Path]::PathSeparator)$oldPath"

  $env:GH_FAKE_SCENARIO = 'auto-merge-drift'
  $autoMergeFailure = $null
  try {
    & (Join-Path $root 'scripts/auto-merge.ps1') -Repo 'kgsmith19/example' -Pr 17 -Risk R2
  }
  catch { $autoMergeFailure = $_.Exception.Message }

  Assert-True 'auto-merge reaches the real live-setting diagnostic' ($autoMergeFailure -match 'Live GitHub setting drift: auto-merge is off')
  Assert-True 'auto-merge does not overwrite the typed PR number with PR JSON' ($autoMergeFailure -notmatch 'PSCustomObject.*System.Int32')

  Clear-Content $log
  $env:GH_FAKE_SCENARIO = 'auto-merge-ready'
  $readyFailure = $null
  try {
    & (Join-Path $root 'scripts/auto-merge.ps1') -Repo 'kgsmith19/example' -Pr 17 -Risk R2
  }
  catch { $readyFailure = $_.Exception.Message }

  Assert-True 'eligible dependency PR passes the unchanged live policy checks' (-not $readyFailure)
  $readyCalls = Get-Content $log -Raw
  Assert-True 'eligible dependency PR arms native squash auto-merge' ($readyCalls -match 'pr merge 17 --repo kgsmith19/example --auto --squash')
  Assert-True 'arming path verifies the GitHub Actions-bound PR Gate ruleset' ($readyCalls -match 'api repos/kgsmith19/example/rulesets/101')

  # #62: auto-merge.ps1 must refuse a fork PR on its own, standalone, without
  # relying on pr-orchestrator.ps1's Deny-ForkPr running first.
  Clear-Content $log
  $env:GH_FAKE_SCENARIO = 'auto-merge-fork'
  $forkFailure = $null
  try {
    & (Join-Path $root 'scripts/auto-merge.ps1') -Repo 'kgsmith19/example' -Pr 17 -Risk R2
  }
  catch { $forkFailure = $_.Exception.Message }

  Assert-True 'auto-merge refuses a fork PR called directly' ($forkFailure -match 'fork')
  Assert-True 'auto-merge fork refusal names the actual head repository' ($forkFailure -match 'attacker/example')
  $forkCalls = Get-Content $log -Raw
  Assert-True 'auto-merge fork refusal happens before any other privileged call' (($forkCalls.Trim() -split "`r?`n").Count -eq 1)
  Assert-True 'auto-merge never arms merge for a fork PR' ($forkCalls -notmatch 'pr merge')

  $fixture = Join-Path $temp 'review-fixture'
  New-Item -ItemType Directory -Path (Join-Path $fixture 'scripts/lib') -Force | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $fixture 'policy') -Force | Out-Null
  Copy-Item (Join-Path $root 'scripts/request-machine-review.ps1') (Join-Path $fixture 'scripts/request-machine-review.ps1')
  Copy-Item (Join-Path $root 'scripts/lib/review-policy.ps1') (Join-Path $fixture 'scripts/lib/review-policy.ps1')
  Copy-Item (Join-Path $root 'scripts/lib/gh-api.ps1') (Join-Path $fixture 'scripts/lib/gh-api.ps1')
  $enabledConfig = Get-Content (Join-Path $root 'policy/github-defaults.json') -Raw | ConvertFrom-Json
  $enabledConfig.independent_review.dispatch_mode = 'enabled'
  $enabledConfig | ConvertTo-Json -Depth 20 | Set-Content (Join-Path $fixture 'policy/github-defaults.json') -Encoding utf8

  Clear-Content $log
  $env:GH_FAKE_SCENARIO = 'review-request'
  $reviewFailure = $null
  try {
    & (Join-Path $fixture 'scripts/request-machine-review.ps1') -Repo 'kgsmith19/example' -Pr 17 -Provider auto
  }
  catch { $reviewFailure = $_.Exception.Message }

  Assert-True 'review requester accepts parsed PR JSON without changing the typed PR number' (-not $reviewFailure)
  $calls = Get-Content $log -Raw
  Assert-True 'review requester reaches the independent reviewer request' ($calls -match 'pr comment 17 --repo kgsmith19/example')
}
finally {
  $env:PATH = $oldPath
  $env:GH_FAKE_LOG = $oldLog
  $env:GH_FAKE_SCENARIO = $oldScenario
  Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
}

Write-Host 'automation-entrypoints tests: PASS' -ForegroundColor Green
