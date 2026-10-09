# Akki Voice Agent — local conversation prototype

A **local sales lead dashboard and conversation prototype** for a website-building business. The original starter includes a React dashboard, FastAPI REST API, SQLite storage, lead requirements, lead statuses, a do-not-call safeguard, and a **scripted voice-conversation simulator**.

> **Honest status:** The scripted starter is preserved. A new **local Ollama conversation lab** adds context-aware text replies, persistent sessions, and validated requirements drafts for human review, with optional browser speech. A **local English microphone prototype** adds faster-whisper, Piper and interruption detection; a separate **private Asterisk SIP-to-SIP lab** passes two-way audio testing. A **private Linux AudioSocket media bridge** now connects SIP to the local AI engine. A **business discovery dashboard** searches OpenStreetMap and imports reviewed prospects with consent unverified. Owner authentication, callback reminders, reports, minimal audit history, private backup/retention commands and a disabled-by-default Telegram outbox are included. An approved private outbound queue calls only consenting test endpoint 1001, enforces quotas, supports developer handoff, and saves reviewed structured requirements. A non-root Docker package serves the dashboard and API together. There is **no Google Maps integration, PSTN connection or activated cloud hosting**. Telugu/Hindi model and voice quality remain experimental. No paid services are activated.

## Current milestone: private outbound queue and reviewed lead qualification

Read [private outbound queue, quotas and developer handoff](docs/CALL_QUEUE.md) and [latest test results](docs/TEST_RESULTS.md). Read [operations and owner access](docs/OPERATIONS.md) and [self-hosting setup and remaining gates](docs/DEPLOYMENT.md). Source publication on GitHub is separate from a running hosted application.

## Business discovery

Find prospects using [OpenStreetMap business discovery](docs/BUSINESS_DISCOVERY.md). Read the [Version 1 audit](docs/AUDIT.md), follow [Ollama setup](docs/LOCAL_AI.md), then [local speech setup](docs/LOCAL_SPEECH.md) and [private Asterisk SIP testing](docs/PRIVATE_SIP.md). Connect them using [SIP-to-AI bridge setup and checks](docs/SIP_AI_BRIDGE.md). Review the [Akki Telephony staged plan](docs/AKKI_TELEPHONY.md). No model download is needed for the original scripted demo or offline tests. The lab requires a separately installed local model. Keep the backend bound to loopback.

## Where files and data live

- Project source: `akki-voice-agent/` directory; keep it in GitHub or your computer for permanent storage.
- Runtime database: `backend/data/leads.sqlite3` on the computer hosting the FastAPI app; **gitignored** so private contacts are not accidentally uploaded to GitHub.
- Browser dashboard: runs at `http://localhost:5173`.
- API docs: `http://localhost:8000/docs`.
- A downloaded ZIP or ChatGPT workspace file is **not a persistent deployment**. Save the ZIP and push the code to your own GitHub repository. Use a separate private backup of SQLite, never a public repository.

## Start on Windows (PowerShell)

Install **Python 3.11+** and **Node.js 20+** first. Extract the ZIP and open a terminal in `akki-voice-agent`.

**Terminal 1 — backend**:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — React frontend**:

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Choose **Load demo data** to add three clearly fictional businesses, select **Demo Spice Garden**, go to **Voice simulator**, and click **Start voice demo**. Type replies in the scripted simulator. For microphone conversations, follow the separate local speech setup. Set **Read replies aloud** to hear browser-generated speech.

