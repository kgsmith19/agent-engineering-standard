param(
  [string]$ConfigPath = (Join-Path $PSScriptRoot '..\policy\github-defaults.json'),
  [string[]]$Repositories
)

$ErrorActionPreference = 'Stop'

function Invoke-GhJson {
  param([string]$Method,[string]$Endpoint,$Body)
  $tmp = [System.IO.Path]::GetTempFileName()
  try {
    $Body | ConvertTo-Json -Depth 20 | Set-Content $tmp -Encoding utf8 -NoNewline
    $raw = & gh api --method $Method $Endpoint --input $tmp 2>&1
    if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
    return ($raw -join "`n")
  } finally { Remove-Item $tmp -Force -ErrorAction SilentlyContinue }
}

function Get-Paged {
  param([string]$Endpoint)
  $raw = & gh api --paginate --slurp $Endpoint 2>&1
  if ($LASTEXITCODE -ne 0) { throw ($raw -join "`n") }
  $pages = ($raw -join "`n") | ConvertFrom-Json
  foreach ($page in @($pages)) { foreach ($item in @($page)) { $item } }
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw 'GitHub CLI (gh) is required. Install it, then run gh auth login.' }
& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'gh is not authenticated.' }

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$owner = $config.owner
$targets = if ($Repositories -and $Repositories.Count -gt 0) { $Repositories } else { @($config.repositories) }
$actionsAppRaw = & gh api /apps/github-actions 2>&1
if ($LASTEXITCODE -ne 0) { throw 'Could not resolve the GitHub Actions App identity.' }
$actionsAppId = [int]((($actionsAppRaw -join "`n") | ConvertFrom-Json).id)

$labels = @(
  @{ name='risk:R0'; color='D4C5F9'; description='non-behavioral/trivial' },
  @{ name='risk:R1'; color='5DADE2'; description='local, reversible behavior' },
  @{ name='risk:R2'; color='F1C40F'; description='normal product/API change' },
  @{ name='risk:R3'; color='E67E22'; description='sensitive/control-plane boundary' },
  @{ name='risk:R4'; color='C0392B'; description='destructive/financial/privileged/irreversible' },
  @{ name='status:ready'; color='0E8A16'; description='promote a coherent draft into the automated merge lane' },
  @{ name='status:blocked'; color='B60205'; description='bounded automation stopped on a real dependency/decision' }
)

