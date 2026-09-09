param(
    [string]$ProjectRoot = "",
    [int]$MaxWaitSec = 30
)

$ErrorActionPreference = "Stop"

if ($env:ELYSIA_OPENCLAW_AUTOSTART -eq "0") {
    Write-Host "[Elysia OpenClaw] Autostart disabled by ELYSIA_OPENCLAW_AUTOSTART=0"
    exit 0
}

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
}
$ProjectRoot = ([string]$ProjectRoot).Trim().Trim('"')

$cfgPath = Join-Path $ProjectRoot "config\openclaw.json"
if (-not (Test-Path -LiteralPath $cfgPath)) {
    exit 0
}

$cfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $cfg.autostart -or -not $cfg.autostart.enabled) {
    exit 0
}

$base = [string]$cfg.base_url
if (-not $base) { $base = "http://127.0.0.1:18789" }
$base = $base.TrimEnd("/")

function Test-OpenClawReachable {
    param([string]$Root)
    foreach ($p in @("/health", "/status", "/api/health")) {
        try {
            $u = "$Root$p"
            Invoke-RestMethod -Uri $u -TimeoutSec 2 | Out-Null
            return $true
        } catch {
        }
    }
    return $false
}

if (Test-OpenClawReachable -Root $base) {
    Write-Host "[Elysia OpenClaw] Already responding at $base"
    exit 0
}

$cmd = $cfg.autostart.command
if (-not $cmd -or @($cmd).Count -eq 0) {
    Write-Host "[Elysia OpenClaw] autostart.enabled but autostart.command is empty - fill config/openclaw.json (see docs/OPENCLAW_INTEGRATION.md)"
    exit 0
}

$exe = [string](@($cmd)[0])
$rest = @()
if (@($cmd).Count -gt 1) {
    $rest = @($cmd)[1..(@($cmd).Count - 1)]
}

$cwd = ""
if ($cfg.autostart.working_directory) { $cwd = [string]$cfg.autostart.working_directory }
if (-not $cwd -and $cfg.autostart.cwd) { $cwd = [string]$cfg.autostart.cwd }

$logDir = Join-Path $ProjectRoot "data\runtime"
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}
$outLog = Join-Path $logDir "openclaw_autostart.stdout.log"
$errLog = Join-Path $logDir "openclaw_autostart.stderr.log"

Write-Host "[Elysia OpenClaw] Starting worker: $exe $($rest -join ' ')"

$spArgs = @{
    FilePath             = $exe
    PassThru             = $true
    WindowStyle          = "Hidden"
    RedirectStandardOutput = $outLog
    RedirectStandardError  = $errLog
}
if ($rest.Count -gt 0) {
    $spArgs.ArgumentList = $rest
}
if ($cwd) {
    $spArgs.WorkingDirectory = $cwd
}

$proc = Start-Process @spArgs

for ($i = 0; $i -lt $MaxWaitSec; $i++) {
    Start-Sleep -Seconds 1
    if (Test-OpenClawReachable -Root $base) {
        Write-Host "[Elysia OpenClaw] Worker is ready at $base (pid=$($proc.Id))"
        exit 0
    }
    try {
        if ($proc.HasExited) {
            Write-Warning "[Elysia OpenClaw] Worker process exited early (exit=$($proc.ExitCode)). Logs: $outLog , $errLog"
            exit 1
        }
    } catch {
    }
}

Write-Warning "[Elysia OpenClaw] Worker did not become reachable within ${MaxWaitSec}s at $base (pid may still be running). Logs: $outLog"
exit 1
