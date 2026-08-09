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

    $existingRaw = & gh pr list --repo $repo --state open --head $branch --json number,url 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($existingRaw -join "`n") }
    $existingPr = @(($existingRaw -join "`n") | ConvertFrom-Json)
    if ($existingPr.Count -gt 0) {
      Write-Host "existing rollout PR #$($existingPr[0].number): $($existingPr[0].url)" -ForegroundColor Yellow
      continue
    }

    $branchRaw = & gh api "repos/$repo/git/ref/heads/$branch" 2>&1
    if ($LASTEXITCODE -eq 0) {
      $branch = "$branch-$(Get-Date -Format yyyyMMddHHmmss)"
      Write-Host "unused remote branch existed; using $branch" -ForegroundColor Yellow
    }

    & gh repo clone $repo $temp -- --quiet
    if ($LASTEXITCODE -ne 0) { throw 'clone failed' }

    Push-Location $temp
    try {
      & git switch -c $branch | Out-Host
      if ($LASTEXITCODE -ne 0) { throw 'branch creation failed' }

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
      Render-Template (Join-Path $standardRoot 'templates/PR_AUTOMATION.yml') '.github/workflows/pr-automation.yml'
      Remove-Item '.github/CODEOWNERS' -Force -ErrorAction SilentlyContinue

      if (-not (Test-Path '.github/dependabot.yml')) {
        New-Item -ItemType Directory -Force '.github' | Out-Null
        Copy-Item (Join-Path $standardRoot 'templates/dependabot.yml') '.github/dependabot.yml' -Force
      }

      # workflow_run identifies the deterministic gate by workflow name. Preserve
      # a dedicated pr-gate.yml; otherwise normalize CI/ci to exact `PR Gate`
      # without changing the repository-specific jobs or commands.
      if (-not (Test-Path '.github/workflows/pr-gate.yml') -and (Test-Path '.github/workflows/ci.yml')) {
        $ci = Get-Content '.github/workflows/ci.yml' -Raw
        if ($ci -match '(?im)^name:\s*ci\s*$' -and $ci -match 'PR Gate') {
          $ci = [regex]::Replace($ci,'(?im)^name:\s*ci\s*$','name: PR Gate',1)
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
      & git push -u origin $branch | Out-Host
      if ($LASTEXITCODE -ne 0) { throw 'push failed' }

      $body = @"
Pins the shared engineering standard to $StandardSha and installs exact-SHA `AI Review` + `PR Automation` callers.

- Removes native CODEOWNERS so Kyle is not auto-requested as a routine reviewer.
- Preserves the repository-specific deterministic gate and normalizes CI/ci workflow name to exact `PR Gate` only when no dedicated `pr-gate.yml` exists.
- Adds the lean Dependabot default only when absent.
- No product behavior change.

Risk: R3 control-plane dependency update. This bootstrap rollout is manually integrated because it changes the caller that will govern later unattended merges.
"@
      $prUrl = (& gh pr create --repo $repo --base $defaultBranch --head $branch --title "Upgrade autonomous engineering standard to $short" --body $body 2>&1 | Out-String).Trim()
      if ($LASTEXITCODE -ne 0 -or -not $prUrl) { throw 'PR creation failed' }
      $createdRaw = & gh pr view $prUrl --repo $repo --json number,url,isDraft 2>&1
      if ($LASTEXITCODE -ne 0) { throw "PR created but its ready-at-creation postcondition could not be verified: $prUrl" }
      $created = ($createdRaw -join "`n") | ConvertFrom-Json
      if ([bool]$created.isDraft) { throw "Ready-at-creation policy violation: rollout PR #$($created.number) is draft: $($created.url)" }
      & gh pr edit $prUrl --add-label 'risk:R3' | Out-Host
      if ($LASTEXITCODE -ne 0) { throw "PR created but risk:R3 could not be applied: $prUrl" }
      Write-Host "created $prUrl" -ForegroundColor Green
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
