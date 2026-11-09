param([Parameter(Mandatory=$true)][string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
$speaker.Rate = 0
try {
    $available = @($speaker.GetInstalledVoices() | Where-Object {$_.Enabled} | ForEach-Object {$_.VoiceInfo.Name})
    foreach ($required in @('Microsoft Hanhan Desktop','Microsoft Zira Desktop')) {
        if ($required -notin $available) {
            throw "Required local voice unavailable: $required. No files generated."
        }
    }
    $samples = @(
        @{ Name='chinese_only'; Parts=@(@{Voice='Microsoft Hanhan Desktop';Text='請等一下，我們從右邊過去。不要刪除這個檔案。'}) },
        @{ Name='english_only'; Parts=@(@{Voice='Microsoft Zira Desktop';Text='Please wait here. Watch the right side.'}) },
        @{ Name='mixed'; Parts=@(@{Voice='Microsoft Hanhan Desktop';Text='請等一下，'},@{Voice='Microsoft Zira Desktop';Text='watch the right side.'},@{Voice='Microsoft Hanhan Desktop';Text='我們一起過去。'}) }
    )
    foreach ($sample in $samples) {
        $builder = New-Object System.Speech.Synthesis.PromptBuilder
        foreach ($part in $sample.Parts) {
            $builder.StartVoice([string]$part.Voice)
            $builder.AppendText([string]$part.Text)
            $builder.EndVoice()
        }
        $speaker.SetOutputToWaveFile((Join-Path $OutputDirectory ($sample.Name+'.wav')))
        $speaker.Speak($builder)
        $speaker.SetOutputToNull()
        Write-Output ('Created '+$sample.Name+'.wav')
    }
} finally { $speaker.Dispose() }
