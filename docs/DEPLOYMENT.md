# GitHub publication and self-hosting

GitHub stores source and runs checks. GitHub Pages serves static files; it cannot host FastAPI, SQLite, Ollama, Whisper, Piper or Asterisk. This repository does not publish a misleading static dashboard that has no backend.

## Docker application package

The package contains the built React dashboard and FastAPI in one non-root container. It supports CRM, scripted demos, OpenStreetMap discovery and operations. AI model downloads, speech dependencies and Asterisk are separate opt-in local services; the base image does not include them or activate telephony.

Prerequisites: Docker with Compose, sufficient disk/RAM, and a private owner key. No paid hosting or cloud account is required for local use.

Linux:

```bash
export AKKI_ADMIN_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
docker compose -f deploy/compose.yaml up --build -d
```

PowerShell:

```powershell
$env:AKKI_ADMIN_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose -f deploy/compose.yaml up --build -d
```

Open `http://localhost:8000`, enter the private key and create a fictional lead first. Store your key securely across restarts. Compose requires a configured key, publishes only loopback, keeps SQLite in a named persistent volume, runs with a read-only root filesystem and drops Linux capabilities. Do not use `docker compose down -v` unless you intend to delete the database volume.

The Docker image and same-origin browser flow have been tested on Linux. Docker Desktop/WSL2 and Windows speech/PBX have not been tested. The Windows CI job checks the portable core and frontend build; verify its result at the published commit. The existing native Windows Python/React setup remains documented in the README; speech/telephony compatibility is unverified.

For remote operation, choose a machine that can stay on, protect it with a VPN or HTTPS reverse proxy, add your exact origin to `AKKI_ALLOWED_ORIGINS`, and set `AKKI_SECURE_COOKIES=1`. The supplied Compose file deliberately binds to loopback. No cloud deployment, public domain, certificate or always-on host is provisioned here. Hosting and electricity can incur costs. Laptop-hosted services stop when the laptop is off.

## Local AI and PBX

Use [local model setup](LOCAL_AI.md), [speech setup](LOCAL_SPEECH.md), and [private SIP bridge setup](SIP_AI_BRIDGE.md) on the host. The model endpoint is fixed to loopback. The base Docker container's loopback is its own namespace, so host Ollama cannot be reached from that image without a separately designed private network configuration. Do not expose Ollama publicly to work around this.

## GitHub checks

GitHub Actions runs the backend test suite, frontend production build and application-container smoke test. Optional model downloads and real telephony are excluded from CI. The tests use fictional records and mocks; they do not call businesses. All contact databases, runtime credentials, model weights and audio files are ignored by Git.

## Remaining production gates

- Human English speech/noise/interruptions evaluation and lower end-to-end latency.
- Hindi/Telugu model and voice selection, licensing and quality tests.
- Windows/WSL2 verification and a usable isolated human softphone network.
- Licensed Indian PSTN connectivity and real human transfer. The implemented approved private queue can call only test endpoint 1001; its quotas and developer follow-up handoff are documented in CALL_QUEUE.md.
- Commercial telecom eligibility, current India-specific consent/promotional requirements and recording/privacy policy review.
- Authenticated hosting with HTTPS, persistent backups, monitoring and operating-cost approval.
- Account lifecycle/MFA, tamper-resistant audit logging, backup retention/erasure operations and security review.
- Google Places integration only after its terms, retention restrictions and billing are approved. OpenStreetMap discovery is available now.

The software is a tested self-hosted prototype, not a completed commercial telephone service.
