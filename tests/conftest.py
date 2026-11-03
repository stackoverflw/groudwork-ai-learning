"""Isolate every acceptance test from the learner's real local records."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uuid
import pytest
from fastapi.testclient import TestClient
from app import db

@pytest.fixture(autouse=True)
def database(tmp_path,monkeypatch):
    monkeypatch.setattr(db,'DATA',tmp_path/'data')
    db.init()
    yield

@pytest.fixture
def client():
    from app.api import app
    with TestClient(app) as client:
        yield client

def post(client,path,payload,key=None):
    return client.post('/api/'+path,json=payload,headers={'Idempotency-Key':key or uuid.uuid4().hex})

def unlock(key):
    from app import content
    for u in content.units():
        if u['id']==key:break
        db.put('progress',u['id'],{'status':'已通过'})

SOLUTIONS={
 'r0-softmax':'import numpy as np\ndef softmax(x):\n x=np.asarray(x,dtype=np.float64);e=np.exp(x-x.max(axis=-1,keepdims=True));return e/e.sum(axis=-1,keepdims=True)',
 'r0-matmul':'def matmul(a,b):\n return a@b',
 'r0-layernorm':'import numpy as np\ndef layernorm(x,eps=1e-5):\n return (x-x.mean(-1,keepdims=True))/np.sqrt(x.var(-1,keepdims=True)+eps)',
 'r0-gradient':'def gradient(x,y,w):\n return 2*x.T@(x@w-y)/len(y)',
 'r0-kv':'def kv_bytes(*args):\n if any(not isinstance(x,int) or x<0 for x in args): raise ValueError()\n result=2\n for x in args: result*=x\n return result',
 'lab-softmax':'import numpy as np\ndef softmax_rows(x):\n e=np.exp(x-x.max(axis=-1,keepdims=True));return e/e.sum(axis=-1,keepdims=True)',
 'lab-attention':'import numpy as np\ndef attention(q,k,v):\n s=q@k.T/np.sqrt(q.shape[-1]);e=np.exp(s-s.max(-1,keepdims=True));return (e/e.sum(-1,keepdims=True))@v'
}
