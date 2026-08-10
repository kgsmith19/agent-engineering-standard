$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$temp = Join-Path ([System.IO.Path]::GetTempPath()) ("upgrade-repos-smoke-" + [guid]::NewGuid().ToString('N'))
$oldPath = $env:PATH
$oldLog = $env:GH_FAKE_LOG

function Assert-True {
  param([string]$Name,$Condition)
  if (-not $Condition) { throw "$Name failed." }
}

# Idempotent-rollout smoke: upgrade-repos.ps1 must reuse ANY open PR whose head
# branch matches chore/standard-* (regardless of which sha it names) by pushing
# regenerated content onto that same branch, rather than opening a new
# branch/PR per standard commit -- which is exactly what orphaned 3 real rollout
# PRs before this fix. Covers the reuse path (including a manual-commit
# preservation regression check), and the unchanged no-existing-PR path,
# against a real local git remote so the actual push is verified, not just the
# gh call shape.
function New-FakeRemote {
  param([string]$Dir, [switch]$WithStaleBranch)
  $remote = Join-Path $Dir 'remote.git'
  & git init --quiet --bare $remote | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'bare remote init failed' }

  $seed = Join-Path $Dir 'seed'
  & git init --quiet -b main $seed | Out-Null
  if ($LASTEXITCODE -ne 0) { throw 'seed init failed' }

  $manualSha = $null
  Push-Location $seed
  try {
    & git config user.email 'test@example.com'
    & git config user.name 'Test'
    New-Item -ItemType Directory -Force '.agent' | Out-Null
    @"
standard: kgsmith19/agent-engineering-standard
commit: 1111111111111111111111111111111111111111
pinned_at: "2026-01-01"
pinned_by: upgrade-repos.ps1
"@ | Set-Content '.agent/standard.lock' -Encoding utf8 -NoNewline
    & git add -A
    if ($LASTEXITCODE -ne 0) { throw 'seed add failed' }
    & git commit --quiet -m seed
    if ($LASTEXITCODE -ne 0) { throw 'seed commit failed' }
    & git remote add origin $remote
    & git push --quiet origin main
    if ($LASTEXITCODE -ne 0) { throw 'seed push failed' }

    if ($WithStaleBranch) {
      & git switch --quiet -c chore/standard-cafebabe
      if ($LASTEXITCODE -ne 0) { throw 'stale branch creation failed' }
      # A manual fixup commit -- not authored by the automation -- already on
      # the rollout branch. The regression this guards against: the script
      # used to recreate the branch from main's HEAD and force-push over this,
      # silently destroying it.
      'manual fixup, not from the automation' | Set-Content 'MANUAL_FIXUP.md' -Encoding utf8
      & git add -A
      if ($LASTEXITCODE -ne 0) { throw 'manual commit add failed' }
      & git commit --quiet -m 'manual: hotfix applied directly to the rollout PR'
      if ($LASTEXITCODE -ne 0) { throw 'manual commit failed' }
      $manualSha = (& git rev-parse HEAD | Out-String).Trim()
      & git push --quiet origin chore/standard-cafebabe
      if ($LASTEXITCODE -ne 0) { throw 'stale branch push failed' }
      & git switch --quiet main
    }
  }
  finally { Pop-Location }

  & git -C $remote symbolic-ref HEAD refs/heads/main | Out-Null
  return [pscustomobject]@{ Remote = $remote; ManualCommitSha = $manualSha }
}

function Get-RemoteBranchSha {
  param([string]$Remote, [string]$Branch)
  $sha = (& git -C $Remote rev-parse "refs/heads/$Branch" 2>$null | Out-String).Trim()
  if ($LASTEXITCODE -ne 0) { return $null }
  return $sha
}

