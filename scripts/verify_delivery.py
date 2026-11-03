"""Black-box startup, forced-kill recovery and offline HTTP verification in isolated data."""
from __future__ import annotations
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import httpx

def main() -> None:
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',9890))==0:
            raise RuntimeError('Stop the running Groundwork instance before verification')
    folder=ROOT/'data'/'verification'
    folder.mkdir(parents=True,exist_ok=True)
    output=ROOT/'logs'/'verification-server.log'
    report={}
    with output.open('w',encoding='utf-8') as log:
        def stop(child):
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True)
            else:child.kill()
            child.wait(timeout=10)
        def start():
            begun=time.perf_counter()
            cmd = ['cmd.exe','/d','/c',str(ROOT/'启动.bat')] if '--bat' in sys.argv else [sys.executable,'run.py','--no-browser']
            child=subprocess.Popen(cmd,cwd=ROOT,env=dict(os.environ,GROUNDWORK_DATA=str(folder)),stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            while time.perf_counter()-begun<5:
                try:
                    if httpx.get('http://127.0.0.1:9890/api/health',timeout=.15,trust_env=False).json().get('app')=='groundwork':
                        return child,time.perf_counter()-begun
                except (OSError,httpx.HTTPError,ValueError):
                    time.sleep(.03)
            stop(child);raise RuntimeError('Server did not become ready')
        process,elapsed=start()
        try:
            report['startup_seconds']=elapsed
            report['via_batch']='--bat' in sys.argv
            with httpx.Client(base_url='http://127.0.0.1:9890',trust_env=False) as client:
                def post(path,payload):
                    r=client.post('/api/'+path,json=payload,headers={'Idempotency-Key':uuid.uuid4().hex});r.raise_for_status();return r.json()
                report['today']=client.get('/api/today').json()
                post('reviews',{'key':'persistence-check','text':'[验收记录] 强杀后必须保留'})
                s=post('session',{'action':'start','kind':'write','unit':'r0-softmax'})
                post('session',{'action':'stop','id':s['id']})
                before=client.get('/api/export').json()
                stop(process)
                process,restart=start()
                after=client.get('/api/export').json()
                report['forced_kill_records_equal']=before==after
                report['restart_seconds']=restart
                # The app has no outbound requests: enforce a local-only socket
                # policy in a separate in-process API test as additional evidence.
                report['request_assets']=['/','/static/styles.css','/static/app.js','/api/today','/api/units','/api/settings']
                report['assets_ok']=all(client.get(p).status_code==200 for p in report['request_assets'])
        finally:
            stop(process)
    (ROOT/'logs'/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    sys.stdout.write(json.dumps({k:v for k,v in report.items() if k!='today'},indent=2)+'\n')
    if not report['forced_kill_records_equal'] or elapsed>3:
        raise SystemExit(1)

if __name__=='__main__':main()
