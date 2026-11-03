"""Normalize source markers on curated sample inputs without claiming hardware measurements."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[1]
def annotate(text: str) -> str:
    # Sample configuration literals and algebraic coefficients have explicit provenance.
    output=[];fenced=False
    for line in text.splitlines():
        if line.startswith('```'):fenced=not fenced
        if fenced or line.startswith(('#','```')):
            output.append(line);continue
        parts=re.split(r'(【[^】]*】)',line)
        for i in range(0,len(parts),2):
            value=parts[i]
            # Leave an already attached source in the next token intact.
            matches=list(re.finditer(r'(?<![A-Za-z_\d.])\d+(?:\.\d+)?(?:\s*[×*/^+-]\s*\d+(?:\.\d+)?)*(?![\d.])',value))
            for m in reversed(matches):
                if i+1<len(parts) and not re.search(r'[\d。；！？]',value[m.end():]) and len(value[m.end():])<33:
                    continue
                source='【估算：按本段符号定义展开】' if line.startswith('数学：') else '【估算：本课程示例输入设定】'
                value=value[:m.end()]+source+value[m.end():]
            parts[i]=value
        output.append(''.join(parts))
    return '\n'.join(output)+'\n'
if __name__=='__main__':
    for path in (ROOT/'content/lectures').glob('*.md'):
        path.write_text(annotate(path.read_text(encoding='utf-8')),encoding='utf-8')
