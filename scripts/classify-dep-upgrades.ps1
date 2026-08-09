<#
.SYNOPSIS
    Classify open Dependabot major-version PRs into compatible upgrade batches
    and propose the minimal coherent grouping before any code changes are made.

.DESCRIPTION
    Fetches open Dependabot pull requests for one or more repositories, groups
    major upgrades by ecosystem and detected coupling (e.g. Vite + Vite plugins,
    React + React-DOM), then emits a proposed batching plan.

    The script does NOT open PRs, merge anything, or close existing Dependabot
    PRs.  It is purely analytical.  A human or agent acts on the plan output.

    Coupling heuristics are intentionally cheap.  The script checks whether two
    packages share a scope or a well-known co-upgrade group; it does not parse
    changelogs or check API compatibility.  For complex migrations the plan
    includes a "needs-review" flag so a human confirms before the batch PR is
    opened.

.PARAMETER Repositories
    One or more "owner/repo" strings to inspect.  Defaults to all repositories
    listed in policy/github-defaults.json.

.PARAMETER ConfigPath
    Path to policy/github-defaults.json.

.PARAMETER MaxPrsPerBatch
    Maximum number of Dependabot PRs to combine into one upgrade PR.  Exceeding
    this limit prevents unreviewed avalanche upgrades.  Default: 5.

.PARAMETER DryRun
    Print the plan without writing any output files.

.EXAMPLE
    pwsh scripts/classify-dep-upgrades.ps1 -Repositories kgsmith19/agentic-command-center-ui
#>

param(
    [string[]]$Repositories,
    [string]$ConfigPath = (Join-Path $PSScriptRoot '..\policy\github-defaults.json'),
    [int]$MaxPrsPerBatch = 5,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

foreach ($cmd in @('gh')) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { throw "$cmd is required." }
}

# ── coupling groups ───────────────────────────────────────────────────────────
# Packages that are always upgraded together within a single PR.
# Each entry is an array of name patterns (case-insensitive prefix or exact).
$CouplingGroups = @(
    # Vite + official plugins
    @('vite', '@vitejs/'),
    # React core
    @('react', 'react-dom', 'react-router', 'react-router-dom'),
    # TypeScript toolchain
    @('typescript', '@typescript-eslint/'),
    # ESLint core + plugins
    @('eslint', '@eslint/', 'eslint-plugin-', 'eslint-config-'),
    # Testing Library
    @('@testing-library/'),
    # Tailwind CSS
    @('tailwindcss', '@tailwindcss/'),
    # Storybook
    @('storybook', '@storybook/')
)

function Get-CouplingGroup {
    param([string]$PackageName)
    $lower = $PackageName.ToLowerInvariant()
    for ($i = 0; $i -lt $CouplingGroups.Count; $i++) {
        foreach ($pattern in $CouplingGroups[$i]) {
            if ($lower -eq $pattern.ToLowerInvariant() -or $lower.StartsWith($pattern.ToLowerInvariant())) {
                return $i
            }
        }
    }
    return -1
}

# ── helpers ───────────────────────────────────────────────────────────────────

function Get-DependabotMajorPrs {
    param([string]$Repo)
    $raw = & gh pr list --repo $Repo --author 'app/dependabot' --state open --json number,title,headRefName,labels --limit 100 2>&1
    if ($LASTEXITCODE -ne 0) { Write-Warning "Cannot list PRs for $Repo: $($raw -join ' ')"; return @() }
    $prs = ($raw -join "`n") | ConvertFrom-Json
    return $prs | Where-Object {
        $_.title -match '\bmajor\b' -or $_.headRefName -match 'major' -or
        ($_.title -match '/(\d+)\.0\.0?' -and ([int]$Matches[1]) -ge 1)
    }
}

