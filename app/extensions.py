"""Additive feature endpoints. Existing /chat remains plain-text streaming."""
import base64
import hashlib
import json
import os
import re
import secrets
import threading
import time
from collections import defaultdict,deque
from urllib.parse import urlsplit
from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel,Field, ValidationError
from starlette.responses import JSONResponse,StreamingResponse
from app import storage
from app.llm import stream_gemini
from app.quality import evaluate
from app.retrieval import context_for
from app.uploads import ingest, MAX_BYTES
router=APIRouter(prefix='/api')
_attempts=defaultdict(deque); _lock=threading.Lock()

def install_extensions(app):
    @app.middleware('http')
    async def same_origin(request,call_next):
        if request.method in {'POST','PUT','PATCH','DELETE'}:
            origin=request.headers.get('origin')
            if origin and origin != str(request.base_url).rstrip('/'):
                return JSONResponse({'detail':'Cross-origin write blocked.'},status_code=403)
            try:size=int(request.headers.get('content-length','0'))
            except ValueError:return JSONResponse({'detail':'Invalid content length.'},status_code=400)
            if size>12*1024*1024:return JSONResponse({'detail':'Request is too large.'},status_code=413)
        # Optional site-wide login gate. Private user data always requires authorization.
        gated = request.url.path == '/chat' or (request.url.path.startswith('/api/') and not request.url.path.startswith('/api/auth/'))
        if os.getenv('HYNEX_REQUIRE_LOGIN','0')=='1' and gated and not storage.user(request):
            return JSONResponse({'detail':'Please sign in to use Hynex.'},status_code=401)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer' if request.url.path.startswith('/api/auth/google/') else 'same-origin'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Permissions-Policy']='camera=(), geolocation=(), microphone=(self)'
        # Authorize the original inline app script by hash, not arbitrary injected scripts.
        index_path=storage.ROOT/'static/index.html'
        inline=re.findall(r'<script>(.*?)</script>',index_path.read_text(encoding='utf-8'),re.S)
        hashes=' '.join("'sha256-"+base64.b64encode(hashlib.sha256(text.encode()).digest()).decode()+"'" for text in inline)
        response.headers['Content-Security-Policy']=("default-src 'self'; script-src 'self' "+hashes+"; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        if os.getenv('HYNEX_COOKIE_SECURE','0')=='1':
            response.headers['Strict-Transport-Security']='max-age=31536000'
        if request.url.path.startswith('/api'):response.headers['Cache-Control']='no-store'
        return response

def visitor_key(request):
    # Request-scoped only: never stored in an account, database, cookie or log.
    key = request.headers.get('x-gemini-api-key', '').strip()
    if key and not re.fullmatch(r'[A-Za-z0-9_-]{20,256}', key):
        raise HTTPException(400, 'Invalid API key format. Paste only your Gemini API key.')
    return key

def prepare_context(request,message,ids):
    docs=storage.documents(storage.owner(request),ids) if ids else []
    context,_=context_for(message,docs)
    return context,docs

class Credentials(BaseModel):
    username:str=Field(min_length=3,max_length=32)
    password:str=Field(min_length=10,max_length=128)

def auth_limit(request):
    key=request.client.host if request.client else 'local'; now=time.monotonic()
    with _lock:
        for old in list(_attempts):
            if not _attempts[old] or _attempts[old][-1]<now-300:del _attempts[old]
        q=_attempts[key]
        while q and q[0]<now-300:q.popleft()
        if len(q)>=12:raise HTTPException(429,'Too many sign-in attempts. Try again in five minutes.')
        q.append(now)

def sign_in(req,request,response,register=False):
    auth_limit(request)
    u,token=storage.authenticate(req.username,req.password,register)
    response.set_cookie(storage.COOKIE,token,httponly=True,samesite='strict',secure=os.getenv('HYNEX_COOKIE_SECURE','0')=='1',max_age=7*86400,path='/')
    return u

@router.get('/auth/config')
def auth_config():
    from app.google_login import config
    try:
        config();enabled=True
    except HTTPException:
        enabled=False
    return {'google_enabled':enabled,'require_login':os.getenv('HYNEX_REQUIRE_LOGIN','0')=='1'}

@router.post('/auth/register')
def register(req:Credentials,request:Request,response:Response):return sign_in(req,request,response,True)
@router.post('/auth/login')
def login(req:Credentials,request:Request,response:Response):return sign_in(req,request,response)
@router.get('/auth/me')
def me(request:Request):return {'user':storage.user(request)}
@router.post('/auth/logout')
def logout(request:Request,response:Response):
    with storage.db() as c:c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256(request.cookies.get(storage.COOKIE,'').encode()).hexdigest(),))
    response.delete_cookie(storage.COOKIE,path='/');return {'ok':True}

