# Quick checks: Elysia status/chat API + OpenClaw gateway reachability.
# Run from repo root: powershell -ExecutionPolicy Bypass -File scripts\verify_openclaw_elysia_wiring.ps1

$ErrorActionPreference = "Continue"

$elyHost = if ($env:ELYSIA_STATUS_HOST) { $env:ELYSIA_STATUS_HOST } else { "127.0.0.1" }
$elyPort = if ($env:ELYSIA_STATUS_PORT) { [int]$env:ELYSIA_STATUS_PORT } else { 8888 }
$gwHost = if ($env:OPENCLAW_GATEWAY_HOST) { $env:OPENCLAW_GATEWAY_HOST } else { "127.0.0.1" }
$gwPort = if ($env:OPENCLAW_GATEWAY_PORT) { [int]$env:OPENCLAW_GATEWAY_PORT } else { 18789 }

Write-Host "=== OpenClaw + Elysia wiring probe ===" -ForegroundColor Cyan
Write-Host ""

function Test-Tcp($h, $p) {
    try {
        $c = Test-NetConnection -ComputerName $h -Port $p -WarningAction SilentlyContinue
        return $c.TcpTestSucceeded
    } catch {
        return $false
    }
}

$eTcp = Test-Tcp $elyHost $elyPort
Write-Host ("Elysia TCP {0}:{1} -> {2}" -f $elyHost, $elyPort, ($(if ($eTcp) { "open" } else { "closed" })))

$gTcp = Test-Tcp $gwHost $gwPort
Write-Host ("OpenClaw gateway TCP {0}:{1} -> {2}" -f $gwHost, $gwPort, ($(if ($gTcp) { "open" } else { "closed" })))

$elyUrl = "http://${elyHost}:${elyPort}"
try {
    $st = Invoke-RestMethod -Uri "$elyUrl/status" -TimeoutSec 4 -Method Get
    Write-Host "GET $elyUrl/status -> OK (keys: $($st.PSObject.Properties.Name.Count) props)" -ForegroundColor Green
} catch {
    Write-Host "GET $elyUrl/status -> FAIL: $($_.Exception.Message)" -ForegroundColor Yellow
}

try {
    $gw = Invoke-WebRequest -Uri "http://${gwHost}:${gwPort}/" -TimeoutSec 4 -UseBasicParsing
    Write-Host "GET http://${gwHost}:${gwPort}/ -> HTTP $($gw.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "GET gateway root -> FAIL: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Same path OpenClaw uses; non-streaming JSON (mirrors provider apiType openai-completions).
$chatTimeoutSec = if ($env:ELYSIA_CHAT_PROBE_TIMEOUT_SEC) { [int]$env:ELYSIA_CHAT_PROBE_TIMEOUT_SEC } else { 120 }
$chatBody = '{"model":"elysia/main","stream":false,"messages":[{"role":"user","content":"Reply with the single word: wiring-ok"}]}'
$chatHeaders = @{ "Content-Type" = "application/json; charset=utf-8" }
if ($env:ELYSIA_API_TOKEN) {
    $chatHeaders["Authorization"] = "Bearer $($env:ELYSIA_API_TOKEN)"
}
try {
    $chatResp = Invoke-RestMethod -Uri "$elyUrl/v1/chat/completions" -Method Post -Body $chatBody -Headers $chatHeaders -TimeoutSec $chatTimeoutSec
    $snippet = ""
    if ($null -ne $chatResp.choices -and $chatResp.choices.Count -gt 0) {
        $c = $chatResp.choices[0].message.content
        if ($c) {
            $snippet = ($c -replace "\s+", " ").Trim()
            if ($snippet.Length -gt 120) { $snippet = $snippet.Substring(0, 120) + "..." }
        }
    }
    if ($snippet) {
        Write-Host "POST $elyUrl/v1/chat/completions -> OK (assistant preview: $snippet)" -ForegroundColor Green
    } else {
        Write-Host "POST $elyUrl/v1/chat/completions -> OK (empty choices/content; check Elysia logs)" -ForegroundColor Yellow
    }
} catch {
    $msg = $_.Exception.Message
    $code = $null
    try {
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
    } catch { }
    if ($code -eq 401) {
        $msg += " (set ELYSIA_API_TOKEN for probe header, or clear token on server)"
    }
    Write-Host "POST $elyUrl/v1/chat/completions -> FAIL: $msg" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Manual steps OpenClaw cannot do for you:" -ForegroundColor Cyan
Write-Host "  1. Merge config/openclaw_provider_elysia.example.json into OpenClaw's models.providers."
Write-Host "  2. Set agent model to elysia/main (or your configured model id)."
Write-Host "  3. If ELYSIA_API_TOKEN is set, use the same value as apiKey in OpenClaw."
Write-Host ""
Write-Host "Elysia -> gateway (delegate_openclaw / skills): base_url in Project Guardian config/openclaw.json"
Write-Host "  or env ELYSIA_OPENCLAW_BASE_URL / OPENCLAW_GATEWAY_URL (default gateway port $gwPort)."
Write-Host ""
