function Test-TrustedAutomationComment {
  param([Parameter(Mandatory)]$Comment,[Parameter(Mandatory)][string]$OwnerLogin)
  return [string]$Comment.user.login -in @('github-actions[bot]', $OwnerLogin)
}

function Get-GateConclusionDecision {
  param([AllowEmptyString()][string]$Conclusion)
  switch ($Conclusion) {
    'success' { return 'success' }
    'failure' { return 'repair' }
    'timed_out' { return 'repair' }
    'startup_failure' { return 'repair' }
    'action_required' { return 'block-workflow-approval' }
    'skipped' { return 'block-gate-skipped' }
    'cancelled' { return 'rerun' }
    'stale' { return 'rerun' }
    'neutral' { return 'block-gate-neutral' }
    default { return 'block-gate-unknown' }
  }
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
    '^scripts/(apply-github-standard|setup-portfolio|doctor|auto-merge|gate-result-router|pr-orchestrator|upgrade-repos|bootstrap-repo)\.ps1$',
    '^(AGENT_RULES|QUALITY_RULES|SECURITY_RISK_AUTONOMY|DELIVERY_GITHUB|EVIDENCE_LEARNING|AGENTS)\.md$'
  )
  return [bool]($patterns | Where-Object { $Path -match $_ } | Select-Object -First 1)
}

function Assert-ManualGateJustification {
  param([Parameter(Mandatory)]$Justification)
  foreach ($field in @('failure_class_prevented','why_automation_is_insufficient','decision_owner','gate_removal_condition')) {
    $property = $Justification.PSObject.Properties[$field]
    if (-not $property -or [string]::IsNullOrWhiteSpace([string]$property.Value)) { throw "Manual gate is not justified: missing '$field'." }
  }
  return $true
}

function Invoke-WithAdminToken {
  # GITHUB_TOKEN cannot read admin repo settings/rulesets and its events never
  # trigger downstream workflows; GH_TOKEN_ADMIN (fine-grained PAT, Administration:read)
  # covers exactly those call sites. Falls back to the ambient token when unset.
  param([Parameter(Mandatory)][scriptblock]$Action)
  if ([string]::IsNullOrWhiteSpace($env:GH_TOKEN_ADMIN)) { return & $Action }
  $previous = $env:GH_TOKEN
  $env:GH_TOKEN = $env:GH_TOKEN_ADMIN
  try { return & $Action } finally { $env:GH_TOKEN = $previous }
}
