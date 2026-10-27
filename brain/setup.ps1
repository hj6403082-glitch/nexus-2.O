<#
.SYNOPSIS
  Creates brain\.venv and installs Zeno's brain dependencies (Windows).

.EXAMPLE
  .\setup.ps1                      # CPU build (default)
  .\setup.ps1 -Cuda                # NVIDIA GPU build, prebuilt CUDA 12.4 wheel
  .\setup.ps1 -Cuda -CudaVersion cu121
  .\setup.ps1 -Cuda -FromSource    # compile against the installed CUDA Toolkit

.EXAMPLE
  .\setup.ps1 -Vision -Voice       # also download the Phase 2 model files into models\
  .\setup.ps1 -VoiceExtra          # also install the optional Kokoro / faster-whisper adapters
#>
param(
  [switch]$Cuda,
  [ValidateSet('cu121', 'cu122', 'cu123', 'cu124', 'cu125')]
  [string]$CudaVersion = 'cu124',
  [switch]$FromSource,
  [switch]$Vision,
  [switch]$Voice,
  [switch]$VoiceExtra
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$llama = 'llama-cpp-python==0.3.36'
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
  Write-Host 'Creating .venv ...'
  py -3 -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required (install it from python.org, tick "Add to PATH").' }
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed.' }
if ($VoiceExtra) {
  & $venvPython -m pip install -r requirements-voice-extra.txt
  if ($LASTEXITCODE -ne 0) { throw 'Optional voice adapters failed to install.' }
}

# J.A.R.V.I.S. wake word: openwakeword ships no model files, it fetches them on first
# use. Pull them now so "Hey Zeno" works at first start. tflite-runtime is Linux-only,
# so on Windows Zeno runs openwakeword under onnxruntime (which download_models covers).
Write-Host 'Fetching wake-word models ...'
& $venvPython -c "from openwakeword.utils import download_models; download_models()"
if ($LASTEXITCODE -ne 0) {
  Write-Warning 'Wake-word model download failed; voice wake stays off until it succeeds (re-run setup.ps1 on a network connection).'
}

if ($Cuda) {
  Write-Host "Switching llama-cpp-python to the CUDA build ..."
  if ($FromSource) {
    $env:CMAKE_ARGS = '-DGGML_CUDA=on'
    & $venvPython -m pip install --force-reinstall --no-deps --no-cache-dir --no-binary llama-cpp-python $llama
    Remove-Item Env:CMAKE_ARGS
  } else {
    & $venvPython -m pip install --force-reinstall --no-deps --no-cache-dir $llama `
      --index-url "https://abetlen.github.io/llama-cpp-python/whl/$CudaVersion" `
      --extra-index-url https://pypi.org/simple
  }
  if ($LASTEXITCODE -ne 0) { throw 'CUDA build of llama-cpp-python failed; see "CPU vs CUDA" in CLAUDE.md.' }
}

# Model files are only fetched when asked for, from the list in model-downloads.txt.
$groups = @(); if ($Vision) { $groups += 'vision' }; if ($Voice) { $groups += 'voice' }
if ($groups.Count) {
  New-Item -ItemType Directory -Force -Path 'models' | Out-Null
  $ProgressPreference = 'SilentlyContinue'  # the progress bar makes large downloads many times slower
  foreach ($line in Get-Content 'model-downloads.txt') {
    if (-not $line.Trim() -or $line.StartsWith('#')) { continue }
    $group, $name, $url = -split $line
    if ($groups -notcontains $group) { continue }
    $target = Join-Path 'models' $name
    if ((Test-Path $target) -and (Get-Item $target).Length -gt 0) { Write-Host "have   $target"; continue }
    Write-Host "fetch  $target"
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile "$target.part"
    Move-Item -Force "$target.part" $target
  }
}

& $venvPython -c "import llama_cpp; print('llama.cpp', llama_cpp.__version__, '| GPU offload:', llama_cpp.llama_supports_gpu_offload())"
Write-Host 'Done. Activate with: .\.venv\Scripts\Activate.ps1   then run: pytest'
