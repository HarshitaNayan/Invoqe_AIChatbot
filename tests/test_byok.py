import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from app.main import app
from app.llm import stream_gemini

class VisitorKeys(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ, {'HYNEX_DB_PATH':str(Path(self.tmp.name)/'db.sqlite3'), 'GEMINI_API_KEY':'owner-key-must-not-be-used', 'HYNEX_REQUIRE_LOGIN':'0'})
        self.env.start();self.client=TestClient(app);self.client.__enter__()
    def tearDown(self):
        self.client.__exit__(None,None,None);self.env.stop();self.tmp.cleanup()
    def test_no_owner_fallback(self):
        with patch('app.llm.requests.post') as post:
            self.assertIn('Offline mode',self.client.post('/chat',json={'message':'hello'}).text)
            self.assertEqual(self.client.post('/api/study',json={'topic':'math'}).status_code,400)
            post.assert_not_called()
    def test_keys_are_request_scoped(self):
        keys=['visitor-one-key-for-tests','visitor-two-key-for-tests']
        for key in keys:
            with patch('app.main.stream_gemini',return_value=iter(['answer'])) as stream:
                r=self.client.post('/chat',headers={'X-Gemini-API-Key':key},json={'message':'explain recursion'})
                self.assertEqual(r.text,'answer');self.assertNotIn(key,r.text)
                self.assertEqual(stream.call_args.kwargs['api_key'],key)
        with patch('app.main.stream_gemini',return_value=iter(['offline'])) as stream:
            self.client.post('/chat',json={'message':'hello'})
            self.assertEqual(stream.call_args.kwargs['api_key'],'')
    def test_study_and_summary_forward_key(self):
        key='visitor-study-key-for-tests';h={'X-Gemini-API-Key':key,'X-Guest-ID':'a'*64}
        data={'cards':[{'front':'Question','back':'Answer'}]}
        with patch('app.extensions.stream_gemini',return_value=iter([json.dumps(data)])) as stream:
            r=self.client.post('/api/study',headers=h,json={'topic':'math','kind':'flashcards','count':1})
            self.assertEqual(r.status_code,200);self.assertEqual(stream.call_args.kwargs['api_key'],key)
        doc=self.client.post('/api/uploads',headers=h,files={'file':('notes.txt',b'A useful study note.')}).json()['id']
        with patch('app.extensions.stream_gemini',return_value=iter(['summary'])) as stream:
            self.assertEqual(self.client.post('/api/summarize',headers=h,json={'attachment_ids':[doc]}).text,'summary')
            self.assertEqual(stream.call_args.kwargs['api_key'],key)
        self.assertNotIn(key,Path(self.tmp.name,'db.sqlite3').read_bytes().decode('latin1'))
    def test_only_selected_key_sent_to_google(self):
        response=Mock(ok=True);response.iter_lines.return_value=iter(['data: '+json.dumps({'candidates':[{'content':{'parts':[{'text':'answer'}]}}]})])
        with patch('app.llm.requests.post',return_value=response) as post:
            self.assertEqual(''.join(stream_gemini([],'hi','',api_key='visitor-only-key')),'answer')
            self.assertEqual(post.call_args.kwargs['headers'],{'x-goog-api-key':'visitor-only-key'})
    def test_bad_header_rejected(self):
        r=self.client.post('/chat',headers={'X-Gemini-API-Key':'bad key'},json={'message':'hello'})
        self.assertEqual(r.status_code,400)

    def test_dotted_key_reaches_provider_unchanged(self):
        key='AQ.fake-test-only.dotted_key-1234567890'
        with patch('app.main.stream_gemini',return_value=iter(['answer'])) as stream:
            result=self.client.post('/chat',headers={'X-Gemini-API-Key':key},json={'message':'Explain a loop'})
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.text,'answer')
            self.assertEqual(stream.call_args.kwargs['api_key'],key)
        for key in ['a'*2049, 'AQ.invalid key with spaces', 'AQ.bad"quoted-key-123456']:
            self.assertEqual(self.client.post('/chat',headers={'X-Gemini-API-Key':key},json={'message':'hi'}).status_code,400)
