# claude-multi-agent

CLI orchestrator built on `claude-agent-sdk` that decomposes work into vertical slices and executes them sequentially. Three agents, one loop, structured handoff.

## Requirements

- Python 3.12+
- `claude-agent-sdk` (`pip install claude-agent-sdk`)
- Claude Code CLI installed and authenticated (`npm install -g @anthropic-ai/claude-code && claude login`)
- Skills at `~/.cursor/skills/`: `define-project`, `plan-to-jira`, `complete-ticket`

## Usage

```bash
cd /your/project

python -m claude_multi_agent "Build a FastAPI service with health check and user CRUD"

# Override model (default: claude-sonnet-4-6)
python -m claude_multi_agent "..." --model claude-opus-4
```

## Architecture

```
claude_multi_agent/
├── __init__.py
├── __main__.py    # CLI entry point (argparse) + orchestrator loop
├── agents.py      # System prompts, query() wrappers, response parsing
├── types.py       # Dataclasses: Slice, SliceResult, ReviewResult
└── log.py         # Structured JSON logging to stderr
```

## Agents

| Agent | Tools | Skills | Output |
|-------|-------|--------|--------|
| Planner | Full access | `define-project`, `plan-to-jira` | `PROJECT_BRIEF.md` + `slices/*.md` |
| Generator | Full access | `complete-ticket` | Code + `COMPLETED_SLICE: <filename>` |
| Reviewer | Read-only (`disallowed_tools`) | None | `{"passed": bool, "feedback": str}` |

## Testing

```bash
# Unit tests
python -m pytest tests/ -v

# Integration tests (hits real Claude Code API — requires auth, costs money)
python -m pytest -m integration
```

## Observability

Structured JSON logs to stderr per agent call:

```json
{"ts": "...", "agent": "generator", "slice": "01-setup", "duration_s": 45.1, "status": "ok", "cost_usd": 0.089, "num_turns": 12}
```

Final summary to stdout: slices completed, retries, duration, total cost.
