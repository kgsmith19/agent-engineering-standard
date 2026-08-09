$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $root 'scripts/lib/review-policy.ps1')

function Assert-Equal {
  param([string]$Name,$Actual,$Expected)
  if ($Actual -cne $Expected) { throw "$Name failed: expected '$Expected', got '$Actual'." }
}
function Assert-Throws {
  param([string]$Name,[scriptblock]$Action)
  try { & $Action | Out-Null } catch { return }
  throw "$Name failed: expected an exception."
}

Assert-Equal 'Codex bot login recognized' (Get-MachineReviewProvider 'chatgpt-codex-connector[bot]') 'codex'
Assert-Equal 'Codex mention login recognized' (Get-MachineReviewProvider 'codex') 'codex'
Assert-Equal 'Copilot review bot recognized' (Get-MachineReviewProvider 'copilot-pull-request-reviewer[bot]') 'copilot'
Assert-Equal 'Copilot coding agent recognized' (Get-MachineReviewProvider 'copilot-swe-agent[bot]') 'copilot'
Assert-Equal 'Unknown reviewer ignored' (Get-MachineReviewProvider 'random-bot[bot]') $null

Assert-Equal 'Unknown human head has no machine implementer' (Get-HeadImplementerProvider -HeadAuthorLogin 'kgsmith19') $null
Assert-Equal 'Latest Copilot commit is detected' (Get-HeadImplementerProvider -HeadAuthorLogin 'Copilot') 'copilot'
Assert-Equal 'Latest Codex commit is detected' (Get-HeadImplementerProvider -HeadCommitterLogin 'chatgpt-codex-connector[bot]') 'codex'
Assert-Equal 'Mixed machine head records both actors' (Get-HeadImplementerProvider -HeadAuthorLogin 'chatgpt-codex-connector[bot]' -HeadCommitterLogin 'Copilot') 'codex+copilot'

Assert-Equal 'Human or unknown head prefers Codex' (Get-PreferredMachineReviewer -HeadAuthorLogin 'kgsmith19') 'codex'
Assert-Equal 'Copilot-implemented head requires Codex' (Get-PreferredMachineReviewer -HeadAuthorLogin 'Copilot') 'codex'
Assert-Equal 'Codex-implemented head requires Copilot' (Get-PreferredMachineReviewer -HeadAuthorLogin 'chatgpt-codex-connector[bot]') 'copilot'
Assert-Throws 'Mixed Codex and Copilot head has no independent connected reviewer' {
  Get-PreferredMachineReviewer -HeadAuthorLogin 'chatgpt-codex-connector[bot]' -HeadCommitterLogin 'Copilot'
}

$copilotAccepted = @(Get-AcceptedMachineReviewProviders -HeadAuthorLogin 'Copilot')
Assert-Equal 'Copilot head has one accepted reviewer' $copilotAccepted.Count 1
Assert-Equal 'Copilot head accepts Codex only' $copilotAccepted[0] 'codex'
$codexAccepted = @(Get-AcceptedMachineReviewProviders -HeadAuthorLogin 'chatgpt-codex-connector[bot]')
Assert-Equal 'Codex head accepts Copilot only' $codexAccepted[0] 'copilot'
$humanAccepted = @(Get-AcceptedMachineReviewProviders -HeadAuthorLogin 'kgsmith19')
Assert-Equal 'Unknown human head allows bounded fallback' $humanAccepted.Count 2
Assert-Equal 'Unknown human head starts with Codex' $humanAccepted[0] 'codex'
Assert-Equal 'Unknown human head allows Copilot fallback' $humanAccepted[1] 'copilot'
$mixedAccepted = @(Get-AcceptedMachineReviewProviders -HeadAuthorLogin 'chatgpt-codex-connector[bot]' -HeadCommitterLogin 'Copilot')
Assert-Equal 'Mixed machine head accepts no connected reviewer' $mixedAccepted.Count 0

Assert-Equal 'Structured AI review failure is material' (Test-MaterialAiReviewBody 'AI-REVIEW FAIL — sha') $true
Assert-Equal 'P1 heading is material' (Test-MaterialAiReviewBody '## P1 — unsafe bypass') $true
Assert-Equal 'P2 bullet is material' (Test-MaterialAiReviewBody '- **P2: missing pagination') $true
Assert-Equal 'P1 badge is material' (Test-MaterialAiReviewBody '![P1 Badge](badge.svg)') $true
Assert-Equal 'Bracketed P1 title is material' (Test-MaterialAiReviewBody '[P1] unsafe bypass') $true
Assert-Equal 'Bracketed markdown P2 bullet is material' (Test-MaterialAiReviewBody '- **[P2] missing pagination**') $true
Assert-Equal 'No-findings prose is not material' (Test-MaterialAiReviewBody 'No P0-P2 findings. Everything is clean.') $false
Assert-Equal 'Ordinary review prose is not material' (Test-MaterialAiReviewBody 'Looks good; no material issues found.') $false

Assert-Equal 'No risk label defaults to R2' (Get-RiskFromLabels @()) 'R2'
Assert-Equal 'Single risk label is parsed' (Get-RiskFromLabels @('risk:R3','status:ready')) 'R3'
Assert-Throws 'Multiple risk labels fail closed' { Get-RiskFromLabels @('risk:R1','risk:R3') }

Assert-Equal 'Workflow is control plane' (Test-ControlPlanePath '.github/workflows/pr-gate.yml') $true
Assert-Equal 'Evaluator is control plane' (Test-ControlPlanePath 'scripts/evaluate-ai-review.ps1') $true
Assert-Equal 'Review repair is control plane' (Test-ControlPlanePath 'scripts/request-review-repair.ps1') $true
Assert-Equal 'Thread reconciler is control plane' (Test-ControlPlanePath 'scripts/reconcile-machine-review-threads.ps1') $true
Assert-Equal 'Ordinary product source is not control plane' (Test-ControlPlanePath 'src/feature.ts') $false

$validGate = [pscustomobject]@{
  failure_class_prevented = 'irreversible production data loss'
  why_automation_is_insufficient = 'intent cannot be inferred from repository state'
  decision_owner = 'authorized human owner'
  gate_removal_condition = 'operation becomes reversible with verified restore'
}
Assert-Equal 'Complete manual gate accepted' (Assert-ManualGateJustification $validGate) $true
Assert-Throws 'Incomplete manual gate refused' {
  Assert-ManualGateJustification ([pscustomobject]@{
    failure_class_prevented = 'x'
    why_automation_is_insufficient = 'y'
    decision_owner = 'z'
  })
}

$bootstrap = Get-Content (Join-Path $root 'scripts/bootstrap-repo.ps1') -Raw
if ($bootstrap -notmatch 'templates/AI_REVIEW\.yml') { throw 'bootstrap must source AI_REVIEW template.' }
if ($bootstrap -notmatch 'templates/PR_AUTOMATION\.yml') { throw 'bootstrap must source PR_AUTOMATION template.' }
if ($bootstrap -match 'templates/CODEOWNERS|Copy-Item[^\r\n]*CODEOWNERS') { throw 'bootstrap must not install native human CODEOWNERS.' }
if ($bootstrap -notmatch 'Remove-Item[^\r\n]*\.github/CODEOWNERS') { throw 'bootstrap must remove legacy native CODEOWNERS.' }

Write-Host 'review-policy tests: PASS' -ForegroundColor Green
