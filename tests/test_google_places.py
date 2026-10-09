import json
import os
from unittest.mock import patch
import httpx
from tests.test_queue import QueueFixture
from backend import db

class GooglePlacesTests(QueueFixture):
    def body(self):return {'query':'Restaurants in Hyderabad','cost_acknowledged':True}
    def configured(self):return patch.dict(os.environ,{'GOOGLE_PLACES_ENABLED':'1','GOOGLE_PLACES_API_KEY':'fictional-test-key','GOOGLE_PLACES_BILLING_APPROVED':'1','GOOGLE_PLACES_TERMS_REVIEWED':'1','GOOGLE_PLACES_DAILY_LIMIT':'1'})
    def test_disabled_by_default_and_no_provider_call(self):
        with patch.dict(os.environ,{'GOOGLE_PLACES_ENABLED':'0'}),patch('backend.google_places.httpx.Client') as network:
            self.assertFalse(self.client.get('/api/google-places/status').json()['configured'])
            self.assertEqual(self.client.post('/api/google-places/search',json=self.body()).status_code,403)
            network.assert_not_called()
    def test_ids_only_no_import_no_retry_and_durable_quota(self):
        requests=[]
        def transport(request):
            requests.append(request)
            self.assertEqual(request.headers['x-goog-fieldmask'],'places.id')
            self.assertEqual(json.loads(request.content)['pageSize'],10)
            return httpx.Response(200,json={'places':[{'id':'ChIJ_fictional','displayName':{'text':'Must not persist'}}]})
        original=httpx.Client
        with self.configured(),patch('backend.google_places.httpx.Client',side_effect=lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(transport))):
            r=self.client.post('/api/google-places/search',json=self.body())
            self.assertEqual(r.status_code,200);self.assertEqual(len(r.json()['results']),1)
            self.assertNotIn('Must not persist',r.text);self.assertFalse(r.json()['contact_allowed'])
            self.assertEqual(self.client.post('/api/google-places/search',json=self.body()).status_code,429)
        self.assertEqual(len(requests),1)
        with db.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM leads').fetchone()[0],1)
            self.assertEqual(connection.execute('SELECT count(*) FROM external_request_attempts').fetchone()[0],1)
    def test_failure_consumes_slot_and_cannot_leak_key(self):
        original=httpx.Client
        with self.configured(),patch('backend.google_places.httpx.Client',side_effect=lambda **kwargs:original(**kwargs,transport=httpx.MockTransport(lambda request:httpx.Response(403,json={'error':'fictional-test-key'})))):
            r=self.client.post('/api/google-places/search',json=self.body())
            self.assertEqual(r.status_code,503);self.assertNotIn('fictional-test-key',r.text)
            self.assertEqual(self.client.post('/api/google-places/search',json=self.body()).status_code,429)
    def test_operator_and_unacknowledged_costs_rejected(self):
        with self.configured(),patch('backend.google_places.httpx.Client') as network:
            data=self.body();data['cost_acknowledged']=False
            self.assertEqual(self.client.post('/api/google-places/search',json=data).status_code,422)
            with patch.dict(os.environ,{'AKKI_ADMIN_KEY':'k'*40,'AKKI_TEAM_KEYS':json.dumps({'staff':{'role':'operator','key':'o'*40}})}):
                self.assertEqual(self.client.post('/api/google-places/search',headers={'Authorization':'Bearer '+'o'*40},json=self.body()).status_code,403)
            network.assert_not_called()
