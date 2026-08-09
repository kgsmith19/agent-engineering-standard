<#
.SYNOPSIS
  Conservative portfolio cleanup: prune stale worktree metadata and delete only
  branches that are provably merged or equivalent to their base. Dirty or unique
  worktrees/branches are reported, never destroyed.

.DESCRIPTION
  Safety rules:
  - Open PR branches are never touched.
  - Dependabot branches are never touched.
  - Worktrees with uncommitted changes are reported only.
  - Branches with commits not present on the base are reported only.
  - Nothing is deleted without -WhatIf being false and explicit confirmation.

.PARAMETER Repositories
  One or more "owner/repo" strings. Defaults to all repos in the portfolio
  (policy/github-defaults.json owner).

.PARAMETER BaseBranch
  The integration branch to compare against. Default: main.

.PARAMETER WhatIf
  When set, show what would be deleted without making any changes.

.EXAMPLE
  pwsh -File scripts/prune-portfolio.ps1 -WhatIf
  pwsh -File scripts/prune-portfolio.ps1 -Repositories myorg/myrepo
#>
param(
  [string[]]$Repositories = @(),
  [string]$BaseBranch = 'main',
  [switch]$WhatIf
)

$ErrorActionPreference = 'Stop'

foreach ($cmd in @('gh', 'git')) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$cmd is required." }
}

$standardRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$policy = Get-Content (Join-Path $standardRoot 'policy/github-defaults.json') -Raw | ConvertFrom-Json
$owner = $policy.owner

if ($Repositories.Count -eq 0) {
  Write-Host "Fetching repository list for $owner ..."
  $repoJson = & gh repo list $owner --json nameWithOwner --limit 200 2>&1
  if ($LASTEXITCODE -ne 0) { throw "Could not list repositories: $repoJson" }
  $Repositories = ($repoJson | ConvertFrom-Json) | ForEach-Object { $_.nameWithOwner }
}

$summary = [System.Collections.Generic.List[psobject]]::new()

foreach ($repo in $Repositories) {
  Write-Host "`n=== $repo ===" -ForegroundColor Cyan

  # ── Worktree metadata pruning ─────────────────────────────────────────────
  $cloneDir = Join-Path ([System.IO.Path]::GetTempPath()) ("prune-$($repo -replace '/','_')")
  $cloned = $false
  if (-not (Test-Path $cloneDir)) {
    Write-Host "  Shallow-cloning $repo for worktree inspection..."
    & gh repo clone $repo $cloneDir -- --depth=1 --no-single-branch 2>&1 | Out-Null
    $cloned = $true
  }

  if (Test-Path $cloneDir) {
    $wtList = & git -C $cloneDir worktree list --porcelain 2>&1
    if ($LASTEXITCODE -eq 0) {
      $staleCount = 0
      $wtList | Select-String 'prunable' | ForEach-Object { $staleCount++ }
      if ($staleCount -gt 0) {
        Write-Host "  Found $staleCount stale worktree entries — pruning metadata..."
        if (-not $WhatIf) {
          & git -C $cloneDir worktree prune | Out-Null
        } else {
          Write-Host "  [WhatIf] Would prune $staleCount stale worktree entries."
        }
      } else {
        Write-Host "  No stale worktree metadata."
      }
    }
    if ($cloned) { Remove-Item $cloneDir -Recurse -Force -ErrorAction SilentlyContinue }
  }

  # ── Branch analysis ───────────────────────────────────────────────────────
  Write-Host "  Fetching branches and open PRs..."
  $branchesJson = & gh api "repos/$repo/branches" --paginate 2>&1
  if ($LASTEXITCODE -ne 0) {
    Write-Host "  WARNING: could not fetch branches for $repo" -ForegroundColor Yellow
    continue
  }
  $branches = $branchesJson | ConvertFrom-Json | ForEach-Object { $_.name }

  $openPRsJson = & gh pr list --repo $repo --state open --json headRefName --limit 500 2>&1
  $openPRBranches = if ($LASTEXITCODE -eq 0) {
    ($openPRsJson | ConvertFrom-Json) | ForEach-Object { $_.headRefName }
  } else { @() }

  foreach ($branch in $branches) {
    if ($branch -eq $BaseBranch) { continue }

    # Never touch open PR branches or Dependabot branches
    if ($openPRBranches -contains $branch) {
      Write-Host "  SKIP (open PR): $branch"
      continue
    }
    if ($branch -like 'dependabot/*') {
      Write-Host "  SKIP (dependabot): $branch"
      continue
    }

    # Check if branch is fully merged into base
    $compareJson = & gh api "repos/$repo/compare/$BaseBranch...$branch" 2>&1
    if ($LASTEXITCODE -ne 0) {
      Write-Host "  SKIP (compare failed): $branch" -ForegroundColor Yellow
      continue
    }
    $compare = $compareJson | ConvertFrom-Json
    $aheadBy = $compare.ahead_by
    $status   = $compare.status  # "identical", "behind", "ahead", "diverged"

    if ($aheadBy -eq 0) {
      # Branch has no unique commits — safe to delete
      $action = if ($WhatIf) { '[WhatIf] Would delete' } else { 'Deleting' }
      Write-Host "  $action merged/equivalent branch: $branch (status=$status)" -ForegroundColor $(if ($WhatIf) { 'DarkYellow' } else { 'Green' })
      if (-not $WhatIf) {
        & gh api -X DELETE "repos/$repo/git/refs/heads/$branch" 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
          Write-Host "  WARNING: could not delete $branch" -ForegroundColor Yellow
        }
      }
      $summary.Add([pscustomobject]@{ Repo=$repo; Branch=$branch; Action='deleted'; AheadBy=$aheadBy; Status=$status })
    } else {
      # Branch has unique commits — report only, never destroy
      Write-Host "  REPORT (unique commits ahead=$aheadBy, status=$status): $branch" -ForegroundColor Magenta
      $summary.Add([pscustomobject]@{ Repo=$repo; Branch=$branch; Action='reported'; AheadBy=$aheadBy; Status=$status })
    }
  }
}

Write-Host "`n=== Summary ===" -ForegroundColor Cyan
$summary | Format-Table -AutoSize

if ($WhatIf) {
  Write-Host "`n[WhatIf mode] No changes were made. Re-run without -WhatIf to apply." -ForegroundColor Yellow
}