## Mac / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd frontend && npm install && npm run dev
```

## Tests

```bash
python -m unittest discover -s tests -v
```

Build the React app with `cd frontend && npm run build`. GitHub Actions runs both the backend tests and frontend build using `npm ci` and the committed lockfile.

## Main features

- **Business discovery:** nearby OpenStreetMap search by category; reviewed imports preserve attribution and do not grant calling permission.
- **Lead directory:** manually add business records obtained with permission; search and filter by category and lead status.
- **Contact consent:** recording consent source is mandatory before enabling outreach; a do-not-call flag prevents demo sessions and cannot be casually undone.
- **Voice demo:** one lead at a time; agent explicitly identifies as AI; saves structured requirements, example budgets, timeline, interest, and conversation history.
- **Privacy:** contact records stay in the local SQLite file; no API keys are required; CORS is localhost-only.
- **No paid APIs:** this prototype calls no paid API and has no mobile/landline connection. Private SIP tests are supported. Local electricity/internet and any hosting you later choose remain your responsibility.

## Future real telephone integration

1. Begin with a private, consenting **SIP-to-SIP Asterisk lab** as described in [Akki Telephony](docs/AKKI_TELEPHONY.md). For later PSTN access, select a licensed SIP trunk or provider subject to India-specific eligibility, KYC, and calling regulations; verify media-streaming support.
2. Test with *your own phone or consenting test recipients only*. Verify whether both outbound dialing and two-way media streaming are included in the trial.
3. Configure owner authentication and HTTPS. Add stronger rate limits, encryption, account lifecycle/MFA, complete audit logs and privacy policies before public deployment.
4. Reduce latency further and evaluate the connected STT -> LLM -> TTS/Asterisk prototype with humans. Add audible AI disclosure, human transfer and appropriate consent management before customer-facing calls.
5. Add a background job queue, per-number calling limits, do-not-call suppression, explicit commercial outreach permissions, and hard cost limits. Never automatically call businesses merely because their number appears on a map.
6. When moving hosting into the cloud, use a persistent managed database instead of relying on an ephemeral free container's SQLite disk. Free tiers are quota-limited and do not guarantee 24/7 availability forever.

## API endpoints

- `GET /api/health` — server health and simulated-only mode
- `GET /api/stats` — summary counts
- `GET /api/leads` — filter/search leads
- `POST /api/leads` — create a lead
- `GET /api/leads/{id}` / `PATCH /api/leads/{id}` — lead detail/update
- `POST /api/leads/{id}/demo/start` — start a non-telephone conversation with consent gate
- `POST /api/leads/{id}/demo/reply` — process a text reply in the **scripted demo**
- `GET /api/leads/{id}/demo/messages` — conversation history

## Security note

The backend supports **owner/operator/viewer access** when `AKKI_ADMIN_KEY` is set, with optional named accounts in private `AKKI_TEAM_KEYS` configuration. When unset, it remains an unauthenticated localhost development mode. Configure a strong key, HTTPS and private network access before remote use; see the operations guide. Do not add real clients' personal information until you have an appropriate privacy/consent policy and access controls. For Indian promotional calling, check current TRAI/DoT rules and use authorized calling infrastructure. Google Places data is subject to Google Maps Platform policies and should not be bulk-exported to your own CRM without complying with them.

## Suggested project milestones

- [x] Working dashboard, backend, local database
- [x] Consent and do-not-call checks
- [x] Rules-based conversation demo and saved requirements
- [x] Optional local LLM text lab, durable sessions, human-review drafts
- [x] Local English STT/TTS and prototype interruption handling
- [ ] Progressive speech streaming and low-latency Telugu/Hindi/English evaluation
- [x] Bridge local English AI voice to private Asterisk AudioSocket media
- [x] Private authenticated SIP-to-SIP Asterisk lab with automated two-way audio test
- [ ] Compliant real telephony trial provider and consented test call
- [ ] Authenticated cloud deployment and persistent cloud database
- [x] Optional Telegram outbox with explicit worker command; actual bot delivery unverified
- [x] Owner/operator/viewer access, callback reminders, reports, account audit and backup/retention tools
- [x] Tested Linux Docker dashboard/API package
- [x] Approved private outbound SIP queue, contact/global quotas, human follow-up handoff and reviewed structured CRM requirements
- [x] OpenStreetMap nearby search, website metadata filter, reviewed import and deduplication
- [ ] Google Places adapter after terms/cost review

## License

No license has been chosen yet. Add an explicit license if you want other developers to reuse the project.

## Verification of this milestone

See [test results and measured limitations](docs/VERIFICATION.md). The local model is
not fast/reliable enough for live calling yet. Optional model and telephony tests are separate from offline CI. Check the repository Actions page for the result at the published commit.

### Privacy controls

The **Follow-ups & reports** screen now includes private business-record export, explicitly confirmed application-data erasure and deployment readiness checks. Erasure preserves hashed phone suppression and a minimal independent call-attempt ledger, so deleting transcripts cannot reset outreach quotas. Active calls/microphones must be stopped first. Existing backups and exports require separate removal. See [operations and privacy setup](docs/OPERATIONS.md).
