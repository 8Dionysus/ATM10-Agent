param(
    [ValidateSet("retrieve", "eval")]
    [string]$Mode = "retrieve",
    [string]$Query = "steel tools",
    [string]$InputPath = "data/ftbquests_norm/quests.jsonl",
    [string]$EvalDocsPath = "tests/fixtures/retrieval_docs_sample.jsonl",
    [string]$EvalCasesPath = "tests/fixtures/retrieval_eval_sample.jsonl",
    [string]$Device = "GPU",
    [int]$TopK = 5,
    [int]$CandidateK = 10,
    [int]$RerankerMaxLength = 512,
    [string]$RerankerModel = "Qwen/Qwen3-Reranker-0.6B"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Python not found: $python. Create/activate .venv first."
}

$vsDevCmd = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\Common7\Tools\VsDevCmd.bat"
if (-not (Test-Path $vsDevCmd)) {
    throw "VsDevCmd not found at '$vsDevCmd'. Install Visual Studio Build Tools (C++ workload)."
}

function Import-VsDevCmdEnvironment {
    param([string]$BatchPath)

    $dump = cmd.exe /s /c "`"$BatchPath`" -arch=amd64 && set"
    foreach ($line in $dump) {
        if ($line -match "^(.*?)=(.*)$") {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

Import-VsDevCmdEnvironment -BatchPath $vsDevCmd

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$args = @()
if ($Mode -eq "retrieve") {
    $args += @(
        "scripts/retrieve_demo.py",
        "--query", $Query,
        "--in", $InputPath
    )
} else {
    $args += @(
        "scripts/eval_retrieval.py",
        "--docs", $EvalDocsPath,
        "--eval", $EvalCasesPath
    )
}

$args += @(
    "--topk", "$TopK",
    "--candidate-k", "$CandidateK",
    "--reranker", "qwen3",
    "--reranker-runtime", "openvino",
    "--reranker-device", $Device,
    "--reranker-model", $RerankerModel,
    "--reranker-max-length", "$RerankerMaxLength"
)

Push-Location $repoRoot
try {
    Write-Host "[run_qwen3_openvino] mode: $Mode"
    Write-Host "[run_qwen3_openvino] device: $Device"
    Write-Host "[run_qwen3_openvino] python: $python"
    & $python @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
