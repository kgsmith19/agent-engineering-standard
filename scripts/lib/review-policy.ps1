function Get-ReviewProviderFromLogin {
  param([Parameter(Mandatory)][string]$Login)

  $normalized = $Login.ToLowerInvariant()
  if ($normalized -in @('chatgpt-codex-connector', 'chatgpt-codex-connector[bot]')) { return 'codex' }
  if ($normalized -in @('copilot-pull-request-reviewer', 'copilot-pull-request-reviewer[bot]')) { return 'copilot' }
  return $null
}

function Get-PreferredIndependentReviewer {
  param(
    [ValidateSet('claude','copilot','codex','human')][string]$Implementer,
    [bool]$CodexAvailable = $true,
    [bool]$CopilotAvailable = $true
  )

  if ($Implementer -ne 'codex' -and $CodexAvailable) { return 'codex' }
  if ($Implementer -ne 'copilot' -and $CopilotAvailable) { return 'copilot' }
  throw "No mechanically connected independent reviewer is available for implementer '$Implementer'."
}

function Test-IndependentReview {
  param(
    [Parameter(Mandatory)][ValidateSet('claude','copilot','codex','human')][string]$Implementer,
    [Parameter(Mandatory)][ValidateSet('copilot','codex')][string]$ReviewerProvider
  )

  if ($Implementer -eq 'human') { return $true }
  return $Implementer -ne $ReviewerProvider
}

function Assert-ManualGateJustification {
  param([Parameter(Mandatory)]$Justification)

  foreach ($field in @('failure_class_prevented','why_automation_is_insufficient','decision_owner','gate_removal_condition')) {
    $property = $Justification.PSObject.Properties[$field]
    if (-not $property -or [string]::IsNullOrWhiteSpace([string]$property.Value)) {
      throw "Manual gate is not justified: missing '$field'."
    }
  }
  return $true
}
