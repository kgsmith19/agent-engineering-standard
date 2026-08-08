$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\scripts\lib\review-policy.ps1')

function Assert-Equal {
  param([string]$Name, $Actual, $Expected)
  if ($Actual -cne $Expected) { throw "$Name failed: expected '$Expected', got '$Actual'." }
}

function Assert-Throws {
  param([string]$Name, [scriptblock]$Action)
  try { & $Action | Out-Null } catch { return }
  throw "$Name failed: expected an exception."
}

Assert-Equal 'Claude implementation routes to Codex' (Get-PreferredIndependentReviewer -Implementer claude) 'codex'
Assert-Equal 'Copilot implementation routes to Codex' (Get-PreferredIndependentReviewer -Implementer copilot) 'codex'
Assert-Equal 'Codex implementation routes to Copilot' (Get-PreferredIndependentReviewer -Implementer codex) 'copilot'
Assert-Throws 'Codex without Copilot is blocked instead of pretending Claude is connected' {
  Get-PreferredIndependentReviewer -Implementer codex -CopilotAvailable $false
}
Assert-Throws 'Codex cannot review Codex when it is the only provider' {
  Get-PreferredIndependentReviewer -Implementer codex -CopilotAvailable $false -CodexAvailable $true
}

Assert-Equal 'Codex bot login recognized' (Get-ReviewProviderFromLogin -Login 'chatgpt-codex-connector[bot]') 'codex'
Assert-Equal 'Copilot bot login recognized' (Get-ReviewProviderFromLogin -Login 'copilot-pull-request-reviewer[bot]') 'copilot'
Assert-Equal 'unknown reviewer ignored' (Get-ReviewProviderFromLogin -Login 'random-bot[bot]') $null
Assert-Equal 'different provider is independent' (Test-IndependentReview -Implementer claude -ReviewerProvider codex) $true
Assert-Equal 'same provider is not independent' (Test-IndependentReview -Implementer codex -ReviewerProvider codex) $false
Assert-Equal 'human implementation accepts an AI reviewer' (Test-IndependentReview -Implementer human -ReviewerProvider codex) $true

$validGate = [pscustomobject]@{
  failure_class_prevented = 'irreversible production data loss'
  why_automation_is_insufficient = 'the intent to destroy cannot be inferred from repository state'
  decision_owner = 'authorized human owner'
  gate_removal_condition = 'operation becomes reversible with independently verified restore'
}
Assert-Equal 'complete manual gate justification accepted' (Assert-ManualGateJustification -Justification $validGate) $true
Assert-Throws 'manual gate missing removal condition is refused' {
  Assert-ManualGateJustification -Justification ([pscustomobject]@{
    failure_class_prevented = 'x'
    why_automation_is_insufficient = 'y'
    decision_owner = 'z'
  })
}

Write-Host 'review-policy tests: PASS' -ForegroundColor Green
