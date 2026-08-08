$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $root 'scripts/lib/legacy-protection.ps1')

function Assert-Sequence {
  param(
    [Parameter(Mandatory)][string]$Name,
    [AllowEmptyCollection()][object[]]$Actual,
    [AllowEmptyCollection()][object[]]$Expected
  )

  $actualText = @($Actual) -join ','
  $expectedText = @($Expected) -join ','
  if ($actualText -ne $expectedText) {
    throw "$Name failed. Expected [$expectedText], got [$actualText]."
  }
}

$mixed = [pscustomobject]@{
  required_status_checks = [pscustomobject]@{
    contexts = @('PR Gate', 'test')
    checks = @(
      [pscustomobject]@{ context = 'quality'; app_id = 1 },
      [pscustomobject]@{ context = 'test'; app_id = 2 }
    )
  }
}

Assert-Sequence -Name 'extracts unique contexts from both GitHub shapes' `
  -Actual @(Get-LegacyRequiredCheckContexts -Protection $mixed) `
  -Expected @('PR Gate', 'test', 'quality')

Assert-Sequence -Name 'reports every noncanonical legacy context' `
  -Actual @(Get-StaleLegacyRequiredCheckContexts -Protection $mixed -RequiredContext 'PR Gate') `
  -Expected @('test', 'quality')

$canonicalOnly = [pscustomobject]@{
  required_status_checks = [pscustomobject]@{
    contexts = @('PR Gate')
    checks = @()
  }
}

Assert-Sequence -Name 'accepts canonical context alone' `
  -Actual @(Get-StaleLegacyRequiredCheckContexts -Protection $canonicalOnly -RequiredContext 'PR Gate') `
  -Expected @()

Assert-Sequence -Name 'accepts absent legacy protection' `
  -Actual @(Get-StaleLegacyRequiredCheckContexts -Protection $null -RequiredContext 'PR Gate') `
  -Expected @()

Write-Host 'legacy-protection tests: PASS' -ForegroundColor Green
