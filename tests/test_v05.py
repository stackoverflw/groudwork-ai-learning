"""v0.5: all-or-nothing content production, roundtrip data and reminder suppression."""
import copy
from datetime import datetime
from app import content,db,scheduler
from conftest import post,unlock

def bundle():
    u=copy.deepcopy(content.find('units','l0-softmax'));u.update(id='week-03',unit='week-03',week=3,layer='L1',order=23,prereq=['l0-measure'])
    lab=copy.deepcopy(content.find('labs','lab-softmax'));lab['unit']='week-03'
    return {'unit':u,'lecture':content.lecture('l0-softmax'),'lab':lab}

def test_factory_strict_atomic_import(client):
    assert '## 9 术语表' in client.get('/api/factory/week-03').text
    p=bundle();bad=copy.deepcopy(p);bad['lecture']='众所周知。'
    r=post(client,'factory/import',bad)
    assert r.status_code==422 and len(r.json()['errors'])>=10
    assert db.all_records('content')==[]
    bad=copy.deepcopy(p);del bad['lab']['acceptance']['memory']
    assert post(client,'factory/import',bad).status_code==422
    r=post(client,'factory/import',p)
    assert r.status_code==200,r.text
    assert content.find('units','week-03')['produced']

def test_export_empty_restore_exact(client):
    post(client,'reviews',{'text':'记忆必须留下'})
    post(client,'session',{'action':'start','kind':'write','unit':'r0-softmax'})
    before=client.get('/api/export').json()
    db.restore({'schema_version':1,'records':{k:[] for k in db.KINDS}})
    assert not db.all_records('mistake')
    assert post(client,'import',before).status_code==200
    assert client.get('/api/export').json()==before

def test_reminder_two_channels_suppression_and_quiet(monkeypatch):
    config={'enabled':True,'time':'20:00','quiet_start':'23:00','quiet_end':'08:00'}
    db.put('setting','reminder',config)
    assert not scheduler.eligible(config,datetime(2026,10,31,23,15))
    assert not scheduler.eligible(dict(config,away_until='2026-11-01'),datetime(2026,10,31,20,1))
    monkeypatch.setattr(scheduler,'notify',lambda:['tray','sound','browser'])
    assert len(scheduler.tick(datetime(2026,10,31,20,1)))>=2
    assert scheduler.tick(datetime(2026,10,31,20,2))==[]
    db.put('reminder','2026-10-31',{'suppressed':True})
    assert scheduler.tick(datetime(2026,10,31,20,3))==[]

def test_batch_is_ascii_and_no_codepage_switch():
    raw=(db.ROOT/'启动.bat').read_bytes()
    assert all(b<128 for b in raw)
    assert b'chcp' not in raw.lower()

def test_new_lab_can_be_imported_and_really_executed(client):
    p=bundle();lab=p['lab'];lab['id']='lab-double'
    lab['scaffold']['signatures']=['double(x)']
    lab['scaffold']['starter']='def double(x):\n    raise NotImplementedError'
    command='python -m app.runner accept lab-double --solution {solution}'
    lab['acceptance']['cmd']=command
    lab['acceptance']['correctness']['dataset']={'entrypoint':'double','cases':[{'args':[[1,2,3]],'expected':[2,4,6]},{'args':[[0]],'expected':[0]},{'args':[[-2,5]],'expected':[-4,10]}],'benchmark_args':[list(range(4096))],'baseline_source':'def baseline(x):\n return np.array([v*2 for v in x])'}
    p['unit'].update(practice='lab-double',acceptance_cmd=command)
    r=post(client,'factory/import',p);assert r.status_code==200,r.text
    unlock('week-03')
    s=post(client,'practice/start',{'unit':'week-03'}).json()
    r=post(client,'attempts',{'unit':'week-03','session':s['session'],'code':'def double(x):\n return x*2'})
    assert r.status_code==200,r.text
    assert r.json()['result']['passed'],r.text
