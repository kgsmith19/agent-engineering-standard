param(
  [string]$ConfigPath = (Join-Path $PSScriptRoot "..\policy\github-defaults.json"),
  [string[]]$Repositories
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  throw "GitHub CLI (gh) is required."
}

& gh auth status | Out-Host
if ($LASTEXITCODE -ne 0) { throw "gh is not authenticated." }

$config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
if ($config.work_tracking.system -ne 'github-projects') { throw "work_tracking.system must be 'github-projects'." }
$owner = $config.owner
$title = $config.project_title
$targets = if ($Repositories -and $Repositories.Count -gt 0) { @($Repositories) } else { @($config.repositories) }

$projectsRaw = & gh project list --owner $owner --format json 2>&1
if ($LASTEXITCODE -ne 0) {
  throw "Cannot access GitHub Projects. Run: gh auth refresh -s project"
}

$projects = ($projectsRaw -join "`n") | ConvertFrom-Json
$project = $projects.projects | Where-Object { $_.title -eq $title } | Select-Object -First 1

if (-not $project) {
  Write-Host "Creating project: $title"
  & gh project create --owner $owner --title $title | Out-Host
  if ($LASTEXITCODE -ne 0) { throw "Project creation failed." }
  $projects = ((& gh project list --owner $owner --format json) -join "`n") | ConvertFrom-Json
  $project = $projects.projects | Where-Object { $_.title -eq $title } | Select-Object -First 1
}

if (-not $project) { throw "Project '$title' could not be resolved after creation." }
$number = $project.number
Write-Host "Using project #${number}: $title"

foreach ($name in $targets) {
  $repo = if ($name -match '/') { $name } else { "$owner/$name" }
  Write-Host "Syncing open work items from $repo"
  $issuesRaw = & gh issue list --repo $repo --state open --limit 100 --json url 2>&1
  if ($LASTEXITCODE -ne 0) {
    Write-Warning "Could not list issues for $repo"
    continue
  }

  $issues = ($issuesRaw -join "`n") | ConvertFrom-Json
  foreach ($issue in $issues) {
    $output = & gh project item-add $number --owner $owner --url $issue.url 2>&1
    if ($LASTEXITCODE -ne 0 -and ($output -join " ") -notmatch "already") {
      Write-Warning "Could not add $($issue.url): $($output -join ' ')"
    }
  }
}

Write-Host "`nProject sync complete. '$title' is the portfolio operating workboard; GitHub Issues remain the durable backing records." -ForegroundColor Green
