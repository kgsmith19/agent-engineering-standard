param(
  [Parameter(Mandatory)][ValidateSet('pr-event','gate-result','review-event','comment-event','watchdog')][string]$Mode,
  [Parameter(Mandatory)][string]$Repo,
  [int]$Pr = 0,
  [string]$GateConclusion = '',
  [string]$GateHeadSha = '',
  [long]$GateRunId = 0,
  [string]$ConfigPath = (Join-Path $PSScriptRoot '..\policy\github-defaults.json')
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'lib/review-policy.ps1')

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required.' }
$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$automation = $config.pr_automation
$reviewPolicy = $config.independent_review

function Get-Paged {
  param([Parameter(Mandatory)][string]$Endpoint)
  $raw = & gh api --paginate --slurp $Endpoint 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $pages = ($raw -join "`n") | ConvertFrom-Json
  foreach ($page in @($pages)) { foreach ($item in @($page)) { $item } }
}

function Get-Pr {
  param([Parameter(Mandatory)][int]$Number)
  $raw = & gh pr view $Number --repo $Repo --json number,state,isDraft,labels,headRefOid,headRefName,baseRefName,author,autoMergeRequest,mergeable,mergeStateStatus,title,updatedAt 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  return (($raw -join "`n") | ConvertFrom-Json)
}

function Get-Comments {
  param([Parameter(Mandatory)][int]$Number)
  return @(Get-Paged "repos/$Repo/issues/$Number/comments?per_page=100")
}

function Get-ChangedFiles {
  param([Parameter(Mandatory)][int]$Number)
  $raw = & gh api --paginate "repos/$Repo/pulls/$Number/files?per_page=100" --jq '.[].filename' 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  return @($raw | Where-Object { $_ })
}

function Add-CommentOnce {
  param([int]$Number,[string]$Marker,[string]$Body)
  $comments = @(Get-Comments $Number)
  if (@($comments | Where-Object { [string]$_.body -like "*$Marker*" }).Count -gt 0) { return $false }
  & gh pr comment $Number --repo $Repo --body "$Body`n`n$Marker" | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Could not comment on $Repo PR #$Number." }
  return $true
}

function Add-Blocked {
  param([int]$Number,[string]$Reason)
  & gh pr edit $Number --repo $Repo --add-label $automation.blocked_label 2>&1 | Out-Null
  $marker = '<!-- pr-automation:blocked -->'
  Add-CommentOnce -Number $Number -Marker $marker -Body "AUTOMATION-BLOCKED: $Reason`nNo human reviewer was assigned. Resolve the stated blocker or explicitly reset the bounded automation budget." | Out-Null
}

function Disable-AutoMerge {
  param([int]$Number,$PrData)
  if ($PrData.autoMergeRequest) {
    $raw = & gh pr merge $Number --repo $Repo --disable-auto 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Could not disable auto-merge for $Repo PR #$Number. $($raw -join ' ')" }
    Write-Host "Auto-merge disabled: $Repo PR #$Number" -ForegroundColor Yellow
  }
}

function Get-PrRisk {
  param($PrData)
  $labels = @($PrData.labels | ForEach-Object { $_.name })
  return Get-RiskFromLabels -Labels $labels
}

function Test-IsControlPlane {
  param([int]$Number)
  if ($Repo -match '/agent-engineering-standard$') { return $true }
  foreach ($file in @(Get-ChangedFiles $Number)) { if (Test-ControlPlanePath -Path $file) { return $true } }
  return $false
}

function Test-IsBlocked {
  param($PrData)
  return @($PrData.labels | ForEach-Object { $_.name }) -contains $automation.blocked_label
}

function Test-AutoMergeEligible {
  param([int]$Number,$PrData)
  if ($PrData.state -ne 'OPEN' -or $PrData.isDraft -or (Test-IsBlocked $PrData)) { return $false }
  $risk = Get-PrRisk $PrData
  if ($risk -eq 'R4') { return $false }
  $riskNumber = [int]$risk.Substring(1)
  $maxRisk = [int]([string]$config.auto_merge_max_risk).Substring(1)
  if ($riskNumber -gt $maxRisk) { return $false }
  if ((Test-IsControlPlane $Number) -and [bool]$config.manual_gates.control_plane.required) { return $false }
  return $true
}

