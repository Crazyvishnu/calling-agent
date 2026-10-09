# Windows 11, 8 GB RAM, RTX 3050 4 GB

This is the target hardware supplied by the owner. We cannot access that PC from this workspace. GitHub Windows CPU tests do not certify the physical microphone, NVIDIA driver or GPU latency.

## Install and start

Install Python **3.12**, Node.js LTS, [Ollama for Windows](https://ollama.com/download/windows), and the current NVIDIA driver. Install the Microsoft Visual C++ x64 redistributable if a speech dependency reports a missing runtime DLL. In PowerShell:

```powershell
cd "D:\experiments\akki-voice-agent"
.\scripts\windows\Setup.ps1
.\scripts\windows\Start.ps1
```

Use `Setup.ps1 -Multilingual` only for experimental Hindi/Telugu evaluation; it downloads multilingual Whisper small and Telugu Piper assets. English alone uses the lighter Whisper base.en. Install [eSpeak NG 1.52.0](https://github.com/espeak-ng/espeak-ng/releases/tag/1.52.0) for the Hindi fallback and add its executable to PATH, or set `ESPEAK_EXECUTABLE` in the private `.env` file. Hindi is robotic, and current Hindi/Telugu recognition samples failed accuracy acceptance. Keep commercial calls disabled.

If PowerShell blocks scripts, use an organization-approved execution policy; do not disable security controls globally. Setup creates a private `.env` only when absent, restricts its Windows ACL and preserves existing settings. Open that file locally to retrieve the generated `AKKI_ADMIN_KEY` for dashboard login. Never paste keys into chat or GitHub. Open `http://localhost:8000` after startup.

## Memory and latency profile

- Ollama holds **one** loaded model and handles **one** request at a time. Start sets `OLLAMA_MAX_LOADED_MODELS=1`, `OLLAMA_NUM_PARALLEL=1`, flash attention and Q8 KV cache. If Ollama is already running in the tray, quit it normally before Start.ps1 so these settings take effect.
- Use the retained Qwen3 1.7B model. A 0.6B CPU experiment was faster on some turns but omitted requirements and is not selected as the default.
- Keep faster-whisper on **CPU INT8**, leaving 4 GB VRAM for Ollama and the desktop. Do not run multiple voice sessions. Close memory-heavy applications; avoid simultaneously running Docker Desktop, a large browser workload and several AI models on 8 GB RAM.
- The launcher profile uses a 400 ms silence endpoint, 200 ms shorter than the default. It can cut off human pauses; restore `AKKI_ENDPOINT_SILENCE_MS=600` if needed. The code bounds this setting to 300–1000 ms.
- Microphone start warms models before capture. Initial warm-up can still take time. General reply latency is not yet accepted for natural telephone sales.

Run `.\scripts\windows\Check.ps1` after a fictional AI turn. `size_vram` greater than zero indicates GPU allocation; it does not prove a latency target. Measure actual microphone STT/model/TTS timings. GPU performance on the owner's RTX 3050 remains unverified.

## Private HTTPS and continued operation

Install [Caddy](https://caddyserver.com/docs/install), then run:

```powershell
.\scripts\windows\Start.ps1 -Https
```

Caddy serves **https://localhost** using its internal CA and proxies the native backend. Trust only the CA generated on your own PC using `caddy trust` in an appropriately authorized local terminal; review the certificate before trusting it. Do not disable TLS certificate verification. The configuration binds only localhost and is not a public website or public CA certificate.

Keep the Start process and the PC powered on, logged in and awake. Locking Windows is fine; shutting down, sleeping, hibernating or logging out stops service availability. You can create a Task Scheduler task for your own logon running `powershell.exe -NoProfile -File "D:\experiments\akki-voice-agent\scripts\windows\Start.ps1" -Https`, with restart-on-failure. This does not provide unattended service before first logon. Do not enable automatic login or open router ports to solve availability.

A separate always-on host is required to work while this PC is off. No such host, domain or hosting subscription has been provisioned. A public deployment still requires a domain, trusted TLS, storage/backup operations and access review. Electricity/network costs remain yours.

## Telephony

Native Windows can run the CRM and browser speech lab. The current AudioSocket bridge uses Unix sockets and requires a separate Linux/WSL2 environment for Asterisk. Windows voice tests do not validate WSL2, a human softphone or PSTN calls. With 8 GB RAM, evaluate memory headroom before adding WSL2/PBX. See [telephone prerequisites](TELEPHONE_CONNECTIVITY.md).
