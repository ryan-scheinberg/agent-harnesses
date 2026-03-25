# agent-harnesses

Thin orchestration harnesses for coding agents. Each harness wraps a specific agent SDK into a multi-agent loop: plan → build → review, slice by slice.

## Harnesses

| Name | SDK | Status |
|------|-----|--------|
| [`copilot/`](#copilot-multi-agent) | `github-copilot-sdk` | ✓ |
| [`claude/`](#claude-multi-agent) | `claude-agent-sdk` | ✓ |

---

## claude-multi-agent

A CLI orchestrator built on `claude-agent-sdk` that decomposes work into vertical slices and executes them sequentially. Port of the Copilot version with a cleaner SDK surface — stateless `query()` calls, structured reviewer output, built-in cost tracking.

### How it works

```
python -m claude_multi_agent "Build a FastAPI service with health check and user CRUD"
```

1. **Planner** writes `PROJECT_BRIEF.md` and `slices/01-*.md … slices/N-*.md` to your working directory
2. **Generator** picks the next undone slice, implements it using `complete-ticket` methodology, reports `COMPLETED_SLICE: <filename>`
3. **Reviewer** reads the code (read-only via `disallowed_tools`). Returns structured JSON: `{"passed": bool, "feedback": str}`
4. If `passed=false`, the generator gets one retry with the feedback
5. Orchestrator marks the slice done via YAML frontmatter and loops
6. Print summary: slices completed, retries, duration, total cost

### Architecture

```
claude/
├── claude_multi_agent/
│   ├── __main__.py    # CLI entry point (argparse) + orchestrator loop
│   ├── agents.py      # System prompts, query() wrappers, response parsing
│   ├── types.py       # Slice, SliceResult, ReviewResult dataclasses
│   └── log.py         # Structured JSON logging to stderr
├── tests/             # Unit (56) + integration (1) tests
├── example-test-from-integration/  # Real integration run output (Flask hello world)
└── pyproject.toml
```

### Key differences from Copilot version

| Aspect | Copilot | Claude |
|--------|---------|--------|
| Agent call | `CopilotClient` → `create_session` → events | `query()` → async iterator → `ResultMessage` |
| Read-only enforcement | Custom permission handler + prompt | `disallowed_tools` (SDK-enforced) |
| Reviewer output | Freeform text, silence = pass | Structured JSON `{"passed": bool, "feedback": str}` |
| Cost tracking | None | `ResultMessage.total_cost_usd` per call |
| Runaway protection | None | `max_turns` per agent |
| Auth | GitHub token (Copilot subscription) | Claude Code CLI (`claude login`) |

### Requirements

- Python 3.12+
- `claude-agent-sdk` (`pip install claude-agent-sdk`)
- Claude Code CLI installed and authenticated (`npm install -g @anthropic-ai/claude-code && claude login`)
- Skills at `~/.cursor/skills/`: `define-project`, `plan-to-jira`, `complete-ticket`

### Usage

```bash
cd /your/project
python -m claude_multi_agent "Build a FastAPI service with health check and user CRUD"

# Override model (default: claude-sonnet-4-6)
python -m claude_multi_agent "..." --model claude-opus-4
```

### Testing

```bash
cd claude/
source .venv/bin/activate

# Unit tests (56 tests, ~0.2s)
python -m pytest tests/ -v

# Integration test (hits real API, costs ~$0.27)
python -m pytest -m integration -v
```

### Example: integration run output

`example-test-from-integration/` contains real output from running the harness against `"Build a simple Flask hello world app"`:

- `PROJECT_BRIEF.md` — scoped brief the planner wrote
- `slices/01-flask-hello-world.md` — single slice, marked `status: done`
- `app.py` — the generated Flask app
- `test_app.py` — pytest with Flask test client
- `requirements.txt` — `Flask`

---

## copilot-multi-agent

A CLI orchestrator built on `github-copilot-sdk` that decomposes work into vertical slices and executes them sequentially. Three agents, one loop, structured handoff.

**The idea:** single-agent coding passes drift on non-trivial work. This harness forces decomposition. You give it a broad prompt; it plans, then builds and reviews — slice by slice — using existing Copilot skills for methodology.

### How it works

```
python -m copilot_multi_agent "Build a FastAPI service with health check and user CRUD"
```

1. **Planner** writes `PROJECT_BRIEF.md` and `slices/01-*.md … slices/N-*.md` to your working directory
2. **Generator** picks the next undone slice, implements it using `complete-ticket` methodology, and reports `COMPLETED_SLICE: <filename>`
3. **Reviewer** reads the code (read-only — no writes, no shell). Silence = pass. Any output = failures only.
4. If the reviewer had feedback, the generator gets one retry with that feedback
5. Orchestrator prepends `status: done` YAML frontmatter to the slice file and loops
6. Repeat until all slices are done, then print a summary

### Architecture

```
copilot/
├── copilot_multi_agent/
│   ├── __main__.py    # CLI entry point (argparse) + orchestrator loop
│   ├── agents.py      # Session creation: planner, generator, reviewer
│   ├── types.py       # Slice, SliceResult, ReviewResult dataclasses
│   └── log.py         # Structured JSON logging to stderr
├── slices/            # Build slices for the harness itself (meta)
├── tests/             # Unit + integration tests
├── example-test-from-integration/  # Real integration run output (Flask hello world)
└── pyproject.toml
```

### Requirements

- Python 3.12+
- `github-copilot-sdk` 0.1.0 (install from GitHub source into `~/.venv`)
- GitHub account with Copilot subscription
- Copilot skills installed at `~/.copilot/skills/`: `define-project`, `plan-to-jira`, `complete-ticket`

### Usage

```bash
cd ~/.venv && source bin/activate
cd /your/project

python -m copilot_multi_agent "Build a FastAPI service with health check and user CRUD"

# Override model (default: claude-sonnet-4.5)
python -m copilot_multi_agent "..." --model claude-opus-4-5
```

### Testing

```bash
cd copilot/

# Unit tests
pytest

# Integration tests (hit the real Copilot API, require auth)
pytest -m integration
```

### Example: integration run output

`example-test-from-integration/` contains the real output from running the harness against the prompt `"Build a simple Flask hello world app"`:

- `PROJECT_BRIEF.md` — scoped brief the planner wrote
- `slices/01-project-setup.md` — scaffold slice, marked `status: done`
- `slices/02-hello-world-route.md` — route implementation slice, marked `status: done`
- `app.py` — the generated Flask app
- `requirements.txt` — `flask>=3.0`
