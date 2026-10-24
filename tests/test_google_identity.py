import json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from urllib.parse import urlsplit,parse_qs
from fastapi.testclient import TestClient
from app.main import app
from app import storage
from app.google_login import FLOW_COOKIE,CALLBACK_PATH,verify_claims
from app.identity import creator_reply
class GoogleAndIdentity(unittest.TestCase):
 def setUp(self):
  from app.extensions import _attempts
  _attempts.clear()
  self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'HYNEX_DB_PATH':str(Path(self.tmp.name)/'auth.sqlite3'),'GOOGLE_CLIENT_ID':'test-client.apps.googleusercontent.com','GOOGLE_CLIENT_SECRET':'test-secret-not-real','GOOGLE_REDIRECT_URI':'http://testserver/api/auth/google/callback','HYNEX_REQUIRE_LOGIN':'0'})
  self.env.start();self.valid=patch('app.google_login.config',return_value=('test-client.apps.googleusercontent.com','test-secret-not-real','http://testserver/api/auth/google/callback'));self.valid.start()
  self.c=TestClient(app);self.c.__enter__()
 def tearDown(self):self.c.__exit__(None,None,None);self.valid.stop();self.env.stop();self.tmp.cleanup()
 def begin(self):
  r=self.c.get('/api/auth/google/start',follow_redirects=False);self.assertEqual(r.status_code,303)
  q=parse_qs(urlsplit(r.headers['location']).query)
  self.assertEqual(q['code_challenge_method'],['S256']);self.assertEqual(q['scope'],['openid email profile']);self.assertNotIn('test-secret',r.headers['location']);self.assertIn('HttpOnly',r.headers['set-cookie']);self.assertIn('SameSite=lax',r.headers['set-cookie'])
  return q
 def token_response(self):return Mock(status_code=200,json=lambda:{'id_token':'mock-jwt'})
 def claims(self,q,**overrides):return {'sub':'google-subject-123','email':'student@example.com','email_verified':True,'nonce':q['nonce'][0],'azp':'test-client.apps.googleusercontent.com',**overrides}
 def callback(self,q):return self.c.get(CALLBACK_PATH,params={'state':q['state'][0],'code':'test-code'},follow_redirects=False)
 def test_verified_login_and_single_use(self):
  q=self.begin()
  with patch('app.google_login.requests.post',return_value=self.token_response()) as exchange,patch('app.google_login.id_token.verify_oauth2_token',return_value=self.claims(q)) as verify:
   r=self.callback(q);self.assertEqual(r.headers['location'],'/');self.assertIn('HttpOnly',r.headers['set-cookie']);self.assertIn('SameSite=strict',r.headers['set-cookie']);self.assertEqual(verify.call_args.kwargs['audience'],'test-client.apps.googleusercontent.com');self.assertTrue(exchange.call_args.kwargs['data']['code_verifier'])
  u=self.c.get('/api/auth/me').json()['user'];self.assertIsNotNone(u)
  self.assertEqual(self.callback(q).status_code,400)
  self.c.post('/api/auth/logout');self.assertIsNone(self.c.get('/api/auth/me').json()['user'])
  # Repeated Google login returns the same local owner, not a new account.
  q=self.begin()
  with patch('app.google_login.requests.post',return_value=self.token_response()),patch('app.google_login.id_token.verify_oauth2_token',return_value=self.claims(q)):self.callback(q)
  self.assertEqual(self.c.get('/api/auth/me').json()['user']['id'],u['id'])
 def test_callback_log_redaction(self):
  import logging
  from app.google_login import RedactOAuthQuery
  record=logging.LogRecord('uvicorn.access',20,'',0,'%s %s %s %s %s',('client','GET',CALLBACK_PATH+'?code=private&state=private','1.1',303),None)
  RedactOAuthQuery().filter(record)
  self.assertNotIn('private',record.getMessage())
 def test_invalid_state_and_cookie(self):
  q=self.begin();self.assertEqual(self.c.get(CALLBACK_PATH,params={'state':'tampered','code':'test'}).status_code,400)
  self.c.cookies.clear();self.assertEqual(self.callback(q).status_code,400)
 def test_expired_flow(self):
  q=self.begin()
  with storage.db() as c:c.execute('UPDATE google_flows SET expires=?',(time.time()-10,))
  self.assertEqual(self.callback(q).status_code,400)
 def test_bad_nonce_rejected(self):
  q=self.begin()
  with patch('app.google_login.requests.post',return_value=self.token_response()),patch('app.google_login.id_token.verify_oauth2_token',return_value=self.claims(q,nonce='wrong')):
   self.assertEqual(self.callback(q).headers['location'],'/?signin=failed')
  self.assertIsNone(self.c.get('/api/auth/me').json()['user'])
 def test_signature_failure_rejected(self):
  q=self.begin()
  with patch('app.google_login.requests.post',return_value=self.token_response()),patch('app.google_login.id_token.verify_oauth2_token',side_effect=ValueError('invalid signature')):
   self.assertEqual(self.callback(q).headers['location'],'/?signin=failed')
  self.assertIsNone(self.c.get('/api/auth/me').json()['user'])
 def test_cancel_and_missing_config(self):
  q=self.begin();r=self.c.get(CALLBACK_PATH,params={'state':q['state'][0],'error':'access_denied'},follow_redirects=False);self.assertEqual(r.headers['location'],'/?signin=cancelled')
  self.valid.stop()
  with patch.dict(os.environ,{'GOOGLE_CLIENT_ID':''}):self.assertEqual(self.c.get('/api/auth/google/start').status_code,503)
  self.valid.start()
 def test_login_gate(self):
  with patch.dict(os.environ,{'HYNEX_REQUIRE_LOGIN':'1'}):
   self.assertEqual(self.c.post('/chat',json={'message':'hi'}).status_code,401)
   self.assertEqual(self.c.post('/api/study',json={'topic':'Python'}).status_code,401)
   self.assertTrue(self.c.get('/api/auth/config').json()['require_login'])
   self.assertEqual(self.c.post('/api/auth/register',json={'username':'allowed_student','password':'test-password-long'}).status_code,200)
   self.assertEqual(self.c.get('/api/chats').status_code,200)
 def test_creator_without_google(self):
  for text in ['Who made you?','Who created Hynex?','Tell me your creator name','Who is your developer?','Tumhe kisne banaya?']:
   with patch('app.main.stream_gemini') as llm:
    r=self.c.post('/chat',json={'message':text});self.assertEqual(r.text,'Hynex was created by Harshita Nayan.');llm.assert_not_called()
  self.assertIsNone(creator_reply('Who created Google?'))
 def test_provider_does_not_link_by_email(self):
  # Two different Google subjects with identical emails remain different accounts.
  ids=[]
  for sub in ['first-sub','second-sub']:
   q=self.begin()
   with patch('app.google_login.requests.post',return_value=self.token_response()),patch('app.google_login.id_token.verify_oauth2_token',return_value=self.claims(q,sub=sub)):
    self.callback(q)
   ids.append(self.c.get('/api/auth/me').json()['user']['id']);self.c.post('/api/auth/logout')
  self.assertNotEqual(*ids)
if __name__=='__main__':unittest.main()
