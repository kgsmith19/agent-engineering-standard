function Get-MachineReviewProvider {
  param([Parameter(Mandatory)][string]$Login)

  $normalized = $Login.ToLowerInvariant()
  if ($normalized -in @('chatgpt-codex-connector','chatgpt-codex-connector[bot]','codex')) { return 'codex' }
  if ($normalized -in @('copilot-pull-request-reviewer','copilot-pull-request-reviewer[bot]','copilot','copilot-swe-agent[bot]')) { return 'copilot' }
  return $null
}

function Get-MachineImplementerProvidersForActors {
  # The PR author's recognized provider is ALWAYS unioned with commit actors:
  # an author whose commits carry other identities still owns the change set.
  param(
    [string[]]$ActorLogins = @(),
    [string]$PrAuthorLogin = ''
  )

  $providers = New-Object System.Collections.Generic.List[string]
  foreach ($login in @(@($ActorLogins) + @($PrAuthorLogin))) {
    if ([string]::IsNullOrWhiteSpace([string]$login)) { continue }
    $provider = Get-MachineReviewProvider -Login ([string]$login)
    if ($provider -and -not $providers.Contains($provider)) { $providers.Add($provider) }
  }
  return @($providers)
}

function Get-AcceptedMachineReviewProvidersForActors {
  param(
    [string[]]$ActorLogins = @(),
    [string]$PrAuthorLogin = ''
  )
  $implementers = @(Get-MachineImplementerProvidersForActors -ActorLogins $ActorLogins -PrAuthorLogin $PrAuthorLogin)
  return @(@('codex','copilot') | Where-Object { $implementers -notcontains $_ })
}

function Get-PreferredMachineReviewerForActors {
  param(
    [string[]]$ActorLogins = @(),
    [string]$PrAuthorLogin = ''
  )
  $accepted = @(Get-AcceptedMachineReviewProvidersForActors -ActorLogins $ActorLogins -PrAuthorLogin $PrAuthorLogin)
  if ($accepted.Count -eq 0) { throw 'No connected machine reviewer is independent of every detected implementer in the current PR.' }
  return $accepted[0]
}

function Get-HeadImplementerProviders {
  param(
    [string]$HeadAuthorLogin = '',
    [string]$HeadCommitterLogin = '',
    [string]$PrAuthorLogin = ''
  )
  return @(Get-MachineImplementerProvidersForActors -ActorLogins @($HeadAuthorLogin,$HeadCommitterLogin) -PrAuthorLogin $PrAuthorLogin)
}

function Get-HeadImplementerProvider {
  param([string]$HeadAuthorLogin = '',[string]$HeadCommitterLogin = '',[string]$PrAuthorLogin = '')
  $providers = @(Get-HeadImplementerProviders -HeadAuthorLogin $HeadAuthorLogin -HeadCommitterLogin $HeadCommitterLogin -PrAuthorLogin $PrAuthorLogin)
  if ($providers.Count -eq 0) { return $null }
  return ($providers -join '+')
}

function Get-AcceptedMachineReviewProviders {
  param([string]$HeadAuthorLogin = '',[string]$HeadCommitterLogin = '',[string]$PrAuthorLogin = '')
  return @(Get-AcceptedMachineReviewProvidersForActors -ActorLogins @($HeadAuthorLogin,$HeadCommitterLogin) -PrAuthorLogin $PrAuthorLogin)
}

function Get-PreferredMachineReviewer {
  param([string]$HeadAuthorLogin = '',[string]$HeadCommitterLogin = '',[string]$PrAuthorLogin = '')
  return Get-PreferredMachineReviewerForActors -ActorLogins @($HeadAuthorLogin,$HeadCommitterLogin) -PrAuthorLogin $PrAuthorLogin
}

function Test-BlockingAiReviewBody {
  param([AllowNull()][string]$Body)
  if ([string]::IsNullOrWhiteSpace($Body)) { return $false }
  if ($Body -match '(?im)^\s*AI-REVIEW\s+FAIL\b') { return $true }
  if ($Body -match '(?im)!\[P[01]\s+Badge\]') { return $true }
  if ($Body -match '(?im)^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?(?:\*\*)?\[P[01]\](?:\*\*)?\s*\S') { return $true }
  return $Body -match '(?im)^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?(?:\*\*)?P[01]\b[^\r\n]{0,120}?(?:\*\*)?\s*(?::|—)\s*\S'
}

