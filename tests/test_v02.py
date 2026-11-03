"""v0.2: all six lecture rules and the pending-acceptance gate."""
from app import content,db
from app.lint import lint
from conftest import post,unlock

def test_all_five_curated_lectures_green():
    for u in content.units():
        if u['lecture']:
            assert lint(content.lecture(u['id']))['color']=='green',u['id']
            summary=content.lecture(u['id']).split('## 6 三分钟复述稿')[1].split('## 7 自测')[0]
            assert len(summary.strip())<=200
    assert '0.93GiB【' in content.lecture('l0-memory')
    assert not any('0【' in line and '.93GiB' in line for line in content.lecture('l0-memory').splitlines())

def test_decimal_and_unit_literals_are_not_split():
    assert any(h['message']=='数字无出处：0.93' for h in lint('权重0.93GiB。')['hits'])
    assert not any(h['rule']=='L4' for h in lint('权重0.93GiB【估算：参数乘字节】。')['hits'])

def test_all_six_rules_and_positions():
    text='众所周知。\n'+('这是没有任何量化依据的模糊描述'*20)+'\n框架很重要。\n速度提升123倍。\n∑x'
    result=lint(text)
    assert {x['rule'] for x in result['hits']}=={'L1','L2','L3','L4','L5','L6'}
    assert result['color']=='red'
    assert next(x for x in result['hits'] if x['rule']=='L4')['line']==4

def test_invalid_content_blocks_pending(client):
    unlock('l0-memory')
    db.put('content','l0-memory',{'unit':content.find('units','l0-memory'),'lecture':'众所周知。','lab':content.find('labs','lab-softmax')})
    r=post(client,'progress',{'unit':'l0-memory','status':'待验收'})
    assert r.status_code==400 and 'lint' in r.json()['error']
    r=post(client,'lint',{'unit':'l0-memory','text':'众所周知。'})
    assert r.json()['color']=='red'
    assert db.all_records('mistake')
