param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\samples")
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null

$lines = @(
    @{ File = "directions_en.wav"; Text = "Please turn left at the next street. I will meet you at the station." },
    @{ File = "watch_right.wav"; Text = "Watch the right side." },
    @{ File = "two_at_a.wav"; Text = "Two enemies are attacking the Alpha point." },
    @{ File = "rotate_b.wav"; Text = "Move to Bravo and hold the corner." }
)

$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice.SelectVoice('Microsoft Zira Desktop')
$voice.Rate = 0
foreach ($line in $lines) {
    $path = Join-Path $OutputDirectory $line.File
    $voice.SetOutputToWaveFile($path)
    $voice.Speak($line.Text)
    $voice.SetOutputToNull()
    Write-Host "Created $path"
}
$voice.Dispose()
