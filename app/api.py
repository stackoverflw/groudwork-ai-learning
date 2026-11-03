"""Local HTTP API: state transitions, practice, experiment ledger and offline content imports."""
from __future__ import annotations
import asyncio
from datetime import date, datetime, timedelta
import hashlib
import json
import logging
import math
import platform
import re
import sys
import time
import uuid
from typing import Any
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import db, content, runner
from .lint import lint, HEADINGS

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1','localhost','testserver'])
WRITE_LOCK = asyncio.Lock()

def now() -> str:
    return datetime.now().isoformat(timespec='microseconds')

def uid() -> str:
    return uuid.uuid4().hex

def error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({'error': message, 'causes': ['输入字段缺失或格式不符','前置单元或验收门禁未满足','本机文件、依赖或进程不可用'], 'diagnostic': '.\\.venv\\Scripts\\python.exe run.py --selfcheck'}, status_code=status)

@app.middleware('http')
async def observe(request: Request, call_next: Any) -> Response:
    started = time.perf_counter()
    status = 500
    try:
        if request.method not in ('GET','HEAD'):
            origin = request.headers.get('origin', '')
            if origin and origin not in ('http://127.0.0.1:9890','http://localhost:9890'):
                return error('仅允许本机页面写入', 403)
            raw = await request.body()
            if len(raw) > 12*1024*1024:
                return error('导入文件超过12MiB限制', 413)
            key = request.headers.get('idempotency-key','')
            if not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', key):
                return error('写操作必须携带唯一 Idempotency-Key')
            fingerprint = hashlib.sha256(request.method.encode()+request.url.path.encode()+raw).hexdigest()
            async with WRITE_LOCK:
                with db.transaction() as c:
                    receipt = c.execute('SELECT * FROM receipts WHERE id=?', (key,)).fetchone()
                    if receipt:
                        status = receipt['status']
                        if receipt['fingerprint'] != fingerprint:
                            return error('同一幂等键对应不同请求', 409)
                        return Response(receipt['body'], status_code=receipt['status'], media_type='application/json')
                    response = await call_next(request)
                    body = b''.join([chunk async for chunk in response.body_iterator])
                    status = response.status_code
                    if status >= 400:
                        c.rollback()
                    else:
                        c.execute('INSERT INTO receipts VALUES(?,?,?,?)', (key, fingerprint, status, body.decode('utf-8')))
                    return Response(body, status_code=status, media_type=response.media_type, headers=dict(response.headers))
        response = await call_next(request)
        status = response.status_code
        return response
    except (ValueError, KeyError, TypeError, OverflowError) as e:
        status = 400
        record_error(request.url.path, str(e))
        return error(str(e))
    except Exception as e:
        record_error(request.url.path, repr(e))
        logging.exception(json.dumps({'event':'request_error','path':request.url.path}))
        return error('本机处理失败：'+type(e).__name__, 500)
    finally:
        logging.info(json.dumps({'event':'request','method':request.method,'path':request.url.path,'status':status,'ms':round((time.perf_counter()-started)*1000,2)}, ensure_ascii=False))

def record_error(path: str, message: str) -> None:
    db.put('error',now()+':'+uid(),{'at':now(),'path':path,'message':message[:300]})
    with db.transaction() as c:
        c.execute("DELETE FROM records WHERE kind='error' AND id NOT IN (SELECT id FROM records WHERE kind='error' ORDER BY id DESC LIMIT 5)")

