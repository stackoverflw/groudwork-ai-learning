"""Start the loopback-only app, or run offline content and environment checks."""
from __future__ import annotations
import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import threading
import webbrowser
import sys

ROOT = Path(__file__).resolve().parent

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--selfcheck', action='store_true')
    parser.add_argument('--reminder', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    (ROOT / 'logs').mkdir(exist_ok=True)
    handler = RotatingFileHandler(ROOT / 'logs/app.log', maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    logging.basicConfig(level=logging.INFO, handlers=[handler], format='%(message)s')
    if not args.selfcheck:
        import http.client
        try:
            probe = http.client.HTTPConnection('127.0.0.1',9890,timeout=.2)
            probe.request('GET','/api/health')
            existing = json.loads(probe.getresponse().read())
            probe.close()
            if existing.get('app') == 'groundwork':
                if not args.no_browser and not args.reminder:
                    webbrowser.open('http://127.0.0.1:9890')
                return
        except (OSError,ValueError):
            pass
    from app import db, content
    db.init()
    db.backup()
    if not db.get('setting', 'plan'):
        from datetime import date
        db.put('setting', 'plan', {'start': date.today().isoformat()})
    if args.selfcheck:
        from app.lint import lint
        results = {}
        for u in content.units():
            if u.get('lecture'):
                try:
                    results[u['id']] = lint(content.lecture(u['id']))
                except ValueError as e:
                    results[u['id']] = {'color':'red','hits':[str(e)]}
        errors = {k: v for k, v in results.items() if v['color'] != 'green'}
        expected = ['r0-softmax','r0-matmul','r0-layernorm','r0-gradient','r0-kv','l0-memory','l0-tensor','l0-softmax','l0-attention','l0-measure']+[f'week-{w:02}' for w in range(3,13)]
        actual = {u['id'] for u in content.units()}
        for key in set(expected)-actual:
            errors[key] = 'Missing unit'
        for key in ('lab-softmax','lab-attention'):
            try:
                from app.runner import parse_acceptance
                lab = content.find('labs',key)
                if not parse_acceptance(lab['acceptance']['cmd'],key):
                    errors[key] = 'Invalid acceptance command'
            except (ValueError,KeyError) as e:
                errors[key] = str(e)
        from app.course import lessons
        for key, lesson in lessons().items():
            if not lesson['unit']['guide']['steps'] or not all(lesson['exercise'][kind] for kind in ('correctness','robustness')):
                errors[key] = 'Missing guide or exercise cases'
            if not next((u['produced'] for u in content.units() if u['id']==key), False):
                errors[key] = 'Course unit unavailable'
        for key in ('l0-check','milestone-1','milestone-2','milestone-3','milestone-4', *lessons()):
            try:
                if len(content.find('quizzes',key)['questions'])!=5:
                    errors[key] = 'Quiz must contain 5 questions'
            except ValueError as e:
                errors[key] = str(e)
        report = {'python': sys.version, 'ready': not errors, 'content': '内容完整' if not errors else '内容失败', 'lectures': len(results), 'units': len(content.units()), 'errors': errors, 'gpu': 'Not probed at startup; use diagnostics'}
        path = ROOT / 'logs/selfcheck.json'
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        raise SystemExit(bool(errors))
    from app.api import app
    from app.scheduler import start
    start(tray=True)
    if not args.no_browser and not args.reminder:
        threading.Timer(0.7, lambda: webbrowser.open('http://127.0.0.1:9890')).start()
    logging.info(json.dumps({'event': 'start', 'url': 'http://127.0.0.1:9890'}))
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=9890, access_log=False, log_config=None)

if __name__ == '__main__':
    main()