try {
  New-Item -ItemType Directory -Path $temp | Out-Null
  $log = Join-Path $temp 'gh.log'

  $fakeGh = Join-Path $temp 'gh'
  @'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$GH_FAKE_LOG"

if [ "$1" = "auth" ] && [ "$2" = "status" ]; then
  exit 0
fi

if [ "$1" = "api" ]; then
  if [ "$2" = "repos/$GH_FAKE_REPO" ]; then
    printf '%s\n' '{"default_branch":"main"}'
    exit 0
  fi
  case "$2" in
    repos/"$GH_FAKE_REPO"/git/ref/heads/*)
      exit 1 ;;
  esac
  printf 'unexpected fake gh api call: %s\n' "$*" >&2
  exit 91
fi

if [ "$1" = "pr" ] && [ "$2" = "list" ]; then
  cat "$GH_FAKE_PR_LIST_FILE"
  exit 0
fi

if [ "$1" = "repo" ] && [ "$2" = "clone" ]; then
  dest="$4"
  git clone --quiet "$GH_FAKE_REMOTE" "$dest"
  exit 0
fi

if [ "$1" = "pr" ] && [ "$2" = "create" ]; then
  printf '%s\n' "$GH_FAKE_PR_URL"
  exit 0
fi

if [ "$1" = "pr" ] && [ "$2" = "view" ]; then
  printf '%s\n' '{"number":99,"url":"'"$GH_FAKE_PR_URL"'","isDraft":false}'
  exit 0
fi

if [ "$1" = "pr" ] && [ "$2" = "edit" ]; then
  exit 0
fi

printf 'unexpected fake gh call: %s\n' "$*" >&2
exit 91
'@ | Set-Content $fakeGh -Encoding utf8 -NoNewline
  & chmod +x $fakeGh
  if ($LASTEXITCODE -ne 0) { throw 'Could not make fake gh executable.' }

  $env:GH_FAKE_LOG = $log
  $env:GH_FAKE_REPO = 'acct/example'
  $env:PATH = "$temp$([System.IO.Path]::PathSeparator)$oldPath"

  $config = @{ owner = 'acct'; repositories = @('example') }
  $configPath = Join-Path $temp 'policy.json'
  $config | ConvertTo-Json -Depth 5 | Set-Content $configPath -Encoding utf8

  # --- Scenario 1: an open rollout PR already exists on a DIFFERENT sha's
  # branch. The script must push onto that same branch instead of creating one.
  $remote1Dir = Join-Path $temp 'scenario1'
  New-Item -ItemType Directory -Path $remote1Dir | Out-Null
  $remote1Info = New-FakeRemote -Dir $remote1Dir -WithStaleBranch
  $remote1 = $remote1Info.Remote
  $manualSha = $remote1Info.ManualCommitSha
  $staleShaBefore = Get-RemoteBranchSha -Remote $remote1 -Branch 'chore/standard-cafebabe'
  Assert-True 'scenario1 stale branch exists before run' ($null -ne $staleShaBefore)
  Assert-True 'scenario1 manual commit is the branch tip before run' ($staleShaBefore -eq $manualSha)

  $prListFile1 = Join-Path $temp 'prlist1.json'
  '[{"number":123,"url":"https://example.invalid/pull/123","headRefName":"chore/standard-cafebabe"}]' | Set-Content $prListFile1 -Encoding utf8

  Set-Content $log '' -NoNewline
  $env:GH_FAKE_REMOTE = $remote1
  $env:GH_FAKE_PR_LIST_FILE = $prListFile1
  $env:GH_FAKE_PR_URL = 'https://example.invalid/pull/999'

  $out1 = & pwsh -NoProfile -File (Join-Path $root 'scripts/upgrade-repos.ps1') -ConfigPath $configPath 2>&1 | Out-String
  Assert-True "reuse-scenario run exits clean (output: $out1)" ($LASTEXITCODE -eq 0)

  $calls1 = Get-Content $log -Raw
  Assert-True 'reuse-scenario does not call pr create' ($calls1 -notmatch '(?m)^pr create ')
  Assert-True 'reuse-scenario lists open PRs' ($calls1 -match '(?m)^pr list --repo acct/example --state open')

  $staleShaAfter = Get-RemoteBranchSha -Remote $remote1 -Branch 'chore/standard-cafebabe'
  Assert-True 'reuse-scenario pushed a new commit onto the existing branch' ($staleShaAfter -and $staleShaAfter -ne $staleShaBefore)

  # Regression check for the history-preservation fix: the manual fixup commit
  # that was already on the branch must still be an ancestor of the new tip,
  # not discarded by a force-push over unrelated history.
  & git -C $remote1 merge-base --is-ancestor $manualSha $staleShaAfter
  Assert-True "reuse-scenario preserves the pre-existing manual commit $manualSha in branch history" ($LASTEXITCODE -eq 0)
  $branchLog1 = (& git -C $remote1 log 'chore/standard-cafebabe' --format='%H %s' | Out-String)
  Assert-True "reuse-scenario branch history still contains the manual commit message (log: $branchLog1)" ($branchLog1 -match 'manual: hotfix applied directly to the rollout PR')

  $newBranches1 = (& git -C $remote1 for-each-ref --format='%(refname:short)' 'refs/heads/chore/standard-*' | Out-String)
  $newBranchCount1 = @($newBranches1 -split "`r?`n" | Where-Object { $_ -and $_ -ne 'chore/standard-cafebabe' }).Count
  Assert-True "reuse-scenario created no additional chore/standard-* branch (found: $newBranches1)" ($newBranchCount1 -eq 0)

  # --- Scenario 2: no existing rollout PR. Behavior is unchanged: a new
  # chore/standard-<short-sha> branch is created and a PR opened on it.
  $remote2Dir = Join-Path $temp 'scenario2'
  New-Item -ItemType Directory -Path $remote2Dir | Out-Null
  $remote2 = (New-FakeRemote -Dir $remote2Dir).Remote

  $prListFile2 = Join-Path $temp 'prlist2.json'
  '[]' | Set-Content $prListFile2 -Encoding utf8

  Set-Content $log '' -NoNewline
  $env:GH_FAKE_REMOTE = $remote2
  $env:GH_FAKE_PR_LIST_FILE = $prListFile2
  $env:GH_FAKE_PR_URL = 'https://example.invalid/pull/1000'

  $out2 = & pwsh -NoProfile -File (Join-Path $root 'scripts/upgrade-repos.ps1') -ConfigPath $configPath 2>&1 | Out-String
  Assert-True "no-existing-PR scenario run exits clean (output: $out2)" ($LASTEXITCODE -eq 0)

  $calls2 = Get-Content $log -Raw
  Assert-True 'no-existing-PR scenario creates a new PR' ($calls2 -match '(?m)^pr create --repo acct/example')
  Assert-True 'no-existing-PR scenario labels the PR risk:R2' ($calls2 -match '(?m)^pr edit .* --add-label risk:R2')

  $newBranches2 = @((& git -C $remote2 for-each-ref --format='%(refname:short)' 'refs/heads/chore/standard-*' | Out-String) -split "`r?`n" | Where-Object { $_ })
  Assert-True "no-existing-PR scenario created exactly one chore/standard-* branch (found: $newBranches2)" ($newBranches2.Count -eq 1)
}
finally {
  $env:PATH = $oldPath
  $env:GH_FAKE_LOG = $oldLog
  Remove-Item Env:\GH_FAKE_REPO -ErrorAction SilentlyContinue
  Remove-Item Env:\GH_FAKE_REMOTE -ErrorAction SilentlyContinue
  Remove-Item Env:\GH_FAKE_PR_LIST_FILE -ErrorAction SilentlyContinue
  Remove-Item Env:\GH_FAKE_PR_URL -ErrorAction SilentlyContinue
  Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
}

Write-Host 'upgrade-repos tests: PASS' -ForegroundColor Green
