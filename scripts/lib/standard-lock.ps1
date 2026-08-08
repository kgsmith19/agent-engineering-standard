function Update-StandardLockContent {
  param(
    [Parameter(Mandatory)][string]$Content,
    [Parameter(Mandatory)][string]$StandardSha,
    [Parameter(Mandatory)][string]$PinnedAt
  )

  return $Content
}