foreach ($name in $targets) {
  $repo = if ($name -match '/') { $name } else { "$owner/$name" }
  Write-Host "`n=== $repo ===" -ForegroundColor Cyan

  $metaRaw = & gh api "repos/$repo" 2>&1
  if ($LASTEXITCODE -ne 0) { Write-Warning "Cannot read $repo; skipping. $($metaRaw -join ' ')"; continue }
  $meta = ($metaRaw -join "`n") | ConvertFrom-Json

  Invoke-GhJson PATCH "repos/$repo" @{
    has_issues = $true
    allow_auto_merge = [bool]$config.allow_auto_merge
    allow_update_branch = [bool]$config.allow_update_branch
    delete_branch_on_merge = [bool]$config.delete_branch_on_merge
    allow_merge_commit = [bool]$config.allow_merge_commit
    allow_rebase_merge = [bool]$config.allow_rebase_merge
    allow_squash_merge = [bool]$config.allow_squash_merge
  } | Out-Null

  Invoke-GhJson PUT "repos/$repo/actions/permissions" @{
    enabled = $true
    allowed_actions = 'all'
    sha_pinning_required = $false
  } | Out-Null
  Invoke-GhJson PUT "repos/$repo/actions/permissions/workflow" @{
    default_workflow_permissions = 'read'
    can_approve_pull_request_reviews = $false
  } | Out-Null

  foreach ($label in $labels) {
    & gh label create $label.name --repo $repo --color $label.color --description $label.description --force 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Warning "Could not create/update label $($label.name) in $repo" }
  }

  $requiredChecks = @(@{ context=$config.required_status_context; integration_id=$actionsAppId })
  if ([bool]$config.independent_review.required_for_auto_merge) {
    $requiredChecks += @{ context=$config.required_ai_review_context; integration_id=$actionsAppId }
  }
  $rules = @(
    @{ type='deletion' },
    @{ type='non_fast_forward' },
    @{
      type='pull_request'
      parameters=@{
        allowed_merge_methods=@('squash')
        dismiss_stale_reviews_on_push=$true
        require_code_owner_review=$false
        require_last_push_approval=$false
        required_approving_review_count=0
        required_review_thread_resolution=[bool]$config.required_review_thread_resolution
      }
    },
    @{
      type='required_status_checks'
      parameters=@{
        do_not_enforce_on_create=$true
        strict_required_status_checks_policy=[bool]$config.strict_required_status_checks_policy
        required_status_checks=$requiredChecks
      }
    }
  )

  $payload = @{
    name=$config.ruleset_name
    target='branch'
    enforcement='active'
    bypass_actors=@()
    conditions=@{ ref_name=@{ include=@('~DEFAULT_BRANCH'); exclude=@() } }
    rules=$rules
  }

  $existingRulesets = @(Get-Paged "repos/$repo/rulesets?per_page=100")
  $existing = ($existingRulesets | Where-Object { $_.name -eq $config.ruleset_name } | Select-Object -First 1)
  if ($existing) { Invoke-GhJson PUT "repos/$repo/rulesets/$($existing.id)" $payload | Out-Null }
  else { Invoke-GhJson POST "repos/$repo/rulesets" $payload | Out-Null }

  # Verify the rulesets actually effective on the default branch. Unrelated
  # release-branch rulesets are intentionally left alone.
  $rulesetsAfter = @(Get-Paged "repos/$repo/rulesets?per_page=100")
  $canonicalAfter = @($rulesetsAfter | Where-Object {
    $_.name -eq $config.ruleset_name -and $_.target -eq 'branch' -and $_.enforcement -eq 'active'
  } | Select-Object -First 1)
  if ($canonicalAfter.Count -eq 0) { throw "Canonical active branch ruleset missing after setup for $repo." }

  $defaultBranchEncoded = [uri]::EscapeDataString([string]$meta.default_branch)
  $effectiveRules = @(Get-Paged "repos/$repo/rules/branches/${defaultBranchEncoded}?per_page=100")
  $conflictingIds = @($effectiveRules |
    ForEach-Object { [long]$_.ruleset_id } |
    Where-Object { $_ -gt 0 -and $_ -ne [long]$canonicalAfter[0].id } |
    Select-Object -Unique)
  if ($conflictingIds.Count -gt 0) {
    $conflicts = @($conflictingIds | ForEach-Object {
      $id = $_
      $match = $rulesetsAfter | Where-Object { [long]$_.id -eq $id } | Select-Object -First 1
      if ($match) { "$($match.name) (#$id)" } else { "ruleset #$id" }
    }) -join ', '
    throw "${repo}: conflicting active default-branch ruleset(s): $conflicts. Disable or remove them, then rerun setup."
  }

  # The canonical ruleset is the single default-branch authority. Any legacy
  # branch-protection rule can silently reintroduce approvals/checks and is removed.
  $legacyRaw = & gh api "repos/$repo/branches/$($meta.default_branch)/protection" 2>&1
  if ($LASTEXITCODE -eq 0) {
    $deleteRaw = & gh api --method DELETE "repos/$repo/branches/$($meta.default_branch)/protection" 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Could not remove legacy branch protection from ${repo}: $($deleteRaw -join ' ')" }
    Write-Host 'legacy branch protection: removed; canonical ruleset is sole authority' -ForegroundColor Yellow
  } elseif (-not (($legacyRaw -join "`n") -match '(?i)branch not protected|\b404\b|not found')) {
    throw "Could not inspect legacy branch protection for ${repo}: $($legacyRaw -join ' ')"
  }

  Write-Host 'repo settings: auto-merge/update-branch/squash/delete-branch configured'
  Write-Host 'workflow token default: read; PR approvals by workflow token disabled'
  Write-Host "ruleset: 0 human approvals, stale reviews dismissed, required checks: $(@($requiredChecks | ForEach-Object { $_.context }) -join ' + ')"
}

Write-Host "`nDone. Run doctor.ps1 -Remote; do not claim readiness until every repo reports READY." -ForegroundColor Green
