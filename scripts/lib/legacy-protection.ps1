function Get-LegacyRequiredCheckContexts {
  param([AllowNull()]$Protection)

  return @()
}

function Get-StaleLegacyRequiredCheckContexts {
  param(
    [AllowNull()]$Protection,
    [Parameter(Mandatory)][string]$RequiredContext
  )

  return @()
}
