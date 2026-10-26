<#
.SYNOPSIS
  Start Zeno's brain when you log on to Windows (Task Scheduler, no admin needed).

.DESCRIPTION
  Registers a Scheduled Task named "Zeno" for the current user that runs
  brain\.venv\Scripts\pythonw.exe -m zeno serve at logon, with no console window,
  restarting it every minute if it fails. It runs as you, never elevated: the Windows
  counterpart of the Linux systemd user service (daemons/zeno.service).

  It also registers Zeno's toast identity (AppUserModelID Zeno.Brain) for your user,
  so desktop notifications show as "Zeno". Logs go to brain\data\logs\zeno.log.

  Run .\setup.ps1 first: this script needs brain\.venv.

.EXAMPLE
  .\daemons\windows_setup.ps1           # register the task (starts at your next logon)
  .\daemons\windows_setup.ps1 -Now      # register it and start Zeno now
  .\daemons\windows_setup.ps1 -Remove   # stop Zeno and remove the task and identity
#>
param(
  [switch]$Now,
  [switch]$Remove
)

$ErrorActionPreference = 'Stop'
$Brain = Split-Path -Parent $PSScriptRoot
$TaskName = 'Zeno'
$AppId = 'Zeno.Brain'
$IdentityKey = "HKCU:\Software\Classes\AppUserModelId\$AppId"
$Pythonw = Join-Path $Brain '.venv\Scripts\pythonw.exe'
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if ($Remove) {
  $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
  if ($task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
  }
  if (Test-Path $IdentityKey) {
    Remove-Item -Path $IdentityKey -Recurse
  }
  Write-Host 'Zeno will no longer start at logon.'
  return
}

if (-not (Test-Path $Pythonw)) {
  throw "No virtual environment at $Brain\.venv. Run .\setup.ps1 first."
}

# Toast identity: notifications from Zeno show under this name.
New-Item -Path $IdentityKey -Force | Out-Null
New-ItemProperty -Path $IdentityKey -Name 'DisplayName' -Value 'Zeno' -PropertyType String -Force | Out-Null

$action = New-ScheduledTaskAction -Execute $Pythonw -Argument '-m zeno serve' -WorkingDirectory $Brain
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) `
  -StartWhenAvailable `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -MultipleInstances IgnoreNew

Register-ScheduledTask `
  -TaskName $TaskName `
  -Description "Zeno's brain on 127.0.0.1 (brain\daemons\windows_setup.ps1)" `
  -Action $action `
  -Trigger $trigger `
  -Principal $principal `
  -Settings $settings `
  -Force | Out-Null

if ($Now) {
  Start-ScheduledTask -TaskName $TaskName
}

$state = (Get-ScheduledTask -TaskName $TaskName).State
Write-Host "Zeno's logon task is registered ($state). Logs: $Brain\data\logs\zeno.log"
Write-Host 'Remove it with: .\daemons\windows_setup.ps1 -Remove'
