import io
from pathlib import Path
import secrets
import time
from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from app.storage import db
MAX_BYTES=5*1024*1024

def ingest(content,filename,who):
    name=Path(filename or 'attachment').name[:120]
    ext=Path(name).suffix.lower(); text=''; raw=b''
    if not content or len(content)>MAX_BYTES:raise HTTPException(413,'Use a nonempty file smaller than 5 MB.')
    try:
        if ext in {'.txt','.md'}:
            mime='text/plain';text=content.decode('utf-8-sig')
        elif ext=='.pdf':
            if not content.startswith(b'%PDF-'):raise ValueError('Not a PDF')
            reader=PdfReader(io.BytesIO(content))
            if reader.is_encrypted:raise HTTPException(400,'Unlock the PDF before uploading.')
            if len(reader.pages)>80:raise HTTPException(400,'Use a PDF with at most 80 pages.')
            text='\n'.join(f'[Page {i+1}]\n{p.extract_text() or ""}' for i,p in enumerate(reader.pages))
            mime='application/pdf'
            # Scans need Gemini vision; retain native PDF for those documents only.
            if len(text.strip())<40:raw=content
        elif ext in {'.png','.jpg','.jpeg','.webp'}:
            with Image.open(io.BytesIO(content)) as im:
                if im.width*im.height>20_000_000:raise HTTPException(400,'Image is too large; use at most 20 megapixels.')
                im.verify()
            mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.webp':'image/webp'}[ext];raw=content
        else:raise HTTPException(400,'Supported files: PDF, UTF-8 TXT/MD, PNG, JPG and WEBP.')
    except HTTPException:raise
    except Exception as exc:
        raise HTTPException(400,'Could not read this file. Check its format and try another copy.') from exc
    if len(text)>160000:raise HTTPException(400,'Text exceeds 160,000 characters. Split the file into smaller parts.')
    with db() as c:
        # Clean abandoned guest uploads after one day.
        c.execute("DELETE FROM documents WHERE owner LIKE 'guest:%' AND created<?",(time.time()-86400,))
        count=c.execute('SELECT count(*) FROM documents WHERE owner=?',(who,)).fetchone()[0]
        if count>=20:raise HTTPException(400,'File library is full (20 files). Remove an old file first.')
        ident=secrets.token_hex(16)
        c.execute('INSERT INTO documents VALUES(?,?,?,?,?,?,?)',(ident,who,name,mime,text,raw,time.time()))
    return {'id':ident,'name':name,'mime':mime,'characters':len(text),'vision_required':bool(raw)}
