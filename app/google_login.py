"""Google OIDC authorization code flow with state, nonce and PKCE.
No Google passwords or long-lived Google access tokens are accepted or stored.
"""
import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import time
from urllib.parse import urlencode,urlsplit
import requests
from fastapi import APIRouter,HTTPException,Request
from fastapi.responses import RedirectResponse,HTMLResponse
from google.oauth2 import id_token
from google.auth.transport.requests import Request as GoogleRequest
from app import storage
router=APIRouter(prefix='/api/auth/google')
FLOW_COOKIE='hynex_google_flow'
CALLBACK_PATH='/api/auth/google/callback'

def config():
    cid=os.getenv('GOOGLE_CLIENT_ID','').strip()
    secret=os.getenv('GOOGLE_CLIENT_SECRET','').strip()
    redirect=os.getenv('GOOGLE_REDIRECT_URI','').strip()
    if not cid or not secret or not redirect:raise HTTPException(503,'Google sign-in is not configured. Follow GOOGLE_SIGN_IN_SETUP.md; never enter your Google password into Hynex.')
    url=urlsplit(redirect)
    local=url.hostname in {'127.0.0.1','localhost'}
    if (url.scheme!='https' and not (local and url.scheme=='http')) or not url.netloc or url.path!=CALLBACK_PATH or url.query or url.fragment or url.username or url.password:
        raise HTTPException(503,'Invalid Google callback configuration. Use HTTPS, or localhost HTTP for development, ending in '+CALLBACK_PATH)
    if not local and os.getenv('HYNEX_COOKIE_SECURE','0')!='1':raise HTTPException(503,'Public Google sign-in requires HYNEX_COOKIE_SECURE=1 and HTTPS.')
    return cid,secret,redirect

