# Owner access and CRM operations

This is a single-owner local application, not a multi-tenant service. Use one Uvicorn worker: microphone locks, call locks and login sessions are process-local. Login sessions last eight hours and expire on restart. Roles, MFA, tamper-resistant audit storage and distributed queues are not implemented.

## Owner key

Generate a random private key (never use a sample/test value):

```powershell
$env:AKKI_ADMIN_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
```

For Linux:

```bash
export AKKI_ADMIN_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

Keep this key private. Backend startup rejects configured keys shorter than 32 characters. When unset, authentication is disabled for localhost development only. Do not expose this mode to other machines. The dashboard asks for the owner key and receives an HttpOnly, SameSite=Strict cookie. Authenticated browser writes also require an allowed Origin and request header. CLI clients can use an Authorization Bearer header. The private media bridge sends this header internally; keys are never put in WebSocket URLs or committed in frontend bundles.

Set `AKKI_ALLOWED_ORIGINS` to a comma-separated list of exact dashboard origins. For a private HTTPS deployment, set `AKKI_SECURE_COOKIES=1`; terminate TLS with a trusted reverse proxy. Limit access to a private VPN/firewall. Five login attempts per minute per observed client IP are allowed. Put additional rate limiting at the reverse proxy for internet-facing services. Do not configure the proxy to trust arbitrary forwarded client IPs.

## Follow-ups and reports

Open **Follow-ups & reports**. Select a lead, enter a callback time and notes, then schedule. Browser-local times are converted to UTC for storage. Overdue reminders are visible in the dashboard; they do not place calls or send messages. Contact eligibility is recalculated from current consent and DNC records. DNC suppression propagates across records sharing an Indian phone number, including +91 and leading-zero variants. Mark reminders completed after reviewing them. Reports show pipeline counts and private SIP outcomes. The minimal audit records lead saves, follow-ups, notification actions, backups and transcript purges; it is not a complete security audit of every AI/media event.

## Optional Telegram outbox

Queue a qualified, consented lead in the operations dashboard. A stable requirements fingerprint prevents duplicate queue entries. Queueing does not send a message. Delivery exports only lead ID and business name, not phone numbers, requirements or transcripts. Decide whether this export fits your privacy policy before enabling it.

Configure private environment variables `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` and `AKKI_TELEGRAM_ENABLED=1`, then explicitly run:

```bash
python scripts/maintenance.py --deliver-one-notification
```

This processes at most one pending item. It rechecks consent/DNC and suppresses revoked leads. A failed or ambiguous delivery becomes `uncertain` and is not automatically retried, because a timeout can occur after Telegram accepted a message. A worker crash during delivery leaves `sending`; review Telegram manually. No scheduler or external message has been activated by development. Tests use mocked HTTP clients, not a real bot.

## Private backups and transcript retention

```bash
python scripts/maintenance.py --backup /private-backups/akki-2026-10-09.sqlite3
python scripts/maintenance.py --purge-transcripts-older-than 30
```

Backups use SQLite's online backup API, require a new path, and set file mode 0600 on POSIX. On Windows, additionally configure NTFS access permissions; POSIX mode does not establish Windows ACLs. Never put backups in GitHub. Stop the service before restoring a backup, replace the live database privately, then restart and verify a known lead and DNC record. Protect and expire backup copies according to your retention policy.

Transcript purging removes old scripted messages and old ended AI sessions (including their call histories). Active sessions remain, and lead records, consent evidence and DNC suppression remain. It does not erase every piece of personal information, audit records or old backups. DNC records must remain available to prevent recontact; a complete erasure/anonymization policy needs separate review. SQLite deletion alone is not guaranteed forensic erasure; use encrypted storage for sensitive deployments.
