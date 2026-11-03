# Groundwork

**An offline platform for learning AI engineering. Spend 12 weeks defining problems, designing evaluations, and building reliable systems.**

[简体中文](README.md) · [Curriculum (Chinese)](课程架构.md) · [User guide (Chinese)](使用说明.md)

Groundwork is designed for first-year students and beginners. Lessons start with a small worked example, followed by a self-check and a coding exercise. Four preparatory lessons cover Python, mathematics, computing basics, and hardware units. The main track moves from NumPy, matrices, gradients, and attention to data validation, retrieval, citation evaluation, retries, permissions, and persistence. The lessons and interface are currently in Simplified Chinese.

The running project is a **local evidence assistant for papers and technical documents**. Select UTF-8 TXT or Markdown files, search for a term, and inspect matching excerpts with filenames and line numbers. The course uses this lexical baseline to teach how to build evaluation sets, distinguish retrieval hits from evidence that supports a claim, and route unsupported cases for review.

## Quick start

You need Windows 10/11 and Python 3.11. Initial setup downloads the Python dependencies.

```powershell
git clone https://github.com/stackoverflw/groudwork-ai-learning.git
cd groudwork-ai-learning
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

If Python is outside PATH, pass `-Python C:\path\to\python.exe` to the setup script. Double-click the **Groundwork** desktop shortcut or `启动.bat` in the repository. [Open the local app](http://127.0.0.1:9890)

On the home page, open the preparatory lessons or follow the current unit from explanation to coding and self-check. In the editor, **Ctrl+S** saves a draft and **Ctrl+Enter** runs tests. Reminders can be enabled in settings.

## Curriculum and features

| Stage | What you build or practice |
| --- | --- |
| Preparation | Python functions, ratios and rates of change, data encoding, and resource estimates |
| Weeks 1–2 | Five operator drills, five detailed lessons, and two local CPU NumPy labs |
| Weeks 3–6 | Input and output contracts, validation, confusion matrices, and resource budgets |
| Weeks 7–9 | Reproducible retrieval, citation checks, and bounded retries |
| Weeks 10–12 | Permission boundaries, idempotency, and an evidence assistant that cites source excerpts |

Groundwork includes four milestone assessments, spaced review, time tracking, and an experiment ledger. Project exercises check correctness and edge cases. Numeric quiz answers are graded automatically. Written explanations and designs use a self-assessment rubric.

## Local data and runtime

The service listens on `127.0.0.1:9890` and runs offline after setup. Progress is stored in `data/groundwork.db`. The ledger supports JSON export and restore. The evidence assistant reads selected files in the browser. Submitted Python runs in a local subprocess with your user permissions, so only execute code you trust.

The NumPy labs measure CPU time and memory. The current evidence assistant uses lexical retrieval and serves as a baseline for studying retrieval-augmented generation and model-based answers.

## Development and checks

```powershell
.\.venv\Scripts\python.exe run.py --selfcheck
.\.venv\Scripts\python.exe -m pytest -q
```

`app/` contains FastAPI, SQLite storage, the exercise runner, and the web UI. `content/` contains lessons and labs. `scripts/` contains setup and maintenance tools. `tests/` covers course progression, recovery, and backup rotation.

Reproducible bug reports, lesson improvements, and additional tests are welcome. Groundwork uses the MIT license. [View LICENSE](LICENSE)