def available(key: str) -> dict[str, Any]:
    u = next((x for x in content.units() if x['id']==key), None)
    if not u or not u['produced']:
        raise ValueError('该单元待生产；请先备下一课')
    if u['blockers']:
        raise ValueError('前置未通过：'+', '.join(u['blockers']))
    phase = max(1, (u['week'] - 1) // 3 + 1)
    if phase > 1:
        completed = {e['quiz'] for e in db.all_records('exam') if e.get('milestone') and e.get('passed')}
        for number in range(1, phase):
            if f'milestone-{number}' not in completed:
                raise ValueError(f'请先通过第 {number} 阶段里程碑，再进入下一阶段')
    return u

def mistake(key: str, text: str, unit: str = '') -> dict[str, Any]:
    old = db.get('mistake', key)
    return old or db.put('mistake', key, {'text':text,'unit':unit,'due':date.today().isoformat(),'ease':2.5,'repetitions':0,'interval':0})

@app.get('/api/today')
def today() -> dict[str, Any]:
    return dict(content.today(), report=report())

@app.get('/api/health')
def health() -> dict[str, str]:
    return {'app':'groundwork','status':'ready','version':'0.6.0'}

@app.get('/api/units')
def units() -> list[dict[str, Any]]:
    return content.units()

@app.get('/api/attempts')
def attempts() -> list[dict[str, Any]]:
    return sorted(db.all_records('attempt'),key=lambda a:a['at'])

@app.get('/api/lecture/{key}')
def lecture(key: str) -> dict[str, Any]:
    available(key)
    text = content.lecture(key)
    result = lint(text)
    return {'markdown':text,'lint':result}

@app.post('/api/lint')
async def run_lint(request: Request) -> dict[str, Any]:
    p = await request.json()
    result = lint(p['text'])
    for hit in result['hits']:
        mistake('lint:'+hashlib.sha256((p.get('unit','')+hit['message']).encode()).hexdigest()[:20], f"{hit['rule']} 行{hit['line']}：{hit['message']}", p.get('unit',''))
    return result

@app.post('/api/progress')
async def progress(request: Request) -> dict[str, Any]:
    p = await request.json()
    u = available(p['unit'])
    target = p['status']
    if target not in ('进行中','待验收','已通过'):
        raise ValueError('不允许的状态；强行推进须使用单独流程')
    if u['status'] == '已通过':
        return db.get('progress',u['id'])
    if target in ('待验收','已通过'):
        if u['lecture']:
            result = lint(content.lecture(u['id']))
            if result['color'] != 'green':
                raise ValueError('讲义lint不是全绿，不能待验收')
        passing = [a for a in attempts() if a['unit']==u['id'] and a['result']['passed']]
        if not passing:
            raise ValueError('请先通过本单元练习')
        if u['lecture']:
            if u['practice'].startswith('lab-') and not any(e['attempt'] in {a['id'] for a in passing} for e in db.all_records('experiment')):
                raise ValueError('缺本单元实验记账')
        if u['lecture'] or u.get('requires_quiz'):
            if not any(e.get('unit')==u['id'] and e.get('passed') and not e.get('milestone') for e in db.all_records('exam')):
                raise ValueError('本单元五题闭卷尚未通过')
    return db.put('progress',u['id'],{'status':target,'updated':now()})

@app.post('/api/override')
async def override(request: Request) -> dict[str, Any]:
    p = await request.json()
    content.find('units',p['unit'])
    if p.get('confirmation') != '确认强行推进' or len(p.get('reason','').strip()) < 8:
        raise ValueError('需第二步确认，且理由至少8字')
    db.put('override',uid(),{'unit':p['unit'],'reason':p['reason'],'at':now(),'warning':True})
    return db.put('progress',p['unit'],{'status':'跳过','updated':now()})

@app.post('/api/task')
async def task(request: Request) -> dict[str, Any]:
    p = await request.json()
    task_id = p['task']
    valid = {t['id'] for t in content.today()['tasks']}
    if task_id not in valid:
        raise ValueError('只能完成今天当前单元任务')
    return db.put('task',task_id,{'at':now()})

@app.post('/api/practice/start')
async def practice_start(request: Request) -> dict[str, Any]:
    p = await request.json()
    u = available(p['unit'])
    mode = p.get('mode','lab' if u['practice'].startswith('lab-') else 'drill')
    if mode not in ('drill','lab','whiteboard'):
        raise ValueError('未知练习模式')
    key = u['practice']
    if key in runner.DRILLS:
        signature, starter = runner.DRILLS[key]
        box = 30
        description: Any = {'signature':signature,'contract':'只用NumPy；单文件不超过80行；隐藏测试含极值、常数和单元素；梯度定义为mean((x@w-y)**2)的导数；KV参数必须为非负整数'}
    elif key.startswith('course-'):
        from .course import exercise
        spec = exercise(key)
        signature, starter = spec['signature'], spec['starter']
        box = spec['minutes']
        description = {'signature':signature,'contract':spec['contract'],'examples':spec['examples']}
    else:
        lab = content.find('labs',key)
        signature, starter = lab['scaffold']['signatures'][0], lab['scaffold']['starter']
        box, description = lab['timebox_min'], lab
    draft = db.get('draft',u['id']+':'+mode,{})
    sid = uid()
    db.put('session',sid,{'unit':u['id'],'practice':key,'mode':mode,'kind':'write','started':now(),'ended':None,'timebox_min':box})
    if u['status'] not in ('已通过', '跳过'):
        db.put('progress',u['id'],{'status':'回炉' if u['status']=='回炉' else '进行中','updated':now()})
    return {'session':sid,'practice':key,'mode':mode,'signature':signature,'code':draft.get('code','' if mode=='whiteboard' else starter),'timebox_min':box,'description':{'signature':signature,'tests':'通过 / 失败（隐藏测试）'} if mode=='whiteboard' else description}

@app.post('/api/draft')
async def save_draft(request: Request) -> dict[str, Any]:
    p = await request.json()
    available(p['unit'])
    return db.put('draft',p['unit']+':'+p['mode'],{'code':p['code'],'updated':now()})

@app.post('/api/attempts')
async def submit(request: Request) -> dict[str, Any]:
    p = await request.json()
    u = available(p['unit'])
    session = db.get('session',p['session'])
    if not session or session['unit'] != u['id'] or session.get('ended'):
        raise ValueError('练习会话不存在或已结束，请重新开始练习')
    if u['practice'].startswith('r0') and len(p['code'].splitlines()) > 80:
        raise ValueError('drill最多80行')
    result = await asyncio.to_thread(runner.run,u['practice'],p['code'])
    elapsed = max(0,(datetime.now()-datetime.fromisoformat(session['started'])).total_seconds())
    first = next((a for a in attempts() if a['practice']==u['practice'] and a['result']['passed'] and a['mode']!='whiteboard'),None)
    record = db.put('attempt',uid(),{'unit':u['id'],'practice':u['practice'],'mode':session['mode'],'session':session['id'],'at':now(),'elapsed_seconds':elapsed,'timebox_min':session['timebox_min'],'overtime':elapsed > session['timebox_min']*60,'result':result})
    if session['mode']=='whiteboard' and first:
        record.update(first_seconds=first['elapsed_seconds'],improvement_pct=(first['elapsed_seconds']-elapsed)/max(first['elapsed_seconds'],.001)*100)
        db.put('attempt',record['id'],record)
    db.put('draft',u['id']+':'+session['mode'],{'code':p['code'],'updated':now()})
    if not result['passed']:
        if u['status'] not in ('已通过', '跳过'):
            db.put('progress',u['id'],{'status':'回炉','updated':now()})
        mistake('attempt:'+u['id'],u['title']+'：练习未通过，请复查失败用例',u['id'])
    elif not u['lecture'] and not u.get('requires_quiz'):
        db.put('progress',u['id'],{'status':'已通过','updated':now()})
    return record

@app.post('/api/experiments')
async def experiment(request: Request) -> dict[str, Any]:
    p = await request.json()
    a = db.get('attempt',p['attempt'])
    if not a or not a['practice'].startswith('lab-'):
        raise ValueError('需要真实lab尝试记录')
    measured = a['result'].get('checks',{}).get('perf',{}).get('measured_ms')
    estimated = float(p['estimated_ms'])
    if measured is None or not math.isfinite(estimated) or estimated <= 0:
        raise ValueError('估算必须为正数；正确性通过后才有可用实测')
    reasons = ['缓存','带宽','精度','调度','测量误差','其他']
    delta = (measured-estimated)/abs(estimated)*100
    if p.get('reason') not in reasons or not p.get('next_change','').strip():
        raise ValueError('差异原因和下次要改什么均必填')
    if (abs(delta)>30 or p['reason']=='其他') and len(p.get('explanation','').strip()) < 8:
        raise ValueError('差异超过30%或选其他时，原因说明至少8字')
    return db.put('experiment',p['attempt'],{'attempt':p['attempt'],'unit':a['unit'],'measured_ms':measured,'estimated_ms':estimated,'delta_pct':delta,'reason':p['reason'],'explanation':p.get('explanation',''),'next_change':p['next_change'],'at':now()})

@app.post('/api/baselines')
async def baseline(request: Request) -> dict[str, Any]:
    def measure() -> dict[str, Any]:
        import numpy as np
        x = np.ones(4*1024*1024,dtype=np.float32)
        ms = runner.measure(lambda: x.copy(),())
        machine = hashlib.sha256((platform.node()+platform.processor()+sys.version).encode()).hexdigest()[:16]
        old = db.get('baseline',machine)
        return {'machine':machine,'cpu':platform.processor(),'python':platform.python_version(),'numpy':np.__version__,'copy_ms':ms,'bandwidth_gbs':x.nbytes*2/ms/1e6,'drift_pct':None if not old else (ms-old['copy_ms'])/old['copy_ms']*100,'protocol':'CPU copy 16MiB; read+write bytes; warmup2; median7; not GPU bandwidth','at':now(),'history':(old or {}).get('history',[])+[{'at':now(),'copy_ms':ms}]}
    result = await asyncio.to_thread(measure)
    return db.put('baseline',result['machine'],result)

@app.get('/api/reviews')
def reviews() -> list[dict[str, Any]]:
    return db.all_records('mistake')

@app.post('/api/reviews')
async def mark_review(request: Request) -> dict[str, Any]:
    p = await request.json()
    return mistake(p.get('key') or uid(),p['text'],p.get('unit',''))

@app.post('/api/review/grade')
async def grade_review(request: Request) -> dict[str, Any]:
    p = await request.json()
    m = db.get('mistake',p['id'])
    q = int(p['quality'])
    if not m or q not in range(6):
        raise ValueError('卡片不存在或质量不在0到5')
    n = m['repetitions']+1 if q>=3 else 0
    ease = max(1.3,m['ease']+.1-(5-q)*(.08+(5-q)*.02))
    # SM-2 ease update with explicit initial course cadence: today / 3 / 7 / 21 days.
    interval = 0 if n==0 else [3,7,21][n-1] if n<=3 else round(m['interval']*ease)
    return db.put('mistake',m['id'],dict(m,ease=ease,repetitions=n,interval=interval,due=(date.today()+timedelta(days=interval)).isoformat()))

@app.get('/api/numbers')
def numbers() -> list[dict[str, str]]:
    return [{'term':'显存换算','value':'1 GiB = 2^30 bytes【估算：二进制单位定义】'}, {'term':'KV cache','value':'2 × L × batch × T × H_kv × D × bytes【估算：键值元素计数】'}, {'term':'FP16','value':'每元素2 bytes【文献：IEEE binary16位宽】；本机峰值吞吐未测'}, {'term':'带宽','value':'有效带宽=实际读写字节/秒【估算：定义】；本机数字请先跑基线'}]

@app.post('/api/session')
async def session_action(request: Request) -> dict[str, Any]:
    p = await request.json()
    if p['action']=='start':
        if p['kind'] not in ('study','write','read'):
            raise ValueError('工时分类不符')
        return db.put('session',uid(),{'kind':p['kind'],'unit':p.get('unit',''),'started':now(),'ended':None})
    s = db.get('session',p['id'])
    if not s:
        raise ValueError('计时会话不存在')
    if not s.get('ended'):
        s['ended'] = now()
        s['seconds'] = max(0,(datetime.fromisoformat(s['ended'])-datetime.fromisoformat(s['started'])).total_seconds())
        db.put('session',s['id'],s)
    return s

@app.get('/api/report')
def report() -> dict[str, Any]:
    monday = date.today()-timedelta(days=date.today().weekday())
    totals = dict(study=0.,write=0.,read=0.)
    for s in db.all_records('session'):
        if s.get('ended'):
            # Split overlapping sessions at the week boundary instead of counting all time.
            end = min(datetime.now(),datetime.fromisoformat(s['ended']))
            start = max(datetime.combine(monday,datetime.min.time()),datetime.fromisoformat(s['started']))
            totals[s['kind']] += max(0,(end-start).total_seconds())/3600
    total = sum(totals.values())
    ratio = totals['write']/total if total else 0
    week = min(12,max(1,(date.today()-date.fromisoformat(db.get('setting','plan',{'start':date.today().isoformat()})['start'])).days//7+1))
    target = sum(sum(u['hours'].values()) for u in content.units() if u['week']==week)
    return {'hours':totals,'total':total,'target':target,'write_ratio':ratio,'warning':total>0 and ratio<.55,'suggestion':f"本周读 {totals['read']:.1f}h、写 {totals['write']:.1f}h；下次先写 {content.current()['practice']} 30分钟，再读讲义。",'overrides':[o for o in db.all_records('override') if o['at'][:10]>=monday.isoformat()],'attempts':attempts(),'exams':db.all_records('exam'),'experiments':db.all_records('experiment'),'baselines':db.all_records('baseline'),'active_sessions':[s for s in db.all_records('session') if not s.get('ended')]}

@app.post('/api/quiz/start')
async def quiz_start(request: Request) -> dict[str, Any]:
    p = await request.json()
    milestone = bool(p.get('milestone'))
    unit_id = p['unit']
    if milestone:
        pending = [e for e in db.all_records('exam') if e.get('milestone') and e.get('submitted') and not e.get('passed') and not e.get('resolved')]
        if pending:
            unit_id = min(pending, key=lambda e: e['started'])['unit']
        else:
            phase_due = content.next_milestone(content.current())
            if phase_due is not None:
                unit_id = f'week-{phase_due * 3:02d}'
    unit = available(unit_id)
    quiz_id = unit_id if any(q['id']==unit_id for q in content.load('quizzes')) else 'l0-check'
    if milestone:
        quiz_id = f"milestone-{max(1, (unit['week'] - 1) // 3 + 1)}"
    quiz = content.find('quizzes',quiz_id)
    record = db.put('exam',uid(),{'unit':unit_id,'quiz':quiz['id'],'started':now(),'milestone':milestone,'submitted':False,'timebox_min':quiz['timebox_min']})
    return dict(record,questions=[{k:v for k,v in q.items() if k not in ('answer','working')} for q in quiz['questions']])

@app.post('/api/quiz/submit')
async def quiz_submit(request: Request) -> dict[str, Any]:
    p = await request.json()
    e = db.get('exam',p['exam'])
    if not e or e['submitted']:
        raise ValueError('考试不存在或已交卷')
    quiz = content.find('quizzes',e['quiz'])
    elapsed = (datetime.now()-datetime.fromisoformat(e['started'])).total_seconds()
    scores, numeric_ok, feedback = [], True, []
    for q in quiz['questions']:
        raw = p['answers'].get(q['id'])
        if q['kind']=='number':
            try:
                answer = float(raw)
                ok = math.isfinite(answer) and abs(answer-q['answer']) <= q['atol']+q['rtol']*abs(q['answer'])
            except (TypeError,ValueError):
                ok = False
            numeric_ok = numeric_ok and ok
            score = float(ok)
        else:
            grade = int(raw)
            if grade not in (0,1,2) or not p.get('responses',{}).get(q['id'],'').strip():
                raise ValueError('概念与设计题需填写回答并按rubric自评0/1/2')
            score, ok = grade/2, grade==2
        scores.append(score)
        feedback.append({'id':q['id'],'score':score,'working':None if ok else q.get('working','按rubric复述并补全缺失条件；此项为自评')})
        if not ok:
            mistake('quiz:'+e['unit']+':'+q['id'],q['prompt'],e['unit'])
    passed = numeric_ok and sum(scores)>=4 and elapsed<=e['timebox_min']*60
    e.update(submitted=True,at=now(),elapsed_seconds=elapsed,overtime=elapsed>e['timebox_min']*60,passed=passed,score=sum(scores),feedback=feedback,responses=p.get('responses',{}),answers=p['answers'])
    db.put('exam',e['id'],e)
    if e['milestone']:
        if not passed:
            if db.get('progress',e['unit'],{}).get('status') not in ('已通过', '跳过'):
                db.put('progress',e['unit'],{'status':'回炉','updated':now()})
            e['rework'] = {'lecture':e['unit'],'lab':content.find('units',e['unit'])['practice'],'timebox_min':60,'instruction':'回看本单元讲解与例题，然后重新参加里程碑考试'}
            db.put('exam',e['id'],e)
        else:
            for old in db.all_records('exam'):
                if old.get('quiz') == e['quiz'] and old.get('milestone') and old.get('submitted') and not old.get('passed'):
                    db.put('exam',old['id'],dict(old,resolved=True))
    return e

@app.get('/api/factory/{key}')
def factory(key: str) -> Response:
    u = content.find('units',key)
    template = '\n\n'.join(f'## {i} {h}\n填写可核对的解释、公式与来源。' for i,h in enumerate(HEADINGS))
    text = f'# 地基 · 离线备课请求\n\n目标单元：{key}\n能力目标：{u["objective"]}\n关键概念（最多六项）：{u["concepts"]}\n\n返回单一JSON对象：unit（完整路线卡）、lecture（Markdown字符串）、lab（完整lab对象）。不要使用API或联网数据。路线卡id必须为{key}。\n\n{template}\n\n每概念：定义、量化后果、符号表和公式、8GB Windows工程预算、以为→实际。复述稿不超过200字且至少三个带来源数字。\n\nLint：禁用 众所周知/不难发现/值得注意的是/在本节中/我们将/总的来说/非常重要/极大地/若干/深入理解/熟悉一下；连续200字须有数字/公式/代码；禁评价句；每个数字就近标【实测】【估算：公式】【文献】；十个编号段（0至9）齐全；特殊公式符号必须有符号表。\n\n禁止历史/提出者/云服务/下载模型/超过200MB的数据/必然OOM。单题120–240分钟。用本地随机数组；不编造硬件实测。\n\n本版执行器支持lab-softmax或lab-attention；扩展新算子前先添加受信任的隐藏测试，不能导入任意shell命令。\n\n路线模板：\n```json\n{json.dumps(u,ensure_ascii=False,indent=2)}\n```\n\nLab模板（改unit到目标单元，保留受支持的id与命令）：\n```json\n{json.dumps(content.find("labs","lab-softmax"),ensure_ascii=False,indent=2)}\n```\n'
    return Response(text,media_type='text/markdown; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="prepare-{key}.md"'})

def validate_bundle(p: dict[str, Any]) -> list[str]:
    import jsonschema
    schema = json.loads((db.ROOT/'content/bundle.schema.json').read_text(encoding='utf-8'))
    errors = [f"{'.'.join(str(v) for v in e.absolute_path)}: {e.message}" for e in jsonschema.Draft202012Validator(schema).iter_errors(p)]
    if errors:
        return errors
    u, lab = p['unit'],p['lab']
    if not any(v['id']==u['id'] for v in content.units()):
        errors.append('unit.id必须对应现有待生产路线卡')
    if any(x not in {v['id'] for v in content.units()} for x in u['prereq']) or u['id'] in u['prereq']:
        errors.append('前置依赖未知或自循环')
    if not runner.parse_acceptance(lab['acceptance']['cmd'],lab['id']):
        errors.append('lab验收命令不可解析，或没有对应的受信任测试运行器')
    canonical = content.CONTENT/'labs'/(lab['id']+'.json')
    if canonical.is_file() and lab['acceptance'] != json.loads(canonical.read_text(encoding='utf-8'))['acceptance']:
        errors.append('验收契约必须与执行器一致；不能通过导入降低正确性、性能、内存门槛')
    if not canonical.is_file():
        dataset = lab['acceptance']['correctness']['dataset']
        if not isinstance(dataset,dict):
            errors.append('新lab必须提供dataset对象：entrypoint/cases/benchmark_args/baseline_source')
        else:
            import ast
            try:
                tree = ast.parse(dataset['baseline_source'])
                if not any(isinstance(n,ast.FunctionDef) and n.name=='baseline' for n in tree.body):
                    errors.append('baseline_source必须定义baseline函数')
            except SyntaxError as e:
                errors.append('基线语法错误：'+str(e))
        protocol = lab['acceptance']['perf']['protocol']
        if protocol != {'warmup':2,'reps':7,'metric':'median_ms','sync':'CPU synchronous NumPy'}:
            errors.append('新lab测量协议须为CPU synchronous NumPy / warmup2 / reps7 / median_ms')
    if u['acceptance_cmd'] != lab['acceptance']['cmd'] or u['practice'] != lab['id'] or lab['unit'] != u['id']:
        errors.append('路线、lab、验收命令关联不一致')
    result = lint(p['lecture'])
    errors += [f"{h['rule']} 行{h['line']}: {h['message']}" for h in result['hits']]
    summary = p['lecture'].split('## 6 三分钟复述稿')[-1].split('## 7 自测')[0]
    if len(summary.strip())>200 or len(re.findall(r'\d+(?:\.\d+)?',summary))<3:
        errors.append('复述稿需不超过200字且包含至少三个数字')
    return errors

@app.post('/api/factory/import')
async def import_bundle(request: Request) -> Any:
    p = await request.json()
    errors = validate_bundle(p)
    if errors:
        return JSONResponse({'error':'内容未导入','errors':errors},status_code=422)
    p['unit'].update(lecture=True,produced=True)
    db.put('content',p['unit']['id'],p)
    db.put('progress',p['unit']['id'],{'status':'未开始','updated':now()})
    return {'imported':p['unit']['id'],'status':'待学习'}

@app.get('/api/export')
def export() -> Response:
    return Response(json.dumps(db.export_all(),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="groundwork-backup.json"'})

@app.post('/api/import')
async def restore(request: Request) -> dict[str, bool]:
    payload = await request.json()
    for bundle in payload.get('records',{}).get('content',[]):
        clean = {k:v for k,v in bundle.items() if k!='id'}
        errors = validate_bundle(clean)
        if errors:
            raise ValueError('; '.join(errors))
    db.restore(payload)
    return {'restored':True}

@app.get('/api/settings')
def settings() -> list[dict[str, Any]]:
    return db.all_records('setting')

@app.post('/api/settings')
async def save_settings(request: Request) -> dict[str, Any]:
    p = await request.json()
    if p['id'] not in ('reminder','appearance'):
        raise ValueError('未知设置项')
    if p['id']=='reminder':
        for key in ('time','quiet_start','quiet_end'):
            datetime.strptime(p[key],'%H:%M')
    return db.put('setting',p['id'],p)

@app.post('/api/reminder/snooze')
def snooze() -> dict[str, Any]:
    return db.put('reminder',date.today().isoformat(),{'suppressed':True,'at':now()})

@app.post('/api/reminder/test')
async def reminder_test() -> dict[str, Any]:
    from .scheduler import notify
    channels = await asyncio.to_thread(notify)
    return {'channels':channels,'note':'系统调用已返回；声音是否可闻、气泡是否可见需在当前桌面确认'}

@app.get('/api/diagnostics')
async def diagnostics() -> dict[str, Any]:
    def probe() -> dict[str, Any]:
        import importlib.util
        gpu: dict[str, Any] = {'torch':None,'cuda':False,'vram_mb':None,'note':'未安装torch；NumPy课程可离线运行'}
        if importlib.util.find_spec('torch'):
            import torch
            gpu.update(torch=torch.__version__,cuda=torch.cuda.is_available())
            if gpu['cuda']:
                gpu.update(vram_mb=torch.cuda.get_device_properties(0).total_memory/1024**2,free_mb=torch.cuda.mem_get_info()[0]/1024**2,name=torch.cuda.get_device_name(0))
        stats = {u['id']:lint(content.lecture(u['id']))['color'] for u in content.units() if u['lecture']}
        return dict(python=platform.python_version(),db_bytes=(db.DATA/'groundwork.db').stat().st_size,lint=stats,errors=db.all_records('error'),gpu=gpu)
    return await asyncio.to_thread(probe)

app.mount('/static', StaticFiles(directory=db.ROOT/'app/web'), name='static')

@app.get('/')
def index() -> FileResponse:
    return FileResponse(db.ROOT/'app/web/index.html',headers={'Cache-Control':'no-store'})
