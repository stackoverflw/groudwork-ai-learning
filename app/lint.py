"""Deterministic lecture lint with severity, line numbers and exact rule matches."""
from __future__ import annotations
import re
from typing import Any

BANNED = '众所周知 不难发现 值得注意的是 在本节中 我们将 总的来说 非常重要 极大地 若干 深入理解 熟悉一下'.split()
HEADINGS = ['速览','心智模型','概念逐条','数字表','代码','边界与失败模式','三分钟复述稿','自测','延伸阅读','术语表']
SOURCE = r'【(?:实测[^】]*|估算：[^】]+|文献[^】]*)】'

def lint(text: str) -> dict[str, Any]:
    hits: list[dict[str, Any]] = []
    def hit(rule: str, severity: str, pos: int, message: str) -> None:
        hits.append({'rule': rule, 'severity': severity, 'line': text[:pos].count('\n')+1, 'message': message})
    for word in BANNED:
        for m in re.finditer(re.escape(word), text):
            hit('L1', 'red', m.start(), f'禁用词：{word}')
    # Ignore fenced runnable code, section labels, symbol definitions and metadata.
    masked = re.sub(r'```[\s\S]*?```', lambda m: ''.join('\n' if c == '\n' else ' ' for c in m.group()), text)
    masked = re.sub(r'^#{1,6} .+$', lambda m: ' '*len(m.group()), masked, flags=re.M)
    for m in re.finditer(r'(?:[^\n]|\n(?!\n))+', masked):
        paragraph = m.group()
        for empty in re.finditer(r'[^\d=∑∏∂⊗]{200,}',paragraph):
            if len(re.sub(r'\s','',empty.group()))>=200:
                hit('L2', 'yellow', m.start()+empty.start(), '连续200字符缺少数字、公式或代码')
        for phrase in re.finditer(r'[^。\n]{0,12}(?:很重要|是核心)|随着[^。\n]*的发展|需要多加练习', paragraph):
            hit('L3', 'yellow', m.start()+phrase.start(), phrase.group())
        # A number in prose must have a source marker immediately after its unit/range.
        clean = re.sub(SOURCE, lambda v: ' '*len(v.group()), paragraph)
        for n in re.finditer(r'(?<![A-Za-z_\d.])\d+(?:\.\d+)?(?:\s*[×*/^+-]\s*\d+(?:\.\d+)?)*(?![\d.])', clean):
            tail = paragraph[n.end():]
            if not re.match(r'(?:\s|[^\d。；！？【】]){0,32}' + SOURCE, tail):
                hit('L4', 'yellow', m.start()+n.start(), f'数字无出处：{n.group()}')
    for i, name in enumerate(HEADINGS):
        if not re.search(rf'^## {i} {re.escape(name)}\s*$', text, re.M):
            hit('L5', 'red', 0, f'缺章节：{i} {name}')
    if re.search('[∑∏∂⊗]', text) and '符号表' not in text:
        hit('L6', 'red', 0, '公式出现未定义符号，缺符号表')
    color = 'red' if any(h['severity']=='red' for h in hits) else 'yellow' if hits else 'green'
    return {'color': color, 'hits': hits}
