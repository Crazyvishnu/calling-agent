"""Bounded OpenStreetMap discovery: explicit search/review, never outreach consent."""
from datetime import datetime, timezone
import ipaddress
import math
import re
from threading import Lock
import time
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool

from .db import connect, phone_key

router = APIRouter(prefix='/api/discovery', tags=['Business discovery'])
ATTRIBUTION = '© OpenStreetMap contributors · ODbL 1.0'
LICENSE_URL = 'https://www.openstreetmap.org/copyright'
LOCATIONS = [
    {'name': 'Hyderabad', 'latitude': 17.3850, 'longitude': 78.4867},
    {'name': 'Secunderabad', 'latitude': 17.4399, 'longitude': 78.4983},
    {'name': 'Gachibowli', 'latitude': 17.4401, 'longitude': 78.3489},
    {'name': 'Kukatpally', 'latitude': 17.4948, 'longitude': 78.3996},
    {'name': 'Banjara Hills', 'latitude': 17.4156, 'longitude': 78.4347},
]
CATEGORIES = {
    'Restaurant': [('amenity', 'restaurant|fast_food')], 'Cafe': [('amenity', 'cafe')],
    'Hotel': [('tourism', 'hotel|motel|guest_house|hostel')], 'Retail shop': [('shop', None)],
    'Salon': [('shop', 'hairdresser|beauty')], 'Clinic': [('amenity', 'clinic|doctors|dentist')],
    'School': [('amenity', 'school|college|kindergarten')],
}
ENDPOINT = 'https://overpass-api.de/api/interpreter'
TTL = 900


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)
    location: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=6, le=37)
    longitude: float = Field(ge=68, le=98)
    category: str
    radius_m: int = Field(default=2000, ge=250, le=5000)


def safe_website(value):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > 300:
        return ''
    value = value.strip()
    if value.startswith('//'): value = 'https:' + value
    elif '://' not in value and ':' not in value: value = 'https://' + value
    try:
        url = urlsplit(value)
        host = url.hostname
        if url.scheme not in ('http', 'https') or not host or '.' not in host or url.username or url.password:
            return ''
        try:
            ipaddress.ip_address(host)
            return ''
        except ValueError:
            pass
        if host.endswith(('.local', '.localhost')) or any(c.isspace() for c in value): return ''
        return urlunsplit((url.scheme, url.netloc, url.path, url.query, ''))
    except ValueError:
        return ''


def distance(lat, lon, latitude, longitude):
    a, b = math.radians(lat), math.radians(latitude)
    delta = math.radians(longitude-lon)
    return round(6371000 * 2 * math.asin(min(1, math.sqrt(math.sin((b-a)/2)**2 + math.cos(a)*math.cos(b)*math.sin(delta/2)**2))))


class OSMProvider:
    def search(self, body):
        clauses = []
        for key, values in CATEGORIES[body.category]:
            tag = f'["{key}"~"^({values})$"]' if values else f'["{key}"]'
            clauses.append(f'nwr(around:{body.radius_m},{body.latitude:.6f},{body.longitude:.6f}){tag}["name"];')
        query = '[out:json][timeout:20][maxsize:8388608];(' + ''.join(clauses) + ');out body center 100;'
        try:
            with httpx.Client(timeout=30, follow_redirects=False, headers={'User-Agent': 'AkkiVoiceAgent-local-discovery/1.0'}) as client:
                # Preserve the environment's HTTPS proxy/certificate trust. No AI data sent.
                with client.stream('POST', ENDPOINT, data={'data': query}) as response:
                    response.raise_for_status()
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2_000_000: raise ValueError('Discovery response exceeded its local bound')
            import json
            data = json.loads(raw)
            if data.get('remark') or not isinstance(data.get('elements'), list): raise ValueError('Incomplete search')
        except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(503, 'OpenStreetMap search unavailable or incomplete. Public servers may be busy; wait and retry. No leads imported.') from exc
        candidates = []
        seen = set()
        for element in data['elements'][:100]:
            if not isinstance(element, dict): continue
            kind, identity, tags = element.get('type'), element.get('id'), element.get('tags', {})
            if kind not in ('node','way','relation') or not isinstance(identity, int) or identity <= 0 or not isinstance(tags, dict): continue
            name = tags.get('name')
            center = element.get('center', element)
            if not isinstance(center,dict): continue
            lat, lon = center.get('lat'), center.get('lon')
            if not isinstance(name, str) or not name.strip() or not isinstance(lat,(int,float)) or not isinstance(lon,(int,float)): continue
            if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180: continue
            key = f'{kind}/{identity}'
            if key in seen: continue
            seen.add(key)
            website_tag = tags.get('contact:website') or tags.get('website') or tags.get('url') or ''
            website = safe_website(website_tag)
            phone = tags.get('contact:phone') or tags.get('phone') or ''
            address = ', '.join(str(tags[k])[:100] for k in ('addr:housenumber','addr:street','addr:suburb','addr:city') if tags.get(k))[:300]
            candidates.append({'key': key, 'business_name': name.strip()[:160], 'category': body.category,
                'city': str(tags.get('addr:city') or body.location)[:100], 'address': address,
                'phone': re.split(r'[;,]', phone)[0].strip()[:30] if isinstance(phone,str) else '', 'website': website,
                'website_signal': 'listed' if website else 'needs_review' if website_tag else 'not_listed',
                'source_url': 'https://www.openstreetmap.org/' + key,
                'latitude': lat, 'longitude': lon, 'distance_m': distance(body.latitude,body.longitude,lat,lon)})
        return sorted(candidates,key=lambda c:c['distance_m'])


