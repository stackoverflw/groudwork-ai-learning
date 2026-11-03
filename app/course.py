"""Read the built-in curriculum and grade its deterministic offline exercises."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]


def lessons() -> dict[str, dict[str, Any]]:
    return json.loads((ROOT / 'content/course.json').read_text(encoding='utf-8'))


def exercise(key: str) -> dict[str, Any]:
    unit_id = key.removeprefix('course-')
    return lessons()[unit_id]['exercise']


def same_value(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            same_value(actual[key], value) for key, value in expected.items()
        )
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(
            same_value(a, e) for a, e in zip(actual, expected)
        )
    return actual == expected


def grade(spec: dict[str, Any], fn: Callable[..., Any]) -> dict[str, Any]:
    checks = {}
    for kind in ('correctness', 'robustness'):
        failures = []
        examples = spec[kind]
        for case, (args, expected) in enumerate(examples, 1):
            try:
                actual = json.dumps(fn(*args), ensure_ascii=False, sort_keys=True, allow_nan=False)
                if same_value(json.loads(actual), expected):
                    continue
            except Exception as error:
                actual = str(error) or type(error).__name__
            failures.append({'case': case, 'expected': expected, 'actual': actual[:250]})
        checks[kind] = {'passed': not failures, 'cases': len(examples), 'failures': failures}
    return {'passed': all(check['passed'] for check in checks.values()), 'checks': checks}
