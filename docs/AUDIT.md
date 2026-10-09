# Version 1 review — 2026-10-09

Reviewed main commit `9c596fa344825da760c06db6a4484ceeb54b805a` in
`Crazyvishnu/calling-agent`: README, backend, frontend, schema, tests and CI.
All five baseline backend tests passed locally. The latest GitHub run for that commit
was completed/success: <https://github.com/Crazyvishnu/calling-agent/actions/runs/37823298580>.
That run covers the original commit, not these unpushed changes.

| Finding | Change |
| --- | --- |
| Consent evidence could be cleared while contact remained enabled | Validate final permission/evidence combination on PATCH |
| Whitespace-only names/messages accepted | Trim and validate meaningful input |
| `yesterday` matched `yes` and incorrectly indicated interest | Match scripted interest terms with word boundaries |
| Plain declines left outreach enabled and conversations could continue | Revoke contact, block declined leads and persist terminal demo state |
| Browser audio/recognition and pending responses could survive switching leads | Mount per lead, clean up audio/recognition and ignore unmounted responses |
| Frontend dependencies varied each CI run | Commit npm lockfile and use `npm ci` |
| No model integration or durable AI sessions | Add loopback Ollama adapter, validated drafts, permission gates and failure/race tests |

Remaining: scripted extraction still uses keywords and is unreliable for negation,
corrections and different languages. Restarting a scripted demo replaces that lead's
demo history; AI lab sessions are separate and preserved. The script is for fictional
examples with local-text disclosure. The AI lab requires additional collection/storage consent.

No authentication, roles, encrypted database, audit trail, automatic retention/backups,
public hosting, business discovery, Telegram, telephone/PBX integration, streaming speech
pipeline or production telecom authorization is implemented. JSON validation checks shape,
not model truthfulness. See [local setup](LOCAL_AI.md) and [telephony plan](AKKI_TELEPHONY.md).

Final local checks and limitations are recorded in [verification](VERIFICATION.md).
