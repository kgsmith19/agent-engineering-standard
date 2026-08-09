function Get-MachineReviewProvider {
  param([Parameter(Mandatory)][string]$Login)

  $normalized = $Login.ToLowerInvariant()
  if ($normalized -in @('chatgpt-codex-connector','chatgpt-codex-connector[bot]','codex')) { return 'codex' }
  if ($normalized -in @('copilot-pull-request-reviewer','copilot-pull-request-reviewer[bot]','copilot','copilot-swe-agent[bot]')) { return 'copilot' }
  return $null
}

function Get-HeadImplementerProvider {
  param(
    [string]$HeadAuthorLogin = '',
    [string]$HeadCommitterLogin = '',
    [string]$PrAuthorLogin = ''
  )

  foreach ($login in @($HeadAuthorLogin,$HeadCommitterLogin,$PrAuthorLogin)) {
    if ([string]::IsNullOrWhiteSpace($login)) { continue }
    $provider = Get-MachineReviewProvider -Login $login
    if ($provider) { return $provider }
  }
  return $null
}

function Get-AcceptedMachineReviewProviders {
  param(
    [string]$HeadAuthorLogin = '',
    [string]$HeadCommitterLogin = '',
    [string]$PrAuthorLogin = ''
  )

  $implementer = Get-HeadImplementerProvider `
    -HeadAuthorLogin $HeadAuthorLogin `
    -HeadCommitterLogin $HeadCommitterLogin `
    -PrAuthorLogin $PrAuthorLogin

  switch ($implementer) {
    'codex' { return @('copilot') }
    'copilot' { return @('codex') }
    default { return @('codex','copilot') }
  }
}

function Get-PreferredMachineReviewer {
  param(
    [string]$HeadAuthorLogin = '',
    [string]$HeadCommitterLogin = '',
    [string]$PrAuthorLogin = ''
  )

  $accepted = @(Get-AcceptedMachineReviewProviders `
    -HeadAuthorLogin $HeadAuthorLogin `
    -HeadCommitterLogin $HeadCommitterLogin `
    -PrAuthorLogin $PrAuthorLogin)
  return $accepted[0]
}

function Test-MaterialAiReviewBody {
  param([AllowNull()][string]$Body)
  if ([string]::IsNullOrWhiteSpace($Body)) { return $false }
  if ($Body -match '(?im)^\s*AI-REVIEW\s+FAIL\b') { return $true }

  # Match actual finding headings/badges, not prose such as "No P0-P2 findings".
  if ($Body -match '(?im)!\[P[0-2]\s+Badge\]') { return $true }
  return $Body -match '(?im)^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?(?:\*\*)?P[0-2]\b[^\r\n]{0,120}?(?:\*\*)?\s*(?::|—)\s*\S'
}

function Get-RiskFromLabels {
  param([string[]]$Labels)
  $risk = @($Labels | Where-Object { $_ -match '^risk:R[0-4]$' })
  if ($risk.Count -gt 1) { throw "Multiple risk labels found: $($risk -join ', ')" }
  if ($risk.Count -eq 0) { return 'R2' }
  return $risk[0].Substring(5)
}

function Test-ControlPlanePath {
  param([Parameter(Mandatory)][string]$Path)
  $patterns = @(
    '^\.github/workflows/', '^\.agent/', '^policy/', '^scripts/lib/',
    '^scripts/(apply-github-standard|setup-portfolio|doctor|auto-merge|request-machine-review|evaluate-ai-review|reconcile-machine-review-threads|pr-orchestrator|upgrade-repos|bootstrap-repo)\.ps1$',
    '^(AGENT_RULES|QUALITY_RULES|SECURITY_RISK_AUTONOMY|DELIVERY_GITHUB|EVIDENCE_LEARNING|AGENTS)\.md$'
  )
  return [bool]($patterns | Where-Object { $Path -match $_ } | Select-Object -First 1)
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
