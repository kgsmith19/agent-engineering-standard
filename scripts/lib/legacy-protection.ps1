function Get-LegacyRequiredCheckContexts {
  param([AllowNull()]$Protection)

  if ($null -eq $Protection -or $null -eq $Protection.required_status_checks) {
    return @()
  }

  $seen = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::Ordinal)
  $contexts = [System.Collections.Generic.List[string]]::new()

  foreach ($candidate in @($Protection.required_status_checks.contexts)) {
    $context = [string]$candidate
    if (-not [string]::IsNullOrWhiteSpace($context) -and $seen.Add($context)) {
      $contexts.Add($context)
    }
  }

  foreach ($check in @($Protection.required_status_checks.checks)) {
    if ($null -eq $check) { continue }
    $context = [string]$check.context
    if (-not [string]::IsNullOrWhiteSpace($context) -and $seen.Add($context)) {
      $contexts.Add($context)
    }
  }

  return @($contexts)
}

function Get-StaleLegacyRequiredCheckContexts {
  param(
    [AllowNull()]$Protection,
    [Parameter(Mandatory)][string]$RequiredContext
  )

  return @(
    Get-LegacyRequiredCheckContexts -Protection $Protection |
      Where-Object { $_ -cne $RequiredContext }
  )
}

function Test-GitHubBranchProtectionAbsent {
  param([AllowEmptyString()][string]$ErrorText)

  return ($ErrorText -match '(?i)branch not protected') -and ($ErrorText -match '\b404\b')
}
