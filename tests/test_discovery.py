import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from backend import db
from backend.discovery import OSMProvider,SearchCache,SearchRequest,get_provider,safe_website
from backend.main import app

BODY={'location':'Hyderabad','latitude':17.385,'longitude':78.4867,'category':'Restaurant','radius_m':1000}
ELEMENTS=[{'type':'node','id':1,'lat':17.386,'lon':78.486,'tags':{'name':'Fictional Discovery Cafe','phone':'+91 9876543210'}},
 {'type':'way','id':2,'center':{'lat':17.385,'lon':78.486},'tags':{'name':'Fictional Discovery Hotel','website':'https://example.org'}},
 {'type':'node','id':3,'lat':17.386,'lon':78.486,'tags':{'name':'Fictional Invalid Website','website':'javascript:alert(1)'}}]

class ProviderTests(unittest.TestCase):
    def test_osm_tags_coordinates_safe_links_and_website_uncertainty(self):
        original=httpx.Client;requests=[]
        def handler(request):
            requests.append(request);return httpx.Response(200,json={'elements':ELEMENTS})
        with patch('backend.discovery.httpx.Client',side_effect=lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(handler))):
            rows=OSMProvider().search(SearchRequest(**BODY))
        self.assertEqual(len(rows),3);self.assertIn('out+body+center+100',requests[0].content.decode())
        by_key={r['key']:r for r in rows}
        self.assertEqual(by_key['node/1']['website_signal'],'not_listed')
        self.assertEqual(by_key['node/3']['website_signal'],'needs_review')
        self.assertEqual(by_key['way/2']['website'],'https://example.org')
        self.assertEqual(by_key['node/1']['source_url'],'https://www.openstreetmap.org/node/1')
        self.assertEqual(safe_website('example.org'),'https://example.org')
        for value in ('http://127.0.0.1','https://user:password@example.org','javascript:alert(1)','http://host.local'):
            self.assertEqual(safe_website(value),'')
    def test_provider_failure_or_partial_response_is_not_empty_success(self):
        original=httpx.Client
        for data,code in [({'remark':'runtime error','elements':[]},200),({},429),({'elements':'wrong'},200)]:
            with self.subTest(code=code),patch('backend.discovery.httpx.Client',side_effect=lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(lambda request:httpx.Response(code,json=data)))):
                from fastapi import HTTPException
                with self.assertRaises(HTTPException) as context:OSMProvider().search(SearchRequest(**BODY))
                self.assertEqual(context.exception.status_code,503)

class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.old=db.DB_PATH;db.DB_PATH=Path(self.temp.name)/'test.sqlite3'
        self.cache=patch('backend.discovery.cache',SearchCache());self.cache.start()
        self.calls=0
        class FakeProvider:
            def search(inner,body):
                self.calls+=1
                return [{'key':'node/1','business_name':'Fictional Prospect','category':body.category,'city':'Hyderabad','address':'',
                         'phone':'+91 9876543210','website':'','website_signal':'not_listed','source_url':'https://www.openstreetmap.org/node/1',
                         'latitude':17.385,'longitude':78.486,'distance_m':50}]
        app.dependency_overrides[get_provider]=FakeProvider
        self.client=TestClient(app).__enter__()
    def tearDown(self):
        self.client.__exit__(None,None,None);app.dependency_overrides.clear();self.cache.stop();db.DB_PATH=self.old;self.temp.cleanup()
    def search(self):
        r=self.client.post('/api/discovery/search',json=BODY);self.assertEqual(r.status_code,200);return r.json()
    def import_result(self,result,**extra):
        return self.client.post('/api/discovery/import',json={'search_id':result['search_id'],'keys':['node/1'],'reviewed':True,**extra})
    def test_search_import_attribution_and_outreach_block(self):
        result=self.search();self.assertEqual(self.client.get('/api/stats').json()['total'],0)
        self.assertIn('OpenStreetMap',result['attribution']);self.assertFalse(self.client.get('/api/discovery/config').json()['google_connected'])
        r=self.import_result(result);self.assertEqual(r.status_code,200,r.text);identity=r.json()['imported'][0]['lead_id']
        lead=self.client.get('/api/leads/'+str(identity)).json()
        self.assertFalse(lead['contact_allowed']);self.assertEqual(lead['consent_source'],'');self.assertEqual(lead['discovery_source'],'osm')
        self.assertEqual(self.client.post(f'/api/leads/{identity}/demo/start').status_code,403)
        self.assertEqual(self.client.post('/api/lab/sessions',json={'lead_id':identity,'collection_consent':True}).status_code,403)
        self.assertEqual(self.import_result(result).json()['imported'],[])
        self.assertEqual(self.search()['results'][0]['duplicate_lead_id'],identity)
    def test_review_server_selection_expiry_and_consent_injection(self):
        result=self.search()
        self.assertEqual(self.import_result(result,reviewed=False).status_code,422)
        self.assertEqual(self.import_result(result,keys=['node/999']).status_code,422)
        self.assertEqual(self.import_result(result,contact_allowed=True).status_code,422)
        self.assertEqual(self.import_result({**result,'search_id':'missing'}).status_code,410)
        import backend.discovery as discovery
        discovery.cache.entries[result['search_id']]['created']-=901
        self.assertEqual(self.import_result(result).status_code,410)
    def test_dnc_phone_duplicate_does_not_create_or_update_lead(self):
        lead=self.client.post('/api/leads',json={'business_name':'Different Name','phone':'09876543210','city':'Other location'}).json()
        self.client.patch('/api/leads/'+str(lead['id']),json={'do_not_call':True})
        result=self.search();self.assertEqual(result['results'][0]['duplicate_lead_id'],lead['id'])
        imported=self.import_result(result).json();self.assertEqual(imported['imported'],[])
        self.assertEqual(self.client.get('/api/stats').json()['total'],1)
        self.assertTrue(self.client.get('/api/leads/'+str(lead['id'])).json()['do_not_call'])
    def test_cache_rate_bounds_and_unsupported_query(self):
        self.search();self.assertTrue(self.search()['cached']);self.assertEqual(self.calls,1)
        self.assertEqual(self.client.post('/api/discovery/search',json={**BODY,'radius_m':2000}).status_code,429)
        for changes in ({'radius_m':10000},{'latitude':1},{'category':'Injected query'},{'url':'http://127.0.0.1'}):
            self.assertEqual(self.client.post('/api/discovery/search',json={**BODY,**changes}).status_code,422)
