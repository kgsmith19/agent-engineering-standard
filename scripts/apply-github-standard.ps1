param(
  [string]$ConfigPath = (Join-Path $PSScriptRoot "..\policy\github-defaults.json"),
  [string[]]$Repositories
)

$ErrorActionPreference = "Stop"

function Invoke-GhJson {
  param(
    [Parameter(Mandatory)][string]$Method,
    [Parameter(Mandatory)][string]$Endpoint,
    [Parameter(Mandatory)]$Body
  )
  $tmp = [System.IO.Path]::GetTempFileName()
  try {
    $Body | ConvertTo-Json -Depth 20 | Set-Content -Path $tmp -Encoding utf8 -NoNewline
    $output = & gh api --method $Method $Endpoint --input $tmp 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($output -join "`n") }
    return ($output -join "`n")
  }
  finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "GitHub CLI (gh) is required. Install it, then run gh auth login." }
& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw "gh is not authenticated." }

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$owner = $config.owner
$targets = if ($Repositories -and $Repositories.Count -gt 0) { $Repositories } else { @($config.repositories) }

# Bind the required check to GitHub Actions, not just a spoofable context name.
$actionsAppRaw = & gh api /apps/github-actions 2>&1
if ($LASTEXITCODE -ne 0) { throw "Could not resolve the GitHub Actions App identity; refusing to create an unbound required check." }
$actionsAppId = [int]((($actionsAppRaw -join "`n") | ConvertFrom-Json).id)

$labels = @(
  @{ name = 'risk:R0'; color = 'D4C5F9'; description = 'non-behavioral/trivial' },
  @{ name = 'risk:R1'; color = '5DADE2'; description = 'local, reversible behavior' },
  @{ name = 'risk:R2'; color = 'F1C40F'; description = 'normal product/API change' },
  @{ name = 'risk:R3'; color = 'E67E22'; description = 'sensitive/control-plane boundary' },
  @{ name = 'risk:R4'; color = 'C0392B'; description = 'destructive/financial/privileged/irreversible' },
  @{ name = 'status:ready'; color = '0E8A16'; description = 'ready for autonomous execution/review' },
  @{ name = 'status:blocked'; color = 'B60205'; description = 'blocked on a real dependency/decision' }
)

foreach ($name in $targets) {
  $repo = if ($name -match "/") { $name } else { "$owner/$name" }
  Write-Host "`n=== $repo ===" -ForegroundColor Cyan

  $metaRaw = & gh api "repos/$repo" 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Warning "Cannot read $repo; skipping. $($metaRaw -join ' ')"; continue }
  $meta = ($metaRaw -join "`n") | ConvertFrom-Json

  $settings = @{
    has_issues               = $true
    allow_auto_merge         = [bool]$config.allow_auto_merge
    delete_branch_on_merge   = [bool]$config.delete_branch_on_merge
    allow_merge_commit       = [bool]$config.allow_merge_commit
    allow_rebase_merge       = [bool]$config.allow_rebase_merge
    allow_squash_merge       = [bool]$config.allow_squash_merge
  }
  Invoke-GhJson -Method PATCH -Endpoint "repos/$repo" -Body $settings | Out-Null
  Write-Host "repo settings: Issues/auto-merge/squash/delete-branch configured"

  $actionsSettings = @{ enabled = $true; allowed_actions = "all"; sha_pinning_required = $false }
  Invoke-GhJson -Method PUT -Endpoint "repos/$repo/actions/permissions" -Body $actionsSettings | Out-Null
  Write-Host "actions: enabled"

  foreach ($label in $labels) {
    & gh label create $label.name --repo $repo --color $label.color --description $label.description --force 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Warning "Could not create/update label $($label.name) in $repo" }
  }
  Write-Host "labels: risk/status baseline configured"

  $rules = @(
    @{ type = "deletion" },
    @{ type = "non_fast_forward" },
    @{
      type = "pull_request"
      parameters = @{
        allowed_merge_methods             = @("squash")
        dismiss_stale_reviews_on_push     = $false
        require_code_owner_review         = [bool]$config.require_code_owner_review
        require_last_push_approval        = $false
        required_approving_review_count   = [int]$config.required_approving_review_count
        required_review_thread_resolution = [bool]$config.required_review_thread_resolution
      }
    },
    @{
      type = "required_status_checks"
      parameters = @{
        do_not_enforce_on_create             = $true
        strict_required_status_checks_policy = [bool]$config.strict_required_status_checks_policy
        required_status_checks = @(
          @{ context = $config.required_status_context; integration_id = $actionsAppId }
        )
      }
    }
  )

  $queueWanted = [bool]$config.merge_queue.desired
  $queueEligibleOwner = $meta.owner.type -eq "Organization"
  if ($queueWanted -and $queueEligibleOwner) {
    $rules += @{
      type = "merge_queue"
      parameters = @{
        check_response_timeout_minutes    = [int]$config.merge_queue.check_response_timeout_minutes
        grouping_strategy                 = $config.merge_queue.grouping_strategy
        max_entries_to_build              = [int]$config.merge_queue.max_entries_to_build
        max_entries_to_merge              = [int]$config.merge_queue.max_entries_to_merge
        merge_method                      = "SQUASH"
        min_entries_to_merge              = [int]$config.merge_queue.min_entries_to_merge
        min_entries_to_merge_wait_minutes = [int]$config.merge_queue.min_entries_to_merge_wait_minutes
      }
    }
  }

  $payload = @{
    name = $config.ruleset_name
    target = "branch"
    enforcement = "active"
    bypass_actors = @()
    conditions = @{ ref_name = @{ include = @("~DEFAULT_BRANCH"); exclude = @() } }
    rules = $rules
  }

  $existingRaw = & gh api "repos/$repo/rulesets" 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Warning "Cannot inspect rulesets for $repo; repo settings and Actions were still applied."; continue }
  $existing = (($existingRaw -join "`n") | ConvertFrom-Json) | Where-Object { $_.name -eq $config.ruleset_name } | Select-Object -First 1

  try {
    if ($existing) {
      Invoke-GhJson -Method PUT -Endpoint "repos/$repo/rulesets/$($existing.id)" -Body $payload | Out-Null
      Write-Host "ruleset: updated $($config.ruleset_name)"
    }
    else {
      Invoke-GhJson -Method POST -Endpoint "repos/$repo/rulesets" -Body $payload | Out-Null
      Write-Host "ruleset: created $($config.ruleset_name)"
    }
    if ($queueWanted -and $queueEligibleOwner) { Write-Host "merge queue: requested" }
    elseif ($queueWanted) { Write-Host "merge queue: queue-ready only; GitHub does not support merge queues on user-owned repos" -ForegroundColor Yellow }
  }
  catch {
    if ($queueWanted -and $queueEligibleOwner) {
      Write-Warning "Merge-queue ruleset application failed; retrying without merge_queue. Reason: $($_.Exception.Message)"
      $payload.rules = @($payload.rules | Where-Object { $_.type -ne "merge_queue" })
      if ($existing) { Invoke-GhJson -Method PUT -Endpoint "repos/$repo/rulesets/$($existing.id)" -Body $payload | Out-Null }
      else { Invoke-GhJson -Method POST -Endpoint "repos/$repo/rulesets" -Body $payload | Out-Null }
      Write-Host "ruleset: applied without queue; retry after organization transfer/plan eligibility" -ForegroundColor Yellow
    }
    else { throw }
  }
}

Write-Host "`nDone. Re-run after moving eligible repos into a supported GitHub organization to add merge queues automatically." -ForegroundColor Green