function Ensure-AutoMergeState {
  param([int]$Number)
  $prData = Get-Pr $Number
  if ($prData.state -ne 'OPEN') { return }

  $labels = @($prData.labels | ForEach-Object { $_.name })
  if ($prData.isDraft) {
    Disable-AutoMerge -Number $Number -PrData $prData
    if ($labels -contains $automation.draft_ready_label) {
      & gh pr ready $Number --repo $Repo | Out-Host
      if ($LASTEXITCODE -ne 0) { throw "Could not mark $Repo PR #$Number ready." }
      Write-Host "Draft promoted to Ready from '$($automation.draft_ready_label)' label." -ForegroundColor Green
    }
    return
  }

  if ($prData.mergeable -eq 'CONFLICTING') {
    Disable-AutoMerge -Number $Number -PrData $prData
    Request-ConflictFix -Number $Number -PrData $prData
    return
  }

  if (-not (Test-AutoMergeEligible -Number $Number -PrData $prData)) {
    Disable-AutoMerge -Number $Number -PrData $prData
    return
  }

  if (-not $prData.autoMergeRequest) {
    $risk = Get-PrRisk $prData
    & pwsh -NoProfile -File (Join-Path $PSScriptRoot 'auto-merge.ps1') -Repo $Repo -Pr $Number -Risk $risk
    if ($LASTEXITCODE -ne 0) { throw "Could not arm auto-merge for $Repo PR #$Number." }
  }
}

function Get-ReviewState {
  param([int]$Number,$PrData)
  $headSha = [string]$PrData.headRefOid
  $author = [string]$PrData.author.login
  $accepted = if ($author.ToLowerInvariant() -match '^chatgpt-codex-connector(?:\[bot\])?$') { @('copilot') } else { @('codex','copilot') }
  $reviews = @(Get-Paged "repos/$Repo/pulls/$Number/reviews?per_page=100")
  $comments = @(Get-Comments $Number)
  $failures = New-Object System.Collections.Generic.List[string]
  $passes = New-Object System.Collections.Generic.List[string]

  foreach ($review in $reviews) {
    $provider = Get-MachineReviewProvider -Login ([string]$review.user.login)
    if (-not $provider -or $review.commit_id -ne $headSha -or $review.state -in @('DISMISSED','PENDING')) { continue }
    if ($review.state -eq 'CHANGES_REQUESTED' -or (Test-MaterialAiReviewBody -Body ([string]$review.body))) {
      $failures.Add("$provider:$($review.id)")
    } elseif ($accepted -contains $provider) { $passes.Add($provider) }
  }

  $structured = @($comments | Where-Object {
    (Get-MachineReviewProvider -Login ([string]$_.user.login)) -eq 'copilot' -and
    $_.body -match '(?im)^\s*AI-REVIEW\s+(PASS|FAIL)\b' -and $_.body -match [regex]::Escape($headSha)
  } | Sort-Object created_at)
  if ($structured.Count -gt 0) {
    if ($structured[-1].body -match '(?im)^\s*AI-REVIEW\s+FAIL\b') { $failures.Add("copilot-comment:$($structured[-1].id)") }
    elseif ($accepted -contains 'copilot') { $passes.Add('copilot') }
  }

  return [pscustomobject]@{ HeadSha=$headSha; Accepted=$accepted; Passes=@($passes); Failures=@($failures); Comments=$comments }
}