class Message(BaseModel):
    role:str=Field(pattern='^(user|assistant)$')
    content:str=Field(max_length=50000)
class Conversation(BaseModel):
    id:int|str
    title:str=Field(min_length=1,max_length=120)
    pinned:bool=False
    attachment_ids:list[str]=Field(default_factory=list,max_length=6)
    messages:list[Message]=Field(default_factory=list,max_length=500)
class Snapshot(BaseModel):
    version:int=Field(ge=0)
    chats:list[Conversation]=Field(max_length=100)
@router.get('/chats')
def read_chats(request:Request):
    u=storage.require_user(request)
    with storage.db() as c:row=c.execute('SELECT * FROM snapshots WHERE uid=?',(u['id'],)).fetchone()
    return {'version':row['version'],'chats':json.loads(row['body'])} if row else {'version':0,'chats':[]}
@router.put('/chats')
def save_chats(req:Snapshot,request:Request):
    u=storage.require_user(request);body=json.dumps([v.model_dump() for v in req.chats])
    if len(body.encode())>3*1024*1024:raise HTTPException(413,'Chat backup exceeds 3 MB. Export and remove older chats.')
    with storage.db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT version FROM snapshots WHERE uid=?',(u['id'],)).fetchone();version=row['version'] if row else 0
        if req.version!=version:raise HTTPException(409,'Another tab updated your chats. Export this tab, then reload before syncing.')
        c.execute('INSERT INTO snapshots VALUES(?,?,?) ON CONFLICT(uid) DO UPDATE SET version=excluded.version,body=excluded.body',(u['id'],version+1,body))
    return {'version':version+1}

@router.post('/uploads')
async def upload(request:Request,file:UploadFile=File(...)):
    try:content=await file.read(MAX_BYTES+1)
    finally:await file.close()
    return ingest(content,file.filename,storage.owner(request))
@router.get('/uploads')
def list_uploads(request:Request):return storage.documents(storage.owner(request))
@router.delete('/uploads/{ident}')
def delete_upload(ident:str,request:Request):
    who=storage.owner(request)
    with storage.db() as c:result=c.execute('DELETE FROM documents WHERE id=? AND owner=?',(ident,who))
    if not result.rowcount:raise HTTPException(404,'File not found.')
    return {'ok':True}

class StudyRequest(BaseModel):
    topic:str=Field(min_length=1,max_length=4000)
    attachment_ids:list[str]=Field(default_factory=list,max_length=6)
    kind:str=Field(default='quiz',pattern='^(quiz|flashcards)$')
    count:int=Field(default=5,ge=1,le=10)
class QuizQuestion(BaseModel):
    question:str=Field(min_length=1,max_length=3000)
    options:list[str]=Field(min_length=4,max_length=4)
    correct_index:int=Field(ge=0,le=3,strict=True)
    explanation:str=Field(min_length=1,max_length=4000)
class QuizSet(BaseModel):
    questions:list[QuizQuestion]=Field(min_length=1,max_length=10)
class Flashcard(BaseModel):
    front:str=Field(min_length=1,max_length=3000)
    back:str=Field(min_length=1,max_length=5000)
class FlashcardSet(BaseModel):
    cards:list[Flashcard]=Field(min_length=1,max_length=10)
class AttachmentRequest(BaseModel):
    attachment_ids:list[str]=Field(min_length=1,max_length=6)

