"""Run local Python submissions with timeouts and independently measured acceptance checks."""
from __future__ import annotations
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from typing import Any
from . import course

ROOT = Path(__file__).resolve().parents[1]
DRILLS = {
 'r0-softmax': ('softmax(x)', 'import numpy as np\n\ndef softmax(x):\n    # TODO 1: convert to float64\n    # TODO 2: subtract the maximum\n    # TODO 3: exponentiate\n    # TODO 4: normalize\n    raise NotImplementedError\n'),
 'r0-matmul': ('matmul(a, b)', 'import numpy as np\n\ndef matmul(a, b):\n    # TODO 1: validate dimensions\n    # TODO 2: allocate output\n    # TODO 3: multiply and accumulate\n    raise NotImplementedError\n'),
 'r0-layernorm': ('layernorm(x, eps=1e-5)', 'import numpy as np\n\ndef layernorm(x, eps=1e-5):\n    # TODO 1: row mean\n    # TODO 2: row variance\n    # TODO 3: normalize\n    raise NotImplementedError\n'),
 'r0-gradient': ('gradient(x, y, w)', 'import numpy as np\n\ndef gradient(x, y, w):\n    # TODO 1: predict x @ w\n    # TODO 2: compute residual\n    # TODO 3: mean squared error gradient\n    raise NotImplementedError\n'),
 'r0-kv': ('kv_bytes(layers, tokens, heads, head_dim, bytes_per_element)', 'def kv_bytes(layers, tokens, heads, head_dim, bytes_per_element):\n    # TODO 1: validate nonnegative integer arguments\n    # TODO 2: count K and V elements\n    # TODO 3: convert to bytes\n    raise NotImplementedError\n'),
}
LAB_SIGNATURES = {'lab-softmax': 'softmax_rows(x)', 'lab-attention': 'attention(q, k, v)'}

def reference(key: str, args: tuple[Any, ...]) -> Any:
    import numpy as np
    if key in ('r0-softmax', 'lab-softmax'):
        x = np.asarray(args[0], dtype=np.float64)
        e = np.exp(x - np.max(x, axis=-1, keepdims=True))
        return e / np.sum(e, axis=-1, keepdims=True)
    if key == 'r0-matmul':
        return args[0] @ args[1]
    if key == 'r0-layernorm':
        x = args[0]
        return (x-x.mean(axis=-1, keepdims=True))/np.sqrt(x.var(axis=-1, keepdims=True)+1e-5)
    if key == 'r0-gradient':
        x, y, w = args
        return 2*x.T@(x@w-y)/len(y)
    if key == 'r0-kv':
        if any(not isinstance(a, int) or a < 0 for a in args):
            raise ValueError('nonnegative integers required')
        return 2*int(np.prod(args))
    q, k, v = args
    return reference('r0-softmax', (q@k.T/np.sqrt(q.shape[-1]),)) @ v

def cases(key: str) -> list[tuple[Any, ...]]:
    import numpy as np
    rng = np.random.default_rng(42)
    if key in ('r0-softmax', 'lab-softmax'):
        return [(np.array([1000., 1001., 999.]) if key.startswith('r0') else np.array([[1000.,1001.,999.], [-1000.,-1001.,-999.]]),), (rng.normal(size=(7, 9)),), (np.zeros((1, 1)),)]
    if key == 'r0-matmul':
        return [(rng.normal(size=(m,k)), rng.normal(size=(k,n))) for m,k,n in [(2,3,4),(1,1,1),(3,0,2)]]
    if key == 'r0-layernorm':
        return [(rng.normal(size=(3,4)),), (np.ones((2,7)),), (np.zeros((1,1)),)]
    if key == 'r0-gradient':
        return [(rng.normal(size=(n,d)), rng.normal(size=n), rng.normal(size=d)) for n,d in [(4,3),(1,1),(8,2)]]
    if key == 'r0-kv':
        return [(24,1024,8,64,2),(0,1,1,1,2),(1,0,1,1,2),(-1,1,1,1,2)]
    return [(rng.normal(size=(n,d)), rng.normal(size=(n,d)), rng.normal(size=(n,d))) for n,d in [(7,4),(1,8),(19,16)]]

def measure(fn: Any, args: tuple[Any, ...], warmup: int = 2, reps: int = 7) -> float:
    for _ in range(warmup):
        fn(*args)
    times = []
    for _ in range(reps):
        start = time.perf_counter_ns()
        fn(*args)
        times.append((time.perf_counter_ns()-start)/1e6)
    return statistics.median(times)

