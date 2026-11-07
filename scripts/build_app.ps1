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

# Optional GPU runtime stays beside the EXE, avoiding a multi-gigabyte onefile.
foreach ($package in @('cublas', 'cudnn')) {
    $source = Join-Path $projectRoot "runtime\nvidia\$package\bin"
    if (Test-Path $source) {
        $destination = Join-Path $projectRoot "dist\runtime\nvidia\$package\bin"
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
        Copy-Item -Path "$source\*.dll" -Destination $destination -Force
    }
}
foreach ($metadata in Get-ChildItem -Path "$projectRoot\runtime" -Directory -Filter 'nvidia_*.dist-info' -ErrorAction SilentlyContinue) {
    $license = Join-Path $metadata.FullName 'License.txt'
    if (Test-Path $license) {
        $licenseDirectory = Join-Path $projectRoot 'dist\runtime\licenses'
        New-Item -ItemType Directory -Force -Path $licenseDirectory | Out-Null
        Copy-Item -LiteralPath $license -Destination (Join-Path $licenseDirectory "$($metadata.Name)-License.txt") -Force
    }
}

Write-Host "Built $projectRoot\dist\GameTranslator.exe"
