<#
.SYNOPSIS
  Install Zeno as an always-on background assistant on Windows (no admin needed).

.DESCRIPTION
  The "J.A.R.V.I.S. Protocol" installer. It:
    - registers a Scheduled Task "Zeno" that starts Zeno at your logon, running
      brain\.venv\Scripts\pythonw.exe -m zeno serve with no console window and
      restarting it every minute if it stops;
    - runs as you, never elevated (the Windows counterpart of the Linux systemd
      user service). A command that truly needs admin asks for it with a UAC prompt
      at that moment; the daemon itself is never Administrator;
    - registers Zeno's toast identity so notifications show as "Zeno";
    - adds a "Send to Zeno" entry to the Explorer right-click menu (per-user);
    - leaves the microphone wake word ("Hey Zeno") on by default. Turn it off by
      setting ZENO_WAKEWORD=false in brain\.env.

  Logs go to brain\data\logs\zeno.log. Run .\setup.ps1 first: this needs brain\.venv.

.EXAMPLE
  .\daemons\install_zeno_windows.ps1           # install (starts at next logon)
  .\daemons\install_zeno_windows.ps1 -Now      # install and start Zeno now
  .\daemons\install_zeno_windows.ps1 -Remove   # stop Zeno, remove the task, menu and identity
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
  if (Test-Path $Pythonw) {
    & $Pythonw -m zeno.hostos.windows.shell_integration --remove
  }
  if (Test-Path $IdentityKey) {
    Remove-Item -Path $IdentityKey -Recurse
  }
  Write-Host 'Zeno will no longer start at logon; its right-click menu is removed.'
  return
}

if (-not (Test-Path $Pythonw)) {
  throw "No virtual environment at $Brain\.venv. Run .\setup.ps1 first."
}

# Toast identity: notifications from Zeno show under this name.
New-Item -Path $IdentityKey -Force | Out-Null
New-ItemProperty -Path $IdentityKey -Name 'DisplayName' -Value 'Zeno' -PropertyType String -Force | Out-Null

# "Send to Zeno" in the Explorer right-click menu (per-user; no admin).
& $Pythonw -m zeno.hostos.windows.shell_integration --install

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
  -Description "Zeno's brain on 127.0.0.1 (brain\daemons\install_zeno_windows.ps1)" `
  -Action $action `
  -Trigger $trigger `
  -Principal $principal `
  -Settings $settings `
  -Force | Out-Null

if ($Now) {
  Start-ScheduledTask -TaskName $TaskName
}

$state = (Get-ScheduledTask -TaskName $TaskName).State
Write-Host "Zeno is installed ($state). Wake word 'Hey Zeno' is on; logs: $Brain\data\logs\zeno.log"
Write-Host 'Remove everything with: .\daemons\install_zeno_windows.ps1 -Remove'
