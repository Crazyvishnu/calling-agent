# Akki release test results — 2026-10-09

**Result: the local application and private SIP workflow pass the tests below. The commercial production project remains incomplete.** No paid service, public telephone connection, real customer outreach or Telegram delivery was activated.

Environment: Linux, Python 3.12, Node 24, Chromium, Asterisk 20.6, local CPU Ollama/Qwen3 1.7B, faster-whisper/base.en INT8 and Piper LJSpeech high. Backend credentials, databases, model weights and audio fixtures are excluded from GitHub.

| Check | Result | Evidence and scope |
|---|---|---|
| Full backend suite | **86 passed** | `python -m unittest discover -s tests -v`; includes private export/erasure, durable quota regression, authentication, consent/DNC, quota, queue lifecycle, review, notifications, media and relay tests |
| Portable backend subset | **73 passed locally** | Same selected modules are run on the Windows CI runner; Unix relay/media tests are excluded there |
| React production build | **Passed** | `npm run build`; bundled dashboard serves from FastAPI |
| Browser application flow | **Passed** | Owner login → new fictional lead/session → approved queue/cancel → actual local LLM turn → explicit human review → structured SQLite record → pending notification → developer handoff |
| Mobile layout | **Passed** | 390px viewport, no horizontal overflow or browser runtime errors in the tested flow |
| Asterisk SIP/RTP baseline | **Passed** | Both authenticated test users registered; 100 verified audio packets each direction; bad password rejected; external destination rejected with 404; BYE completed |
| Actual private outbound AI call | **Passed** | Backend queue originated to registered 1001; two-way AudioSocket/Whisper/Ollama/Piper; menu/budget extracted; opt-out persisted; clean hangup; reservation released |
| Interruption/opt-out during playback | **Passed** | Reply cut to 3,040 PCMU bytes, opt-out saved, later contact blocked, clean termination |
| Hangup during inference | **Passed** | Caller hung up while model was thinking; no reply audio; saved revision **0**; reservation released |
| Telegram delivery | **Mock tests passed; real bot unverified** | Disabled delivery, deduplication, revoked consent and ambiguous timeouts tested without sending a message |
| GitHub CI | **See exact release run in Actions** | Linux suite, frontend, Docker app smoke and Windows portable/backend/frontend jobs; final result must match the published commit |

## Measured voice latency

These are individual synthetic English samples on this CPU, not a benchmark percentile or human-quality result. Durations begin after endpoint detection; add approximately 600 ms configured endpoint silence, network scheduling, audio playback and any cold model loading. Initial cold/noisy-load samples can exceed 11 seconds.

| Scenario | STT | Model | TTS | Total processing |
|---|---:|---:|---:|---:|
| Warm private outbound qualification | 711 ms | 4,411 ms | 1,440 ms | **6,564 ms** |
| Warm qualification before barge-in | 719 ms | 4,183 ms | 1,376 ms | **6,279 ms** |
| First opt-out closing in that process | 689 ms | 2 ms | 1,812 ms | **2,506 ms** |
| Repeated opt-out with generic-prompt cache | 672 ms | 2 ms | 1 ms | **678 ms** |

Only fixed generic application prompts are cached in memory. Customer-derived replies are not added to this cache. This measurably reduces repeated closing-prompt synthesis; general model reply latency is still too high for dependable natural sales calls.

## Remaining unverified or unimplemented work

- Human speech, Indian English accents, noise/echo, headset interruptions and conversation accuracy.
- Hindi/Telugu human quality and real human phone transfer. Synthetic recognition accuracy failed; see the measurements below.
- Physical Windows PC microphone/GPU/PBX, Docker Desktop/WSL2, host softphone access and Windows NTFS permissions. A separate Windows workflow exercises actual synthetic synthesis/recognition; its success certifies execution, not language accuracy.
- Licensed Indian PSTN trunk, commercial telecom eligibility, promotional calling/recording/privacy requirements and carrier spend limits.
- Actual always-on host and public domain, private storage/backup operations and deployment monitoring. Local CA-verified HTTPS, secure cookies and authenticated WSS were tested in Docker; this is not public hosting. GitHub publishes source and checks; it does not run the AI/PBX stack.
- Account lifecycle/MFA, comprehensive/tamper-resistant audit, backup erasure/retention operations and production security review.
- Live Google Places access and billing/terms approval. Optional IDs-only integration passes mocked tests and is disabled by default. OpenStreetMap remains the active discovery source; no paid Google request was made.

