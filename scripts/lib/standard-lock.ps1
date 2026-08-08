function Update-StandardLockText {
  param(
    [Parameter(Mandatory)][string]$Text,
    [Parameter(Mandatory)][string]$StandardSha,
    [Parameter(Mandatory)][string]$PinnedAt
  )

  # RED-first seam. Implementation follows once tests prove the current gap.
  return $Text
}
