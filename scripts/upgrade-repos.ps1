param(
  [string]$StandardSha,
  [string]$ConfigPath = (Join-Path $PSScriptRoot "..\policy\github-defaults.json")
)

$ErrorActionPreference = 'Stop'
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
      if (-not (Test-Path $lock)) {
        New-Item -ItemType Directory -Force '.agent' | Out-Null
        @"
standard: $owner/agent-engineering-standard
commit: $StandardSha
pinned_at: "$(Get-Date -Format yyyy-MM-dd)"
pinned_by: upgrade-repos.ps1
"@ | Set-Content $lock -Encoding utf8
      }
      else {
        $text = Get-Content $lock -Raw
        if ($text -notmatch '(?m)^commit:\s*[0-9a-fA-F]{40}\s*$') {
          throw 'Unrecognized standard.lock format; refusing to guess.'
        }
        $text = [regex]::Replace($text, '(?m)^commit:\s*[0-9a-fA-F]{40}\s*$', "commit: $StandardSha")
        $text = [regex]::Replace($text, '(?m)^pinned_at:.*$', "pinned_at: `"$(Get-Date -Format yyyy-MM-dd)`"")
        Set-Content $lock $text -Encoding utf8
      }

      $project = '.agent/project.yaml'
      if (Test-Path $project) {
        $p = Get-Content $project -Raw
        $p = [regex]::Replace($p, '(?m)^(\s*(?:sha|standard_sha|commit):\s*)[0-9a-fA-F]{40}(\s*(?:#.*)?)$', "`$1$StandardSha`$2")
        Set-Content $project $p -Encoding utf8
      }

      $paths = @($lock)
      if (Test-Path $project) { $paths += $project }
      & git add -- $paths
      if ($LASTEXITCODE -ne 0) { throw 'git add failed' }

      & git diff --cached --quiet
      $hasChanges = $LASTEXITCODE -ne 0
      if ($hasChanges) {
        & git commit -m "chore: upgrade agent engineering standard to $short" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'commit failed' }
        & git push -u origin $branch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'push failed' }
        $body = "Pins the shared engineering standard to $StandardSha. No product behavior change. Review as an R3 control-plane dependency update; existing repo-specific quality gates remain authoritative."
        & gh pr create --repo $repo --base main --head $branch --title "Upgrade agent engineering standard to $short" --body $body | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'PR creation failed' }
      }
      else {
        Write-Host 'already pinned; no PR needed'
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
