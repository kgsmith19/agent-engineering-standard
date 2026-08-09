function Get-ReviewProviderFromLogin {
  param([Parameter(Mandatory)][string]$Login)

  $normalized = $Login.ToLowerInvariant()
  if ($normalized -in @('chatgpt-codex-connector', 'chatgpt-codex-connector[bot]')) { return 'codex' }
  if ($normalized -in @('copilot-pull-request-reviewer', 'copilot-pull-request-reviewer[bot]', 'copilot', 'copilot-swe-agent[bot]')) { return 'copilot' }
  return $null
}

function Get-RequiredReviewProviders {
  param([Parameter(Mandatory)][ValidateSet('chatgpt','claude','copilot','codex','human','unknown')][string]$Implementer)

  switch ($Implementer) {
    'codex' { return @('copilot') }
    'chatgpt' { return @('copilot') }
    'copilot' { return @('codex') }
    'claude' { return @('codex') }
    default { return @('codex','copilot') }
  }
}

function Get-NextRequiredReviewProvider {
  param(
    [Parameter(Mandatory)][string[]]$RequiredProviders,
    [string[]]$PassedProviders = @()
  )

  foreach ($provider in $RequiredProviders) {
    if ($PassedProviders -notcontains $provider) { return $provider }
  }
  return $null
}

function Get-PreferredIndependentReviewer {
  param(
    [Parameter(Mandatory)][ValidateSet('chatgpt','claude','copilot','codex','human','unknown')][string]$Implementer,
    [bool]$CodexAvailable = $true,
    [bool]$CopilotAvailable = $true
  )

  $required = @(Get-RequiredReviewProviders -Implementer $Implementer)
  $provider = Get-NextRequiredReviewProvider -RequiredProviders $required
  if ($provider -eq 'codex' -and $CodexAvailable) { return 'codex' }
  if ($provider -eq 'copilot' -and $CopilotAvailable) { return 'copilot' }
  throw "Next required reviewer '$provider' is unavailable for implementer '$Implementer'."
}

function Test-IndependentReview {
  param(
    [Parameter(Mandatory)][ValidateSet('chatgpt','claude','copilot','codex','human','unknown')][string]$Implementer,
    [Parameter(Mandatory)][ValidateSet('copilot','codex')][string]$ReviewerProvider
  )

  return @((Get-RequiredReviewProviders -Implementer $Implementer)) -contains $ReviewerProvider
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
