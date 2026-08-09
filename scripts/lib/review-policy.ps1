function Get-MachineReviewProvider {
  param([Parameter(Mandatory)][string]$Login)

  $normalized = $Login.ToLowerInvariant()
  if ($normalized -in @('chatgpt-codex-connector','chatgpt-codex-connector[bot]','codex')) { return 'codex' }
  if ($normalized -in @('copilot-pull-request-reviewer','copilot-pull-request-reviewer[bot]','copilot','copilot-swe-agent[bot]')) { return 'copilot' }
  return $null
}

function Get-HeadImplementerProviders {
  param(
    [string]$HeadAuthorLogin = '',
    [string]$HeadCommitterLogin = '',
    [string]$PrAuthorLogin = ''
  )

  $providers = New-Object System.Collections.Generic.List[string]
  foreach ($login in @($HeadAuthorLogin,$HeadCommitterLogin)) {
    if ([string]::IsNullOrWhiteSpace($login)) { continue }
    $provider = Get-MachineReviewProvider -Login $login
    if ($provider -and -not $providers.Contains($provider)) { $providers.Add($provider) }
  }

  # PR author is only a fallback when the head commit itself has no detected
  # machine actor. This prevents an old PR creator from masking the current head.
  if ($providers.Count -eq 0 -and -not [string]::IsNullOrWhiteSpace($PrAuthorLogin)) {
    $provider = Get-MachineReviewProvider -Login $PrAuthorLogin
    if ($provider) { $providers.Add($provider) }
  }
  return @($providers)
}

function Get-HeadImplementerProvider {
  param(
    [string]$HeadAuthorLogin = '',
    [string]$HeadCommitterLogin = '',
    [string]$PrAuthorLogin = ''
  )

  $providers = @(Get-HeadImplementerProviders `
    -HeadAuthorLogin $HeadAuthorLogin `
    -HeadCommitterLogin $HeadCommitterLogin `
    -PrAuthorLogin $PrAuthorLogin)
  if ($providers.Count -eq 0) { return $null }
  return ($providers -join '+')
}

function Get-AcceptedMachineReviewProviders {
  param(
    [string]$HeadAuthorLogin = '',
    [string]$HeadCommitterLogin = '',
    [string]$PrAuthorLogin = ''
  )

  $implementers = @(Get-HeadImplementerProviders `
    -HeadAuthorLogin $HeadAuthorLogin `
    -HeadCommitterLogin $HeadCommitterLogin `
    -PrAuthorLogin $PrAuthorLogin)
  return @(@('codex','copilot') | Where-Object { $implementers -notcontains $_ })
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
  if ($accepted.Count -eq 0) { throw 'No connected machine reviewer is independent of every detected latest-head implementer.' }
  return $accepted[0]
}

function Test-MaterialAiReviewBody {
  param([AllowNull()][string]$Body)
  if ([string]::IsNullOrWhiteSpace($Body)) { return $false }
  if ($Body -match '(?im)^\s*AI-REVIEW\s+FAIL\b') { return $true }

  # Match badges, bracketed findings, and ordinary P0-P2 headings without
  # matching prose such as "No P0-P2 findings".
  if ($Body -match '(?im)!\[P[0-2]\s+Badge\]') { return $true }
  if ($Body -match '(?im)^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?(?:\*\*)?\[P[0-2]\](?:\*\*)?\s*\S') { return $true }
  return $Body -match '(?im)^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?(?:\*\*)?P[0-2]\b[^\r\n]{0,120}?(?:\*\*)?\s*(?::|—)\s*\S'
}

function Test-TrustedAutomationComment {
  param([Parameter(Mandatory)]$Comment,[Parameter(Mandatory)][string]$OwnerLogin)
  return [string]$Comment.user.login -in @('github-actions[bot]', $OwnerLogin)
}

function Get-ReviewRepairDecision {
  param(
    [Parameter(Mandatory)][string]$HeadSha,
    [string[]]$AttemptedHeadShas = @(),
    [Parameter(Mandatory)][int]$MaxAttempts,
    [Parameter(Mandatory)][bool]$HasFindings
  )

  if ($MaxAttempts -lt 1) { throw 'MaxAttempts must be at least 1.' }
  if (-not $HasFindings) { return 'none' }

  $attempted = @($AttemptedHeadShas | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
  if ($attempted -contains $HeadSha) {
    # The repair agent was already asked to fix this exact head. Re-triggering
    # on the request comment itself must not consume another attempt or block.
    return 'pending'
  }
  if ($attempted.Count -ge $MaxAttempts) { return 'block' }
  return 'request'
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
    '^scripts/(apply-github-standard|setup-portfolio|doctor|auto-merge|request-machine-review|request-review-repair|evaluate-ai-review|reconcile-machine-review-threads|pause-pending-review|pr-orchestrator|upgrade-repos|bootstrap-repo)\.ps1$',
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
