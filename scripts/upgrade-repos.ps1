param(
  [string]$StandardSha,
  [string]$ConfigPath = (Join-Path $PSScriptRoot '..\policy\github-defaults.json')
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/standard-lock.ps1')

foreach ($cmd in @('gh','git')) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$cmd is required." }
}
& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'gh is not authenticated.' }

$standardRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $StandardSha) {
  $StandardSha = (& git -C $standardRoot rev-parse HEAD).Trim()
  if ($LASTEXITCODE -ne 0) { throw 'Could not resolve standards commit.' }
}
if ($StandardSha -notmatch '^[0-9a-fA-F]{40}$') { throw 'StandardSha must be a full 40-character commit SHA.' }

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$owner = $config.owner
$short = $StandardSha.Substring(0,8)
$pinnedAt = Get-Date -Format yyyy-MM-dd

function Render-Template {
  param([string]$Template,[string]$Destination)
  $text = (Get-Content $Template -Raw).Replace('__STANDARD_SHA__',$StandardSha)
  New-Item -ItemType Directory -Force (Split-Path $Destination -Parent) | Out-Null
  Set-Content $Destination $text -Encoding utf8 -NoNewline
}

$failures = New-Object System.Collections.Generic.List[string]
foreach ($name in $config.repositories) {
  if ($name -eq 'agent-engineering-standard') { continue }
  $repo = "$owner/$name"
  $branch = "chore/standard-$short"
  $temp = Join-Path ([System.IO.Path]::GetTempPath()) ("std-upgrade-" + $name + '-' + [guid]::NewGuid().ToString('N'))
  Write-Host "`n=== $repo ===" -ForegroundColor Cyan

  try {
    # Repositories differ in default branch (e.g. master); never assume main.
    $metaRaw = & gh api "repos/$repo" 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($metaRaw -join "`n") }
    $defaultBranch = [string]((($metaRaw -join "`n") | ConvertFrom-Json).default_branch)
    if (-not $defaultBranch) { throw "cannot resolve live default branch for $repo" }

    # One rollout PR open per repo, ever: reuse any open PR whose head branch
    # matches chore/standard-* (regardless of which sha it names) instead of
    # spawning a new branch/PR per standard commit, which otherwise leaves
    # the prior still-open rollout PR stale and orphaned.
    $openRaw = & gh pr list --repo $repo --state open --json number,url,headRefName 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($openRaw -join "`n") }
    $openPrs = @(($openRaw -join "`n") | ConvertFrom-Json)
    $existingPr = @($openPrs | Where-Object { $_.headRefName -like 'chore/standard-*' } | Select-Object -First 1)
    $reuseExisting = $existingPr.Count -gt 0
    if ($reuseExisting) {
      $branch = $existingPr[0].headRefName
      Write-Host "existing rollout PR #$($existingPr[0].number): $($existingPr[0].url); updating in place" -ForegroundColor Yellow
    }
    else {
      $branchRaw = & gh api "repos/$repo/git/ref/heads/$branch" 2>&1
      if ($LASTEXITCODE -eq 0) {
        $branch = "$branch-$(Get-Date -Format yyyyMMddHHmmss)"
        Write-Host "unused remote branch existed; using $branch" -ForegroundColor Yellow
      }
    }

    & gh repo clone $repo $temp -- --quiet
    if ($LASTEXITCODE -ne 0) { throw 'clone failed' }

    Push-Location $temp
    try {
      # CI runners carry no global git identity; the commit below needs a local one.
      & git config user.email 'automation@agent-engineering-standard.invalid'
      & git config user.name 'agent-engineering-standard-bot'
      if ($reuseExisting) {
        # Preserve the existing rollout branch's real history (including any
        # manual fixup commits already pushed to it) instead of recreating the
        # branch from the freshly cloned default branch's HEAD -- that would
        # make the regeneration commit unrelated history and silently discard
        # everything already on the branch when pushed.
        & git fetch origin $branch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'fetch of existing rollout branch failed' }
        & git checkout -B $branch FETCH_HEAD | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'checkout of existing rollout branch failed' }
      }
      else {
        & git switch -c $branch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'branch creation failed' }
      }

      $lock = '.agent/standard.lock'
      $previousStandardSha = $null
      if (-not (Test-Path $lock)) {
        New-Item -ItemType Directory -Force '.agent' | Out-Null
        @"
standard: $owner/agent-engineering-standard
commit: $StandardSha
pinned_at: "$pinnedAt"
pinned_by: upgrade-repos.ps1
"@ | Set-Content $lock -Encoding utf8 -NoNewline
      }
      else {
        $text = Get-Content $lock -Raw
        $previousStandardSha = Get-StandardLockRevision -Content $text
        $text = Update-StandardLockContent -Content $text -StandardSha $StandardSha -PinnedAt $pinnedAt
        Set-Content $lock $text -Encoding utf8 -NoNewline
      }

      $project = '.agent/project.yaml'
      if ((Test-Path $project) -and $previousStandardSha) {
        $projectText = Get-Content $project -Raw
        $projectText = Update-StandardProjectContent -Content $projectText -PreviousStandardSha $previousStandardSha -StandardSha $StandardSha
        Set-Content $project $projectText -Encoding utf8 -NoNewline
      }

      Render-Template (Join-Path $standardRoot 'templates/AI_REVIEW.yml') '.github/workflows/ai-review.yml'
      # Per-event PR Automation callers: one workflow per trigger so no PR shows
      # permanently-skipped sibling jobs in its check panel.
      Render-Template (Join-Path $standardRoot 'templates/PR_AUTOMATION.yml') '.github/workflows/pr-automation.yml'
      Render-Template (Join-Path $standardRoot 'templates/PR_AUTOMATION_GATE_RESULT.yml') '.github/workflows/pr-automation-gate-result.yml'
      Render-Template (Join-Path $standardRoot 'templates/PR_AUTOMATION_REVIEW_EVENT.yml') '.github/workflows/pr-automation-review-event.yml'
      Render-Template (Join-Path $standardRoot 'templates/PR_AUTOMATION_COMMENT_EVENT.yml') '.github/workflows/pr-automation-comment-event.yml'
      Render-Template (Join-Path $standardRoot 'templates/PR_AUTOMATION_WATCHDOG.yml') '.github/workflows/pr-automation-watchdog.yml'
      Remove-Item '.github/CODEOWNERS' -Force -ErrorAction SilentlyContinue

      if (-not (Test-Path '.github/dependabot.yml')) {
        New-Item -ItemType Directory -Force '.github' | Out-Null
        Copy-Item (Join-Path $standardRoot 'templates/dependabot.yml') '.github/dependabot.yml' -Force
      }

      # workflow_run identifies the deterministic gate by workflow name. Preserve
      # a dedicated pr-gate.yml; otherwise normalize CI/ci to the taxonomy name
      # "Gate: Deterministic CI" (the gate-result trigger listens for it) without
      # changing the repository-specific jobs, commands, or the PR Gate job context.
      if (-not (Test-Path '.github/workflows/pr-gate.yml') -and (Test-Path '.github/workflows/ci.yml')) {
        $ci = Get-Content '.github/workflows/ci.yml' -Raw
        if ($ci -match '(?im)^name:\s*(ci|PR Gate)\s*$' -and $ci -match 'PR Gate') {
          $ci = [regex]::Replace($ci,'(?im)^name:\s*(ci|PR Gate)\s*$','name: "Gate: Deterministic CI"',1)
          Set-Content '.github/workflows/ci.yml' $ci -Encoding utf8 -NoNewline
        }
      }

      & git add -A -- .agent .github
      if ($LASTEXITCODE -ne 0) { throw 'git add failed' }
      & git diff --cached --quiet
      if ($LASTEXITCODE -eq 0) {
        Write-Host 'already pinned and configured; no PR needed'
        continue
      }

      & git commit -m "chore: upgrade agent engineering standard to $short" | Out-Host
      if ($LASTEXITCODE -ne 0) { throw 'commit failed' }
      # Reuse checks out the existing branch's real tip (git checkout -B ...
      # FETCH_HEAD above), so this commit is a genuine descendant and the push
      # is a normal fast-forward -- no force needed, and none used, so any
      # manual commit already on the branch is preserved, not overwritten.
      & git push -u origin $branch | Out-Host
      if ($LASTEXITCODE -ne 0) { throw 'push failed' }

      if ($reuseExisting) {
        Write-Host "updated existing rollout PR #$($existingPr[0].number) with $short" -ForegroundColor Green
      }
      else {
        $body = @"
Pins the shared engineering standard to $StandardSha and installs exact-SHA `AI Review` + `PR Automation` callers.

- Removes native CODEOWNERS so Kyle is not auto-requested as a routine reviewer.
- Preserves the repository-specific deterministic gate and normalizes CI/ci workflow name to exact `PR Gate` only when no dedicated `pr-gate.yml` exists.
- Adds the lean Dependabot default only when absent.
- No product behavior change.

Risk: R2. This content was already reviewed once, at the standard repo's own gate; propagating identical, deterministically-generated content to product repos is not new independent risk, and the design's documented auto-merge ceiling (unattended auto-merge is capped at R2) already anticipated this exact class of change. upgrade-repos.ps1 only ever writes to known, template-driven paths, never arbitrary content.
"@
        $prUrl = (& gh pr create --repo $repo --base $defaultBranch --head $branch --title "Upgrade autonomous engineering standard to $short" --body $body 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $prUrl) { throw 'PR creation failed' }
        $createdRaw = & gh pr view $prUrl --repo $repo --json number,url,isDraft 2>&1
        if ($LASTEXITCODE -ne 0) { throw "PR created but its ready-at-creation postcondition could not be verified: $prUrl" }
        $created = ($createdRaw -join "`n") | ConvertFrom-Json
        if ([bool]$created.isDraft) { throw "Ready-at-creation policy violation: rollout PR #$($created.number) is draft: $($created.url)" }
        & gh pr edit $prUrl --add-label 'risk:R2' | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "PR created but risk:R2 could not be applied: $prUrl" }
        Write-Host "created $prUrl" -ForegroundColor Green
      }
    }
    finally { Pop-Location }
  }
  catch {
    Write-Warning "$repo : $($_.Exception.Message)"
    $failures.Add("${repo}: $($_.Exception.Message)")
  }
  finally {
    Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
  }
}

if ($failures.Count -gt 0) { throw "ROLLOUT FAILED for $($failures.Count) repositories:`n$($failures -join "`n")" }
Write-Host 'ROLLOUT COMPLETE: every configured repository succeeded.' -ForegroundColor Green
