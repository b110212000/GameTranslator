$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
py -m pip install --target runtime --no-deps nvidia-cublas-cu12==12.4.5.8 nvidia-cudnn-cu12==9.1.1.17
if ($LASTEXITCODE -ne 0) { throw 'NVIDIA runtime installation failed.' }
Write-Host 'App-local NVIDIA libraries are ready. Rebuild to copy them beside the EXE.'
