# Flask Hello World

## Context

Minimal Flask app with a single `GET /` route returning `Hello, World!`. Starting point for a Python web service — proves the stack boots, the route resolves, and the response is correct.

## Audience

Developer validating a Python/Flask foundation before layering in real functionality.

## Scope

### The MVP Slice

A user can `GET /` and receive `Hello, World!` in plain text with a 200 response.

### In Scope

- Flask app with a single `/` route
- `requirements.txt` pinning Flask
- Basic test asserting the route returns the expected response and status code
- `.gitignore` for Python/Flask

### Out of Scope

- Auth, middleware, database
- Docker / containerization
- Multiple routes or environments
- WSGI server config (gunicorn, uwsgi)

## Technical Approach

- **Language:** Python 3.11+
- **Framework:** Flask (latest stable)
- **Test runner:** pytest + Flask test client
- **Entry point:** `app.py` — single file, no factory pattern needed at this scale
- **No blueprints, no config objects** — YAGNI

```
flask-hello-world/
├── app.py
├── requirements.txt
├── test_app.py
└── .gitignore
```

## Testing & Observability

- `test_app.py` — one test: `GET /` returns 200 and body `Hello, World!`
- No structured logging needed at this scope — Flask default is fine
- If this breaks, pytest output is the signal

## Deployment & Rollout

- Run locally: `flask run` or `python app.py`
- No CI config in scope — add it when there's something worth protecting
- Rollback: `git revert`

## Risks & Open Questions

- None. This is a hello world app. Ship it.
