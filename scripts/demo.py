"""Create clearly labelled demo records after backing up the current database."""
import json
import sys
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import db
db.init()
folder=db.DATA/'backups';folder.mkdir(exist_ok=True)
(folder/('before-demo-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')).write_text(json.dumps(db.export_all(),ensure_ascii=False,indent=2),encoding='utf-8')
db.restore({'schema_version':1,'records':{k:[] for k in db.KINDS}})
for index,kind in enumerate(['write','read','study']):
    end=datetime.now()-timedelta(hours=index*2)
    db.put('session',f'demo-{index}',{'kind':kind,'unit':'r0-softmax','started':(end-timedelta(minutes=90 if kind=='write' else 30)).isoformat(),'ended':end.isoformat(),'demo':True})
db.put('mistake','demo-concept',{'text':'[演示] 为什么softmax减最大值不改变结果？','unit':'r0-softmax','due':datetime.now().date().isoformat(),'ease':2.5,'repetitions':0,'interval':0,'demo':True})
