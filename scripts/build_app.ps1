$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

py -m PyInstaller `
    --noconfirm `
    --clean `
    --noconsole `
    --onefile `
    --name GameTranslator `
    --hidden-import argostranslate.translate `
    --collect-data opencc `
    app.py

Write-Host "Built $projectRoot\dist\GameTranslator.exe"
