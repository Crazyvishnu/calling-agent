# Verification — discovery and private SIP/AI milestones, 2026-10-09

Baseline repository commit: `9c596fa344825da760c06db6a4484ceeb54b805a`.
The original main GitHub Actions run was successful:
<https://github.com/Crazyvishnu/calling-agent/actions/runs/37823298580>.
The release verification below covers local checks. See the Actions page for CI at the published commit. Environment: Linux, Python 3.12,
Node 24.19, Chromium, Ollama 0.40.1/Qwen3 1.7B on CPU, faster-whisper 1.2.1,
Piper 1.8.0, Asterisk 20.6 in a local Docker container.


## Business discovery milestone

- **48 backend tests passed** including six discovery tests covering response parsing,
  source errors/partial results, safe website links, review/selection/expiry gates,
  consent injection rejection, rate/caching bounds, duplicate imports and DNC preservation.
- Live OpenStreetMap Overpass search around central Hyderabad returned 10 restaurant
  records; 9 contained no website tag. Missing tags do not prove absent websites.
- Browser → Vite → FastAPI → real OSM search displayed 10 records. Search created
  **zero CRM leads**; no real records were imported or contacted in this test.
- Browser search/filter/review/import → API → SQLite was separately exercised with
  fictional provider fixtures. Provenance persisted, unconsented demo calls were blocked,
  duplicates became unselectable and the lead directory displayed the imported fixture.
- 390px layout checked without overflow or browser runtime errors; mobile sidebar
  navigation icons remain available. Frontend production build passed.
- Google Maps/Places is not connected. No paid service, billing account, API credential
  or messaging/calling workflow was activated. New changes remain local.

## Current bridge milestone

- **42 backend tests passed**, including all original tests, AudioSocket framing,
  waveform pacing/cancellation, missing/revoked consent, single-call admission,
  authenticated relay duplex forwarding, UUID rejection and early-worker cancellation.
- Frontend build passed. Browser reserve/disconnect controls exercised through the
  actual Vite → API → speech WebSocket → relay. Typed replies were disabled while SIP
  owned the session and restored after disconnect. No browser runtime errors or
  overflow at 390px were observed.
- Actual synthetic SIP → Asterisk → AudioSocket → local Whisper/Ollama/Piper → SIP
  conversation passed. The AI opening, contextual reply and opt-out closing all reached
  the caller as PCMU RTP. Recognized menu and **12,000 rupees** budget were persisted.
  Spoken opt-out set DNC, disabled contact, closed the session and ended the SIP call.
- Received synthetic SIP audio was explicitly inspected in a temporary test: local STT
  recognized the AI introduction (including “AI Assistant”) and the generated design
  question. This establishes intelligible wiring, not perceptual quality or human accuracy.
- Speaking opt-out during the AI reply cut received reply audio from about 28,000 PCMU
  bytes in the complete-reply test to 3,040 bytes, then delivered closing speech and
  enforced DNC. Synthetic barge-in only; room echo/headsets/real people are unverified.
- A separate actual SIP caller hung up while call status was `thinking`; revision stayed
  **0**, no partial turn was saved and the reservation cleared.
- The committed reproducible helper passed:
  `python -m scripts.check_sip_ai --run-private-test --hangup-during-inference`.
  Full exchange and barge-in were also exercised with the same synthetic SIP caller.
- The original two-user SIP test still passed after bridge changes: 99 and 100 expected
  audio packets received, wrong password and external destination rejected, clean hangup.

Compact extraction with entirely optional fields initially missed timeline. Four required
core fields were restored and the successful two-turn check retained menu, budget,
timeline and callback. CPU thread limiting gave a successful callback turn of 5.39 s
versus 7.13 s in the earlier warm check; model cold loads affected first-turn comparisons.
The model remains local and all drafts require review.

Matching warm-up and inference thread/context options removed an in-call reload. A
successful qualification measured **673 ms STT + 4656 ms model + 1377 ms TTS = 6708 ms**
after endpointing, versus **11200 ms** before that correction. Opt-out bypassed the model:
2572 ms including recognition and TTS. Add utterance duration and 600 ms endpoint
silence. These are observations on this CPU, not controlled benchmarks or guaranteed
latency. They remain too slow for natural customer conversations.

The verified bridge is **Linux only** with a protected shared Unix socket. Docker's
internal network did not activate configured localhost publishing, so the synthetic SIP
caller runs inside the container. Native Windows, WSL2, human softphones, human speech,
Hindi/Telugu, production security and telecom authorization remain unverified. No PSTN,
paid service or outbound campaign was activated. No changes were pushed to GitHub.

## Earlier speech and separate SIP baseline

The sections below describe the preceding milestone before the media bridge was added.
Their measurements remain historical context, not the current feature inventory.

## Regression and transport checks

- `python -m unittest discover -s tests -v`: **31 tests passed**, including five
  original tests. Additional coverage includes consent, decline/DNC, stale revisions,
  canceled turns without persistence, PCM/VAD bounds, origin and microphone permission
  gates, suppression despite TTS failure, and streamed model response cleanup.
- `npm ci --no-audit --no-fund` and `npm run build`: passed. Build rerun after voice UI.
- Browser → Vite WebSocket proxy → FastAPI → local STT/model/TTS → SQLite → browser
  playback exercised with a synthetic English microphone clip and fictional lead.
  Recognition: “I need a restaurant website with a menu. My budget is 12,000 rupees.”
  Persisted draft: menu, budget 12000. Budget grounding accepts comma-separated
  thousands while rejecting a partial amount such as 2000 inside 12000.
