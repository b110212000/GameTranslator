$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

py -m PyInstaller `
    --noconfirm `
    --noconsole `
    --onefile `
    --name GameTranslator `
    --version-file scripts\version_info.txt `
    --collect-data faster_whisper `
    --collect-data argostranslate `
    --exclude-module torch `
    --exclude-module spacy `
    --exclude-module stanza `
    --collect-data opencc `
    app.py

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE). Close the old app and retry." }
if (-not (Test-Path "$projectRoot\dist\GameTranslator.exe")) { throw "EXE was not produced." }

Write-Host "Built $projectRoot\dist\GameTranslator.exe"
