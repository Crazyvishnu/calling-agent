# Akki release test results — 2026-10-09

**Result: the local application and private SIP workflow pass the tests below. The commercial production project remains incomplete.** No paid service, public telephone connection, real customer outreach or Telegram delivery was activated.

Environment: Linux, Python 3.12, Node 24, Chromium, Asterisk 20.6, local CPU Ollama/Qwen3 1.7B, faster-whisper/base.en INT8 and Piper LJSpeech high. Backend credentials, databases, model weights and audio fixtures are excluded from GitHub.

| Check | Result | Evidence and scope |
|---|---|---|
| Full backend suite | **76 passed** | `python -m unittest discover -s tests -v`; includes private export/erasure, durable quota regression, authentication, consent/DNC, quota, queue lifecycle, review, notifications, media and relay tests |
| Portable backend subset | **63 passed locally** | Same selected modules are run on the Windows CI runner; Unix relay/media tests are excluded there |
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
- Hindi/Telugu model/voice quality, multilingual speech evaluation and real human phone transfer.
- Native Windows speech/PBX, Docker Desktop/WSL2, host softphone access and Windows NTFS permissions. Windows CI covers the portable core and frontend build only.
- Licensed Indian PSTN trunk, commercial telecom eligibility, promotional calling/recording/privacy requirements and carrier spend limits.
- Actual always-on host, HTTPS/domain, private storage/backup operations and deployment monitoring. GitHub publishes source and checks; it does not run the AI/PBX stack.
- Account lifecycle/MFA, comprehensive/tamper-resistant audit, backup erasure/retention operations and production security review.
- Google Places integration and its billing/retention permissions. OpenStreetMap discovery is implemented; Google Maps is not connected.

Read [private queue setup](CALL_QUEUE.md), [operations](OPERATIONS.md), and [deployment gates](DEPLOYMENT.md). The completed deliverable is a tested self-hosted prototype, not a licensed commercial telecom service.

Windows CI exposed a backup file-handle leak: SQLite connection context managers commit/rollback but do not close the connection. The maintenance command now closes the destination explicitly. POSIX database files also use mode 0600; Windows ACL validation remains separate. Verify the corrected release run in Actions.

Current privacy regression tests also verify isolated export, active-call erasure rejection, permanent reimport suppression and call quotas surviving transcript deletion. Historical voice measurements above were not repeated for this privacy-only change.

This release also passed the packaged dashboard privacy flow in Chromium: owner login, fictional record creation, private JSON download, confirmed erasure, 390px mobile layout and no runtime errors. Microphone erasure blocking and logout revocation have automated regression coverage. The complete speech/PBX measurements remain from the previous voice release.

Named owner/operator/viewer permission tests pass, covering owner-only consent grants, call approval/dispatch, private export/erasure, read-only viewer media rejection, account audit attribution, cookie CSRF, key rotation, role downgrade and invalid configuration.
