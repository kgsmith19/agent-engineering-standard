param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path $Root -PathType Container)) { throw "Lint root does not exist: $Root" }

$extensions = @('.ps1','.psm1','.sh','.bash','.js','.mjs','.cjs','.ts','.tsx','.py','.rb','.yml','.yaml','.json')
$excludedDirectories = @('.git','.worktrees','.superpowers','docs','tests','node_modules','vendor')
$patterns = @(
  [pscustomobject]@{ name='gh draft flag'; regex='(?im)\bgh\s+pr\s+create\b[^\r\n]*(?:--draft|(?:^|\s)-d(?:\s|$))' },
  [pscustomobject]@{ name='API or SDK draft true'; regex='(?im)(?:["'']?draft["'']?)\s*[:=]\s*(?:true|\$true)\b' }
)

$violations = New-Object System.Collections.Generic.List[string]
$resolvedRoot = (Resolve-Path $Root).Path
foreach ($file in Get-ChildItem $resolvedRoot -Recurse -File) {
  if ($file.FullName -eq $PSCommandPath) { continue }
  if ($extensions -notcontains $file.Extension.ToLowerInvariant()) { continue }
  $relative = [System.IO.Path]::GetRelativePath($resolvedRoot,$file.FullName)
  $segments = $relative -split '[\\/]'
  if (@($segments | Where-Object { $excludedDirectories -contains $_ }).Count -gt 0) { continue }

  $content = Get-Content $file.FullName -Raw
  $normalized = $content -replace '(?m)`\s*\r?\n',' ' -replace '(?m)\\\s*\r?\n',' '
  foreach ($pattern in $patterns) {
    if ($normalized -match $pattern.regex) { $violations.Add("${relative}: $($pattern.name)") }
  }
}

if ($violations.Count -gt 0) {
  throw "Draft PR creation is forbidden. Create Ready with draft:false; gh callers must omit --draft and -d.`n$($violations -join "`n")"
}

Write-Host 'PR creation lint: PASS' -ForegroundColor Green
