$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $root 'scripts/lib/review-policy.ps1')

function Assert-Equal {
  param([string]$Name, $Actual, $Expected)
  if ($Actual -cne $Expected) { throw "$Name failed: expected '$Expected', got '$Actual'." }
}

function Assert-Throws {
  param([string]$Name, [scriptblock]$Action)
  try { & $Action | Out-Null } catch { return }
  throw "$Name failed: expected an exception."
}

Assert-Throws 'review routing requires an explicit implementer' { Get-PreferredIndependentReviewer }
Assert-Equal 'ChatGPT implementation routes to Copilot' (Get-PreferredIndependentReviewer -Implementer chatgpt) 'copilot'
Assert-Equal 'Claude implementation routes to Codex' (Get-PreferredIndependentReviewer -Implementer claude) 'codex'
Assert-Equal 'Copilot implementation routes to Codex' (Get-PreferredIndependentReviewer -Implementer copilot) 'codex'
Assert-Equal 'Codex implementation routes to Copilot' (Get-PreferredIndependentReviewer -Implementer codex) 'copilot'
Assert-Equal 'Unknown provenance starts with Codex' (Get-PreferredIndependentReviewer -Implementer unknown) 'codex'
Assert-Equal 'Human/user-authored provenance starts with Codex' (Get-PreferredIndependentReviewer -Implementer human) 'codex'
Assert-Throws 'Codex without Copilot is blocked instead of pretending Claude is connected' { Get-PreferredIndependentReviewer -Implementer codex -CopilotAvailable $false }
Assert-Throws 'Unknown provenance never skips unavailable Codex to spend Copilot early' { Get-PreferredIndependentReviewer -Implementer unknown -CodexAvailable $false -CopilotAvailable $true }

$unknownProviders = @(Get-RequiredReviewProviders -Implementer unknown)
Assert-Equal 'Unknown provenance requires two providers' $unknownProviders.Count 2
Assert-Equal 'Unknown first provider is Codex' $unknownProviders[0] 'codex'
Assert-Equal 'Unknown second provider is Copilot' $unknownProviders[1] 'copilot'
Assert-Equal 'ChatGPT requires Copilot specifically' (@(Get-RequiredReviewProviders -Implementer chatgpt)[0]) 'copilot'
Assert-Equal 'Unknown with no passes requires Codex next' (Get-NextRequiredReviewProvider -RequiredProviders $unknownProviders) 'codex'
Assert-Equal 'Unknown after Codex pass requires Copilot next' (Get-NextRequiredReviewProvider -RequiredProviders $unknownProviders -PassedProviders @('codex')) 'copilot'
Assert-Equal 'Unknown after both passes needs no provider' (Get-NextRequiredReviewProvider -RequiredProviders $unknownProviders -PassedProviders @('codex','copilot')) $null

Assert-Equal 'Codex bot login recognized' (Get-ReviewProviderFromLogin -Login 'chatgpt-codex-connector[bot]') 'codex'
Assert-Equal 'Copilot bot login recognized' (Get-ReviewProviderFromLogin -Login 'copilot-pull-request-reviewer[bot]') 'copilot'
Assert-Equal 'Copilot coding-agent login recognized' (Get-ReviewProviderFromLogin -Login 'copilot-swe-agent[bot]') 'copilot'
Assert-Equal 'unknown reviewer ignored' (Get-ReviewProviderFromLogin -Login 'random-bot[bot]') $null
Assert-Equal 'Claude-Codex pair is valid' (Test-IndependentReview -Implementer claude -ReviewerProvider codex) $true
Assert-Equal 'Codex-Codex pair is invalid' (Test-IndependentReview -Implementer codex -ReviewerProvider codex) $false
Assert-Equal 'ChatGPT-Codex is not accepted as cross-provider' (Test-IndependentReview -Implementer chatgpt -ReviewerProvider codex) $false
Assert-Equal 'ChatGPT-Copilot is cross-provider' (Test-IndependentReview -Implementer chatgpt -ReviewerProvider copilot) $true

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

$bootstrap = Get-Content (Join-Path $root 'scripts/bootstrap-repo.ps1') -Raw
if ($bootstrap -notmatch "templates/AI_REVIEW\.yml") { throw 'bootstrap-repo.ps1 must source templates/AI_REVIEW.yml.' }
if ($bootstrap -notmatch "\.github/workflows/ai-review\.yml") { throw 'bootstrap-repo.ps1 must install .github/workflows/ai-review.yml before applying the ruleset.' }

Write-Host 'review-policy tests: PASS' -ForegroundColor Green
