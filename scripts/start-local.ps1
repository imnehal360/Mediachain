param(
    [switch]$NoReload
)

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

$environmentFile = Join-Path $projectRoot ".env"
if (-not (Test-Path -LiteralPath $environmentFile)) {
    throw "Missing .env. Run the local setup first."
}

foreach ($line in Get-Content -LiteralPath $environmentFile) {
    $trimmed = $line.Trim()
    if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
    $separator = $trimmed.IndexOf("=")
    if ($separator -lt 1) { continue }
    $name = $trimmed.Substring(0, $separator).Trim()
    $value = $trimmed.Substring($separator + 1).Trim()
    [Environment]::SetEnvironmentVariable($name, $value, "Process")
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv Python interpreter."
}
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "frontend\dist\index.html"))) {
    throw "The frontend has not been built. Run .\scripts\setup-local.ps1 first."
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
        throw "Ollama was not found."
    }
}
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 3 | Out-Null
}
catch {
    Write-Host "Starting the local Ollama service..."
    Start-Process -FilePath $ollamaExecutable -ArgumentList "serve" -WindowStyle Hidden
    $ready = $false
    foreach ($attempt in 1..20) {
        Start-Sleep -Milliseconds 500
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 2 | Out-Null
            $ready = $true
            break
        }
        catch { }
    }
    if (-not $ready) { throw "Ollama did not become ready." }
}

$keyMap = $env:MEDIACHAIN_API_KEYS | ConvertFrom-Json
$workspaceKey = $keyMap.PSObject.Properties | Select-Object -First 1 -ExpandProperty Name

Write-Host "Mediachain will be available at http://127.0.0.1:8000"
Write-Host "Workspace key: $workspaceKey"
Write-Host "Press Ctrl+C to stop the server."

$arguments = @(
    "-m", "uvicorn", "mediachain.runtime.server:app",
    "--host", "127.0.0.1", "--port", "8000"
)
if (-not $NoReload) { $arguments += "--reload" }
& $python @arguments
