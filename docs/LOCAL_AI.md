# Local Ollama conversation lab

This lab connects local LLM text inference to the dashboard. Optional browser
speech reads replies. The subsequent [local speech milestone](LOCAL_SPEECH.md) adds
faster-whisper, Piper and prototype interruption handling. The separate
[private SIP lab](PRIVATE_SIP.md) can use the [Linux AI media bridge](SIP_AI_BRIDGE.md). There is no paid model API.
Downloads use bandwidth/disk; inference uses your computer and electricity. This lab
stops when its computer is switched off.

## Windows setup

1. Install Ollama from <https://ollama.com/download/windows>.
2. Download a **local** model in PowerShell:

   ```powershell
   ollama pull qwen3:1.7b
   ```

   Qwen3 1.7B is an Apache-2.0-licensed starting model, not a guarantee of sales accuracy or Telugu/Hindi quality. The adapter disables its thinking mode to limit latency.
   Larger local models require more RAM. Review the selected model's license and size.
   Never select a `:cloud` model here.

3. Disable Ollama cloud. Exit an already running Ollama tray application before starting
   your explicit local server in its own terminal:

   ```powershell
   $env:OLLAMA_NO_CLOUD = "1"
   $env:OLLAMA_HOST = "127.0.0.1:11434"
   ollama serve
   ```

   A port-in-use error means another Ollama server is running; stop that instance first.
   The backend connects only to `127.0.0.1:11434` and rejects remote models reported by
   Ollama. Disable cloud in Ollama itself as well.

4. Activate your existing Python environment, install dependencies, copy `.env.example`
   only on first setup (preserve any existing `.env`), and run the backend:

   ```powershell
   cd "D:\experiments\akki-voice-agent"
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements-dev.txt
   if (!(Test-Path .env)) { Copy-Item .env.example .env }
   python -m uvicorn backend.main:app --env-file .env --host 127.0.0.1 --port 8000
   ```

   To use another installed local model, set `OLLAMA_MODEL` in `.env` and restart
   FastAPI. The file alone does not reconfigure a running Ollama server.

5. Run the frontend in a separate terminal:

   ```powershell
   cd "D:\experiments\akki-voice-agent\frontend"
   npm ci
   npm run dev
   ```

6. Open <http://localhost:5173>, load fictional demo data, and open **AI conversation lab**.
   Select a test lead and confirm permission to collect requirements, store the transcript,
   and use the local model. **Check model** reports availability, not conversation quality.
7. Start a session and type, for example: “I need a menu and booking page. My approximate
   budget is ₹12000 and I'd like it next month.” Compare the draft with the transcript.
   End the session when finished. Saved sessions can be reopened or deleted.

Linux uses the same model/application commands with `export OLLAMA_NO_CLOUD=1`,
`export OLLAMA_HOST=127.0.0.1:11434`, and `source .venv/bin/activate`.

## Behavior and limits

- The scripted demo remains separate. Its voice selector does not translate the English script.
- Hindi/Telugu openings and language instructions are included, but comprehension,
  pronunciation and extraction quality depend on the model/browser voice. They remain
  experimental until evaluated with speakers.
- Browser speech may use vendor services. Disable speech for local typed conversations.
  No audio is recorded. Stop audio manually; sending a reply also cancels current speech.
- Transcripts and drafts use the existing gitignored SQLite database. Startup adds tables
  without replacing existing leads. Drafts are suggestions and require human review.
- The model cannot grant consent, initiate calls, or auto-qualify CRM leads. It is instructed to avoid
  price/delivery promises, but model accuracy and prompt-injection resistance are not guaranteed.
- A reply guard replaces observed English approval/availability/scheduling assurances with
  a human-review reminder. It is a heuristic, not complete multilingual semantic enforcement;
  all generated replies still need supervision before any customer-facing voice deployment.
- Draft values must appear as excerpts in participant messages; invented/paraphrased values
  are discarded. This can miss legitimate paraphrases and cannot prove that an excerpt was
  assigned to the correct field. The prompt requests new-field updates; nonempty extracted updates replace existing values and omissions
  preserve previous values. Deletions/corrections still need human review.
- Start/reply checks documented outreach consent. Known English/Hindi/Telugu decline phrases
  bypass model inference; model-detected opt-outs also suppress contact. Phrase matching is
  a prototype safeguard, not a complete multilingual classifier or commercial compliance system.
- Plain declines close the session, disable contact and mark the lead not interested. Explicit
  do-not-call additionally sets irreversible DNC. A human reviews any future reauthorization.
- Revisions reject stale replies. Consent and session state are rechecked after inference.
  Failed/timed-out/invalid turns are not saved. Retry does not duplicate the transcript.
- Sessions stop after 20 replies. Combined messages/draft are limited to 8,000 characters
  before inference, a context heuristic rather than a tokenizer. Some models/scripts may
  need a smaller budget. Timeout is 90 seconds, not a real-time telephone latency target.
- Delete removes a session's transcript/draft and preserves the lead and suppression.
  SQLite deletion is not secure disk erasure. Protect disks and private backups separately.
- The API still has no authentication. Bind to loopback and use fictional/consenting test
  records. Public deployment is outside this milestone.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /api/lab/status` | Local model availability |
| `POST /api/lab/sessions` | Start with `lead_id`, `language`, `collection_consent: true` |
| `GET /api/lab/sessions?lead_id=...` | Recent sessions |
| `GET /api/lab/sessions/{id}` | Transcript, draft, state, revision |
| `POST /api/lab/sessions/{id}/reply` | Send `message` and current `revision` |
| `POST /api/lab/sessions/{id}/end` | End without model inference |
| `DELETE /api/lab/sessions/{id}` | Delete transcript and draft |

`403`: revoked/missing permission, declined or DNC. `409`: ended/stale session; reload.
`422`: invalid input/collection permission. `503`: local model unavailable, timeout, or
context budget exceeded. `502`: invalid model JSON; try a different local model.

Run offline tests: `python -m unittest discover -s tests -v`. Run `npm run build` in
`frontend`. These require no model. Live inference/audio evaluation are separate checks.

Optional English model smoke check (activate the virtual environment first):

```powershell
python -m scripts.check_local_model
```

This uses only fictional text, checks budget/features/timeline and callback memory, and
prints the generated replies for review. It does not write CRM records, place calls, or
test voice quality. It reads `OLLAMA_MODEL` from the process environment, so set
`$env:OLLAMA_MODEL` when testing a different model; it does not load `.env` itself.
