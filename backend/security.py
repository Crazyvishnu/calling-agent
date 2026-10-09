"""Named owner/operator/viewer access. Configure private keys before deployment."""
import hashlib
import json
from contextvars import ContextVar
import hmac
import os
import secrets
import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

router = APIRouter(prefix='/api/auth', tags=['Owner access'])
audit_actor = ContextVar('akki_actor', default='local-owner')
sessions = {}
attempts = defaultdict(list)

def key():
    return os.environ.get('AKKI_ADMIN_KEY', '')

def origins():
    return {'http://localhost:5173', 'http://127.0.0.1:5173'} | {x.strip().rstrip('/') for x in os.environ.get('AKKI_ALLOWED_ORIGINS', '').split(',') if x.strip()}

def credentials():
    records = [{'name': 'owner', 'role': 'owner', 'key': key()}] if key() else []
    raw = os.environ.get('AKKI_TEAM_KEYS', '{}') or '{}'
    data = json.loads(raw)
    if not isinstance(data, dict) or len(data) > 20:
        raise ValueError('AKKI_TEAM_KEYS must be an object with at most 20 named accounts')
    import re
    used = {key()}
    for name, account in data.items():
        if not re.fullmatch(r'[a-zA-Z0-9_-]{3,32}', name) or name == 'owner':
            raise ValueError('Invalid team account name')
        if not isinstance(account, dict) or set(account) != {'role', 'key'} or account['role'] not in ('operator', 'viewer'):
            raise ValueError('Team accounts require exactly role (operator/viewer) and key')
        secret = account['key']
        if not isinstance(secret, str) or not 32 <= len(secret) <= 512 or secret in used:
            raise ValueError('Team keys must be unique and 32 to 512 characters long')
        if not key():
            raise ValueError('Team accounts require the owner key')
        used.add(secret)
        records.append({'name': name, 'role': account['role'], 'key': secret})
    return records


def principal(scope):
    if not key():
        return {'name': 'local-owner', 'role': 'owner'}
    headers = dict(scope.get('headers', []))
    bearer = headers.get(b'authorization', b'')
    accounts = credentials()
    if bearer.startswith(b'Bearer '):
        for account in accounts:
            if hmac.compare_digest(bearer[7:], account['key'].encode()):
                return {'name': account['name'], 'role': account['role'], 'bearer': True}
    from http.cookies import SimpleCookie, CookieError
    try:
        parsed = SimpleCookie(headers.get(b'cookie', b'').decode(errors='replace'))
        token = parsed.get('akki_session')
        record = sessions.get(hashlib.sha256(token.value.encode()).hexdigest()) if token else None
        if record and record[0] > time.time():
            for account in accounts:
                if hmac.compare_digest(record[1], hashlib.sha256(account['key'].encode()).hexdigest()):
                    return {'name': account['name'], 'role': account['role']}
    except CookieError:
        pass
    return None


def authorized(scope):
    return principal(scope) is not None


def require_owner(request):
    identity = principal(request.scope)
    if not identity or identity['role'] != 'owner':
        raise HTTPException(403, 'Only the owner can grant or change contact consent')

class AccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        path = scope.get('path', '')
        public = path in ('/api/health', '/api/auth/status', '/api/auth/login') or not (path.startswith('/api/') or path in ('/docs', '/redoc', '/openapi.json'))
        headers = dict(scope.get('headers', []))
        identity = principal(scope)
        denied = not public and identity is None
        # Cookies cannot authorize cross-site writes. CLI/bridge bearer access is independent.
        if key() and not public and scope['type'] == 'http' and scope['method'] not in ('GET', 'HEAD', 'OPTIONS') and not (identity and identity.get('bearer')):
            denied = denied or headers.get(b'x-akki-request') != b'1' or headers.get(b'origin', b'').decode(errors='replace') not in origins()
        if denied:
            if scope['type'] == 'websocket':
                return await send({'type': 'websocket.close', 'code': 4401})
            return await JSONResponse({'detail': 'Owner login required, or request origin rejected'}, status_code=401)(scope, receive, send)
        owner_only = (path.startswith('/api/privacy/leads/') or
                      (path.startswith('/api/call-queue') and scope.get('method') == 'POST' and not path.endswith('/cancel')) or
                      (path.startswith('/api/telephony/sessions/') and path.endswith('/connect')))
        read_only = identity and identity['role'] == 'viewer' and (
            scope['type'] == 'websocket' or scope.get('method') not in ('GET', 'HEAD', 'OPTIONS') and path != '/api/auth/logout')
        if not public and identity and (read_only or owner_only and identity['role'] != 'owner'):
            if scope['type'] == 'websocket':
                return await send({'type': 'websocket.close', 'code': 4403})
            return await JSONResponse({'detail': 'This action requires a higher access role'}, status_code=403)(scope, receive, send)
        actor_token = audit_actor.set(identity['name'] if identity else 'anonymous')
        async def private_send(message):
            if message['type'] == 'http.response.start' and not public:
                message = dict(message)
                message['headers'] = list(message.get('headers', [])) + [
                    (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                    (b'referrer-policy', b'no-referrer'), (b'x-frame-options', b'DENY')]
                if scope['method'] not in ('GET', 'HEAD', 'OPTIONS') and scope.get('route'):
                    from .operations import audit
                    # Route templates and status only: no contact identifiers, bodies or credentials.
                    audit('http-' + scope['method'].lower() + '-' + str(message['status']), scope['route'].path)
            await send(message)
        try:
            await self.app(scope, receive, private_send)
        finally:
            audit_actor.reset(actor_token)

class Login(BaseModel):
    key: str = Field(min_length=1, max_length=512)

@router.get('/status')
def status(request: Request):
    identity = principal(request.scope)
    return {'enabled': bool(key()), 'authenticated': identity is not None, 'role': identity['role'] if identity else None, 'account': identity['name'] if identity else None}

@router.post('/login')
def login(body: Login, request: Request, response: Response):
    if not key():
        raise HTTPException(409, 'Authentication is not configured; this is local development mode.')
    origin = request.headers.get('origin', '')
    if origin not in origins():
        raise HTTPException(403, 'Login origin rejected')
    now = time.time()
    ip = request.client.host if request.client else 'unknown'
    if len(attempts) > 1024:
        attempts.clear()
    attempts[ip] = [t for t in attempts[ip] if t > now - 60]
    if len(attempts[ip]) >= 5:
        raise HTTPException(429, 'Too many login attempts; wait one minute.')
    attempts[ip].append(now)
    account = next((item for item in credentials() if hmac.compare_digest(body.key.encode(), item['key'].encode())), None)
    if not account:
        raise HTTPException(401, 'Invalid access key')
    for token, record in list(sessions.items()):
        if record[0] <= now:
            sessions.pop(token, None)
    if len(sessions) >= 64:
        sessions.pop(next(iter(sessions)))
    token = secrets.token_urlsafe(32)
    sessions[hashlib.sha256(token.encode()).hexdigest()] = (now + 8 * 3600, hashlib.sha256(account['key'].encode()).hexdigest())
    response.set_cookie('akki_session', token, max_age=8 * 3600, httponly=True, samesite='strict', secure=os.environ.get('AKKI_SECURE_COOKIES') == '1')
    return {'authenticated': True, 'role': account['role'], 'account': account['name']}

@router.post('/logout')
def logout(request: Request, response: Response):
    token = request.cookies.get('akki_session', '')
    sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
    response.delete_cookie('akki_session')
    return {'authenticated': False}
