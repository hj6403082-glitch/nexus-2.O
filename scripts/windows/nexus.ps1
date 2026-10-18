# Zeno app launcher for Windows. Double-click "Start ZENO.cmd" (or the Zeno
# desktop shortcut it creates) instead of using a terminal. It:
#   1. installs Node.js via winget if missing (first run only),
#   2. installs dependencies and builds Zeno when the code changed,
#   3. starts the Zeno engine hidden in the background on 127.0.0.1:3001,
#   4. starts the Ollama app if it is installed but not running,
#   5. opens Zeno in its own app window (Edge/Chrome app mode, no tabs or address bar),
#   6. creates Desktop and Start-menu shortcuts with the Zeno icon.
# Everything stays on this computer; the engine only listens on loopback.
param([switch]$Stop, [switch]$NoWindow)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Port = 3001
$Url = "http://127.0.0.1:$Port/"
$LogDir = Join-Path $env:LOCALAPPDATA 'Zeno'
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log = Join-Path $LogDir 'engine.log'
Add-Type -AssemblyName PresentationFramework
function Say($text) { Write-Host "  ZENO  $text" -ForegroundColor Cyan }
function Fail($text) { [System.Windows.MessageBox]::Show($text, 'Zeno', 'OK', 'Warning') | Out-Null; exit 1 }
function EngineUp {
  try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri "${Url}api/ai/status"; return $r.StatusCode -lt 500 } catch { return $false }
}
function EnginePids {
  try { return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop | Select-Object -ExpandProperty OwningProcess -Unique) } catch { return @() }
}

if ($Stop) {
  $pids = EnginePids
  foreach ($id in $pids) { Stop-Process -Id $id -Force -ErrorAction SilentlyContinue }
  if ($pids.Count) { Say 'Engine stopped.' } else { Say 'The engine was not running.' }
  exit 0
}

Set-Location $Root

if (-not (EngineUp)) {
  if (EnginePids) { Fail "Port $Port is used by another program. Close it, then start Zeno again." }

  # 1. Node.js
  $node = Get-Command node -ErrorAction SilentlyContinue
  if (-not $node) {
    if (Get-Command winget -ErrorAction SilentlyContinue) {
      Say 'Installing Node.js (one time)...'
      winget install --id OpenJS.NodeJS.LTS -e --silent --accept-package-agreements --accept-source-agreements | Out-Host
      $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
      $node = Get-Command node -ErrorAction SilentlyContinue
    }
    if (-not $node) { Start-Process 'https://nodejs.org/en/download'; Fail 'Zeno needs Node.js 22 or newer. Install it from the page that just opened, then start Zeno again.' }
  }
  $npm = Join-Path (Split-Path $node.Source) 'npm.cmd'
  if (-not (Test-Path $npm)) { $npm = 'npm.cmd' }

  # 2. Settings, dependencies and build
  if (-not (Test-Path '.env.local') -and (Test-Path '.env.example')) { Copy-Item '.env.example' '.env.local'; Say 'Created .env.local with the local Ollama defaults.' }
  $lock = Get-Item 'package-lock.json'
  $stamp = 'node_modules\.nexus-installed'
  if (-not (Test-Path $stamp) -or (Get-Item $stamp).LastWriteTime -lt $lock.LastWriteTime) {
    Say 'Installing components (first run takes a few minutes)...'
    & $npm ci --no-audit --no-fund | Out-Host
    if ($LASTEXITCODE -ne 0) { & $npm install --no-audit --no-fund | Out-Host }
    if ($LASTEXITCODE -ne 0) { Fail "Installing Zeno components failed. Check your internet connection and try again." }
    Set-Content $stamp (Get-Date -Format o)
    if (Test-Path 'scripts\setup-tracking.mjs') { & $node.Source 'scripts\setup-tracking.mjs' | Out-Host }
  }
  $buildId = '.next\BUILD_ID'
  $newest = Get-ChildItem -Recurse -File -Path 'src', 'public', 'package.json', 'next.config.ts' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not (Test-Path $buildId) -or ($newest -and $newest.LastWriteTime -gt (Get-Item $buildId).LastWriteTime)) {
    Say 'Building Zeno (only after updates)...'
    & $npm run build | Out-Host
    if ($LASTEXITCODE -ne 0) { Fail "Building Zeno failed. The details are in this window; send them to Claude." }
  }

  # 3. Start the engine hidden
  Say 'Starting the spatial engine...'
  $next = Join-Path $Root 'node_modules\next\dist\bin\next'
  # WScript.Shell.Run with style 0 keeps the engine's console fully hidden.
  $runner = New-Object -ComObject WScript.Shell
  $runner.CurrentDirectory = $Root
  $line = 'cmd /c ""' + $node.Source + '" "' + $next + '" start --hostname 127.0.0.1 --port ' + $Port + ' > "' + $Log + '" 2>&1"'
  $runner.Run($line, 0, $false) | Out-Null
  $deadline = (Get-Date).AddSeconds(60)
  while (-not (EngineUp)) {
    if ((Get-Date) -gt $deadline) { Fail "The Zeno engine did not start. Its log is at $Log" }
    Start-Sleep -Milliseconds 500
  }
}

# 4. The AI brain: start Ollama if it is installed but not running.
try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri 'http://127.0.0.1:11434/api/tags' | Out-Null }
catch {
  $ollama = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama app.exe'
  if (Test-Path $ollama) { Start-Process -FilePath $ollama -WindowStyle Hidden }
}

# 6. Shortcuts with the Zeno icon (created once; they point back at this launcher).
$icon = Join-Path $Root 'public\icons\nexus.ico'
$cmd = Join-Path $Root 'Start ZENO.cmd'
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {
  $old = Join-Path $folder 'NEXUS.lnk'; if (Test-Path $old) { Remove-Item $old -Force -ErrorAction SilentlyContinue }
  $path = Join-Path $folder 'Zeno.lnk'
  if (-not (Test-Path $path)) {
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $cmd; $link.WorkingDirectory = $Root; $link.IconLocation = $icon; $link.WindowStyle = 7; $link.Description = 'Zeno spatial operating system'
    $link.Save()
  }
}

# 5. Open the app window.
if ($NoWindow) { exit 0 }
$candidates = @(
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe", "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe", "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe")
$browser = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if ($browser) { Start-Process -FilePath $browser -ArgumentList "--app=$Url", '--start-maximized' }
else { Start-Process $Url }
