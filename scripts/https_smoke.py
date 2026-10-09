"""Verify private HTTPS with the generated CA. Never disables TLS verification."""
import argparse
import asyncio
import json
import os
import ssl
import httpx
import websockets


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ca',required=True)
    parser.add_argument('--url',default='https://localhost:8443')
    args=parser.parse_args()
    context=ssl.create_default_context(cafile=args.ca)
    with httpx.Client(base_url=args.url,verify=context,trust_env=False,timeout=15) as client:
        assert client.get('/').status_code==200
        assert client.get('/api/leads').status_code==401
        response=client.post('/api/auth/login',headers={'Origin':args.url},json={'key':os.environ['AKKI_ADMIN_KEY']})
        assert response.status_code==200
        assert 'secure' in response.headers['set-cookie'].lower()
        assert client.post('/api/leads',headers={'Origin':'https://untrusted.example','X-Akki-Request':'1'},json={'business_name':'Blocked cross-site'}).status_code==401
        response=client.post('/api/leads',headers={'Origin':args.url,'X-Akki-Request':'1'},json={'business_name':'Fictional HTTPS Cafe'})
        assert response.status_code==201
        assert client.get('/api/google-places/status').json()['configured'] is False
        token=client.cookies.get('akki_session')
        async def check_wss():
            async with websockets.connect(args.url.replace('https://','wss://')+'/api/speech/sessions/missing/ws',
                ssl=context,origin=args.url,additional_headers={'Cookie':'akki_session='+token},proxy=None) as ws:
                result=json.loads(await asyncio.wait_for(ws.recv(),5))
                assert result['type']=='error' and 'not found' in result['detail'].lower()
        asyncio.run(check_wss())
    print('PASS: verified private TLS, Secure cookie, CSRF rejection, CRM write, disabled Google and authenticated WebSocket proxy')

if __name__=='__main__':main()
