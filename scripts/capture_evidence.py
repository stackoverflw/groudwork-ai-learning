"""Capture real CLI lab output and a scheduled Windows reminder in local evidence files."""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx
from app import db,scheduler

def main() -> None:
    solutions=runpy.run_path(str(ROOT/'tests/conftest.py'))['SOLUTIONS']
    folder=ROOT/'logs'/'solutions';folder.mkdir(exist_ok=True)
    results={}
    for key in ('lab-softmax','lab-attention'):
        path=folder/(key+'.py');path.write_text(solutions[key],encoding='utf-8')
        cmd=[sys.executable,'-m','app.runner','accept',key,'--solution',str(path)]
        result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True)
        results[key]={'command':subprocess.list2cmdline(cmd),'result':json.loads(result.stdout)}
    (ROOT/'logs/lab-evidence.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    with httpx.Client(base_url='http://127.0.0.1:9890',trust_env=False,timeout=10) as client:
        def post(path,body):
            response=client.post('/api/'+path,json=body,headers={'Idempotency-Key':uuid.uuid4().hex});response.raise_for_status();return response.json()
        config={'id':'reminder','enabled':True,'time':datetime.now().strftime('%H:%M'),'quiet_start':'00:00','quiet_end':'00:00','away_until':''}
        post('settings',config)
        end=time.monotonic()+20
        record={}
        while time.monotonic()<end:
            record=db.get('reminder',datetime.now().date().isoformat(),{})
            if record.get('delivered'):break
            time.sleep(.5)
        post('reminder/snooze',{})
        suppressed=not scheduler.eligible(config,datetime.now())
        post('settings',dict(config,enabled=False))
        reminder={'scheduled':record,'suppression_verified':suppressed,'note':'OS calls returned success; audibility and notification display depend on desktop settings'}
        (ROOT/'logs/reminder-evidence.json').write_text(json.dumps(reminder,ensure_ascii=False,indent=2),encoding='utf-8')
        (ROOT/'logs/ui-verification.json').write_text(json.dumps(client.get('/api/export').json(),ensure_ascii=False,indent=2),encoding='utf-8')
    sys.stdout.write(json.dumps({'labs':{k:v['result']['passed'] for k,v in results.items()},'reminder':reminder},ensure_ascii=True,indent=2)+'\n')
    if not record.get('delivered') or len(record.get('channels',[]))<2 or not suppressed:raise SystemExit(1)

if __name__=='__main__':main()
