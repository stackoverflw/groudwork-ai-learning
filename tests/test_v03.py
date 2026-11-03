"""v0.3: executable four-part lab acceptance and mandatory experiment accounting."""
import json
import subprocess
import sys
import pytest
from app import content,runner
from conftest import post,unlock,SOLUTIONS

@pytest.mark.parametrize('key',['lab-softmax','lab-attention'])
def test_direct_acceptance_commands(key,tmp_path):
    solution=tmp_path/'solution.py';solution.write_text(SOLUTIONS[key],encoding='utf-8')
    lab=content.find('labs',key)
    assert runner.parse_acceptance(lab['acceptance']['cmd'],key)
    p=subprocess.run([sys.executable,'-m','app.runner','accept',key,'--solution',str(solution)],capture_output=True,text=True)
    result=json.loads(p.stdout)
    assert p.returncode==0,result
    assert set(result['checks'])=={'correctness','perf','memory','robustness'}
    assert result['checks']['memory']['peak_mb']>0
    assert result['checks']['perf']['baseline_ms']>0

def test_wrong_then_correct_lab_and_accounting(client):
    unlock('l0-softmax')
    s=post(client,'practice/start',{'unit':'l0-softmax'}).json()
    bad=post(client,'attempts',{'unit':'l0-softmax','session':s['session'],'code':'def softmax_rows(x): return x'}).json()
    assert not bad['result']['passed']
    assert client.get('/api/today').json()['unit']['status']=='回炉'
    good=post(client,'attempts',{'unit':'l0-softmax','session':s['session'],'code':SOLUTIONS['lab-softmax']}).json()
    assert good['result']['passed'],good
    p={'attempt':good['id'],'estimated_ms':good['result']['checks']['perf']['measured_ms']/2,'next_change':'固定线程数再跑一次'}
    assert post(client,'experiments',p).status_code==400
    assert post(client,'experiments',dict(p,reason='缓存')).status_code==400
    ok=post(client,'experiments',dict(p,reason='缓存',explanation='临时数组分配和缓存命中差异')).json()
    assert abs(ok['delta_pct']-100)<1e-6
    assert post(client,'progress',{'unit':'l0-softmax','status':'已通过'}).status_code==400

def test_same_machine_baseline_rerun(client):
    a=post(client,'baselines',{}).json();b=post(client,'baselines',{}).json()
    assert a['id']==b['id'] and b['drift_pct'] is not None and len(b['history'])==2

def test_full_lecture_gate_and_whiteboard_comparison(client):
    unlock('l0-softmax')
    s=post(client,'practice/start',{'unit':'l0-softmax'}).json()
    a=post(client,'attempts',{'unit':'l0-softmax','session':s['session'],'code':SOLUTIONS['lab-softmax']}).json()
    measured=a['result']['checks']['perf']['measured_ms']
    assert post(client,'experiments',{'attempt':a['id'],'estimated_ms':measured,'reason':'测量误差','next_change':'固定负载后重复相同输入'}).status_code==200
    quiz=post(client,'quiz/start',{'unit':'l0-softmax'}).json()
    r=post(client,'quiz/submit',{'exam':quiz['id'],'answers':{'c1':2,'c2':2,'n1':.5,'n2':4,'d1':2},'responses':{'c1':'同因子缩放','c2':'每行独立归一化','d1':'同机预热重复中位数、正确性和峰值'}})
    assert r.json()['passed'],r.text
    assert post(client,'progress',{'unit':'l0-softmax','status':'待验收'}).status_code==200
    assert post(client,'progress',{'unit':'l0-softmax','status':'已通过'}).status_code==200
    s=post(client,'practice/start',{'unit':'l0-softmax','mode':'whiteboard'}).json()
    assert s['code']=='' and 'scaffold' not in s['description']
    a=post(client,'attempts',{'unit':'l0-softmax','session':s['session'],'code':SOLUTIONS['lab-softmax']}).json()
    assert a['result']['passed'] and 'improvement_pct' in a
