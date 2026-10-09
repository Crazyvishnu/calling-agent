# Owner access and CRM operations

This is a local single-workspace application with owner/operator/viewer access, not a multi-tenant service. Use one Uvicorn worker: microphone locks, call locks and login sessions are process-local. Login sessions last eight hours and expire on restart. MFA, tamper-resistant audit storage and distributed queues are not implemented.

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

## Private export and erasure

In **Follow-ups & reports → Privacy & readiness**, select a business, download its private JSON export if needed, and explicitly confirm erasure. Owner authentication protects these routes when configured. Erasure removes the business's transcripts, AI drafts/sessions, call history, queue jobs, reminders, notification records and contact/profile fields. Stop active calls and disconnect browser microphones first; preparation and live media block erasure. Logging out revokes the browser voice session on its next input or inference checkpoint.

A minimal lead tombstone, HMAC phone suppression, call-attempt ledger and audit records remain. The random HMAC key is stored privately in the database and included in database backups, never in the JSON export. Reimporting the same normalized phone cannot restore calling eligibility. Erasing transcripts or changing a phone does not reset the rolling 24-hour call quota. Existing backups and downloaded exports require separate retention/removal; this endpoint does not promise forensic erasure of SQLite pages, disks or backups. HMAC records are still protected pseudonymous data.

API: `GET /api/privacy/leads/{id}/export`, `POST /api/privacy/leads/{id}/erase` with `{"reviewed":true}`, and `GET /api/privacy/readiness`. Readiness reports current configuration and explicitly lists unverified production gates; a healthy database alone does not certify production readiness.

Private API responses use `Cache-Control: no-store` and browser security headers. Cookie writes require the request marker and an allowed Origin even if an invalid Authorization header is present. Authenticated HTTP mutations now record route template, method and response status without request bodies or contact identifiers. This local audit is not tamper-resistant, identifies named accounts but does not capture every WebSocket/media event. See team access below.

## Team access

`AKKI_ADMIN_KEY` retains full owner authority. Optionally set the private server environment variable `AKKI_TEAM_KEYS` to a JSON object of named accounts, each containing `role` and a unique random `key` of at least 32 characters. Example structure (replace these placeholders privately):

```json
{"reviewer":{"role":"viewer","key":"REPLACE_WITH_UNIQUE_RANDOM_VIEWER_KEY"},"staff":{"role":"operator","key":"REPLACE_WITH_UNIQUE_RANDOM_OPERATOR_KEY"}}
```

Use the dashboard's **Access key** field for any account. Never put this JSON in source files, frontend configuration or issue reports. Invalid roles, duplicate keys and weak/short keys fail backend startup. At most 20 named accounts are supported. This is a single CRM workspace: viewers can read CRM records, transcripts and reports; there is no per-business data isolation.

| Role | Permissions |
|---|---|
| Owner | All operations, including recording consent, approving/dispatching private calls and private export/erasure |
| Operator | Read CRM, edit requirements/notes, discover/import unapproved businesses, use approved local AI sessions, revoke consent, suppress numbers, manage follow-ups and stop/cancel calls |
| Viewer | Read-only CRM/reports; no microphone/media sessions, mutations or privacy exports |

Operators cannot grant or modify consent evidence, approve/dispatch queue jobs, connect private SIP calls or export/erase customer data. The backend enforces these boundaries even when an API client bypasses the dashboard. Audit events identify the named account. Removing/rotating a key invalidates its cookies; changing a role affects subsequent requests and browser voice checkpoints. Production configuration normally requires a controlled restart, which cancels calls and expires sessions. Keep one worker. Password accounts, self-service account management, MFA/SSO and tenant separation remain unimplemented.
