# Approved private outbound SIP queue

The backend can now originate an actual private Asterisk call to the fixed SIP endpoint **1001**. It does not accept telephone numbers, arbitrary SIP destinations, trunks or CLI commands. No PSTN route is installed. Use consenting test participants only.

## Start the local engine

Follow [local model](LOCAL_AI.md), [local speech](LOCAL_SPEECH.md) and [private bridge](SIP_AI_BRIDGE.md) setup. Set a private `AKKI_ADMIN_KEY`, your exact dashboard origin in `AKKI_ALLOWED_ORIGINS`, and `AKKI_SIP_LAB=1`. Run one Uvicorn worker. Recreate/restart Asterisk after updating its relay script. No paid provider is required for these isolated tests.

Create a fictional or consenting lead, document contact permission, and start an English AI session with explicit requirements/transcript consent. In **Approved private outbound queue**, enter the approved test time and approval evidence, and confirm participant 1001 approved the private call and audio processing. Register the consenting participant's SIP endpoint in the isolated lab first.

Press **Call consenting test user 1001** after the approved time. Dispatch warms local models, opens the authenticated private relay, and tells Asterisk to originate `PJSIP/1001` into AudioSocket with the parsed session UUID. The recipient answers the call. UUID admission prevents a stale ringing call from entering a different reservation. The operator cannot submit a different destination. The existing consenting inbound 1001→1002 workflow is retained.

The current internal Docker network can run simulated endpoints inside the container; host softphone access is not established. Do not relax network isolation or expose a PBX to the internet without a separate security review. Private origination rings for Asterisk's default timeout; stopping before answer closes media admission but a ringing endpoint may take that timeout to stop. This is not a production outbound dialer or a human phone transfer service.

## Limits and lifecycle

- One active reservation per backend process, one Uvicorn worker.
- At most 20 pending queue jobs and one pending job per AI session.
- Default maximum **five call attempts in a rolling 24 hours**, adjustable with `AKKI_PRIVATE_DAILY_LIMIT` between 1 and 10. Failed reservations count too.
- At most one attempt per CRM lead or normalized Indian contact number in the last 24 hours. The private test endpoint can be reused only across separately approved fictional tests within the global cap.
- Consent, DNC, session state and quotas are rechecked before dispatch and again at reservation; permission is checked after model warmup and throughout voice processing.
- No automatic dispatch, retries or restart recovery of calls. A failed job must be reviewed before a new approved job. A queued job stays queued after restart.
- Jobs follow persisted SIP call states. Cancel queued jobs directly; disconnect waiting/connected jobs through their call. Preparation must finish before the current cancellation API can cancel its reservation.
- Typed turns, competing microphone/SIP controls, transcript deletion and review are disabled in the UI during queue-owned calls. The backend also rejects typed turns for a SIP-owned session.

## Developer handoff and reviewed requirements

English requests such as “I want to speak to a human” end AI qualification without waiting for the model, mark the session for a human and move the lead to follow-up. This preserves contact consent; a decline or opt-out takes priority. No personal callback or live transfer is placed automatically.

The owner can also press **Hand to developer for follow-up** after disconnecting private media. Schedule the actual callback in **Follow-ups & reports**.

Review every extracted field before pressing **I reviewed this draft — save to CRM**. The API rejects stale revisions, declined/unconsented leads and active SIP calls. It saves the full structured draft, including pages/features, design preferences and callback text, and updates the lead's requirements/budget/timeline/qualification status. Saving the same revision is idempotent. A minimal Telegram alert is queued transactionally; delivery remains opt-in and requires the explicit worker command. No Telegram message was sent during validation.

## Reproduce actual SIP checks

The smoke script accepts both module and direct execution. If authentication is enabled, it uses the private owner key from the environment and never puts it in a URL.

```bash
python -m scripts.check_sip_ai --run-private-test --outbound
python -m scripts.check_sip_ai --run-private-test --barge-in
python -m scripts.check_sip_ai --run-private-test --hangup-during-inference
```

Each check creates a new clearly fictional lead and consenting session. Do not run them against customer records. The outbound check first registers a synthesized test recipient, queues the approved call, dispatches through the real backend/PBX and verifies requirements, opt-out, hangup and released reservation. Audio fixtures are temporary and removed. These checks exercise synthetic English speech, not human conversation quality.