def get_provider():
    return OSMProvider()


def duplicate(db, candidate):
    rows = db.execute('SELECT * FROM leads').fetchall()
    name = ' '.join(candidate['business_name'].casefold().split())
    city = ' '.join(candidate['city'].casefold().split())
    phone = phone_key(candidate['phone'])
    website = safe_website(candidate['website']).lower().rstrip('/')
    for row in rows:
        if row['discovery_source']=='osm' and row['discovery_source_id']==candidate['key']:
            return row['id']
        if phone and phone == phone_key(row['phone']): return row['id']
        if website and website == safe_website(row['website']).lower().rstrip('/'): return row['id']
        if name == ' '.join(row['business_name'].casefold().split()) and city == ' '.join(row['city'].casefold().split()): return row['id']
    return None


class SearchCache:
    def __init__(self):
        self.lock=Lock(); self.entries={}; self.last_request=None; self.busy=False

cache=SearchCache()


@router.get('/config')
def config():
    return {'provider':'openstreetmap','categories':list(CATEGORIES),'locations':LOCATIONS,
        'attribution':ATTRIBUTION,'license_url':LICENSE_URL,'google_connected':False,
        'min_radius_m':250,'max_radius_m':5000,'max_results':100,'search_interval_seconds':60,
        'detail':'OpenStreetMap discovery; manual review required. Map listings do not grant contact permission.'}


@router.post('/search')
def search(body: SearchRequest, provider=Depends(get_provider)):
    if body.category not in CATEGORIES: raise HTTPException(422,'Unsupported business category')
    signature = body.model_dump_json(); now=time.monotonic()
    with cache.lock:
        cache.entries={key:value for key,value in cache.entries.items() if now-value['created']<TTL}
        previous=next((value for value in cache.entries.values() if value['signature']==signature),None)
        if previous:
            result=previous['result']; cached=True
        else:
            if cache.busy or (cache.last_request is not None and now-cache.last_request<60):
                raise HTTPException(429,'Please wait 60 seconds between new searches. Recent identical searches are cached.')
            cache.busy=True;cache.last_request=now; result=None;cached=False
    if result is None:
        try:
            candidates=provider.search(body)
            result={'search_id':str(uuid4()),'location':body.location,'category':body.category,'radius_m':body.radius_m,
                'observed_at':datetime.now(timezone.utc).isoformat(),'expires_in_seconds':TTL,
                'attribution':ATTRIBUTION,'license_url':LICENSE_URL,'results':candidates,
                'may_be_truncated':len(candidates)>=100,'cached':False}
            with cache.lock:
                if len(cache.entries)>=16: cache.entries.pop(next(iter(cache.entries)))
                cache.entries[result['search_id']]={'created':time.monotonic(),'signature':signature,'result':result}
        finally:
            with cache.lock: cache.busy=False
    with connect() as db:
        results=[{**c,'duplicate_lead_id':duplicate(db,c)} for c in result['results']]
    with cache.lock:
        stored=cache.entries.get(result['search_id'])
        remaining=max(0,int(TTL-(time.monotonic()-stored['created']))) if stored else 0
    return {**result,'results':results,'cached':cached,'expires_in_seconds':remaining}


class ImportRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    search_id: str = Field(min_length=1,max_length=40)
    keys: list[str] = Field(min_length=1,max_length=20)
    reviewed: StrictBool


@router.post('/import')
def import_candidates(body: ImportRequest):
    if not body.reviewed: raise HTTPException(422,'Confirm that selected business records were reviewed.')
    with cache.lock:
        stored=cache.entries.get(body.search_id)
        if not stored or time.monotonic()-stored['created']>=TTL: raise HTTPException(410,'Search expired; search again before importing.')
        result=stored['result']
    by_key={candidate['key']:candidate for candidate in result['results']}
    keys=list(dict.fromkeys(body.keys))
    if any(key not in by_key for key in keys): raise HTTPException(422,'Selection is not part of this search.')
    imported=[];skipped=[]
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for key in keys:
            candidate=by_key[key]; existing=duplicate(db,candidate)
            if existing:
                skipped.append({'key':key,'lead_id':existing});continue
            notes=f'Imported after manual review. {ATTRIBUTION}. Missing website metadata does not prove no website. Address: {candidate["address"]}'[:1000]
            row=db.execute('INSERT INTO leads (business_name,category,city,phone,website,contact_allowed,consent_source,notes,discovery_source,discovery_source_id,discovery_source_url,discovery_observed_at) VALUES (?,?,?,?,?,0,?,?,?,?,?,?)',
                (candidate['business_name'],candidate['category'],candidate['city'],candidate['phone'],candidate['website'],'',notes,'osm',key,candidate['source_url'],result['observed_at']))
            imported.append({'key':key,'lead_id':row.lastrowid})
    return {'imported':imported,'skipped_duplicates':skipped,'contact_allowed':False,'attribution':ATTRIBUTION}
