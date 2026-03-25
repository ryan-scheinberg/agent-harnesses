# copilot-multi-agent

Multi-agent CLI orchestrator on `github-copilot-sdk`. Give it a prompt, get a planned + implemented + reviewed codebase.

## Requirements

- Python 3.12+, `~/.venv`
- `github-copilot-sdk` 0.1.0 (from GitHub source)
- Copilot subscription
- Skills at `~/.copilot/skills/`: `define-project`, `plan-to-jira`, `complete-ticket`

## Usage

```bash
source ~/.venv/bin/activate
cd /your/project

python -m copilot_multi_agent "Build a FastAPI service with health check and user CRUD"

# Override model (default: claude-sonnet-4.5)
python -m copilot_multi_agent "..." --model claude-opus-4-5
```

Outputs `PROJECT_BRIEF.md` and `slices/` to the working directory. Logs JSON to stderr, summary to stdout.

## What it does

1. **Planner** writes `PROJECT_BRIEF.md` + numbered slice files in `slices/`
2. **Generator** implements each slice (new session per slice, `complete-ticket` methodology)
3. **Reviewer** checks the work read-only — silence = pass, any output = failures only
4. One retry if reviewer has feedback, then slice is marked `status: done`
5. Repeat until all slices done

## Tests

```bash
pytest                  # unit tests
pytest -m integration   # hit real API (requires Copilot auth)
```

## Layout

```
copilot_multi_agent/
├── __main__.py   # CLI + orchestrator loop
├── agents.py     # planner / generator / reviewer sessions
├── types.py      # Slice, SliceResult, ReviewResult
└── log.py        # JSON logging to stderr
```

See `example-test-from-integration/` for a real run output (Flask hello world).
