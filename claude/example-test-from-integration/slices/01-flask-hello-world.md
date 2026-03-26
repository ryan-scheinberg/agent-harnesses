---
status: done
completed_at: 2026-03-25T22:21:54.742472+00:00
---
# Flask Hello World App

## What

A running Flask app with a single `GET /` route that returns `Hello, World!`, a passing pytest test, pinned dependencies, and a README — fully functional end-to-end.

## Acceptance Criteria

- `requirements.txt` exists with Flask pinned to a specific version
- `app.py` defines a Flask app with a single route: `GET /` returns `Hello, World!` with HTTP 200
- `test_app.py` contains `test_index_returns_hello_world` using Flask's test client; asserts status code 200 and response body equals `Hello, World!`
- `pytest` passes with zero failures from a clean `pip install -r requirements.txt`
- `flask run` (or `python app.py`) starts the server without error and `curl http://localhost:5000/` returns `Hello, World!`
- `README.md` includes install, run, and test instructions

## Key Decisions

- Flat structure: `app.py`, `test_app.py`, `requirements.txt`, `README.md` — no packages, no blueprints
- Python 3.11+; Flask latest stable pinned explicitly (e.g. `Flask==3.1.0`)
- Test uses Flask's built-in test client (`app.test_client()`), not a live server
- App entry point: `app.py` creates the Flask instance as `app` and runs with `debug=False` under `if __name__ == "__main__"`
- No `.env`, no config object — hardcode defaults at this scope
