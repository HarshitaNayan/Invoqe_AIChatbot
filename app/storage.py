"""SQLite account/session, private uploads, chat snapshots and human feedback."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from fastapi import HTTPException, Request

ROOT = Path(__file__).resolve().parent.parent
COOKIE = 'hynex_session'

def db_path():
    return Path(os.getenv('HYNEX_DB_PATH', str(ROOT/'runtime/hynex.sqlite3')))

@contextmanager
def db():
    path=db_path(); path.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(path,timeout=20)
    con.row_factory=sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback(); raise
    finally: con.close()

def init_db():
    with db() as c:
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE, salt TEXT, password TEXT);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, uid TEXT, expires REAL);
        CREATE TABLE IF NOT EXISTS snapshots(uid TEXT PRIMARY KEY, version INTEGER NOT NULL, body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY, owner TEXT, name TEXT, mime TEXT, text TEXT, raw BLOB, created REAL);
        CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY, owner TEXT, question TEXT, answer TEXT, rating INTEGER, comment TEXT, created REAL);
        CREATE INDEX IF NOT EXISTS document_owner ON documents(owner);
        ''')

def user(request: Request):
    token=request.cookies.get(COOKIE,'')
    if not token:return None
    digest=hashlib.sha256(token.encode()).hexdigest()
    with db() as c:
        row=c.execute('SELECT users.id, username FROM sessions JOIN users ON users.id=sessions.uid WHERE token=? AND expires>?',(digest,time.time())).fetchone()
    return dict(row) if row else None

def require_user(request):
    u=user(request)
    if not u:raise HTTPException(401,'Sign in to use server chat storage.')
    return u

def owner(request):
    u=user(request)
    if u:return 'user:'+u['id']
    token=request.headers.get('x-guest-id','')
    if not re.fullmatch(r'[a-f0-9]{64}',token):raise HTTPException(401,'A guest session is required. Refresh the page.')
    return 'guest:'+hashlib.sha256(token.encode()).hexdigest()

def hash_password(password,salt):
    return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1,maxmem=64*1024*1024).hex()

def authenticate(username,password,register=False):
    username=username.strip().lower()
    if not re.fullmatch(r'[a-z0-9_]{3,32}',username):raise HTTPException(400,'Username: 3–32 lowercase letters, numbers or underscores.')
    if not 10<=len(password)<=128:raise HTTPException(400,'Password must have 10–128 characters.')
    with db() as c:
        row=c.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
        if register:
            if row:raise HTTPException(409,'Username is unavailable.')
            salt=secrets.token_hex(16); uid=secrets.token_hex(16)
            try:c.execute('INSERT INTO users VALUES(?,?,?,?)',(uid,username,salt,hash_password(password,salt)))
            except sqlite3.IntegrityError:raise HTTPException(409,'Username is unavailable.')
        else:
            # Perform the expensive hash even for unknown accounts.
            salt=row['salt'] if row else '00'*16
            digest=hash_password(password,salt)
            if not row or not hmac.compare_digest(digest,row['password']):raise HTTPException(401,'Incorrect username or password.')
            uid=row['id']
        token=secrets.token_urlsafe(32)
        c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,time.time()+7*86400))
    return {'id':uid,'username':username},token

def documents(owner_id, ids=None):
    if ids is not None and len(ids)>6:raise HTTPException(400,'Attach up to six files per request.')
    with db() as c:
        if ids is None:
            return [dict(r) for r in c.execute('SELECT id,name,mime,created,length(text) AS characters FROM documents WHERE owner=? ORDER BY created DESC',(owner_id,))]
        rows=[]
        for ident in dict.fromkeys(ids):
            row=c.execute('SELECT * FROM documents WHERE id=? AND owner=?',(ident,owner_id)).fetchone()
            if not row:raise HTTPException(404,'An attached file is missing or belongs to another session. Reattach it.')
            rows.append(dict(row))
        return rows
