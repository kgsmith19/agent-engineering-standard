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

Assert-Equal 'Codex bot login recognized' (Get-MachineReviewProvider -Login 'chatgpt-codex-connector[bot]') 'codex'
Assert-Equal 'Copilot review bot recognized' (Get-MachineReviewProvider -Login 'copilot-pull-request-reviewer[bot]') 'copilot'
Assert-Equal 'Copilot coding agent recognized' (Get-MachineReviewProvider -Login 'copilot-swe-agent[bot]') 'copilot'
Assert-Equal 'Unknown reviewer ignored' (Get-MachineReviewProvider -Login 'random-bot[bot]') $null

Assert-Equal 'Normal PR prefers fresh Codex review task' (Get-PreferredMachineReviewer -PrAuthorLogin 'kgsmith19') 'codex'
Assert-Equal 'Copilot-authored PR prefers Codex' (Get-PreferredMachineReviewer -PrAuthorLogin 'Copilot') 'codex'
Assert-Equal 'Codex-app-authored PR requires Copilot' (Get-PreferredMachineReviewer -PrAuthorLogin 'chatgpt-codex-connector[bot]') 'copilot'

Assert-Equal 'Structured AI review failure is material' (Test-MaterialAiReviewBody -Body 'AI-REVIEW FAIL — sha') $true
Assert-Equal 'P1 heading is material' (Test-MaterialAiReviewBody -Body '## P1 — unsafe bypass') $true
Assert-Equal 'P2 bullet is material' (Test-MaterialAiReviewBody -Body '- **P2: missing pagination') $true
Assert-Equal 'P1 badge is material' (Test-MaterialAiReviewBody -Body '![P1 Badge](badge.svg)') $true
Assert-Equal 'No-findings prose is not material' (Test-MaterialAiReviewBody -Body 'No P0-P2 findings. Everything is clean.') $false
Assert-Equal 'Ordinary review prose is not material' (Test-MaterialAiReviewBody -Body 'Looks good; no material issues found.') $false

Assert-Equal 'No risk label defaults to R2' (Get-RiskFromLabels -Labels @()) 'R2'
Assert-Equal 'Single risk label is parsed' (Get-RiskFromLabels -Labels @('risk:R3','status:ready')) 'R3'
Assert-Throws 'Multiple risk labels fail closed' { Get-RiskFromLabels -Labels @('risk:R1','risk:R3') }

Assert-Equal 'Workflow is control plane' (Test-ControlPlanePath -Path '.github/workflows/pr-gate.yml') $true
Assert-Equal 'Evaluator is control plane' (Test-ControlPlanePath -Path 'scripts/evaluate-ai-review.ps1') $true
Assert-Equal 'Ordinary product source is not control plane' (Test-ControlPlanePath -Path 'src/feature.ts') $false

$validGate = [pscustomobject]@{
  failure_class_prevented = 'irreversible production data loss'
  why_automation_is_insufficient = 'intent cannot be inferred from repository state'
  decision_owner = 'authorized human owner'
  gate_removal_condition = 'operation becomes reversible with verified restore'
}
Assert-Equal 'Complete manual gate accepted' (Assert-ManualGateJustification -Justification $validGate) $true
Assert-Throws 'Incomplete manual gate refused' {
  Assert-ManualGateJustification -Justification ([pscustomobject]@{
    failure_class_prevented = 'x'
    why_automation_is_insufficient = 'y'
    decision_owner = 'z'
  })
}

$bootstrap = Get-Content (Join-Path $root 'scripts/bootstrap-repo.ps1') -Raw
if ($bootstrap -notmatch 'templates/AI_REVIEW\.yml') { throw 'bootstrap must source AI_REVIEW template.' }
if ($bootstrap -notmatch 'templates/PR_AUTOMATION\.yml') { throw 'bootstrap must source PR_AUTOMATION template.' }
if ($bootstrap -match 'templates/CODEOWNERS|\.github/CODEOWNERS') { throw 'bootstrap must not install native human CODEOWNERS.' }

Write-Host 'review-policy tests: PASS' -ForegroundColor Green
