param(
  [string[]]$Repositories = @(),
  [string]$LocalRoot = '',
  [switch]$Apply
)

$ErrorActionPreference = 'Stop'
foreach ($cmd in @('gh','git')) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$cmd is required." }
}

$standardRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$config = Get-Content (Join-Path $standardRoot 'policy/github-defaults.json') -Raw | ConvertFrom-Json
if (-not $LocalRoot) { $LocalRoot = Split-Path $standardRoot -Parent }
if ($Repositories.Count -eq 0) {
  $Repositories = @($config.repositories | ForEach-Object { "$($config.owner)/$_" })
}

& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'gh is not authenticated.' }

foreach ($repo in $Repositories) {
  Write-Host "`n=== $repo ===" -ForegroundColor Cyan
  $name = ($repo -split '/')[-1]
  $local = Join-Path $LocalRoot $name

  if (Test-Path (Join-Path $local '.git')) {
    Write-Host "Local clone: $local"
    $worktrees = & git -C $local worktree list --porcelain 2>&1
    if ($LASTEXITCODE -eq 0) {
      foreach ($line in $worktrees) {
        if ($line -like 'worktree *') {
          $path = $line.Substring(9)
          if (Test-Path $path) {
            $dirty = & git -C $path status --porcelain 2>$null
            if ($dirty) { Write-Host "  DIRTY WORKTREE (kept): $path" -ForegroundColor Yellow }
          }
        }
      }
    }

    if ($Apply) {
      & git -C $local worktree prune --verbose | Out-Host
      if ($LASTEXITCODE -ne 0) { throw "worktree prune failed for $repo" }
    } else {
      & git -C $local worktree prune --dry-run --verbose | Out-Host
      if ($LASTEXITCODE -ne 0) { throw "worktree prune dry-run failed for $repo" }
    }
  } else {
    Write-Host "Local clone not found under $LocalRoot; local worktree cleanup skipped." -ForegroundColor DarkGray
  }

  $metaRaw = & gh api "repos/$repo" 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Warning "Cannot inspect $repo"; continue }
  $defaultBranch = (($metaRaw -join "`n") | ConvertFrom-Json).default_branch

  $branchesRaw = & gh api --paginate "repos/$repo/branches?per_page=100" --jq '.[].name' 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Warning "Cannot list branches for $repo"; continue }
  $branches = @($branchesRaw | Where-Object { $_ })

  $openPrRaw = & gh pr list --repo $repo --state open --json headRefName --limit 500 2>&1
  $openPrBranches = if ($LASTEXITCODE -eq 0) {
    @(($openPrRaw -join "`n") | ConvertFrom-Json | ForEach-Object { $_.headRefName })
  } else { @() }

  foreach ($branch in $branches) {
    if ($branch -eq $defaultBranch -or $branch -like 'dependabot/*' -or $openPrBranches -contains $branch) { continue }

    $baseEncoded = [uri]::EscapeDataString([string]$defaultBranch)
    $branchEncoded = [uri]::EscapeDataString([string]$branch)
    $compareRaw = & gh api "repos/$repo/compare/$baseEncoded...$branchEncoded" 2>&1
    if ($LASTEXITCODE -ne 0) {
      Write-Host "  KEEP (compare failed): $branch" -ForegroundColor Yellow
      continue
    }
    $compare = ($compareRaw -join "`n") | ConvertFrom-Json
    if ([int]$compare.ahead_by -gt 0) {
      Write-Host "  KEEP (unique commits=$($compare.ahead_by)): $branch" -ForegroundColor Magenta
      continue
    }

    if ($Apply) {
      & gh api --method DELETE "repos/$repo/git/refs/heads/$branchEncoded" 2>&1 | Out-Null
      if ($LASTEXITCODE -eq 0) { Write-Host "  DELETED merged/equivalent branch: $branch" -ForegroundColor Green }
      else { Write-Host "  KEEP (delete failed): $branch" -ForegroundColor Yellow }
    } else {
      Write-Host "  WOULD DELETE merged/equivalent branch: $branch" -ForegroundColor DarkYellow
    }
  }
}

if (-not $Apply) {
  Write-Host "`nDRY RUN ONLY. Re-run with -Apply to prune stale metadata and delete only proven merged/equivalent remote branches." -ForegroundColor Yellow
}