class RedactOAuthQuery(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3:
            args=list(record.args)
            if isinstance(args[2],str) and args[2].startswith(CALLBACK_PATH+'?'):
                args[2]=CALLBACK_PATH+'?[redacted]'
                record.args=tuple(args)
        return True

def init_google_tables():
    access=logging.getLogger('uvicorn.access')
    if not any(isinstance(f,RedactOAuthQuery) for f in access.filters):
        access.addFilter(RedactOAuthQuery())
    with storage.db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS google_flows(state_hash TEXT PRIMARY KEY, binding_hash TEXT, nonce TEXT, verifier TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS google_identities(sub TEXT PRIMARY KEY, uid TEXT UNIQUE, email TEXT);
        ''')

def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def flow_cookie_secure(redirect):return urlsplit(redirect).scheme=='https'

def attach_session(response,token,redirect):
    response.set_cookie(storage.COOKIE,token,httponly=True,secure=flow_cookie_secure(redirect),samesite='strict',max_age=7*86400,path='/')
    response.delete_cookie(FLOW_COOKIE,path=CALLBACK_PATH,secure=flow_cookie_secure(redirect),httponly=True,samesite='lax')

def google_account(claims):
    # Identity is Google's stable subject, not an email address supplied by a client.
    subject=claims['sub']; email=claims.get('email','')
    with storage.db() as c:
        c.execute('BEGIN IMMEDIATE')
        row=c.execute('SELECT uid FROM google_identities WHERE sub=?',(subject,)).fetchone()
        if row:
            uid=row['uid'];username=c.execute('SELECT username FROM users WHERE id=?',(uid,)).fetchone()['username']
            c.execute('UPDATE google_identities SET email=? WHERE sub=?',(email,subject))
        else:
            uid=secrets.token_hex(16)
            label=re.sub(r'[^a-z0-9]+','_',str(claims.get('given_name','student')).lower()).strip('_')[:14] or 'student'
            username='google_'+label+'_'+secrets.token_hex(4)
            # A random unrecoverable local password prevents password login to this account.
            salt=secrets.token_hex(16)
            c.execute('INSERT INTO users VALUES(?,?,?,?)',(uid,username,salt,storage.hash_password(secrets.token_urlsafe(64),salt)))
            c.execute('INSERT INTO google_identities VALUES(?,?,?)',(subject,uid,email))
        token=secrets.token_urlsafe(32)
        c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(digest(token),uid,time.time()+7*86400))
    return token

@router.get('/start')
def start(request:Request):
    cid,_,redirect=config()
    from app.extensions import auth_limit
    auth_limit(request)
    state=secrets.token_urlsafe(32);binding=secrets.token_urlsafe(32);nonce=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    with storage.db() as c:
        c.execute('DELETE FROM google_flows WHERE expires<?',(time.time(),))
        c.execute('INSERT INTO google_flows VALUES(?,?,?,?,?)',(digest(state),digest(binding),nonce,verifier,time.time()+600))
    target='https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':cid,'redirect_uri':redirect,'response_type':'code','scope':'openid email profile','state':state,'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256','prompt':'select_account'})
    response=RedirectResponse(target,status_code=303)
    response.set_cookie(FLOW_COOKIE,binding,httponly=True,samesite='lax',secure=flow_cookie_secure(redirect),max_age=600,path=CALLBACK_PATH)
    response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer'
    return response

def verify_claims(token,cid,nonce):
    # Official Google verifier checks signature, audience, issuer and expiry.
    claims=id_token.verify_oauth2_token(token,GoogleRequest(),audience=cid)
    if not isinstance(claims.get('sub'),str) or not claims['sub'] or len(claims['sub'])>255:raise ValueError('Missing subject')
    if not isinstance(claims.get('nonce'),str) or not hmac.compare_digest(claims['nonce'],nonce):raise ValueError('Nonce mismatch')
    if claims.get('azp') and claims['azp']!=cid:raise ValueError('Authorized party mismatch')
    if claims.get('email_verified') is not True:raise ValueError('Email not verified')
    return claims

@router.get('/callback')
def callback(request:Request,state:str='',code:str='',error:str=''):
    cid,secret,redirect=config()
    binding=request.cookies.get(FLOW_COOKIE,'')
    if not state or not binding or len(state)>256 or len(binding)>256:raise HTTPException(400,'Google sign-in session is missing. Start sign-in again from Hynex.')
    # Consume a valid browser-bound flow exactly once, including on errors.
    with storage.db() as c:
        c.execute('BEGIN IMMEDIATE')
        flow=c.execute('SELECT * FROM google_flows WHERE state_hash=?',(digest(state),)).fetchone()
        if not flow or flow['expires']<time.time() or not hmac.compare_digest(flow['binding_hash'],digest(binding)):
            raise HTTPException(400,'Google sign-in session is invalid or expired. Start again from Hynex.')
        c.execute('DELETE FROM google_flows WHERE state_hash=?',(digest(state),))
    if error or not code or len(code)>4096:
        response=RedirectResponse('/?signin=cancelled',status_code=303)
        response.delete_cookie(FLOW_COOKIE,path=CALLBACK_PATH);return response
    try:
        r=requests.post('https://oauth2.googleapis.com/token',data={'client_id':cid,'client_secret':secret,'code':code,'code_verifier':flow['verifier'],'grant_type':'authorization_code','redirect_uri':redirect},timeout=20)
        try:
            r.raise_for_status();token=r.json().get('id_token')
        finally:r.close()
        if not token:raise ValueError('ID token missing')
        claims=verify_claims(token,cid,flow['nonce'])
        session=google_account(claims)
    except Exception:
        # Never expose ID tokens, authorization codes, secrets or provider response bodies.
        response=RedirectResponse('/?signin=failed',status_code=303)
        response.delete_cookie(FLOW_COOKIE,path=CALLBACK_PATH);return response
    # Rotate the previous Hynex session rather than retaining an older credential.
    old=request.cookies.get(storage.COOKIE)
    if old:
        with storage.db() as c:c.execute('DELETE FROM sessions WHERE token=?',(digest(old),))
    response=RedirectResponse('/',status_code=303)
    attach_session(response,session,redirect)
    response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer'
    return response
