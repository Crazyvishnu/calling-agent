[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
Set-Location $project
$memory = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
Write-Host "System RAM: $memory GB. On 8 GB, keep Whisper on CPU and close heavy applications."
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader }
else { Write-Warning 'NVIDIA driver tools unavailable; GPU offload is not verified.' }
try {
  $loaded = Invoke-RestMethod http://127.0.0.1:11434/api/ps -TimeoutSec 5
  foreach ($model in $loaded.models) { Write-Host ('Model: {0}; GPU memory: {1} MiB' -f $model.name,[math]::Round($model.size_vram/1MB)) }
  if (-not $loaded.models) { Write-Warning 'No model loaded yet. Run a fictional conversation, then check again.' }
} catch { Write-Warning 'Ollama is not running.' }
$python = Join-Path $project '.venv\Scripts\python.exe'
if (Test-Path $python) { & $python -c "import platform; print('Python:', platform.python_version()); import faster_whisper,piper; print('Speech packages: import OK')" }
Write-Host 'This check does not certify microphone quality, RTX inference performance or telephone access.'
