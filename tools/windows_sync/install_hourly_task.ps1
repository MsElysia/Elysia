# Install a current-user Scheduled Task that runs Elysia sync_check hourly.
# Never force-resets git. Does not promote releases.
param(
  [string]$DevRoot = "C:\Users\Owner\Elysia-Dev",
  [string]$Python = "C:\Users\Owner\Project guardian\.venv\Scripts\python.exe",
  [string]$TaskName = "ElysiaWindowsSyncHourly"
)

$ErrorActionPreference = "Stop"
$script = Join-Path $DevRoot "tools\windows_sync\sync_check.py"
if (-not (Test-Path $script)) { throw "Missing sync_check.py at $script" }
if (-not (Test-Path $Python)) { throw "Missing python at $Python" }

$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$script`"" -WorkingDirectory $DevRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddMinutes(5) -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null
Write-Host "Registered scheduled task: $TaskName"
Get-ScheduledTask -TaskName $TaskName | Format-List TaskName, State