- Browser manual interrupt stopped playback; Stop microphone left the capture track
  in `ended` state. No runtime errors or overflow at 390px viewport were observed.
  This checks pipeline wiring with synthetic input, not human microphone accuracy
  or perceptual voice quality.
- Live WebSocket check interrupted an in-flight local model turn: interrupt event
  acknowledgement about 6 ms; canceled turn did not increment persisted revision.
  Offline VAD tests separately exercise detected speech onset during pending inference.
- Previous text-lab browser checks exercised scripted simulation, saved-session reopen,
  end/delete, DNC enforcement, actual English extraction and callback memory.

## Measured CPU latency

The two-turn English text smoke check before prompt/schema reduction took 31.60 s and
20.34 s. A successful optimized check took 6.56 s and 6.51 s with the same model/CPU.
An initial optimization dropped callback extraction; prompt correction and a subsequent
successful two-turn check verified the callback alongside budget, timeline and menu.
These are smoke observations, not controlled benchmarks or reliability guarantees.

The final synthetic-microphone browser turn measured STT 1541 ms, model 4761 ms, TTS
2072 ms: **8376 ms total after endpointing**, in addition to the spoken utterance and
600 ms silence threshold. A separate earlier live transport turn took 9753 ms. First
model loads and hardware differences affect these values. This remains too slow for
natural telephone dialogue. Speech recognition and synthesis are utterance-based;
only model tokens and microphone frames stream. TTS is a completed WAV before playback.

Reproduce local checks with `python -m scripts.check_local_model` and
`python -m scripts.check_local_speech` after explicitly installing/downloading assets.
The speech smoke uses fictional synthesized speech, processes audio in memory and
stores no recording. It does not establish real-user accuracy.

## Actual private SIP call

`docker compose exec -T asterisk python3 /opt/akki/sip_smoke.py` passed:

- Both private users authenticated and registered; incorrect password rejected.
- Authenticated 1001 → 1002 SIP call answered.
- 100 expected RTP/PCMU audio payload packets received by each user (200 total).
- BYE/hangup completed on both legs.
- An external-style telephone destination was rejected with 404; no PSTN trunk exists.

This was an actual Asterisk SIP/RTP call with two simulated consenting endpoints inside
an isolated Linux container. It was not a mobile/landline call or an AI SIP conversation.
The subsequent AudioSocket milestone below connects the PBX and local speech engine. An outbound dialer and production carrier integration remain unimplemented.

## Practical limits

English alone was exercised. Human speech, noisy rooms, headset barge-in, Hindi/Telugu,
Windows/Docker Desktop, human softphones, public deployment and commercial telecom
eligibility remain unverified. Energy detection is vulnerable to noise/echo, canceled
STT/TTS kernels may finish in the background, and all generated drafts need human review.
The API now supports single-owner authentication; production multi-user roles and complete security auditing remain absent. Use one Uvicorn worker for this lab.
No provider account, paid service, carrier trunk, deployment or customer outreach was
activated. Downloaded models, private credentials, audio and databases are excluded
from the source archive. The software uses laptop compute and stops when it is off.

Piper software is GPL-3.0; the selected LJSpeech model card describes public-domain
training data. Licenses require separate review before distributing components.
The installed FastAPI/Starlette emits a legacy httpx TestClient deprecation warning;
the suite passed. Dependency pinning should be addressed in stabilization work.


## Owner access and application packaging milestone — 2026-10-09

- **55 backend tests passed**, covering owner HTTP/WebSocket gates, cookie login and CSRF rejection, logout, login throttling, timezone conversion, callback permissions after DNC, notification deduplication and revocation, ambiguous-delivery handling, backup permissions, transcript retention and duplicate-phone DNC propagation, alongside all prior regression tests.
- React production build passed. Built same-origin dashboard browser check passed: owner login → fictional lead → callback reminder → SQLite persistence and audit event → completion → logout and unauthorized API rejection. No browser runtime errors; 390px layout had no overflow.
- Non-root Docker application built successfully. A read-only container with dropped capabilities served the dashboard, blocked unauthenticated records, accepted owner login and CSRF-protected lead creation, and stored fictional records in a persistent volume. The package requires a configured owner key.
- Telegram sends were mocked in tests. No real Telegram messages, paid services, customer outreach or PSTN connection were activated. Manual notification delivery is opt-in and unverified with a real bot.
- Public hosting, human voice testing, Hindi/Telugu, Windows and commercial telecom eligibility remain unverified. GitHub publication is source hosting, not a running AI/PBX deployment.

## Final feature scope

See [deployment gates](DEPLOYMENT.md) for what remains. The project is a self-hosted prototype with a private SIP media bridge, not a finished commercial calling platform. Current media latency still needs improvement. The initial base Docker package hosts CRM/API only; separately installed host models and PBX are documented and are not bundled in that image.


## Private outbound queue and reviewed CRM milestone

See [latest test report](TEST_RESULTS.md) for 67 backend tests, actual approved outbound SIP, interruption/hangup evidence, measured latency, browser flow and remaining production gates. [Private queue setup](CALL_QUEUE.md) supersedes the earlier inbound-only scope.
