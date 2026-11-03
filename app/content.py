"""Load curated local content and determine prerequisite-driven learning tasks."""
from __future__ import annotations
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from . import course, db

CONTENT = db.ROOT / 'content'

def load(group: str) -> list[dict[str, Any]]:
    result = [json.loads(p.read_text(encoding='utf-8')) for p in sorted((CONTENT / group).glob('*.json'))]
    if group in ('units', 'quizzes'):
        field = 'unit' if group == 'units' else 'quiz'
        curriculum = course.lessons()
        additions = {key: lesson[field] for key, lesson in curriculum.items()}
        if group == 'quizzes':
            for phase, weeks in ((2, (4, 5, 6)), (3, (7, 8, 9)), (4, (10, 11, 12))):
                a, b, c = [curriculum[f'week-{week:02d}']['quiz']['questions'] for week in weeks]
                key = f'milestone-{phase}'
                questions = [a[0], dict(b[0], id='c2'), b[2], dict(c[3], id='n2'), c[4]]
                additions[key] = {'id': key, 'questions': questions, 'timebox_min': 40}
        result = [item for item in result if item['id'] not in additions] + list(additions.values())
    if group == 'units':
        for record in db.all_records('content'):
            result = [u for u in result if u['id'] != record['unit']['id']] + [record['unit']]
    elif group == 'labs':
        merged = {r['id']:r for r in result}
        merged.update({r['lab']['id']:r['lab'] for r in db.all_records('content')})
        result = list(merged.values())
    return sorted(result, key=lambda x: (x.get('order', 999), x['id']))

def find(group: str, key: str) -> dict[str, Any]:
    item = next((u for u in load(group) if u['id'] == key), None)
    if item is None:
        raise ValueError(f'Content not found: {group}/{key}')
    return item

def lecture(key: str) -> str:
    override = db.get('content', key)
    if override:
        return override['lecture']
    path = CONTENT / 'lectures' / (key + '.md')
    if not path.is_file():
        raise ValueError('Lecture is awaiting production')
    return path.read_text(encoding='utf-8')

def units() -> list[dict[str, Any]]:
    progress = {record['id']: record['status'] for record in db.all_records('progress')}
    result = []
    for u in load('units'):
        blockers = [p for p in u['prereq'] if progress.get(p) not in ('已通过', '跳过')]
        result.append(dict(u, status=progress.get(u['id'], '未开始'), blockers=blockers))
    return result

def current() -> dict[str, Any]:
    route = [u for u in units() if not u.get('supplement')]
    return next((u for u in route if u['status'] not in ('已通过', '跳过')), route[-1])


def next_milestone(unit: dict[str, Any]) -> int | None:
    if unit.get('supplement'):
        return None
    phase = max(1, (unit['week'] - 1) // 3 + 1)
    completed = {e['quiz'] for e in db.all_records('exam') if e.get('milestone') and e.get('passed')}
    route = {u['id']: u for u in units()}
    for number in range(1, phase + 1):
        anchor = route[f'week-{number * 3:02d}']
        if f'milestone-{number}' not in completed and anchor['status'] in ('已通过', '跳过'):
            return number
    return None

def today() -> dict[str, Any]:
    u = current()
    day = date.today().isoformat()
    rework = u['status'] == '回炉'
    project = u['practice'].startswith('course-')
    tasks = [{'id': f'{day}:{u["id"]}:{kind}', 'kind': kind, 'minutes': minutes, 'title': title,
              'done': bool(db.get('task', f'{day}:{u["id"]}:{kind}'))} for kind, minutes, title in
             [('read', 15, ('回看 · ' if rework else '阅读 · ') + u['title']),
              ('write', 45 if project else 60, ('重做 · ' if rework else '动手 · ') + (u['title'] if project else u.get('practice', '待生产'))),
              ('study', 15, '闭卷 · 五题自测')]]
    start = date.fromisoformat(db.get('setting', 'plan', {'start': day})['start'])
    milestone = start + timedelta(days=((date.today() - start).days // 21 + 1) * 21)
    due = [m for m in db.all_records('mistake') if m['due'] <= day]
    dates = {s['ended'][:10] for s in db.all_records('session') if s.get('ended')}
    streak, d = 0, date.today()
    if day not in dates:
        d -= timedelta(days=1)
    while d.isoformat() in dates:
        streak += 1
        d -= timedelta(days=1)
    due_phase = next_milestone(u)
    return {'unit': u, 'tasks': tasks, 'streak': streak, 'milestone_days': (milestone - date.today()).days, 'milestone_due': due_phase is not None, 'milestone_phase':due_phase, 'course_complete': u['id']=='week-12' and u['status'] in ('已通过','跳过') and due_phase is None, 'reviews': due}
