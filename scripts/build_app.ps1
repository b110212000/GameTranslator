param([string]$Python='py', [string]$OutputDirectory='', [string]$BuildDirectory='')
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$buildCallerLocation = Get-Location
try {
Set-Location $projectRoot
if (-not $OutputDirectory) { $OutputDirectory=Join-Path $projectRoot 'dist' }
if (-not $BuildDirectory) { $BuildDirectory=Join-Path $projectRoot 'build' }

& $Python -B -m PyInstaller `
    --noconfirm `
    --noconsole `
    --onefile `
    --name GameTranslator `
    --distpath $OutputDirectory `
    --workpath $BuildDirectory `
    --specpath $BuildDirectory `
    --version-file (Join-Path $projectRoot 'scripts\version_info.txt') `
    --collect-data faster_whisper `
    --collect-data argostranslate `
    --exclude-module torch `
    --exclude-module spacy `
    --exclude-module stanza `
    --collect-data opencc `
    --add-data "$(Join-Path $projectRoot '使用教學.html');docs" `
    (Join-Path $projectRoot 'app.py')

if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed (exit $LASTEXITCODE). Close the old app and retry." }
if (-not (Test-Path "$OutputDirectory\GameTranslator.exe")) { throw "EXE was not produced." }

# Optional GPU runtime stays beside the EXE, avoiding a multi-gigabyte onefile.
foreach ($package in @('cublas', 'cudnn')) {
    $source = Join-Path $projectRoot "runtime\nvidia\$package\bin"
    if (Test-Path $source) {
        $destination = Join-Path $OutputDirectory "runtime\nvidia\$package\bin"
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
        Copy-Item -Path "$source\*.dll" -Destination $destination -Force
    }
}
foreach ($metadata in Get-ChildItem -Path "$projectRoot\runtime" -Directory -Filter 'nvidia_*.dist-info' -ErrorAction SilentlyContinue) {
    $license = Join-Path $metadata.FullName 'License.txt'
    if (Test-Path $license) {
        $licenseDirectory = Join-Path $OutputDirectory 'runtime\licenses'
        New-Item -ItemType Directory -Force -Path $licenseDirectory | Out-Null
        Copy-Item -LiteralPath $license -Destination (Join-Path $licenseDirectory "$($metadata.Name)-License.txt") -Force
    }
}

Write-Host "Built $OutputDirectory\GameTranslator.exe"
New-Item -ItemType Directory -Force -Path (Join-Path $OutputDirectory 'docs') | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot '使用教學.html') -Destination (Join-Path $OutputDirectory 'docs\使用教學.html') -Force
} finally { Set-Location $buildCallerLocation }