function Request-MachineReview {
  param([int]$Number)
  $prData = Get-Pr $Number
  if ($prData.state -ne 'OPEN' -or $prData.isDraft) { return }
  $state = Get-ReviewState -Number $Number -PrData $prData
  if ($state.Failures.Count -gt 0) { Request-ReviewFix -Number $Number -PrData $prData -ReviewState $state; return }
  if ($state.Passes.Count -gt 0) { return }

  $comments = @($state.Comments)
  $requestedHeads = @{}
  foreach ($comment in $comments) {
    if ([string]$comment.body -match 'ai-review-request:(?:codex|copilot):([0-9a-f]{40})') { $requestedHeads[$Matches[1]] = $true }
  }
  $currentHeadAlreadyRequested = @($comments | Where-Object { [string]$_.body -match "ai-review-request:(?:codex|copilot):$($state.HeadSha)" })
  if ($currentHeadAlreadyRequested.Count -eq 0 -and $requestedHeads.Count -ge [int]$reviewPolicy.max_review_heads_per_pr) {
    Add-Blocked -Number $Number -Reason "Machine-review head budget exhausted ($($reviewPolicy.max_review_heads_per_pr))."
    return
  }

  $preferred = Get-PreferredMachineReviewer -PrAuthorLogin ([string]$prData.author.login)
  $preferredMarker = "<!-- ai-review-request:$preferred:$($state.HeadSha) -->"
  $preferredRequest = @($comments | Where-Object { [string]$_.body -like "*$preferredMarker*" } | Sort-Object created_at | Select-Object -Last 1)

  if ($preferredRequest.Count -eq 0) {
    if ($preferred -eq 'codex') {
      $body = "@codex review`n`nIndependently review the CURRENT PR head only. You are the reviewer, not the implementer. Apply one batched pass: software/security correctness, requirement/spec fit, business/product ROI, systems/operational optimization, and strict leanness/complexity. Report material P0-P2 findings only. Do not modify files during review."
    } else {
      $body = "@copilot Independently review the CURRENT PR head only. Do not modify files. Apply software/security, requirement/spec, business/ROI, systems/optimization, and strict leanness lenses. Report only material P0-P2 findings. Start with AI-REVIEW PASS or AI-REVIEW FAIL and include exact SHA $($state.HeadSha)."
    }
    Add-CommentOnce -Number $Number -Marker $preferredMarker -Body $body | Out-Null
    Write-Host "Requested $preferred machine review for $($state.HeadSha)." -ForegroundColor Green
    return
  }

  if ($preferred -eq 'codex' -and [bool]$reviewPolicy.fallback_provider -and $reviewPolicy.fallback_provider -eq 'copilot') {
    $age = [datetimeoffset]::UtcNow - [datetimeoffset]$preferredRequest[0].created_at
    $fallbackMarker = "<!-- ai-review-request:copilot:$($state.HeadSha) -->"
    if ($age.TotalMinutes -ge [int]$reviewPolicy.review_stall_minutes -and @($comments | Where-Object { [string]$_.body -like "*$fallbackMarker*" }).Count -eq 0) {
      $body = "@copilot Codex review is stalled. Independently review the CURRENT PR head only. Do not modify files. Apply software/security, requirement/spec, business/ROI, systems/optimization, and strict leanness lenses. Report material P0-P2 findings only. Start with AI-REVIEW PASS or AI-REVIEW FAIL and include exact SHA $($state.HeadSha)."
      Add-CommentOnce -Number $Number -Marker $fallbackMarker -Body $body | Out-Null
      Write-Host 'Requested bounded Copilot fallback review.' -ForegroundColor Yellow
    }
  }
}

function Request-CiFix {
  param([int]$Number,[long]$RunId=0,[string]$HeadSha='')
  $comments = @(Get-Comments $Number)
  $attempts = @($comments | Where-Object { [string]$_.body -match '<!-- auto-fix:ci:' }).Count
  if ($attempts -ge [int]$automation.max_ci_fix_attempts) {
    Add-Blocked -Number $Number -Reason "PR Gate repair budget exhausted ($($automation.max_ci_fix_attempts))."
    return
  }
  if (-not $HeadSha) { $HeadSha = [string](Get-Pr $Number).headRefOid }
  $marker = "<!-- auto-fix:ci:$HeadSha:$RunId -->"
  $runText = if ($RunId -gt 0) { "GitHub Actions run $RunId" } else { 'the current failing PR Gate' }
  $body = "@codex investigate and fix $runText on PR #$Number. Read the complete failing check/logs before editing. Follow AGENTS.md and the linked Issue/SPEC. If the root cause is nontrivial or crosses concerns, use a thin plan/spec before implementation. Make the smallest root-cause fix, never weaken tests/policies/evaluators, run the relevant verification, and update this existing PR. This is bounded repair attempt $($attempts + 1)/$($automation.max_ci_fix_attempts)."
  Add-CommentOnce -Number $Number -Marker $marker -Body $body | Out-Null
}

function Request-ReviewFix {
  param([int]$Number,$PrData,$ReviewState)
  $comments = @(Get-Comments $Number)
  $attempts = @($comments | Where-Object { [string]$_.body -match '<!-- auto-fix:review:' }).Count
  if ($attempts -ge [int]$automation.max_review_fix_attempts) {
    Add-Blocked -Number $Number -Reason "Machine-review repair budget exhausted ($($automation.max_review_fix_attempts))."
    return
  }
  $marker = "<!-- auto-fix:review:$($ReviewState.HeadSha):$($attempts + 1) -->"
  $body = "@codex address the material machine-review feedback on the CURRENT head $($ReviewState.HeadSha). Read every current-head review finding before editing. Follow AGENTS.md and the Issue/SPEC. If the change is nontrivial, plan the smallest coherent fix first. Fix valid findings only, explicitly explain false positives, never weaken gates/tests, run relevant verification, and update this existing PR. After the push, CI and a fresh exact-head machine review will run again. Attempt $($attempts + 1)/$($automation.max_review_fix_attempts)."
  Add-CommentOnce -Number $Number -Marker $marker -Body $body | Out-Null
}

