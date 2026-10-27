$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $projectRoot

$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$env:Path = "$machinePath;$userPath"

$nodeDirectory = Join-Path $projectRoot ".tools\node"
if (Test-Path -LiteralPath (Join-Path $nodeDirectory "node.exe")) {
    $env:Path = "$nodeDirectory;$env:Path"
}
$ffmpegDirectory = Join-Path $projectRoot ".tools\ffmpeg"
if (Test-Path -LiteralPath (Join-Path $ffmpegDirectory "ffmpeg.exe")) {
    $env:Path = "$ffmpegDirectory;$env:Path"
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv. Create the Python environment before running local setup."
}

$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npm) {
    throw "npm was not found. Install Node.js or place portable Node in .tools\node."
}

$ollama = Get-Command ollama.exe -ErrorAction SilentlyContinue
if ($ollama) {
    $ollamaExecutable = $ollama.Source
}
else {
    $ollamaPath = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path -LiteralPath $ollamaPath) {
        $ollamaExecutable = $ollamaPath
    }
    else {
        throw "Ollama was not found. Install Ollama before running local setup."
    }
}

$ffmpeg = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
if (-not $ffmpeg) {
    throw "FFmpeg was not found."
}

if (Test-Path -LiteralPath (Join-Path $projectRoot "frontend\dist\index.html")) {
    Write-Host "The local web interface is already built."
}
else {
    Write-Host "Building the local web interface..."
    Push-Location (Join-Path $projectRoot "frontend")
    try {
        & $npm.Source ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
        & $npm.Source run build
        if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
    }
    finally {
        Pop-Location
    }
}

Write-Host "Downloading the local chat and vision model..."
& $ollamaExecutable pull qwen3-vl:2b-instruct
if ($LASTEXITCODE -ne 0) { throw "Ollama model download failed" }

Write-Host "Downloading the local embedding model..."
& $python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
if ($LASTEXITCODE -ne 0) { throw "Embedding model download failed" }

Write-Host "Downloading the local speech model..."
& $python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
if ($LASTEXITCODE -ne 0) { throw "Speech model download failed" }

Write-Host "Local setup is complete."
Write-Host "Start Mediachain with: powershell -ExecutionPolicy Bypass -File .\scripts\start-local.ps1"
