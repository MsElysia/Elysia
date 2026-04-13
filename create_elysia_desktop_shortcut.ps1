# Creates an easy desktop entry for Elysia (shortcut + optional folder).
# Run: INSTALL_ELYSIA_DESKTOP_SHORTCUT.bat
#   or: powershell -NoProfile -ExecutionPolicy Bypass -File create_elysia_desktop_shortcut.ps1
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = Join-Path $ProjectRoot "START_ELYSIA_UNIFIED.bat"
$BackendHelper = Join-Path $ProjectRoot "Start_Elysia_Backend.cmd"

foreach ($req in @($Launcher, $BackendHelper, (Join-Path $ProjectRoot "elysia.py"), (Join-Path $ProjectRoot "wait_for_elysia_backend.py"))) {
    if (-not (Test-Path -LiteralPath $req)) {
        Write-Error "Missing required file: $req"
        exit 1
    }
}

$Wsh = New-Object -ComObject WScript.Shell
$Desktop = [Environment]::GetFolderPath("Desktop")
if (-not $Desktop) { $Desktop = [Environment]::GetFolderPath("UserProfile") + "\Desktop" }

function New-ElysiaShortcut {
    param([string]$Path)
    $Sc = $Wsh.CreateShortcut($Path)
    $Sc.TargetPath = $Launcher
    $Sc.WorkingDirectory = $ProjectRoot
    $Sc.WindowStyle = 1
    $Sc.Description = "Elysia: START_ELYSIA_UNIFIED.bat (full backend + wait + UI). Target must stay this .bat; Start in = project root."
    try {
        $py = (Get-Command python -ErrorAction SilentlyContinue).Source
        if (-not $py) { $py = (Get-Command py -ErrorAction SilentlyContinue).Source }
        if ($py -and (Test-Path -LiteralPath $py)) {
            $Sc.IconLocation = "$py,0"
        }
    } catch { }
    $Sc.Save()
}

# 1) Top-level desktop shortcut (one double-click)
$Top = Join-Path $Desktop "Start Elysia.lnk"
New-ElysiaShortcut -Path $Top
Write-Host "OK: $Top"

# 2) "Elysia" folder on desktop with the same shortcut + open-folder link
$Folder = Join-Path $Desktop "Elysia"
if (-not (Test-Path -LiteralPath $Folder)) {
    New-Item -ItemType Directory -Path $Folder | Out-Null
}
$InFolder = Join-Path $Folder "Start Elysia.lnk"
New-ElysiaShortcut -Path $InFolder
Write-Host "OK: $InFolder"

$OpenFolder = Join-Path $Folder "Open Elysia project folder.lnk"
$Fo = $Wsh.CreateShortcut($OpenFolder)
$Fo.TargetPath = "explorer.exe"
$Fo.Arguments = "`"$ProjectRoot`""
$Fo.WorkingDirectory = $ProjectRoot
$Fo.Description = "Open Project Guardian folder in File Explorer"
$Fo.Save()
Write-Host "OK: $OpenFolder"

Write-Host ""
Write-Host "Done. Double-click 'Start Elysia' on your desktop (or Desktop\Elysia\)."