def worker(key: str, solution: Path) -> dict[str, Any]:
    if key.startswith('course-'):
        spec = course.exercise(key)
        module_spec = importlib.util.spec_from_file_location('submission', solution)
        module = importlib.util.module_from_spec(module_spec)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            module_spec.loader.exec_module(module)
            return course.grade(spec, getattr(module, spec['signature'].split('(')[0]))
    import numpy as np
    import psutil
    spec = importlib.util.spec_from_file_location('submission', solution)
    module = importlib.util.module_from_spec(spec)
    custom = None
    if key not in DRILLS and key not in LAB_SIGNATURES:
        from .content import find
        custom = find('labs',key)
        dataset = custom['acceptance']['correctness']['dataset']
    # Student output is discarded; only independently computed results are returned.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(module)
        name = dataset['entrypoint'] if custom else LAB_SIGNATURES.get(key, DRILLS.get(key, ('',))[0]).split('(')[0]
        fn = getattr(module, name)
        failures = []
        convert = lambda values: tuple(np.asarray(a,dtype=np.float64) if isinstance(a,list) else a for a in values)
        testcases = [convert(c['args']) for c in dataset['cases']] if custom else cases(key)
        for index, args in enumerate(testcases, 1):
            try:
                expected = dataset['cases'][index-1]['expected'] if custom else reference(key, args)
            except ValueError:
                try:
                    fn(*args)
                    failures.append({'case': index, 'expected': 'ValueError', 'actual': 'no exception'})
                except ValueError:
                    pass
                continue
            try:
                actual = fn(*args)
                tolerance = custom['acceptance']['correctness'] if custom else {'atol':1e-6,'rtol':1e-5}
                if np.shape(actual) != np.shape(expected) or not np.allclose(actual, expected, atol=tolerance['atol'], rtol=tolerance['rtol'], equal_nan=False):
                    failures.append({'case': index, 'expected': np.asarray(expected).tolist(), 'actual': np.asarray(actual).tolist() if np.size(actual) < 100 else str(np.shape(actual))})
            except Exception as e:
                failures.append({'case': index, 'expected': 'valid output', 'actual': type(e).__name__ + ': ' + str(e)[:160]})
        checks = {'correctness': {'passed': not failures, 'atol': tolerance['atol'], 'rtol': tolerance['rtol'], 'failures': failures}, 'robustness': {'passed': not failures, 'cases': len(testcases)}}
        is_lab = key not in DRILLS
        if is_lab and not failures:
            rng = np.random.default_rng(73)
            if custom:
                namespace = {'np':np}
                exec(compile(dataset['baseline_source'],'<local teacher baseline>','exec'),namespace)
                slow = namespace['baseline']
                for sample in dataset['cases']:
                    got = slow(*convert(sample['args']))
                    if np.shape(got)!=np.shape(sample['expected']) or not np.allclose(got,sample['expected'],atol=tolerance['atol'],rtol=tolerance['rtol']):
                        raise ValueError('Imported teacher baseline fails its own correctness contract')
                args = convert(dataset['benchmark_args'])
            elif key == 'lab-softmax':
                args = (rng.normal(size=(256,256)),)
                def slow(x: Any) -> Any:
                    return np.array([reference('r0-softmax', (row,)) for row in x])
            else:
                args = tuple(rng.normal(size=(96,32)) for _ in range(3))
                def slow(q: Any, k: Any, v: Any) -> Any:
                    score = np.array([[np.dot(a,b) for b in k] for a in q])/np.sqrt(q.shape[-1])
                    return reference('r0-softmax', (score,)) @ v
            baseline = measure(slow, args)
            measured = measure(fn, args)
            tracemalloc.start()
            fn(*args)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            rss = psutil.Process().memory_info()
            peak_mb = max(peak, getattr(rss, 'peak_wset', rss.rss))/1024**2
            target = custom['acceptance']['perf']['target_x'] if custom else 1.2
            limit = custom['acceptance']['memory']['limit_mb'] if custom else 256
            checks['perf'] = {'passed': baseline/max(measured, 1e-9) >= target, 'baseline_ms': baseline, 'measured_ms': measured, 'speedup': baseline/max(measured, 1e-9), 'target_x': target, 'protocol': 'CPU float64; warmup=2; reps=7; median perf_counter_ns; synchronous numpy; same-process baseline'}
            checks['memory'] = {'passed': peak_mb <= limit, 'peak_mb': peak_mb, 'limit_mb': limit, 'api': 'Windows peak_wset (whole child process) + tracemalloc; CPU, not VRAM'}
        elif is_lab:
            checks.update(perf={'passed': False, 'reason': 'correctness failed; not measured'}, memory={'passed': False, 'reason': 'correctness failed; not measured'})
    return {'passed': all(c['passed'] for c in checks.values()), 'checks': checks}

def run(key: str, code: str, timeout: int = 15) -> dict[str, Any]:
    if key.startswith('course-'):
        course.exercise(key)
    elif key not in DRILLS and key not in LAB_SIGNATURES:
        from .content import find
        find('labs',key)
    if len(code.encode('utf-8')) > 65536:
        raise ValueError('Submission exceeds 64 KiB')
    from . import db
    folder = db.DATA / 'runs'
    folder.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(dir=folder) as temp:
        solution = Path(temp) / 'solution.py'
        solution.write_text(code, encoding='utf-8')
        with (Path(temp) / 'out').open('w+', encoding='utf-8') as out:
            p = subprocess.Popen([sys.executable, '-m', 'app.runner', 'worker', key, '--solution', str(solution)], cwd=ROOT, stdout=out, stderr=out, env=dict(os.environ, GROUNDWORK_DATA=str(db.DATA), OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1'))
            try:
                p.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == 'nt':
                    subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'], capture_output=True, check=False)
                else:
                    p.kill()
                p.wait()
                return {'passed': False, 'error': 'Execution timeout', 'wall_seconds': time.perf_counter()-started}
            out.seek(0)
            raw = out.read(100000)
        try:
            result = json.loads(raw)
        except ValueError:
            result = {'passed': False, 'error': raw[-600:] or f'Worker exited {p.returncode}'}
    return dict(result, wall_seconds=time.perf_counter()-started)

def parse_acceptance(command: str, key: str) -> bool:
    import re
    return bool(re.fullmatch(r'lab-[a-z0-9-]{1,60}',key)) and command == f'python -m app.runner accept {key} --solution {{solution}}'

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['accept','worker'])
    parser.add_argument('key')
    parser.add_argument('--solution', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = worker(args.key, args.solution) if args.mode == 'worker' else run(args.key, args.solution.read_text(encoding='utf-8'))
    except BaseException as e:
        result = {'passed': False, 'error': type(e).__name__ + ': ' + str(e)[:300]}
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdout.write(json.dumps(result, ensure_ascii=False, allow_nan=False) + '\n')
    raise SystemExit(not result['passed'])
