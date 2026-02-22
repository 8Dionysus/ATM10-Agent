param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8765,
    [string]$AsrModelDir = "models\whisper-large-v3-turbo-ov",
    [string]$WarmupAudio = "",
    [string]$WarmupLanguage = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

$args = @(
    "scripts/voice_runtime_service.py",
    "--host", $BindHost,
    "--port", "$Port",
    "--asr-backend", "whisper_genai",
    "--asr-model", $AsrModelDir,
    "--asr-device", "NPU",
    "--asr-task", "transcribe",
    "--asr-warmup-request",
    "--no-preload-asr",
    "--no-preload-tts"
)

if (-not [string]::IsNullOrWhiteSpace($WarmupAudio)) {
    $args += @("--asr-warmup-audio", $WarmupAudio)
}
if (-not [string]::IsNullOrWhiteSpace($WarmupLanguage)) {
    $args += @("--asr-warmup-language", $WarmupLanguage)
}

Write-Host "[start_voice_whisper_npu] python: $pythonExe"
Write-Host "[start_voice_whisper_npu] launching whisper_genai NPU service on http://$BindHost`:$Port"
& $pythonExe @args
