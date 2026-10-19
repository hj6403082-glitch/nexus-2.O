<#
.SYNOPSIS
  Creates brain\.venv and installs Zeno's brain dependencies (Windows).

.EXAMPLE
  .\setup.ps1                      # CPU build (default)
  .\setup.ps1 -Cuda                # NVIDIA GPU build, prebuilt CUDA 12.4 wheel
  .\setup.ps1 -Cuda -CudaVersion cu121
  .\setup.ps1 -Cuda -FromSource    # compile against the installed CUDA Toolkit
#>
param(
  [switch]$Cuda,
  [ValidateSet('cu121', 'cu122', 'cu123', 'cu124', 'cu125')]
  [string]$CudaVersion = 'cu124',
  [switch]$FromSource
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

& $venvPython -c "import llama_cpp; print('llama.cpp', llama_cpp.__version__, '| GPU offload:', llama_cpp.llama_supports_gpu_offload())"
Write-Host 'Done. Activate with: .\.venv\Scripts\Activate.ps1   then run: pytest'
