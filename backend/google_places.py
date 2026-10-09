"""Optional Google Places IDs-only discovery. Disabled until owner setup and approval."""
import json
import os
import re
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from .db import connect
from .security import principal

router = APIRouter(prefix='/api/google-places', tags=['Optional Google Places'])
ENDPOINT = 'https://places.googleapis.com/v1/places:searchText'


def initialize_google():
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS external_request_attempts (
          id INTEGER PRIMARY KEY,provider TEXT NOT NULL,created_at TEXT NOT NULL DEFAULT (datetime('now')))""")
        db.execute('CREATE INDEX IF NOT EXISTS idx_external_attempts ON external_request_attempts(provider,created_at)')


def quota_limit():
    try:
        return max(0,min(10,int(os.environ.get('GOOGLE_PLACES_DAILY_LIMIT','0'))))
    except ValueError:
        return 0


def gates():
    return {'enabled':os.environ.get('GOOGLE_PLACES_ENABLED')=='1',
            'key_configured':bool(os.environ.get('GOOGLE_PLACES_API_KEY')),
            'billing_approved':os.environ.get('GOOGLE_PLACES_BILLING_APPROVED')=='1',
            'terms_reviewed':os.environ.get('GOOGLE_PLACES_TERMS_REVIEWED')=='1',
            'quota_configured':quota_limit()>0}


@router.get('/status')
def status():
    values=gates()
    with connect() as db:
        used=db.execute("SELECT count(*) FROM external_request_attempts WHERE provider='google-places' AND created_at>=datetime('now','-1 day')").fetchone()[0]
    return {**values,'configured':all(values.values()),'live_verified':False,
            'daily_limit':quota_limit(),'remaining_requests':max(0,quota_limit()-used),
            'fields':'places.id','crm_import_supported':False,
            'detail':'Manual IDs-only search. No business names, phones, reviews or website data are copied into CRM. Provider billing and terms still apply.'}


class Search(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    query:str=Field(min_length=3,max_length=160)
    cost_acknowledged:StrictBool


@router.post('/search')
def search(body:Search,request:Request):
    if principal(request.scope)['role']!='owner':
        raise HTTPException(403,'Only the owner may approve a provider request')
    if not body.cost_acknowledged:
        raise HTTPException(422,'Explicit acknowledgement of provider costs is required')
    if not all(gates().values()):
        raise HTTPException(403,'Google Places is disabled. Configure API access, review terms and explicitly approve billing and a quota first.')
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        count=db.execute("SELECT count(*) FROM external_request_attempts WHERE provider='google-places' AND created_at>=datetime('now','-1 day')").fetchone()[0]
        if count>=quota_limit():raise HTTPException(429,'Google Places rolling 24-hour request quota reached')
        db.execute("INSERT INTO external_request_attempts(provider) VALUES ('google-places')")
    # Reserve before network I/O. Failed/uncertain requests consume a slot; never retry automatically.
    try:
        with httpx.Client(timeout=20,follow_redirects=False) as client:
            with client.stream('POST',ENDPOINT,
                headers={'X-Goog-Api-Key':os.environ['GOOGLE_PLACES_API_KEY'],'X-Goog-FieldMask':'places.id'},
                json={'textQuery':body.query,'regionCode':'IN','pageSize':10}) as response:
                response.raise_for_status(); raw=bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw)>128000:raise ValueError('Oversized provider response')
        data=json.loads(raw)
        if not isinstance(data,dict) or not isinstance(data.get('places',[]),list):raise ValueError('Invalid response')
        ids=[]
        for row in data.get('places',[])[:10]:
            value=row.get('id') if isinstance(row,dict) else None
            if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,300}',value):raise ValueError('Invalid place identifier')
            if value not in ids:ids.append(value)
    except (httpx.HTTPError,ValueError,TypeError) as exc:
        raise HTTPException(503,'Google Places request failed. No automatic retry or CRM import occurred; the attempt consumed one quota slot.') from exc
    return {'results':[{'place_id':value,'maps_url':'https://www.google.com/maps/search/?'+urlencode({'api':'1','query':body.query,'query_place_id':value})} for value in ids],
            'attribution':'Google Maps','contact_allowed':False,'crm_import_supported':False,'cached':False}
