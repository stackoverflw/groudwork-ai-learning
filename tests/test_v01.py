"""v0.1: durable storage, real drills, state-driven tasks and API smoke checks."""
import json
import os
import subprocess
import sys
import pytest
from app import db,runner
from conftest import post,SOLUTIONS

def test_db_atomic_and_restart():
    db.put('progress','r0-softmax',{'status':'进行中'})
    with pytest.raises(RuntimeError):
        with db.transaction():
            db.put('progress','r0-softmax',{'status':'已通过'})
            raise RuntimeError('power-loss simulation')
    assert db.get('progress','r0-softmax')['status']=='进行中'
    result=subprocess.run([sys.executable,'-c','from app import db; import json; db.init(); print(json.dumps(db.get("progress","r0-softmax")))'],env=dict(os.environ,GROUNDWORK_DATA=str(db.DATA)),capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)['status']=='进行中'

def test_db_backup():
    db.put('progress','x',{'status':'已通过'})
    assert db.backup().is_file()
    assert len(list((db.DATA/'backups').glob('*.db')))==1

@pytest.mark.parametrize('key',list(runner.DRILLS))
def test_hidden_drills(key):
    assert runner.run(key,SOLUTIONS[key])['passed']
    bad=runner.run(key,'def '+runner.DRILLS[key][0]+':\n return 0')
    assert not bad['passed']
    assert bad['checks']['correctness']['failures'][0]['case']>=1

def test_runner_timeout():
    assert runner.run('r0-softmax','while True: pass',timeout=1)['error']=='Execution timeout'

def test_today_transition_idempotency_and_history(client):
    assert client.get('/').status_code==200
    today=client.get('/api/today').json()
    assert today['unit']['id']=='r0-softmax' and len(today['tasks'])==3
    assert client.post('/api/draft',json={}).status_code==400
    start=post(client,'practice/start',{'unit':'r0-softmax'}).json()
    p={'unit':'r0-softmax','session':start['session'],'code':SOLUTIONS['r0-softmax']}
    a=post(client,'attempts',p,'same-attempt-key')
    assert a.status_code==200,a.text
    assert a.json()['result']['passed']
    assert post(client,'attempts',p,'same-attempt-key').json()==a.json()
    assert len(client.get('/api/attempts').json())==1
    assert post(client,'attempts',dict(p,code='bad'),'same-attempt-key').status_code==409
    assert client.get('/api/today').json()['unit']['id']=='r0-matmul'
    assert post(client,'practice/start',{'unit':'r0-kv'}).status_code==400

def test_foreign_origin_rejected(client):
    r=client.post('/api/session',json={},headers={'Origin':'https://example.com','Idempotency-Key':'a-long-enough-key'})
    assert r.status_code==403
