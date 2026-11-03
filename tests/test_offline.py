"""Enforce offline operation and kill an uncommitted writer to verify SQLite durability."""
import os
import socket
import subprocess
import sys
import time
from app import db
from conftest import post

def test_offline_api_without_external_sockets(client,monkeypatch):
    original=socket.socket.connect
    def local_only(sock,address):
        if isinstance(address,tuple) and address[0] not in ('127.0.0.1','localhost','::1'):
            raise AssertionError('Unexpected outbound connection: '+str(address))
        return original(sock,address)
    monkeypatch.setattr(socket.socket,'connect',local_only)
    assert client.get('/api/today').status_code==200
    assert client.get('/api/units').status_code==200
    assert client.get('/api/diagnostics').status_code==200
    assert post(client,'reviews',{'text':'离线复习'}).status_code==200
    assert client.get('/api/export').status_code==200

def test_force_kill_discards_only_uncommitted_records(tmp_path):
    marker=tmp_path/'ready'
    script='''import sys,time
from pathlib import Path
from app import db
db.init()
db.put('progress','committed',{'status':'已通过'})
with db.transaction():
 db.put('progress','uncommitted',{'status':'进行中'})
 Path(sys.argv[1]).write_text('ready')
 time.sleep(30)
'''
    p=subprocess.Popen([sys.executable,'-c',script,str(marker)],env=dict(os.environ,GROUNDWORK_DATA=str(db.DATA)))
    try:
        deadline=time.monotonic()+5
        while not marker.exists() and time.monotonic()<deadline:time.sleep(.03)
        assert marker.exists()
    finally:
        p.kill();p.wait(timeout=10)
    assert db.get('progress','committed')['status']=='已通过'
    assert db.get('progress','uncommitted') is None
