"""Exercise the new course through its real worker and progression API."""
from datetime import datetime, timedelta
from contextlib import redirect_stdout
from io import StringIO
import sqlite3

from app import content, db, scheduler
from app.course import lessons
from conftest import post, unlock


SOLUTIONS = {
    'foundation-python': 'def total(prices):\n    return sum(prices)',
    'foundation-math': 'def rate(passed, total):\n    return passed / total if total else None',
    'foundation-cs': 'from collections import Counter\ndef count_events(events):\n    return dict(Counter(events))',
    'foundation-units': 'def transfer_seconds(size, bandwidth):\n    return size / bandwidth if bandwidth else None',
    'week-03': """def route(text):
    words = set(text.casefold().split())
    paper, repo = 'paper' in words, 'repo' in words
    if 'private' in words or paper == repo:
        return 'review'
    return 'paper' if paper else 'repository'
""",
    'week-04': """def normalize(record):
    if isinstance(record, dict):
        fields = [record.get(key) for key in ('id', 'text')]
        if all(isinstance(value, str) and value.strip() for value in fields):
            return {'id': fields[0].strip(), 'text': fields[1].strip()}
    return {'error': 'invalid'}
""",
    'week-05': """def confusion(labels, predictions):
    if len(labels) != len(predictions):
        return {'error': 'length'}
    table = {(1, 1): 'tp', (0, 1): 'fp', (1, 0): 'fn', (0, 0): 'tn'}
    counts = dict.fromkeys(table.values(), 0)
    for pair in zip(labels, predictions):
        counts[table[pair]] += 1
    return counts
""",
    'week-06': 'def estimate(size, bandwidth, compute_seconds):\n    return size / bandwidth + compute_seconds if bandwidth else None',
    'week-07': """def rank(query, documents, k):
    words = set(query.casefold().split())
    scores = [(len(words.intersection(doc['text'].casefold().split())), doc['id']) for doc in documents]
    scores.sort(key=lambda pair: (-pair[0], pair[1]))
    return [key for score, key in scores if score][:max(k, 0)]
""",
    'week-08': """def check_answer(draft, allowed):
    if isinstance(draft, dict):
        answer, source = draft.get('answer'), draft.get('source')
        if isinstance(answer, str) and answer.strip() and isinstance(source, str) and source in allowed:
            return 'accepted'
    return 'needs_review'
""",
    'week-09': """def run_with_budget(events, limit):
    attempts = 0
    for event in events[:limit]:
        attempts += 1
        if event == 'ok':
            return {'status': 'ok', 'attempts': attempts}
        if event == 'invalid':
            break
    return {'status': 'review', 'attempts': attempts}
""",
    'week-10': """def authorize(action, approved):
    if action in ('lookup', 'draft'):
        return 'allow'
    if action == 'send':
        return 'allow' if approved is True else 'review'
    return 'deny'
""",
    'week-11': """def process(records):
    seen = {}
    statuses = []
    for key, value in records:
        if key not in seen:
            seen[key] = value
            statuses.append('created')
        else:
            statuses.append('duplicate' if seen[key] == value else 'conflict')
    return statuses
""",
    'week-12': """def assist(query, documents):
    words = set(query.casefold().split())
    if 'private' not in words:
        ranked = sorted(documents, key=lambda doc: (-len(words.intersection(doc['text'].casefold().split())), doc['id']))
        if ranked and words.intersection(ranked[0]['text'].casefold().split()):
            best = ranked[0]
            return {'status': 'answered', 'source': best['id'], 'answer': best['text']}
    return {'status': 'review'}
""",
}


def submit_quiz(client, started, wrong=False):
    quiz = content.find('quizzes', started['quiz'])
    answers = {}
    responses = {}
    for q in quiz['questions']:
        if q['kind'] == 'number':
            answers[q['id']] = q['answer'] + int(wrong)
        else:
            answers[q['id']] = 2
            responses[q['id']] = q['rubric'][2]
    return post(client, 'quiz/submit', {
        'exam': started['id'], 'answers': answers, 'responses': responses
    }).json()


def submit_code(client, unit_id, code):
    start = post(client, 'practice/start', {'unit': unit_id})
    assert start.status_code == 200, start.text
    session = start.json()['session']
    attempt = post(client, 'attempts', {'unit': unit_id, 'session': session, 'code': code})
    assert attempt.status_code == 200, attempt.text
    post(client, 'session', {'action': 'stop', 'id': session})
    return attempt.json()['result']


def test_complete_project_route_and_retake(client):
    unlock('week-03')
    for week in range(3, 13):
        key = f'week-{week:02d}'
        today = client.get('/api/today').json()
        assert today['unit']['id'] == key
        if today['milestone_due']:
            assert post(client, 'practice/start', {'unit': key}).status_code == 400
            exam = post(client, 'quiz/start', {'unit': key, 'milestone': True}).json()
            if week == 4:
                assert not submit_quiz(client, exam, wrong=True)['passed']
                exam = post(client, 'quiz/start', {'unit': key, 'milestone': True}).json()
                assert exam['unit'] == 'week-03'
            assert submit_quiz(client, exam)['passed']
        assert submit_code(client, key, SOLUTIONS[key])['passed']
        assert post(client, 'progress', {'unit': key, 'status': '已通过'}).status_code == 400
        exam = post(client, 'quiz/start', {'unit': key}).json()
        assert submit_quiz(client, exam)['passed']
        assert post(client, 'progress', {'unit': key, 'status': '已通过'}).status_code == 200
    assert not client.get('/api/today').json()['course_complete']
    exam = post(client, 'quiz/start', {'unit': 'week-12', 'milestone': True}).json()
    assert submit_quiz(client, exam)['passed']
    assert client.get('/api/today').json()['course_complete']
    assert not submit_code(client, 'week-03', 'def route(text): return "wrong"')['passed']
    assert db.get('progress', 'week-03')['status'] == '已通过'


def test_foundation_examples_and_real_workers(client):
    for key, lesson in lessons().items():
        with redirect_stdout(StringIO()):
            exec(compile(lesson['unit']['guide']['example'], key, 'exec'), {})
        if lesson['unit']['supplement']:
            assert submit_code(client, key, SOLUTIONS[key])['passed']
    assert client.get('/api/today').json()['unit']['id'] == 'r0-softmax'


def test_twelve_weeks_of_daily_backups_and_reminders(monkeypatch):
    class Calendar(datetime):
        current = datetime(2026, 11, 3, 20)

        @classmethod
        def now(cls, tz=None):
            return cls.current

    monkeypatch.setattr(db, 'datetime', Calendar)
    monkeypatch.setattr(scheduler, 'notify', lambda: ['test'])
    db.put('setting', 'reminder', {'enabled': True, 'time': '19:00'})
    for day in range(84):
        Calendar.current = datetime(2026, 11, 3, 20) + timedelta(days=day)
        assert scheduler.tick(Calendar.current) == ['test']
        assert scheduler.tick(Calendar.current) == []
        db.put('progress', 'week-03', {'day': day})
        latest = db.backup()
    assert len(list(latest.parent.glob('*.db'))) == 14
    with sqlite3.connect(latest) as connection:
        assert connection.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
        assert connection.execute("SELECT json_extract(body,'$.day') FROM records WHERE kind='progress'").fetchone()[0] == 83
