param(
    [Parameter(Mandatory=$true)]
    [string]$Root,
    [string]$OutputDir = ".\guardian_triage_output"
)

$ErrorActionPreference = "Stop"

function Get-Category([string]$Path) {
    $p = $Path.ToLowerInvariant()
    if ($p -match "\\\.git(\\|$)") { return "git_internal" }
    if ($p -match "\\(\.venv|venv|env)(\\|$)") { return "python_env" }
    if ($p -match "\\node_modules(\\|$)") { return "node_modules" }
    if ($p -match "\\(__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|\.cache)(\\|$)") { return "cache" }
    if ($p -match "\\(dist|build|target|out)(\\|$)") { return "build_output" }
    if ($p -match "\\(logs?|tmp|temp)(\\|$)") { return "logs_or_temp" }
    if ($p -match "\.(zip|7z|rar|tar|gz|tgz)$") { return "archive" }
    if ($p -match "\.(db|sqlite|sqlite3|duckdb)$") { return "database" }
    if ($p -match "\.(bin|pt|pth|safetensors|onnx|gguf|ckpt)$") { return "model_or_binary" }
    if ($p -match "(^|\\)(old modules|old|legacy|backup|backups|archive|archives)(\\|$)") { return "legacy_or_backup" }
    if ($p -match "(^|\\)(\.env|secrets?|credentials?)(\.|\\|$)") { return "potential_secret" }
    return "project_or_unknown"
}

$rootPath = (Resolve-Path -LiteralPath $Root).Path
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$outPath = (Resolve-Path -LiteralPath $OutputDir).Path

Write-Host "Scanning read-only: $rootPath"
Write-Host "Output: $outPath"

$files = Get-ChildItem -LiteralPath $rootPath -File -Recurse -Force -ErrorAction SilentlyContinue

$rows = foreach ($f in $files) {
    $rel = $f.FullName.Substring($rootPath.Length).TrimStart('\')
    [pscustomobject]@{
        relative_path = $rel
        extension = $f.Extension
        size_bytes = [int64]$f.Length
        size_mb = [math]::Round($f.Length / 1MB, 3)
        modified_utc = $f.LastWriteTimeUtc.ToString("o")
        category = Get-Category $f.FullName
    }
}

$manifestCsv = Join-Path $outPath "guardian_file_manifest.csv"
$rows | Sort-Object relative_path | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $manifestCsv

$categorySummary = $rows | Group-Object category | ForEach-Object {
    $bytes = ($_.Group | Measure-Object size_bytes -Sum).Sum
    [pscustomobject]@{
        category = $_.Name
        file_count = $_.Count
        size_bytes = [int64]$bytes
        size_mb = [math]::Round($bytes / 1MB, 2)
        size_gb = [math]::Round($bytes / 1GB, 3)
    }
} | Sort-Object size_bytes -Descending

$categoryCsv = Join-Path $outPath "guardian_category_summary.csv"
$categorySummary | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $categoryCsv

$topFiles = $rows | Sort-Object size_bytes -Descending | Select-Object -First 100
$topCsv = Join-Path $outPath "guardian_top_100_files.csv"
$topFiles | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $topCsv

$dirSummary = $rows | ForEach-Object {
    $first = ($_.relative_path -split '\\')[0]
    [pscustomobject]@{ top_level = $first; size_bytes = $_.size_bytes }
} | Group-Object top_level | ForEach-Object {
    $bytes = ($_.Group | Measure-Object size_bytes -Sum).Sum
    [pscustomobject]@{
        top_level = $_.Name
        file_count = $_.Count
        size_mb = [math]::Round($bytes / 1MB, 2)
        size_gb = [math]::Round($bytes / 1GB, 3)
    }
} | Sort-Object size_gb -Descending

$dirCsv = Join-Path $outPath "guardian_top_level_summary.csv"
$dirSummary | Export-Csv -NoTypeInformation -Encoding UTF8 -Path $dirCsv

$totalBytes = ($rows | Measure-Object size_bytes -Sum).Sum
$summary = [ordered]@{
    analysis_type = "read_only_guardian_local_triage"
    root = $rootPath
    generated_utc = (Get-Date).ToUniversalTime().ToString("o")
    file_count = $rows.Count
    total_bytes = [int64]$totalBytes
    total_gb = [math]::Round($totalBytes / 1GB, 3)
    modifies_source = $false
    hashes_files = $false
    notes = @(
        "This pass is intentionally fast and read-only.",
        "It does not delete, move, execute, import, or hash project files.",
        "Potential-secret paths are classified but file contents are never printed.",
        "Use the detailed legacy inventory tool for hashing/symbol analysis after size triage."
    )
    category_summary = $categorySummary
    top_level_summary = $dirSummary
}

$summaryJson = Join-Path $outPath "guardian_triage_summary.json"
$summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 -Path $summaryJson

Write-Host ""
Write-Host "Guardian triage complete. Source was not modified."
Write-Host ("Files: {0:N0}" -f $rows.Count)
Write-Host ("Total: {0:N3} GB" -f ($totalBytes / 1GB))
Write-Host ""
$categorySummary | Format-Table -AutoSize
Write-Host ""
Write-Host "Reports written to: $outPath"
