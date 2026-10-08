# Akki Voice Agent — free local MVP

A **working, consent-first sales lead dashboard** for a website-building business. This first version includes a React dashboard, FastAPI REST API, SQLite storage, lead requirements, lead statuses, a do-not-call safeguard, and a **scripted voice-conversation simulator**.

> **Honest status:** This is **not yet an AI LLM or a telephone dialer**. The simulator uses a rules-based conversation, not a neural model. Browser text-to-speech can read the replies; browser speech recognition, where available, may depend on the browser provider's servers. **No real outbound calls, Google Maps scraping, always-on cloud hosting, or Telegram notifications are implemented yet.** Free trials cannot guarantee free unlimited phone calls. This code is a starter, not a production-ready calling platform.

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

Open **http://localhost:5173**. Choose **Load demo data** to add three clearly fictional businesses, select **Demo Spice Garden**, go to **Voice simulator**, and click **Start voice demo**. Type replies or use the microphone if supported by your browser. Set **Read replies aloud** to hear browser-generated speech.

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

Build the React app with `cd frontend && npm run build`. GitHub Actions runs both the backend tests and frontend build using `npm install` in CI (the lockfile is generated when you first install dependencies).

## Main features

- **Lead directory:** manually add business records obtained with permission; search and filter by category and lead status.
- **Contact consent:** recording consent source is mandatory before enabling outreach; a do-not-call flag prevents demo sessions and cannot be casually undone.
- **Voice demo:** one lead at a time; agent explicitly identifies as AI; saves structured requirements, example budgets, timeline, interest, and conversation history.
- **Privacy:** contact records stay in the local SQLite file; no API keys are required; CORS is localhost-only.
- **No charges:** this MVP calls no paid API and places no telephone calls. Local electricity/internet and any hosting you later choose remain your responsibility.

## Future real telephone integration

1. Select a legitimate telephony provider with available developer credits and documented **two-way real-time audio streaming**, subject to India-specific eligibility, KYC, and calling regulations.
2. Test with *your own phone or consenting test recipients only*. Verify whether both outbound dialing and two-way media streaming are included in the trial.
3. Add server-side authentication, HTTPS, rate limits, encryption, audit logs, access controls, and explicit retention/deletion policies before public deployment.
4. Implement a streaming voice pipeline (STT -> LLM -> TTS), with clear AI disclosure, interruption handling, human transfer and consent management. This is separate from the current rules-based demo.
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

The backend **has no authentication** and is explicitly a **localhost development prototype**. Do not bind it to a public IP or deploy it on an internet-facing server as-is. Do not add real clients' personal information until you have an appropriate privacy/consent policy and access controls. For Indian promotional calling, check current TRAI/DoT rules and use authorized calling infrastructure. Google Places data is subject to Google Maps Platform policies and should not be bulk-exported to your own CRM without complying with them.

## Suggested project milestones

- [x] Working dashboard, backend, local database
- [x] Consent and do-not-call checks
- [x] Rules-based conversation demo and saved requirements
- [ ] LLM-based voice with realistic low-latency Telugu/Hindi/English support
- [ ] Compliant real telephony trial provider and consented test call
- [ ] Authenticated cloud deployment and persistent cloud database
- [ ] Telegram follow-up notifications
- [ ] Permitted business discovery integration

## License

No license has been chosen yet. Add an explicit license if you want other developers to reuse the project.
