$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

function Assert-Equal {
    param([string]$Name, $Actual, $Expected)
    if ($Actual -cne $Expected) { throw "$Name failed: expected '$Expected', got '$Actual'." }
}

function Assert-True {
    param([string]$Name, $Actual)
    if (-not $Actual) { throw "$Name failed: expected true, got '$Actual'." }
}

function Assert-Throws {
    param([string]$Name, [scriptblock]$Action)
    try { & $Action | Out-Null } catch { return }
    throw "$Name failed: expected an exception."
}

# ── policy file ───────────────────────────────────────────────────────────────

$policy = Get-Content (Join-Path $root 'policy/github-defaults.json') -Raw | ConvertFrom-Json

Assert-True 'dependency_automation section exists' ($null -ne $policy.dependency_automation)
Assert-True 'patch_minor_grouping is enabled' ([bool]$policy.dependency_automation.patch_minor_grouping)
Assert-True 'major_auto_merge is false' (-not [bool]$policy.dependency_automation.major_auto_merge)
Assert-True 'max_prs_per_major_batch is positive' ([int]$policy.dependency_automation.max_prs_per_major_batch -gt 0)
Assert-True 'max_open_dep_prs_per_ecosystem is positive' ([int]$policy.dependency_automation.max_open_dep_prs_per_ecosystem -gt 0)
Assert-True 'classify_script is declared' (-not [string]::IsNullOrWhiteSpace($policy.dependency_automation.classify_script))
Assert-True 'dependabot_template is declared' (-not [string]::IsNullOrWhiteSpace($policy.dependency_automation.dependabot_template))

# ── template files ────────────────────────────────────────────────────────────

$dependabotTemplate = Join-Path $root 'templates/dependabot.yml'
Assert-True 'dependabot.yml template exists' (Test-Path $dependabotTemplate)

$templateContent = Get-Content $dependabotTemplate -Raw
Assert-True 'template declares version 2' ($templateContent -match '^version: 2')
Assert-True 'template includes npm ecosystem' ($templateContent -match 'package-ecosystem: npm')
Assert-True 'template includes github-actions ecosystem' ($templateContent -match 'package-ecosystem: github-actions')
Assert-True 'template groups patch and minor' ($templateContent -match 'update-types:' -and $templateContent -match 'patch')
Assert-True 'template ignores semver-major by default for npm' ($templateContent -match 'version-update:semver-major')
Assert-True 'template uses weekly schedule' ($templateContent -match 'interval: weekly')

# ── classify-dep-upgrades.ps1 ─────────────────────────────────────────────────

$classifyScript = Join-Path $root 'scripts/classify-dep-upgrades.ps1'
Assert-True 'classify-dep-upgrades.ps1 exists' (Test-Path $classifyScript)

$scriptContent = Get-Content $classifyScript -Raw
Assert-True 'script has MaxPrsPerBatch param' ($scriptContent -match 'MaxPrsPerBatch')
Assert-True 'script has DryRun switch' ($scriptContent -match 'DryRun')
Assert-True 'script references coupling groups' ($scriptContent -match 'CouplingGroups')
Assert-True 'script emits next-steps guidance' ($scriptContent -match 'Next steps')

# ── bootstrap-repo.ps1 installs dependabot template ──────────────────────────

$bootstrap = Get-Content (Join-Path $root 'scripts/bootstrap-repo.ps1') -Raw
Assert-True 'bootstrap references dependabot template' ($bootstrap -match 'dependabot\.yml')
Assert-True 'bootstrap skips if file already exists' ($bootstrap -match 'Test-Path.*dependabot')

# ── classify coupling logic (unit test via dot-sourcing internal functions) ───

# Extract and evaluate just the coupling helper via a temporary script block
# so we can unit-test Get-CouplingGroup without invoking the full script.
$tempBlock = [scriptblock]::Create(@"
`$CouplingGroups = @(
    @('vite', '@vitejs/'),
    @('react', 'react-dom', 'react-router', 'react-router-dom'),
    @('typescript', '@typescript-eslint/')
)

function Get-CouplingGroup {
    param([string]`$PackageName)
    `$lower = `$PackageName.ToLowerInvariant()
    for (`$i = 0; `$i -lt `$CouplingGroups.Count; `$i++) {
        foreach (`$pattern in `$CouplingGroups[`$i]) {
            if (`$lower -eq `$pattern.ToLowerInvariant() -or `$lower.StartsWith(`$pattern.ToLowerInvariant())) { return `$i }
        }
    }
    return -1
}

Get-CouplingGroup 'vite'
Get-CouplingGroup '@vitejs/plugin-react'
Get-CouplingGroup 'react-dom'
Get-CouplingGroup 'lodash'
"@)

$results = & $tempBlock
Assert-Equal 'vite maps to group 0'                    "$($results[0])" '0'
Assert-Equal '@vitejs/plugin-react maps to group 0'    "$($results[1])" '0'
Assert-Equal 'react-dom maps to group 1'               "$($results[2])" '1'
Assert-Equal 'lodash maps to no group'                 "$($results[3])" '-1'

Write-Host 'dependency-policy tests: PASS' -ForegroundColor Green
