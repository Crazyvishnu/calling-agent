[CmdletBinding()]
param([switch]$Https)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $project
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path $python) -or -not (Test-Path .env)) { throw 'Run scripts/windows/Setup.ps1 first.' }
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_FLASH_ATTENTION = '1'
$env:OLLAMA_KV_CACHE_TYPE = 'q8_0'
$ownedOllama = $null
$ownedCaddy = $null
try {
  try { $null = Invoke-RestMethod http://127.0.0.1:11434/api/tags -TimeoutSec 3 }
  catch {
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { throw 'Install Ollama for Windows first.' }
    $ownedOllama = Start-Process ollama -ArgumentList 'serve' -PassThru -WindowStyle Hidden
  }
  if ($Https) {
    if (-not (Get-Command caddy -ErrorAction SilentlyContinue)) { throw 'Install Caddy for Windows first; see docs/WINDOWS_3050.md.' }
    $env:AKKI_SECURE_COOKIES = '1'
    $env:AKKI_ALLOWED_ORIGINS = 'https://localhost'
    $ownedCaddy = Start-Process caddy -ArgumentList @('run','--config','deploy/Caddyfile.windows') -PassThru -WindowStyle Hidden -WorkingDirectory $project
  }
  & $python -m uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000 --workers 1 --ws-max-size 65536
  if ($LASTEXITCODE -ne 0) { throw 'The backend failed. Check the displayed startup error.' }
} finally {
  if ($ownedCaddy -and -not $ownedCaddy.HasExited) { Stop-Process -Id $ownedCaddy.Id }
  if ($ownedOllama -and -not $ownedOllama.HasExited) { Stop-Process -Id $ownedOllama.Id }
}
