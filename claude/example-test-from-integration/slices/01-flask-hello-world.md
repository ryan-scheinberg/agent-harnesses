---
status: done
completed_at: 2026-03-25T21:58:45.472859+00:00
---
# Flask Hello World — MVP Slice

## What

A working Flask app with a single `GET /` route returning `Hello, World!`, a passing pytest test, and a `requirements.txt`. Fully demoable: clone, install, run, curl, done.

## Acceptance Criteria

- `GET /` returns HTTP 200 with body `Hello, World!`
- `pytest` passes with at least one test covering the route
- `requirements.txt` pins Flask so `pip install -r requirements.txt` works clean
- `python app.py` starts the dev server without errors
- `.gitignore` excludes `__pycache__`, `.venv`, `*.pyc`

## Key Decisions

- Single `app.py` — no factory pattern, no blueprints
- pytest + Flask test client for testing — no external HTTP calls in tests
- Plain text response — no JSON envelope, no HTML template
- Python 3.11+ assumed; no version pinning in `requirements.txt` beyond Flask itself
