"""v0.4: closed-book grading, exam timebox, rework, SM-2 and weekly warnings."""
from datetime import datetime,timedelta
from app import db
from conftest import post,unlock

def answers(n1=2):
    return {'answers':{'c1':2,'c2':2,'n1':n1,'n2':48,'d1':2},'responses':{'c1':'权重固定，KV随上下文增长，激活随batch变化','c2':'分子分母同因子缩放','d1':'固定数据，同机对照，预热重复中位数，数值门禁'}}

def test_quiz_rework_then_pass(client):
    unlock('l0-memory')
    e=post(client,'quiz/start',{'unit':'l0-memory','milestone':True}).json()
    assert all('answer' not in q for q in e['questions'])
    bad=post(client,'quiz/submit',dict(exam=e['id'],**answers(3))).json()
    assert not bad['passed'] and bad['rework']['timebox_min']==60
    assert '2' not in bad['feedback'][2]['working']
    assert db.get('progress','l0-memory')['status']=='回炉'
    e=post(client,'quiz/start',{'unit':'l0-memory','milestone':True}).json()
    good=post(client,'quiz/submit',dict(exam=e['id'],**answers())).json()
    assert good['passed'] and good['score']==5
    assert all(x.get('resolved') for x in db.all_records('exam') if x.get('submitted') and not x.get('passed'))

def test_server_enforces_exam_timebox(client):
    e=post(client,'quiz/start',{'unit':'r0-softmax','milestone':True}).json()
    stored=db.get('exam',e['id']);stored['started']=(datetime.now()-timedelta(minutes=41)).isoformat();db.put('exam',e['id'],stored)
    r=post(client,'quiz/submit',dict(exam=e['id'],**answers())).json()
    assert r['overtime'] and not r['passed']

def test_sm2_cadence_and_lapse(client):
    m=post(client,'reviews',{'text':'KV缓存公式'}).json()
    for interval in [3,7,21]:
        m=post(client,'review/grade',{'id':m['id'],'quality':4}).json()
        assert m['interval']==interval
    m=post(client,'review/grade',{'id':m['id'],'quality':1}).json()
    assert m['interval']==0 and m['repetitions']==0

def test_override_and_write_ratio_warning(client):
    assert post(client,'override',{'unit':'r0-softmax','reason':'太难','confirmation':'确认强行推进'}).status_code==400
    assert post(client,'override',{'unit':'r0-softmax','reason':'已经在纸上完整重写并复核','confirmation':'确认强行推进'}).status_code==200
    db.put('session','read',{'kind':'read','unit':'r0-softmax','started':(datetime.now()-timedelta(hours=1)).isoformat(),'ended':datetime.now().isoformat()})
    r=client.get('/api/report').json()
    assert r['warning'] and r['overrides'][0]['warning']
    assert client.get('/api/today').json()['unit']['id']=='r0-matmul'
