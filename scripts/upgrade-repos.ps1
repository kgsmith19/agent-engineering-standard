param(
  [string]$StandardSha,
  [string]$ConfigPath = (Join-Path $PSScriptRoot "..\policy\github-defaults.json")
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
  param([Parameter(Mandatory)][string]$Template,[Parameter(Mandatory)][string]$Destination)
  $text = (Get-Content $Template -Raw).Replace('__STANDARD_SHA__',$StandardSha)
  $parent = Split-Path $Destination -Parent
  New-Item -ItemType Directory -Force $parent | Out-Null
  Set-Content $Destination $text -Encoding utf8 -NoNewline
}

foreach ($name in $config.repositories) {
  if ($name -eq 'agent-engineering-standard') { continue }
  $repo = "$owner/$name"
  $temp = Join-Path ([System.IO.Path]::GetTempPath()) ("std-upgrade-" + $name + '-' + [guid]::NewGuid().ToString('N'))
  Write-Host "`n=== $repo ===" -ForegroundColor Cyan

  try {
    & gh repo clone $repo $temp -- --quiet
    if ($LASTEXITCODE -ne 0) { throw 'clone failed' }

    Push-Location $temp
    try {
      $branch = "chore/standard-$short"
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

      Render-Template -Template (Join-Path $standardRoot 'templates/AI_REVIEW.yml') -Destination '.github/workflows/ai-review.yml'
      Render-Template -Template (Join-Path $standardRoot 'templates/PR_AUTOMATION.yml') -Destination '.github/workflows/pr-automation.yml'
      Remove-Item '.github/CODEOWNERS' -Force -ErrorAction SilentlyContinue

      if (-not (Test-Path '.github/dependabot.yml')) {
        Copy-Item (Join-Path $standardRoot 'templates/dependabot.yml') '.github/dependabot.yml' -Force
      }

      # The automation listens for a completed workflow named exactly PR Gate.
      # Preserve a dedicated pr-gate.yml when present; otherwise normalize the
      # repository's CI workflow name without changing its jobs or commands.
      if (-not (Test-Path '.github/workflows/pr-gate.yml') -and (Test-Path '.github/workflows/ci.yml')) {
        $ci = Get-Content '.github/workflows/ci.yml' -Raw
        if ($ci -match '(?m)^name:\s*CI\s*$' -and $ci -match 'PR Gate') {
          $ci = [regex]::Replace($ci,'(?m)^name:\s*CI\s*$','name: PR Gate',1)
          Set-Content '.github/workflows/ci.yml' $ci -Encoding utf8 -NoNewline
        }
      }

      & git add -A -- .agent .github
      if ($LASTEXITCODE -ne 0) { throw 'git add failed' }

      & git diff --cached --quiet
      $hasChanges = $LASTEXITCODE -ne 0
      if ($hasChanges) {
        & git commit -m "chore: upgrade agent engineering standard to $short" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'commit failed' }
        & git push -u origin $branch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'push failed' }
        $body = @"
Pins the shared engineering standard to `$StandardSha` and installs exact-SHA `AI Review` + `PR Automation` callers.

- Removes native CODEOWNERS so Kyle is not auto-requested as a routine reviewer.
- Preserves the repository-specific deterministic gate and normalizes its workflow name to `PR Gate` only when no dedicated `pr-gate.yml` exists.
- Adds the lean Dependabot default only when absent.
- No product behavior change.

Risk: R3 control-plane dependency update. This bootstrap rollout is manually integrated because it changes the caller that will govern later unattended merges.
"@
        & gh pr create --repo $repo --base main --head $branch --title "Upgrade autonomous engineering standard to $short" --body $body | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'PR creation failed' }
      }
      else {
        Write-Host 'already pinned and configured; no PR needed'
      }
    }
    finally { Pop-Location }
  }
  catch {
    Write-Warning "$repo : $($_.Exception.Message)"
  }
  finally {
    Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue
  }
}
