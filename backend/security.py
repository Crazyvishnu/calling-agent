"""Single-owner authentication. Configure a private key before exposing the app."""
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

router = APIRouter(prefix='/api/auth', tags=['Owner access'])
sessions = {}
attempts = defaultdict(list)

def key():
    return os.environ.get('AKKI_ADMIN_KEY', '')

def origins():
    return {'http://localhost:5173', 'http://127.0.0.1:5173'} | {x.strip().rstrip('/') for x in os.environ.get('AKKI_ALLOWED_ORIGINS', '').split(',') if x.strip()}

def authorized(scope):
    if not key():
        return True
    headers = dict(scope.get('headers', []))
    bearer = headers.get(b'authorization', b'').decode()
    if bearer.startswith('Bearer ') and hmac.compare_digest(bearer[7:], key()):
        return True
    cookie = headers.get(b'cookie', b'').decode()
    from http.cookies import SimpleCookie, CookieError
    try:
        parsed = SimpleCookie(cookie)
        token = parsed.get('akki_session')
        record = sessions.get(hashlib.sha256(token.value.encode()).hexdigest()) if token else None
        return bool(record and record[0] > time.time() and hmac.compare_digest(record[1], hashlib.sha256(key().encode()).hexdigest()))
    except CookieError:
        return False

class AccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            return await self.app(scope, receive, send)
        path = scope.get('path', '')
        public = path in ('/api/health', '/api/auth/status', '/api/auth/login') or not (path.startswith('/api/') or path in ('/docs', '/redoc', '/openapi.json'))
        headers = dict(scope.get('headers', []))
        denied = not public and not authorized(scope)
        # Cookies cannot authorize cross-site writes. CLI/bridge bearer access is independent.
        if key() and not public and scope['type'] == 'http' and scope['method'] not in ('GET', 'HEAD', 'OPTIONS') and b'authorization' not in headers:
            denied = denied or headers.get(b'x-akki-request') != b'1' or headers.get(b'origin', b'').decode() not in origins()
        if denied:
            if scope['type'] == 'websocket':
                return await send({'type': 'websocket.close', 'code': 4401})
            return await JSONResponse({'detail': 'Owner login required, or request origin rejected'}, status_code=401)(scope, receive, send)
        await self.app(scope, receive, send)

class Login(BaseModel):
    key: str = Field(min_length=1, max_length=512)

@router.get('/status')
def status(request: Request):
    return {'enabled': bool(key()), 'authenticated': authorized(request.scope)}

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
    if not hmac.compare_digest(body.key, key()):
        raise HTTPException(401, 'Invalid owner key')
    for token, record in list(sessions.items()):
        if record[0] <= now:
            sessions.pop(token, None)
    if len(sessions) >= 64:
        sessions.pop(next(iter(sessions)))
    token = secrets.token_urlsafe(32)
    sessions[hashlib.sha256(token.encode()).hexdigest()] = (now + 8 * 3600, hashlib.sha256(key().encode()).hexdigest())
    response.set_cookie('akki_session', token, max_age=8 * 3600, httponly=True, samesite='strict', secure=os.environ.get('AKKI_SECURE_COOKIES') == '1')
    return {'authenticated': True}

@router.post('/logout')
def logout(request: Request, response: Response):
    token = request.cookies.get('akki_session', '')
    sessions.pop(hashlib.sha256(token.encode()).hexdigest(), None)
    response.delete_cookie('akki_session')
    return {'authenticated': False}
