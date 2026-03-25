# Hello World Flask App

## Context
A minimal Python web application using the Flask framework. The app serves as a starting point or proof-of-concept, exposing a single HTTP endpoint that returns a greeting.

## Scope

### In Scope
- A single Flask application file (`app.py`)
- One route: `GET /` → returns `Hello, World!`
- A `requirements.txt` pinning Flask
- Basic project structure ready to run locally

### Out of Scope
- Authentication
- Database integration
- Multiple routes or templates
- Deployment configuration (Docker, CI/CD)
- Tests (beyond manual verification)

## Technical Approach
- **Language**: Python 3
- **Framework**: Flask (latest stable)
- **Entry point**: `app.py` — creates a Flask app instance, registers the `/` route, and runs via `if __name__ == '__main__'`
- **Dependencies**: declared in `requirements.txt`

## Risks
- Python version mismatch — Flask 3.x requires Python 3.8+; document the requirement
- Port conflicts on local dev — default port 5000 may be in use on macOS (AirPlay Receiver); can be overridden via env var