Read [private queue setup](CALL_QUEUE.md), [operations](OPERATIONS.md), and [deployment gates](DEPLOYMENT.md). The completed deliverable is a tested self-hosted prototype, not a licensed commercial telecom service.

Windows CI exposed a backup file-handle leak: SQLite connection context managers commit/rollback but do not close the connection. The maintenance command now closes the destination explicitly. POSIX database files also use mode 0600; Windows ACL validation remains separate. Verify the corrected release run in Actions.

Current privacy regression tests also verify isolated export, active-call erasure rejection, permanent reimport suppression and call quotas surviving transcript deletion. Historical voice measurements above were not repeated for this privacy-only change.

This release also passed the packaged dashboard privacy flow in Chromium: owner login, fictional record creation, private JSON download, confirmed erasure, 390px mobile layout and no runtime errors. Microphone erasure blocking and logout revocation have automated regression coverage. The complete speech/PBX measurements remain from the previous voice release.

Named owner/operator/viewer permission tests pass, covering owner-only consent grants, call approval/dispatch, private export/erasure, read-only viewer media rejection, account audit attribution, cookie CSRF, key rotation, role downgrade and invalid configuration.

## This release: latency, Windows setup, multilingual and HTTPS

The 86-test Linux suite and 73-test portable subset include Google gates/quotas, language-specific fixed replies, configurable endpoint timing, speech warm-up and connection cleanup. React production build passed. CA-verified Docker HTTPS smoke passed dashboard, owner login, Secure cookie, cross-origin rejection, CRM write and authenticated voice WebSocket upgrade. No TLS verification was disabled.

Actual English API preparation measured **6,016 ms initially and 640 ms on repeat**. The optional Windows profile reduces endpoint silence from 600 to 400 ms; that may cut off pauses and requires human testing. One resident Ollama model and one parallel request bound memory on the 8 GB target. A 0.6B model was faster but extracted requirements inaccurately, so the default remains Qwen3 1.7B. Two bounded-memory model turns measured 9.93 and 7.36 seconds; general conversational latency has not passed acceptance.

Linux synthetic speech (fictional fixtures; not human recordings):

| STT model | Language | TTS / STT ms | Word error rate | Outcome |
|---|---|---:|---:|---|
| base INT8 | English | 2,868 / 1,436 | 0.154 | Pipeline executed; numeral formatting contributes to errors |
| base INT8 | Hindi / eSpeak | 56 / 795 | 1.000 | Accuracy failed; wrong script |
| base INT8 | Telugu / Piper | 1,176 / 988 | 1.000 | Accuracy failed; wrong script |
| small INT8 | English | 3,127 / 5,208 | 0.154 | Pipeline executed |
| small INT8 | Hindi / eSpeak | 49 / 2,779 | 1.000 | Accuracy failed; garbled recognition |
| small INT8 | Telugu / Piper | 1,187 / 15,178 | 1.000 | Accuracy failed; garbled recognition |

Hindi uses robotic eSpeak NG; Telugu uses the CC-BY-4.0 Padmavathi voice with model-card attribution. Noncommercial Hindi Piper models are not selected. The Windows synthetic workflow uploads per-language accuracy and latency, but does not assert human-quality acceptance. Use `--max-wer` to enforce an explicit accuracy gate. Windows 11 / 8 GB / RTX 3050 4 GB setup scripts and private localhost HTTPS instructions are provided; the user's PC has not been accessed or validated.

Earlier SIP voice measurements in this report are historical and were not repeated for this release. No human voice recordings, Google credentials, licensed trunk or always-on domain were supplied. Those acceptance checks remain open.