function Test-AdvisoryAiReviewBody {
  param([AllowNull()][string]$Body)
  if ([string]::IsNullOrWhiteSpace($Body)) { return $false }
  if ($Body -match '(?im)!\[P2\s+Badge\]') { return $true }
  if ($Body -match '(?im)^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?(?:\*\*)?\[P2\](?:\*\*)?\s*\S') { return $true }
  return $Body -match '(?im)^\s*(?:[-*]\s*)?(?:#{1,6}\s*)?(?:\*\*)?P2\b[^\r\n]{0,120}?(?:\*\*)?\s*(?::|—)\s*\S'
}

function Test-AdvisoryOnlyAiReviewBody {
  param([AllowNull()][string]$Body)
  return (Test-AdvisoryAiReviewBody $Body) -and -not (Test-BlockingAiReviewBody $Body)
}

function Test-BlockingAiReviewEvidence {
  # A CHANGES_REQUESTED review with no P0-P2 classification fails closed;
  # a P2-only classification is advisory and never blocks the merge lane.
  param([AllowNull()][string]$Body,[string]$ReviewState = '')
  if ($ReviewState -eq 'CHANGES_REQUESTED') {
    if (Test-BlockingAiReviewBody $Body) { return $true }
    return -not (Test-AdvisoryOnlyAiReviewBody $Body)
  }
  return Test-BlockingAiReviewBody $Body
}

function Test-AiReviewPassingConclusion {
  param([AllowNull()][string]$Conclusion)
  return $Conclusion -in @('success','neutral')
}

function Get-TrustedAiReviewAdvisoryIssueNumber {
  param(
    [object[]]$Comments = @(),
    [Parameter(Mandatory)][string]$HeadSha,
    [Parameter(Mandatory)][string]$OwnerLogin
  )
  $pattern = "<!-- ai-review-advisory:$([regex]::Escape($HeadSha)):([0-9]+) -->"
  $maps = @($Comments | Where-Object {
    (Test-TrustedAutomationComment -Comment $_ -OwnerLogin $OwnerLogin) -and
    [string]$_.body -match $pattern
  } | Sort-Object created_at)
  if ($maps.Count -eq 0) { return $null }
  [string]$maps[-1].body -match $pattern | Out-Null
  return [int]$Matches[1]
}

function Test-TrustedAutomationComment {
  param([Parameter(Mandatory)]$Comment,[Parameter(Mandatory)][string]$OwnerLogin)
  return [string]$Comment.user.login -in @('github-actions[bot]', $OwnerLogin)
}

function Get-TrustedStructuredCopilotReview {
  param(
    [object[]]$Comments = @(),
    [Parameter(Mandatory)][string]$HeadSha,
    [Parameter(Mandatory)][string]$OwnerLogin
  )

  $requests = @($Comments | Where-Object {
    (Test-TrustedAutomationComment -Comment $_ -OwnerLogin $OwnerLogin) -and
    [string]$_.body -like "*ai-review-request:copilot:$HeadSha*"
  } | Sort-Object created_at)
  if ($requests.Count -eq 0) { return $null }

  $requestTime = [datetimeoffset]$requests[-1].created_at
  $responses = @($Comments | Where-Object {
    (Get-MachineReviewProvider -Login ([string]$_.user.login)) -eq 'copilot' -and
    [string]$_.body -match '(?im)^\s*AI-REVIEW\s+(PASS|FAIL)\b' -and
    [string]$_.body -match [regex]::Escape($HeadSha) -and
    ([datetimeoffset]$_.created_at) -ge $requestTime
  } | Sort-Object created_at)
  if ($responses.Count -eq 0) { return $null }
  return $responses[-1]
}

function Get-ReviewRepairDecision {
  param(
    [Parameter(Mandatory)][string]$HeadSha,
    [string[]]$AttemptedHeadShas = @(),
    [Parameter(Mandatory)][int]$MaxAttempts,
    [Parameter(Mandatory)][bool]$HasBlockingFindings
  )

  if ($MaxAttempts -lt 1) { throw 'MaxAttempts must be at least 1.' }
  if (-not $HasBlockingFindings) { return 'none' }
  $attempted = @($AttemptedHeadShas | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -Unique)
  if ($attempted -contains $HeadSha) { return 'pending' }
  if ($attempted.Count -ge $MaxAttempts) { return 'block' }
  return 'request'
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
    '^scripts/(apply-github-standard|setup-portfolio|doctor|auto-merge|gate-result-router|request-machine-review|request-review-repair|evaluate-ai-review|reconcile-machine-review-threads|pause-pending-review|pr-orchestrator|upgrade-repos|bootstrap-repo)\.ps1$',
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