function Request-ConflictFix {
  param([int]$Number,$PrData)
  $comments = @(Get-Comments $Number)
  $attempts = @($comments | Where-Object { [string]$_.body -match '<!-- auto-fix:conflict:' }).Count
  if ($attempts -ge [int]$automation.max_conflict_fix_attempts) {
    Add-Blocked -Number $Number -Reason "Merge-conflict repair budget exhausted ($($automation.max_conflict_fix_attempts))."
    return
  }
  $headSha = [string]$PrData.headRefOid
  $marker = "<!-- auto-fix:conflict:$headSha:$($attempts + 1) -->"
  if ([string]$PrData.author.login -eq 'dependabot[bot]') {
    $body = '@dependabot rebase'
  } else {
    $body = "@codex resolve the merge conflict for this PR against the current default branch. Read both sides of every conflict; preserve current-main behavior plus this PR's intended scope. Do not take ours/theirs blindly. Run relevant verification and update this existing PR. Attempt $($attempts + 1)/$($automation.max_conflict_fix_attempts)."
  }
  Add-CommentOnce -Number $Number -Marker $marker -Body $body | Out-Null
}

function Handle-PrEvent {
  param([int]$Number)
  Ensure-AutoMergeState -Number $Number
}

function Handle-GateResult {
  param([int]$Number,[string]$Conclusion,[string]$HeadSha,[long]$RunId)
  $prData = Get-Pr $Number
  if ($prData.state -ne 'OPEN' -or $prData.isDraft) { return }
  if ($HeadSha -and $prData.headRefOid -ne $HeadSha) { Write-Host 'Ignoring stale PR Gate result for older head.'; return }
  Ensure-AutoMergeState -Number $Number
  if ($Conclusion -eq 'success') { Request-MachineReview -Number $Number }
  elseif ($Conclusion -in @('failure','timed_out','cancelled','action_required','startup_failure')) { Request-CiFix -Number $Number -RunId $RunId -HeadSha ([string]$prData.headRefOid) }
}

function Handle-ReviewEvent {
  param([int]$Number)
  $prData = Get-Pr $Number
  if ($prData.state -ne 'OPEN' -or $prData.isDraft) { return }
  $state = Get-ReviewState -Number $Number -PrData $prData
  if ($state.Failures.Count -gt 0) { Request-ReviewFix -Number $Number -PrData $prData -ReviewState $state }
}

function Handle-Watchdog {
  $raw = & gh pr list --repo $Repo --state open --limit 100 --json number 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $prs = @(($raw -join "`n") | ConvertFrom-Json)
  foreach ($item in $prs) {
    $number = [int]$item.number
    try {
      Ensure-AutoMergeState -Number $number
      $prData = Get-Pr $number
      if ($prData.state -ne 'OPEN' -or $prData.isDraft) { continue }
      $checksRaw = & gh pr checks $number --repo $Repo --json name,bucket,state,workflow 2>&1
      if ($checksRaw) {
        try { $checks = @(($checksRaw -join "`n") | ConvertFrom-Json) } catch { $checks = @() }
        $gate = @($checks | Where-Object { $_.name -eq 'PR Gate' } | Select-Object -First 1)
        if ($gate.Count -gt 0 -and $gate[0].bucket -eq 'pass') { Request-MachineReview -Number $number }
        elseif ($gate.Count -gt 0 -and $gate[0].bucket -eq 'fail') { Request-CiFix -Number $number -HeadSha ([string]$prData.headRefOid) }
      }
      $state = Get-ReviewState -Number $number -PrData $prData
      if ($state.Failures.Count -gt 0) { Request-ReviewFix -Number $number -PrData $prData -ReviewState $state }
    }
    catch { Write-Warning "$Repo PR #$number watchdog: $($_.Exception.Message)" }
  }
}

switch ($Mode) {
  'pr-event' { if ($Pr -le 0) { throw 'Pr is required for pr-event.' }; Handle-PrEvent -Number $Pr }
  'gate-result' { if ($Pr -le 0) { throw 'Pr is required for gate-result.' }; Handle-GateResult -Number $Pr -Conclusion $GateConclusion -HeadSha $GateHeadSha -RunId $GateRunId }
  'review-event' { if ($Pr -le 0) { throw 'Pr is required for review-event.' }; Handle-ReviewEvent -Number $Pr }
  'comment-event' { if ($Pr -le 0) { throw 'Pr is required for comment-event.' }; Handle-ReviewEvent -Number $Pr }
  'watchdog' { Handle-Watchdog }
}
