[CmdletBinding()]
param([switch]$Multilingual)
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $project
function Check-Exit([string]$Step) { if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE" } }
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { throw 'Install Python 3.12 and add it to PATH first.' }
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js LTS first.' }
python -c "import sys; assert sys.version_info[:2] in ((3,11),(3,12)), 'Use Python 3.11 or 3.12 for this validated stack'"
Check-Exit 'Python version'
python -m venv .venv
Check-Exit 'Virtual environment'
$python = Join-Path $project '.venv\Scripts\python.exe'
& $python -m pip install -r backend/requirements-speech.txt
Check-Exit 'Speech dependencies'
Push-Location frontend
try { npm.cmd ci --no-audit --no-fund; Check-Exit 'Frontend dependencies'; npm.cmd run build; Check-Exit 'Frontend build' } finally { Pop-Location }
if ($Multilingual) {
  & $python -m scripts.setup_speech --download --languages en hi te --stt-model small
} else { & $python -m scripts.setup_speech --download }
Check-Exit 'Speech assets'
if (-not (Test-Path .env)) {
  $accessKey = & $python -c 'import secrets; print(secrets.token_urlsafe(32))'
  Check-Exit 'Owner credential generation'
  $lines = @('AKKI_REQUIRE_AUTH=1', "AKKI_ADMIN_KEY=$accessKey", 'AKKI_ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,https://localhost', 'OLLAMA_MODEL=qwen3:1.7b', 'OLLAMA_NUM_THREADS=2', 'AKKI_ENDPOINT_SILENCE_MS=400', 'STT_DEVICE=cpu', 'STT_COMPUTE_TYPE=int8', 'AKKI_SIP_LAB=0', 'GOOGLE_PLACES_ENABLED=0', 'GOOGLE_PLACES_DAILY_LIMIT=0')
  if ($Multilingual) { $lines += @('STT_MODEL_PATH=backend/models/whisper-small', 'STT_LANGUAGES=en,hi,te', 'TTS_BACKEND_HI=espeak', 'PIPER_VOICE_TE_PATH=backend/models/te_IN-padmavathi-medium.onnx') }
  [IO.File]::WriteAllLines((Join-Path $project '.env'), $lines, [Text.UTF8Encoding]::new($false))
  # Keep generated credentials private to this Windows account and SYSTEM.
  $account = [Security.Principal.WindowsIdentity]::GetCurrent().Name
  & icacls.exe (Join-Path $project '.env') /inheritance:r /grant:r "${account}:(F)" 'SYSTEM:(F)' | Out-Null
  Check-Exit 'Credential file permissions'
}
if (Get-Command ollama -ErrorAction SilentlyContinue) {
  ollama pull qwen3:1.7b
  Check-Exit 'Local language model download'
} else { Write-Warning 'Install Ollama for Windows, then run ollama pull qwen3:1.7b. No model API subscription is needed.' }
Write-Host 'Setup complete. Existing .env settings were preserved. For Hindi install eSpeak NG. Read docs/WINDOWS_3050.md before starting.'
