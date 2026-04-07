Param(
    [string]$Remote = "origin",
    [string]$SourceBranch = "codex/analyze-full-setyme-diopkq",
    [string]$BaseBranch = "claude/check-file-version-fpb60",
    [string]$ConflictFile = "video-editor-system/backend/super_auto_editor.py"
)

$ErrorActionPreference = "Stop"

Write-Host "Fetching latest refs from $Remote..."
git fetch $Remote

Write-Host "Checking out source branch: $SourceBranch"
git checkout $SourceBranch

Write-Host "Merging base branch: $Remote/$BaseBranch"
try {
    git merge -X ours "$Remote/$BaseBranch" --no-edit
}
catch {
    Write-Warning "Merge returned conflict(s). Forcing ours on $ConflictFile"
    git checkout --ours $ConflictFile
    git add $ConflictFile
    git commit -m "Resolve PR conflict in super_auto_editor.py (keep source branch version)"
}

Write-Host "Pushing updated branch..."
git push $Remote $SourceBranch

Write-Host "Done. Refresh PR page."
