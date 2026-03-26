# Flask Hello World

## Context

Minimal Flask app with a single `GET /` route returning `Hello, World!`. Serves as a working, deployable baseline — not a toy snippet, but a properly structured Python web service with dependencies pinned, a test, and a way to run it.

## Audience

The developer running this locally and any agent picking up future slices of this repo. The structure should be extensible without rewrites.

## Scope

### The MVP Slice

A user can `curl http://localhost:5000/` and get `Hello, World!` back from a running Flask server.

### In Scope

- `app.py` with a single `GET /` route
- `requirements.txt` with Flask pinned
- One test asserting the route returns 200 and the expected body
- `README` instructions to install, run, and test

### Out of Scope

- Auth, middleware, blueprints, database — anything beyond one route
- Docker / containerization
- CI pipeline setup

## Technical Approach

- **Language:** Python 3.11+
- **Framework:** Flask (latest stable, pinned in `requirements.txt`)
- **Test runner:** pytest with Flask's built-in test client
- **Structure:** flat — `app.py`, `test_app.py`, `requirements.txt`, `README.md`
- No factory pattern or blueprints needed at this scale; `app.py` creates and exposes the app directly

## Testing & Observability

- `test_app.py`: one test, `test_index_returns_hello_world`, asserts `GET /` → 200, body == `Hello, World!`
- No structured logging needed at this scope; Flask's default request logging is sufficient
- "Working in production" means the process starts without error and the route responds

## Deployment & Rollout

Run locally with `flask run` or `python app.py`. No deployment target defined for this scope.

## Risks & Open Questions

- None. This is fully scoped and decided.
