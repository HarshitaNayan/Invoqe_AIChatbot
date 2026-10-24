"""Local hybrid retrieval: sparse TF-IDF + dense LSA embeddings (not neural)."""
from functools import lru_cache
from pathlib import Path
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import normalize
ROOT=Path(__file__).resolve().parent.parent

def chunks(text,size=1100,overlap=160):
    return [text[i:i+size] for i in range(0,len(text),size-overlap) if text[i:i+size].strip()]

def base_notes():
    notes=[]
    for item in json.loads((ROOT/'data/intents.json').read_text(encoding='utf-8'))['intents']:
        notes.append((f"Intent: {item['tag']}",' '.join(item['patterns'])+'\n'+'\n'.join(item['responses'])))
    for p in sorted((ROOT/'data/knowledge').glob('*')):
        if p.suffix.lower() in {'.md','.txt'}:
            for n,part in enumerate(chunks(p.read_text(encoding='utf-8')[:160000])):notes.append((f'{p.name} · section {n+1}',part))
    return notes

@lru_cache(maxsize=6)
def index(records):
    vec=TfidfVectorizer(ngram_range=(1,2),max_features=12000,sublinear_tf=True)
    matrix=vec.fit_transform([r[1] for r in records])
    svd=None; dense=None
    n=min(64,matrix.shape[0]-1,matrix.shape[1]-1)
    if n>=2:
        svd=TruncatedSVD(n_components=n,random_state=42)
        dense=normalize(svd.fit_transform(matrix))
    return vec,matrix,svd,dense

def retrieve(query,extra=(),k=4):
    records=tuple(base_notes()+list(extra))
    if not records or not query.strip():return []
    try:vec,matrix,svd,dense=index(records)
    except ValueError:return []
    q=vec.transform([query]); sparse=(matrix@q.T).toarray().ravel()
    scores=sparse
    if svd is not None:
        scores=.65*sparse+.35*(dense@normalize(svd.transform(q))[0])
    out=[]
    for i in np.argsort(scores)[::-1]:
        if scores[i]<.08 or len(out)>=k:break
        out.append({'source':records[i][0],'text':records[i][1],'score':round(float(scores[i]),4)})
    return out

def context_for(query,docs):
    extra=[]
    for doc in docs:
        extra.extend((doc['name']+f' · excerpt {i+1}',part) for i,part in enumerate(chunks(doc['text'])[:120]))
    hits=retrieve(query,extra)
    return '\n\n'.join(f"[{h['source']}]\n{h['text']}" for h in hits),hits
