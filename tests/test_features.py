import io,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter
from app.main import app
from app.retrieval import retrieve
from app.quality import evaluate
from app.llm import stream_gemini
class Features(unittest.TestCase):
 def setUp(self):
  from app.extensions import _attempts
  _attempts.clear()
  self.tmp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'HYNEX_DB_PATH':str(Path(self.tmp.name)/'test.sqlite3')});self.env.start();self.c=TestClient(app);self.c.__enter__();self.g={'X-Guest-ID':'a'*64};self.other={'X-Guest-ID':'b'*64}
 def tearDown(self):self.c.__exit__(None,None,None);self.env.stop();self.tmp.cleanup()
 def upload(self):return self.c.post('/api/uploads',headers=self.g,files={'file':('notes.txt',b'Recursion calls a function itself with a base case.')})
 def test_original_chat(self):
  self.assertIn('What do you want to learn today?',self.c.get('/').text)
  with patch.dict(os.environ,{'GEMINI_API_KEY':''}):r=self.c.post('/chat',json={'message':'hello'})
  self.assertIn('Offline mode',r.text)
 def test_upload_isolation(self):
  r=self.upload();self.assertEqual(r.status_code,200,r.text);ident=r.json()['id']
  self.assertEqual(self.c.get('/api/uploads',headers=self.other).json(),[])
  self.assertEqual(self.c.post('/chat',headers=self.other,json={'message':'summarize','attachment_ids':[ident]}).status_code,404)
  self.assertEqual(self.c.delete('/api/uploads/'+ident,headers=self.other).status_code,404)
  self.assertEqual(self.c.delete('/api/uploads/'+ident,headers=self.g).status_code,200)
 def test_upload_formats(self):
  for name,data,code in [('bad.exe',b'hello',400),('bad.png',b'bad',400),('large.txt',b'a'*(5*1024*1024+1),413)]:
   self.assertEqual(self.c.post('/api/uploads',headers=self.g,files={'file':(name,data)}).status_code,code)
  b=io.BytesIO();Image.new('RGB',(2,2),'red').save(b,format='PNG')
  r=self.c.post('/api/uploads',headers=self.g,files={'file':('image.png',b.getvalue())});self.assertEqual(r.status_code,200);self.assertTrue(r.json()['vision_required'])
  b=io.BytesIO();w=PdfWriter();w.add_blank_page(width=100,height=100);w.write(b)
  r=self.c.post('/api/uploads',headers=self.g,files={'file':('scan.pdf',b.getvalue())});self.assertEqual(r.status_code,200);self.assertTrue(r.json()['vision_required'])
 def test_accounts_sync_conflict(self):
  cred={'username':'test_student','password':'test-password-long'}
  self.assertEqual(self.c.post('/api/auth/register',json=cred).status_code,200)
  self.assertEqual(self.c.get('/api/auth/me').json()['user']['username'],'test_student')
  chats=[{'id':123,'title':'Renamed chat','pinned':True,'messages':[{'role':'user','content':'Hi'}]}]
  self.assertEqual(self.c.put('/api/chats',json={'version':0,'chats':chats}).json()['version'],1)
  self.assertEqual(self.c.put('/api/chats',json={'version':0,'chats':[]}).status_code,409)
  self.c.post('/api/auth/logout');self.assertEqual(self.c.get('/api/chats').status_code,401)
  self.assertEqual(self.c.post('/api/auth/login',json={**cred,'password':'incorrect-password'}).status_code,401)
  self.assertEqual(self.c.post('/api/auth/login',json=cred).status_code,200)
  self.assertEqual(self.c.get('/api/chats').json()['chats'][0]['title'],'Renamed chat')
  self.c.post('/api/auth/logout');self.c.post('/api/auth/register',json={'username':'another_student','password':'different-password'})
  self.assertEqual(self.c.get('/api/chats').json()['chats'],[])
 def test_origin_and_private_files(self):
  self.assertEqual(self.c.post('/api/auth/logout',headers={'Origin':'https://evil.example'}).status_code,403)
  self.assertEqual(self.c.get('/runtime/hynex.sqlite3').status_code,404)
  self.assertEqual(self.c.get('/.env').status_code,404)
 def test_retrieval_feedback(self):
  hits=retrieve('numpy reshape array dimensions');self.assertTrue(hits)
  doc=self.upload().json()['id'];r=self.c.post('/api/knowledge/search',headers=self.g,json={'query':'recursive function base case','attachment_ids':[doc]});self.assertEqual(r.status_code,200);self.assertTrue(r.json()['hits'])
  self.assertEqual(evaluate('same answer','same answer')['token_f1'],1)
  self.assertEqual(self.c.post('/api/quality/feedback',headers=self.g,json={'question':'recursion','answer':'A function calls itself','rating':4}).status_code,200)
  self.assertEqual(len(self.c.get('/api/quality/feedback',headers=self.g).json()),1)
  self.assertEqual(len(self.c.get('/api/quality/feedback',headers=self.other).json()),0)
 def test_study_summary(self):
  q={'questions':[{'question':'2+2?','options':['1','2','3','4'],'correct_index':3,'explanation':'2+2=4'}]}
  with patch('app.extensions.stream_gemini',return_value=iter([json.dumps(q)])):
   self.assertEqual(self.c.post('/api/study',json={'topic':'addition','count':1}).status_code,200)
  with patch('app.extensions.stream_gemini',return_value=iter(['{"cards":[{"front":"Q","back":"A"}]}'])):
   self.assertEqual(self.c.post('/api/study',json={'topic':'test','count':1,'kind':'flashcards'}).status_code,200)
  with patch('app.extensions.stream_gemini',return_value=iter(['not JSON'])):
   self.assertEqual(self.c.post('/api/study',json={'topic':'test','count':1}).status_code,502)
  doc=self.upload().json()['id']
  with patch('app.extensions.stream_gemini',return_value=iter(['A short summary.'])):
   self.assertIn('short summary',self.c.post('/api/summarize',headers=self.g,json={'attachment_ids':[doc]}).text)
  with patch.dict(os.environ,{'GEMINI_API_KEY':''}):self.assertEqual(self.c.post('/api/study',json={'topic':'test'}).status_code,503)
 def test_multimodal_contract(self):
  response=Mock(ok=True);response.iter_lines.return_value=iter(['data: '+json.dumps({'candidates':[{'content':{'parts':[{'text':'Visible image'}]}}]})])
  with patch.dict(os.environ,{'GEMINI_API_KEY':'test-only'}),patch('app.llm.requests.post',return_value=response) as post:
   self.assertEqual(''.join(stream_gemini([],'describe','',[{'mime':'image/png','raw':b'example'}])),'Visible image')
   self.assertEqual(post.call_args.kwargs['json']['contents'][-1]['parts'][1]['inline_data']['mime_type'],'image/png');response.close.assert_called_once()
if __name__=='__main__':unittest.main()
