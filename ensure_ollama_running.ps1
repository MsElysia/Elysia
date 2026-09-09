param(
    [string]$ApiUrl = "http://127.0.0.1:11434/api/tags",
    [int]$MaxWaitSec = 20
)

$ErrorActionPreference = "Stop"

function Test-OllamaApi {
    param([string]$Url)
    try {
        Invoke-RestMethod -Uri $Url -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

if ($env:ELYSIA_OLLAMA_AUTOSTART -eq "0") {
    Write-Host "[Elysia Ollama] Autostart disabled by ELYSIA_OLLAMA_AUTOSTART=0"
    exit 0
}

if (Test-OllamaApi -Url $ApiUrl) {
    Write-Host "[Elysia Ollama] API already responding at $ApiUrl"
    exit 0
}

$ollamaExe = $null
try {
    $cmd = Get-Command ollama -ErrorAction Stop
    if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
        $ollamaExe = $cmd.Source
    }
} catch {
}

if (-not $ollamaExe) {
    $fallback = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path -LiteralPath $fallback) {
        $ollamaExe = $fallback
    }
}

if (-not $ollamaExe) {
    Write-Warning "[Elysia Ollama] ollama.exe not found; continuing without local Ollama."
    exit 1
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$stdoutLog = Join-Path $projectRoot "tmp_ollama_autostart.out"
$stderrLog = Join-Path $projectRoot "tmp_ollama_autostart.err"

Write-Host "[Elysia Ollama] Starting Ollama from $ollamaExe"
Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutLog -RedirectStandardError $stderrLog

for ($i = 0; $i -lt $MaxWaitSec; $i++) {
    Start-Sleep -Seconds 1
    if (Test-OllamaApi -Url $ApiUrl) {
        Write-Host "[Elysia Ollama] API is ready at $ApiUrl"
        exit 0
    }
}

Write-Warning "[Elysia Ollama] Started Ollama, but the API did not become ready within $MaxWaitSec seconds."
exit 1