@router.post('/summarize')
def summarize(req:AttachmentRequest,request:Request):
    key=visitor_key(request)
    if not key:raise HTTPException(400,'Add your Gemini API key using API key before requesting a summary.')
    docs=storage.documents(storage.owner(request),req.attachment_ids)
    # Bound combined output context and explicitly tell users which source range was sent.
    notes='\n\n'.join(f"[{d['name']}]\n{d['text'][:30000]}" for d in docs)
    if len(notes)>100000:raise HTTPException(400,'Summarize fewer files at once.')
    def generate():
        try:
            yield from stream_gemini([], 'Summarize each attached source separately with key points and a short revision checklist. Text sources may be excerpts limited to the first 30,000 characters; say when the available text is incomplete. Do not invent unreadable content.',notes,docs,api_key=key)
        except Exception:
            yield '\n\n[Summary unavailable. Check Gemini API key, model access, connection and quota.]'
    return StreamingResponse(generate(),media_type='text/plain; charset=utf-8')

@router.post('/study')
def study(req:StudyRequest,request:Request):
    key=visitor_key(request)
    if not key:raise HTTPException(400,'Add your Gemini API key using API key before generating study material.')
    context,docs=prepare_context(request,req.topic,req.attachment_ids)
    schema='{"questions":[{"question":"...","options":["A","B","C","D"],"correct_index":0,"explanation":"..."}]}' if req.kind=='quiz' else '{"cards":[{"front":"...","back":"..."}]}'
    prompt=f'Create exactly {req.count} {req.kind} about: {req.topic}. Use provided sources when relevant and avoid unsupported claims. Return ONLY a JSON object, no markdown. Schema: {schema}. correct_index is a zero-based integer from 0 to 3.'
    try:
        raw=''.join(stream_gemini([],prompt,context,docs,api_key=key))
    except Exception:raise HTTPException(503,'Study generation needs a working Gemini connection. Check your API key, model and quota.')
    raw=re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip())
    try:
        payload=json.loads(raw)
        if req.kind=='quiz':
            result=QuizSet.model_validate(payload)
            if len(result.questions)!=req.count:raise ValueError('Wrong question count')
        else:
            result=FlashcardSet.model_validate(payload)
            if len(result.cards)!=req.count:raise ValueError('Wrong card count')
        return result.model_dump()
    except (ValueError,KeyError,TypeError):
        raise HTTPException(502,'The model returned an invalid study set. Please generate again.')


class QualityRequest(BaseModel):
    answer:str=Field(min_length=1,max_length=50000)
    reference:str=Field(default='',max_length=50000)
@router.post('/quality/check')
def check(req:QualityRequest):return evaluate(req.answer,req.reference)
class Feedback(BaseModel):
    question:str=Field(max_length=20000)
    answer:str=Field(max_length=50000)
    rating:int=Field(ge=1,le=5)
    comment:str=Field(default='',max_length=2000)
@router.post('/quality/feedback')
def feedback(req:Feedback,request:Request):
    who=storage.owner(request)
    with storage.db() as c:
        if c.execute('SELECT count(*) FROM feedback WHERE owner=?',(who,)).fetchone()[0]>=1000:raise HTTPException(400,'Feedback limit reached.')
        c.execute('INSERT INTO feedback VALUES(?,?,?,?,?,?,?)',(secrets.token_hex(16),who,req.question,req.answer,req.rating,req.comment,time.time()))
    return {'ok':True}
@router.get('/quality/feedback')
def feedback_list(request:Request):
    with storage.db() as c:return [dict(r) for r in c.execute('SELECT question,answer,rating,comment,created FROM feedback WHERE owner=? ORDER BY created DESC',(storage.owner(request),))]
class RetrieveRequest(BaseModel):
    query:str=Field(min_length=1,max_length=20000)
    attachment_ids:list[str]=Field(default_factory=list,max_length=6)
@router.post('/knowledge/search')
def search(req:RetrieveRequest,request:Request):
    docs=storage.documents(storage.owner(request),req.attachment_ids) if req.attachment_ids else []
    _,hits=context_for(req.query,docs)
    return {'method':'Hybrid TF-IDF + local LSA dense embeddings (not neural)','hits':hits}
