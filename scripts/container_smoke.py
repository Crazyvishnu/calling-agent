"""Fictional smoke check for the built self-hosted application; never places calls."""
import os
import sys
import time
import httpx

url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8080'
with httpx.Client(base_url=url, trust_env=False) as client:
    for _ in range(30):
        try:
            if client.get('/api/health').status_code == 200:
                break
        except httpx.TransportError:
            pass
        time.sleep(0.5)
    else:
        raise RuntimeError('Container did not become healthy')
    assert client.get('/').status_code == 200
    assert client.get('/api/leads').status_code == 401
    response = client.post('/api/auth/login', headers={'Origin': url}, json={'key': os.environ['AKKI_ADMIN_KEY']})
    assert response.status_code == 200, response.text
    assert 'HttpOnly' in response.headers['set-cookie']
    response = client.post('/api/leads', headers={'Origin': url, 'X-Akki-Request': '1'}, json={'business_name': 'Fictional Container Cafe'})
    assert response.status_code == 201, response.text
    identity = response.json()['id']
    assert client.get('/api/privacy/readiness').json()['database_ok']
    exported = client.get(f'/api/privacy/leads/{identity}/export')
    assert exported.status_code == 200 and exported.headers['cache-control'].startswith('no-store')
    assert exported.json()['lead']['business_name'] == 'Fictional Container Cafe'
    assert any(x['business_name'] == 'Fictional Container Cafe' for x in client.get('/api/leads').json())
    assert client.post(f'/api/privacy/leads/{identity}/erase', headers={'Origin': url, 'X-Akki-Request': '1'}, json={'reviewed': True}).status_code == 200
    assert client.get(f'/api/leads/{identity}').json()['business_name'] == f'Erased lead {identity}'
    assert client.post('/api/auth/logout', headers={'Origin': url, 'X-Akki-Request': '1'}).status_code == 200
    assert client.get('/api/leads').status_code == 401
print('PASS: dashboard, owner login, CSRF-protected lead persistence, private export/erasure and logout')
