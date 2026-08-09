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
$projectTitle = $config.project_title
$short = $StandardSha.Substring(0,8)
$pinnedAt = Get-Date -Format yyyy-MM-dd

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
      $projectText = if (Test-Path $project) { Get-Content $project -Raw } else { '' }
      if ($previousStandardSha -and $projectText) {
        $projectText = Update-StandardProjectContent -Content $projectText -PreviousStandardSha $previousStandardSha -StandardSha $StandardSha
      }
      $projectText = Update-ProjectWorkTrackingContent -Content $projectText -ProjectTitle $projectTitle
      Set-Content $project $projectText -Encoding utf8 -NoNewline

      New-Item -ItemType Directory -Force '.github/workflows' | Out-Null
      $aiReview = '.github/workflows/ai-review.yml'
      $prAutomation = '.github/workflows/pr-automation.yml'
      Copy-Item (Join-Path $standardRoot 'templates/AI_REVIEW.yml') $aiReview -Force
      Copy-Item (Join-Path $standardRoot 'templates/PR_AUTOMATION.yml') $prAutomation -Force

      $paths = @($lock, $project, $aiReview, $prAutomation)
      & git add -- $paths
      if ($LASTEXITCODE -ne 0) { throw 'git add failed' }

      & git diff --cached --quiet
      $hasChanges = $LASTEXITCODE -ne 0
      if ($hasChanges) {
        & git commit -m "chore: upgrade agent engineering standard to $short" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'commit failed' }
        & git push -u origin $branch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'push failed' }
        $body = "Pins the shared engineering standard to $StandardSha, migrates work tracking to the '$projectTitle' Project with Issues as durable backing records, and refreshes the canonical AI Review + PR Automation callers. No product behavior change. Review as an R3 control-plane dependency update; the repo-specific PR Gate remains authoritative."
        & gh pr create --repo $repo --base main --head $branch --title "Upgrade agent engineering standard to $short" --body $body | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'PR creation failed' }
      }
      else {
        Write-Host 'already converged; no PR needed'
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
