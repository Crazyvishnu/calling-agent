# Private Asterisk SIP-to-SIP lab

This lab registers two test users, calls extension 1002 from 1001, exchanges PCMU
audio through Asterisk in both directions and hangs up. It has no telephone trunk,
external dialplan, production recording or public-number calling capability. An optional [AI media bridge](SIP_AI_BRIDGE.md) connects a reserved consented session.
Only consenting test users belong in this lab.

## Run

Install Docker Desktop with its Linux container engine on Windows (WSL2), or Docker
Engine plus Compose on Linux. From the project root with Python available:

```powershell
python -m scripts.setup_telephony
cd telephony
docker compose up --build -d
docker compose exec -T asterisk python3 /opt/akki/sip_smoke.py
```

The setup script generates random credentials and configuration in gitignored
`telephony/runtime`. The smoke check prints outcomes, never credentials. It verifies
two authenticated registrations, rejection of a wrong password, rejection of an
external-style destination, a private call, received audio packets in both directions
and clean hangup. Test traffic stays within the isolated container network.

Stop and remove the test container when done:

```powershell
docker compose down
```

The container runs without root privileges, on an internal Docker network, with
read-only configuration and temporary runtime storage. SIP UDP 5060 and RTP UDP
10000–10019 are configured for loopback publishing only. In the tested Docker 28
internal network, these mappings were not activated; the automated test stays inside
the container. HTTP/ARI and AMI administration are
disabled. Do not replace loopback bindings with public bindings or add a trunk.
The image downloads free Ubuntu/Asterisk packages; bandwidth, Docker licensing for
your organization, computer resources and electricity still need consideration.

## Optional human softphone check

This check is not yet verified. First verify loopback publishing works with your
Docker version; the tested internal network did not expose host ports. Do not weaken
isolation or expose SIP publicly. With a working private local connection, use two SIP clients on this same computer
with accounts 1001 and 1002, server `127.0.0.1:5060`, UDP and PCMU/G.711 u-law.
Read each password locally from `runtime/credentials.json`; never paste that file
into chat, logs, screenshots or GitHub. Dial 1002 from 1001, or 600 for echo testing.
Only one registration per user is configured. Human softphone audio and Docker
Desktop networking on Windows have not been verified; the automated call was
verified inside the Linux container. SIP is unencrypted in this isolated lab.

## AI bridge and next steps

The [Linux AudioSocket bridge](SIP_AI_BRIDGE.md) now connects the AI engine to this PBX.
Continue evaluating PCMU↔16 kHz PCM conversion, packet pacing,
generation cancellation, opt-out/hangup cleanup and human speech before adding a
call queue. Do not enable a carrier connection as part of that work. Ordinary Indian
telephone numbers still need an authorized provider and applicable telecom consent,
registration and commercial calling requirements, plus explicit spending approval.