function ConvertTo-BatchPlan {
    param([array]$Prs, [string]$Repo, [int]$MaxPerBatch)

    # Parse package name from dependabot branch name: dependabot/<ecosystem>/<name>-<version>
    $annotated = $Prs | ForEach-Object {
        $pr = $_
        $eco = 'unknown'
        $pkg = $pr.title
        if ($pr.headRefName -match '^dependabot/([^/]+)/(.+)$') {
            $eco = $Matches[1]
            $raw = $Matches[2]
            # strip trailing version segment e.g. "-18.0.0"
            $pkg = ($raw -replace '-\d+\.\d+.*$', '')
        }
        [pscustomobject]@{
            Pr         = $pr.number
            Title      = $pr.title
            Ecosystem  = $eco
            Package    = $pkg
            CouplingId = (Get-CouplingGroup $pkg)
        }
    }

    # Group: first by ecosystem, then by coupling id
    $grouped = $annotated | Group-Object Ecosystem | ForEach-Object {
        $ecosystemGroup = $_
        $byCouple = $ecosystemGroup.Group | Group-Object CouplingId
        $batches = @()
        foreach ($g in $byCouple) {
            $members = @($g.Group)
            # Split if batch exceeds max size
            for ($start = 0; $start -lt $members.Count; $start += $MaxPerBatch) {
                $slice = $members[$start..([Math]::Min($start + $MaxPerBatch - 1, $members.Count - 1))]
                $needsReview = ($slice | Where-Object { $_.CouplingId -eq -1 }).Count -gt 0
                $batches += [pscustomobject]@{
                    Ecosystem   = $ecosystemGroup.Name
                    Packages    = ($slice | Select-Object -ExpandProperty Package)
                    PrNumbers   = ($slice | Select-Object -ExpandProperty Pr)
                    NeedsReview = $needsReview
                    Count       = $slice.Count
                }
            }
        }
        $batches
    }

    return $grouped
}

# ── main ──────────────────────────────────────────────────────────────────────

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$targets = if ($Repositories -and $Repositories.Count -gt 0) {
    $Repositories
} else {
    @($config.repositories) | ForEach-Object { "$($config.owner)/$_" }
}

$budget = $config.dependency_automation
$maxPrsPerBatchEffective = if ($budget -and $budget.max_prs_per_major_batch) {
    [int]$budget.max_prs_per_major_batch
} else { $MaxPrsPerBatch }

$allPlans = [System.Collections.Generic.List[pscustomobject]]::new()

foreach ($repo in $targets) {
    Write-Host "`n=== $repo ===" -ForegroundColor Cyan
    $majorPrs = @(Get-DependabotMajorPrs -Repo $repo)
    if ($majorPrs.Count -eq 0) {
        Write-Host '  No open major-version Dependabot PRs.' -ForegroundColor Gray
        continue
    }
    Write-Host "  Found $($majorPrs.Count) major PR(s)."
    $plan = @(ConvertTo-BatchPlan -Prs $majorPrs -Repo $repo -MaxPerBatch $maxPrsPerBatchEffective)
    foreach ($batch in $plan) {
        $flag = if ($batch.NeedsReview) { ' [needs-review]' } else { '' }
        Write-Host "  Batch ($($batch.Ecosystem))$flag: $($batch.Packages -join ', ') [PR #$($batch.PrNumbers -join ', #')]"
    }
    $allPlans.Add([pscustomobject]@{ Repo = $repo; Batches = $plan })
}

if (-not $DryRun) {
    $outPath = Join-Path $PSScriptRoot '..\dep-upgrade-plan.json'
    $allPlans | ConvertTo-Json -Depth 10 | Set-Content $outPath -Encoding utf8
    Write-Host "`nPlan written to $outPath" -ForegroundColor Green
}

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "  1. For each batch without [needs-review]: open one branch combining those Dependabot changes."
Write-Host "  2. For [needs-review] batches: a compatibility agent reviews migration requirements first."
Write-Host "  3. Close superseded individual Dependabot PRs only after the batch PR proves equivalent coverage."

return $allPlans
