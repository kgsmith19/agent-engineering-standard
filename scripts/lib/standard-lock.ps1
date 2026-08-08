function Update-StandardLockText {
  param(
    [Parameter(Mandatory)][string]$Text,
    [Parameter(Mandatory)][string]$StandardSha,
    [Parameter(Mandatory)][string]$PinnedAt
  )

  if ($StandardSha -notmatch '^[0-9a-fA-F]{40}$') {
    throw 'StandardSha must be a full 40-character commit SHA.'
  }

  $commitPattern = '(?m)^(?<prefix>\s*(?:commit|sha|standard_commit):\s*)(?<value>[0-9a-fA-F]{40})(?<suffix>\s*(?:#.*)?)$'
  $commitRegex = [regex]::new($commitPattern)
  $matches = $commitRegex.Matches($Text)

  if ($matches.Count -eq 0) {
    throw 'Unrecognized standard.lock format; expected exactly one commit:, sha:, or standard_commit: line.'
  }
  if ($matches.Count -gt 1) {
    throw 'Ambiguous standard.lock format; found more than one recognized standard commit line.'
  }

  $updated = $commitRegex.Replace(
    $Text,
    { param($match) "$($match.Groups['prefix'].Value)$StandardSha$($match.Groups['suffix'].Value)" },
    1
  )

  $dateRegex = [regex]::new('(?m)^(?<prefix>\s*pinned_at:\s*).*$')
  if ($dateRegex.IsMatch($updated)) {
    $updated = $dateRegex.Replace(
      $updated,
      { param($match) "$($match.Groups['prefix'].Value)`"$PinnedAt`"" },
      1
    )
  }

  return $updated
}
