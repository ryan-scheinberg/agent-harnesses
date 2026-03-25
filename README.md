# agent-harnesses

Thin orchestration harnesses for coding agents. Each harness wraps a specific agent SDK into a multi-agent loop: plan → build → review, slice by slice.

## Harnesses

| Name | SDK | Status |
|------|-----|--------|
| [`copilot/`](#copilot-multi-agent) | `github-copilot-sdk` | ✓ |

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

### Agents

**Planner** — full tool access (file writes)
- Skills: `define-project`, `plan-to-jira` (from `~/.copilot/skills/`)
- Phase 1: explores cwd, writes `PROJECT_BRIEF.md`
- Phase 2: breaks brief into vertical slices, writes `slices/NN-<title>.md`

**Generator** — full tool access (file reads/writes, shell)
- Skills: `complete-ticket`
- New session per slice — clean context boundaries
- Picks the next slice, implements it with TDD, ends with `COMPLETED_SLICE: <filename>`

**Reviewer** — read-only
- No skills, no file writes, no shell
- Harsh system prompt: only failures, silence = pass, no praise
- Outputs specific file/line/reason or nothing

### Slice format

Each slice file follows this structure:

```markdown
# <Title>

## What
<Demoable outcome>

## Acceptance Criteria
- <Testable criterion>

## Key Decisions
- <Constraints and architectural decisions>
```

When completed, the orchestrator prepends:

```yaml
---
status: done
completed_at: 2026-03-25T19:08:44.784730+00:00
---
```

### Observability

Structured JSON logs to stderr for every agent call:

```json
{"ts": "...", "agent": "planner",    "slice": null,              "duration_s": 12.3, "status": "ok"}
{"ts": "...", "agent": "generator",  "slice": "01-project-setup", "duration_s": 45.1, "status": "ok"}
{"ts": "...", "agent": "reviewer",   "slice": "01-project-setup", "duration_s": 8.2,  "status": "pass"}
{"ts": "...", "agent": "generator",  "slice": "01-project-setup", "duration_s": 20.0, "status": "retry"}
```

Final summary to stdout: slices completed, retries used, total duration.

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

This is a useful reference for what the planner's output looks like and how completed slice frontmatter is structured.

### Known risks / open questions

- **Reviewer softness** — Claude defaults to polite. The prompt is tuned for harshness but may need iteration if it starts producing false passes.
- **Generator slice selection** — the generator picks which slice to implement. If it picks poorly, the orchestrator can't catch it without explicit validation.
- **SDK maturity** — `github-copilot-sdk` is in technical preview. Pin to a known-good commit.
- **No resume** — if a run fails mid-way, re-run from scratch. Slices with `status: done` are skipped, so partial progress is preserved.
