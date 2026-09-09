# Creates desktop shortcuts for Elysia: start (unified), optional toggle, stop-only.
# Run: INSTALL_ELYSIA_DESKTOP_SHORTCUT.bat
#   or: powershell -NoProfile -ExecutionPolicy Bypass -File create_elysia_desktop_shortcut.ps1
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartUnified = Join-Path $ProjectRoot "START_ELYSIA_UNIFIED.bat"
$Toggle = Join-Path $ProjectRoot "TOGGLE_ELYSIA_DESKTOP.bat"
$StopOnly = Join-Path $ProjectRoot "STOP_ELYSIA_DESKTOP.bat"
$BackendHelper = Join-Path $ProjectRoot "Start_Elysia_Backend.cmd"

foreach ($req in @($StartUnified, $Toggle, $StopOnly, $BackendHelper, (Join-Path $ProjectRoot "toggle_elysia_desktop.py"), (Join-Path $ProjectRoot "elysia.py"), (Join-Path $ProjectRoot "wait_for_elysia_backend.py"))) {
    if (-not (Test-Path -LiteralPath $req)) {
        Write-Error "Missing required file: $req"
        exit 1
    }
}

$Wsh = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath("Desktop")
if (-not $Desktop) { $Desktop = [Environment]::GetFolderPath("UserProfile") + "\Desktop" }

function Set-PythonIcon {
    param($Shortcut)
    try {
        $py = (Get-Command python -ErrorAction SilentlyContinue).Source
        if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
        if ($py -and (Test-Path -LiteralPath $py)) {
            $Shortcut.IconLocation = "$py,0"
        }
    } catch { }
}

function New-ElysiaStartShortcut {
    param([string]$Path)
    $Sc = $Wsh.CreateShortcut($Path)
    $Sc.TargetPath = $StartUnified
    $Sc.WorkingDirectory = $ProjectRoot
    $Sc.WindowStyle = 1
    $Sc.Description = "Elysia: start unified backend + interface (START_ELYSIA_UNIFIED.bat). Does not toggle off — use Elysia Stop or Elysia Toggle."
    Set-PythonIcon -Shortcut $Sc
    $Sc.Save()
}

function New-ElysiaToggleShortcut {
    param([string]$Path)
    $Sc = $Wsh.CreateShortcut($Path)
    $Sc.TargetPath = $Toggle
    $Sc.WorkingDirectory = $ProjectRoot
    $Sc.WindowStyle = 1
    $Sc.Description = "Elysia: if backend is running, graceful shutdown; if off, start unified launcher (TOGGLE_ELYSIA_DESKTOP.bat)."
    Set-PythonIcon -Shortcut $Sc
    $Sc.Save()
}

function New-ElysiaStopShortcut {
    param([string]$Path)
    $Sc = $Wsh.CreateShortcut($Path)
    $Sc.TargetPath = $StopOnly
    $Sc.WorkingDirectory = $ProjectRoot
    $Sc.WindowStyle = 1
    $Sc.Description = "Elysia: graceful shutdown only (POST /shutdown). Does not start if already off (STOP_ELYSIA_DESKTOP.bat)."
    Set-PythonIcon -Shortcut $Sc
    $Sc.Save()
}

# 1) Primary: start only (avoids accidental stop on second double-click)
$Top = Join-Path $Desktop "Elysia.lnk"
New-ElysiaStartShortcut -Path $Top
Write-Host "OK: $Top -> START_ELYSIA_UNIFIED.bat"

$ToggleLnk = Join-Path $Desktop "Elysia Toggle.lnk"
New-ElysiaToggleShortcut -Path $ToggleLnk
Write-Host "OK: $ToggleLnk -> TOGGLE_ELYSIA_DESKTOP.bat"

$StopLnk = Join-Path $Desktop "Elysia Stop.lnk"
New-ElysiaStopShortcut -Path $StopLnk
Write-Host "OK: $StopLnk -> STOP_ELYSIA_DESKTOP.bat"

# 2) "Elysia" folder on desktop with shortcuts + open-folder link
$Folder = Join-Path $Desktop "Elysia"
if (-not (Test-Path -LiteralPath $Folder)) {
    New-Item -ItemType Directory -Path $Folder | Out-Null
}
$InFolder = Join-Path $Folder "Elysia.lnk"
New-ElysiaStartShortcut -Path $InFolder
Write-Host "OK: $InFolder"

$InFolderToggle = Join-Path $Folder "Elysia Toggle.lnk"
New-ElysiaToggleShortcut -Path $InFolderToggle
Write-Host "OK: $InFolderToggle"

$InFolderStop = Join-Path $Folder "Elysia Stop.lnk"
New-ElysiaStopShortcut -Path $InFolderStop
Write-Host "OK: $InFolderStop"

$OpenFolder = Join-Path $Folder "Open Elysia project folder.lnk"
$Fo = $Wsh.CreateShortcut($OpenFolder)
$Fo.TargetPath = "explorer.exe"
$Fo.Arguments = "`"$ProjectRoot`""
$Fo.WorkingDirectory = $ProjectRoot
$Fo.Description = "Open Project Guardian folder in File Explorer"
$Fo.Save()
Write-Host "OK: $OpenFolder"

Write-Host ""
Write-Host "Done. Use 'Elysia' to start; 'Elysia Stop' to shut down; 'Elysia Toggle' for one-click on/off."
