# claude-multi-agent

## Context

Port of `copilot-multi-agent` from `github-copilot-sdk` to `claude-agent-sdk`. Same idea — thin harness that decomposes a broad prompt into vertical slices, then plans, builds, and reviews them sequentially. Three agents, one loop, structured handoff.

The Copilot version works. It proved the pattern. But the SDK is in technical preview with a bespoke event model, `skill_directories` that may or may not load correctly, and a `CopilotClient`/`create_session` lifecycle that's more complex than it needs to be.

`claude-agent-sdk` is a cleaner fit. `query()` gives stateless one-shot agent calls — exactly what generator and reviewer need. `ClaudeAgentOptions` consolidates system prompt, tool permissions, permission mode, and model into one config object. No event listeners, no `done.wait()` — just an async iterator of messages. The SDK also gives us cost tracking for free via `ResultMessage`, `max_turns` to cap runaway agents, `disallowed_tools` for hard enforcement (not just prompt-based), and structured output for deterministic reviewer responses.

The harness still leverages skill methodology — `define-project` for scoping, `plan-to-jira` for slicing, `complete-ticket` for execution — loaded at runtime from `~/.cursor/skills/` so they stay fresh as skills evolve.

## Audience

Ryan. Solo + agents. Same as the Copilot version — local CLI tool that turns a vague prompt into sequenced, scoped agent work against your repo checkout.

## Scope

### The MVP Slice

A user runs `python -m claude_multi_agent "Build a FastAPI service with health check and user CRUD"` and gets a `PROJECT_BRIEF.md`, numbered slice files in `slices/`, each slice implemented and reviewed, and a final summary with cost.

### In Scope

- **Planning agent**: Takes a broad prompt → writes `PROJECT_BRIEF.md` (runtime-loaded `define-project` methodology) → writes numbered slice files in `slices/` (runtime-loaded `plan-to-jira` methodology). Uses `query()` with `permission_mode="bypassPermissions"`. Single call, two-phase system prompt.
- **Generator agent**: New `query()` call per slice. Sees remaining undone slices, picks one, implements it, reports `COMPLETED_SLICE: <filename>`. Runtime-loaded `complete-ticket` methodology. `permission_mode="bypassPermissions"`, `max_turns=50`.
- **Reviewer agent**: New `query()` call per review. Hard-enforced read-only via `disallowed_tools`. Returns structured JSON: `{"passed": bool, "feedback": str}`. Harsh, terse, failures only. If `passed=false`, generator gets one retry with `feedback`.
- **Orchestrator loop**: Read `slices/`, find undone, call generator (which picks a slice), call reviewer, one retry if `passed=false`, mark done, repeat.
- **CLI entry point**: `python -m claude_multi_agent "<prompt>"` with optional `--model` override.
- **Structured logging**: JSON to stderr. Agent name, slice, duration, status, cost.
- **Cost tracking**: `ResultMessage.total_cost_usd` per agent call, aggregated in final summary. `N/A` if the SDK returns `None`.

### Out of Scope

- Parallel slice execution. Sequential for v1.
- Web UI or API server. CLI tool.
- Custom MCP tools. Use Claude Code's built-in toolset.
- Persistent state across runs. Standalone invocations.
- Agent-to-agent communication beyond the orchestrator.
- Jira integration. Local files only.
- Session persistence / resume. Re-run from scratch; `status: done` frontmatter preserves partial progress for future `--resume`.
- `ClaudeSDKClient` continuous conversation mode. `query()` is simpler and sufficient — clean session per agent call is a feature, not a limitation.
- Safety hooks for destructive commands. Git is the safety net for v1.

## Technical Approach

### Stack

- Python 3.12+, `claude-agent-sdk` (`pip install claude-agent-sdk`)
- Auth via Claude Code CLI (must be installed and authenticated — this is not raw Anthropic API key auth)
- stdlib only beyond the SDK. No pydantic, no extra deps.

### Architecture

```
claude_multi_agent/
├── __init__.py
├── __main__.py    # CLI entry point (argparse) + orchestrator loop
├── agents.py      # System prompts, query() wrappers, response parsing
├── types.py       # Dataclasses: Slice, SliceResult, ReviewResult
└── log.py         # Structured JSON logging to stderr
```

Four files + init. Same layout as the Copilot version. Prompts live in `agents.py` because each agent IS its prompt + options — keeping them together means one file to understand each agent.

`types.py` is duplicated from the Copilot version (identical dataclasses). 91 lines of types isn't worth coupling the harnesses with a shared module.

### SDK Pattern

All three agents use `query()` — stateless, one-shot, async iterator. No client lifecycle management. No event listeners. Each call spawns a Claude Code CLI subprocess, runs the agent, returns messages.

```python
from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, TextBlock, ResultMessage

async def _run_agent(user_prompt: str, options: ClaudeAgentOptions) -> tuple[str, float]:
    """Run an agent, collect text response and cost."""
    text_parts: list[str] = []
    cost = 0.0

    async for message in query(prompt=user_prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
        elif isinstance(message, ResultMessage):
            cost = message.total_cost_usd or 0.0

    return "\n".join(text_parts), cost
```

This `_run_agent` helper is the entire SDK integration layer. Each agent function calls it with different `ClaudeAgentOptions`.

### Runtime Skill Loading

System prompts load skill methodology from `~/.cursor/skills/` at runtime:

```python
def _load_skill(name: str) -> str:
    path = Path.home() / ".cursor" / "skills" / name / "SKILL.md"
    return path.read_text()
```

Skills are read once per harness invocation and injected into the system prompt templates. If a skill file doesn't exist, the run fails immediately with a clear error — skills are a hard dependency, not optional.

| Agent | Loaded Skill | Why |
|-------|-------------|-----|
| Planner | `define-project` + `plan-to-jira` | Scoping methodology + story-slicing methodology |
| Generator | `complete-ticket` | TDD execution, acceptance criteria, incremental delivery |
| Reviewer | None (prompt only) | Custom behavior: harsh, read-only, structured output |

### Planning Agent

Single `query()` call with a two-phase system prompt:

**Phase 1**: `define-project` methodology — understand the prompt, explore cwd if there's existing code, write `PROJECT_BRIEF.md` to disk.

**Phase 2**: `plan-to-jira` slicing — break the brief into vertical slices, write each as `slices/NN-<title>.md`.

Slice format (same as Copilot version):

```markdown
# <Title>

## What
<Demoable outcome>

## Acceptance Criteria
- <Testable criterion>

## Key Decisions
- <Constraints and architectural decisions>
```

Config:

```python
ClaudeAgentOptions(
    system_prompt=planner_system_prompt,  # inlined define-project + plan-to-jira methodology
    permission_mode="bypassPermissions",
    model="claude-sonnet-4.6",
    cwd=working_dir,
    max_turns=30,
)
```

### Generator Agent

New `query()` per slice. The generator picks which slice to implement from the remaining list. User prompt includes remaining undone slice filenames + titles, the original prompt for context, and instructions to end with `COMPLETED_SLICE: <filename>`.

Inlines `complete-ticket` methodology: read the slice, understand acceptance criteria, explore the codebase, build incrementally, verify.

Config:

```python
ClaudeAgentOptions(
    system_prompt=generator_system_prompt,  # inlined complete-ticket methodology
    permission_mode="bypassPermissions",
    model="claude-sonnet-4.6",
    cwd=working_dir,
    max_turns=50,
)
```

### Reviewer Agent

New `query()` per review. Hard-enforced read-only via `disallowed_tools` — the SDK won't execute write/bash tools regardless of what the model tries. No `allowed_tools` needed; `disallowed_tools` is sufficient since it overrides everything including `bypassPermissions`.

Returns structured JSON via `output_format`:

```python
reviewer_schema = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "passed": {"type": "boolean"},
            "feedback": {"type": "string"},
        },
        "required": ["passed", "feedback"],
    },
}
```

If `passed=true`, `feedback` is empty. If `passed=false`, `feedback` contains specific file/line/reason findings. No ambiguity about what silence means — the boolean is the gate.

Config:

```python
ClaudeAgentOptions(
    system_prompt=reviewer_system_prompt,
    disallowed_tools=["Write", "Edit", "Bash", "NotebookEdit"],
    permission_mode="default",
    model="claude-sonnet-4.6",
    cwd=working_dir,
    max_turns=10,
    output_format=reviewer_schema,
)
```

### Orchestrator

```
1. Load skills from ~/.cursor/skills/ (fail fast if missing)
2. Call planner with user prompt
   → Writes PROJECT_BRIEF.md and slices/*.md
3. Loop:
   a. discover_slices() — read slices/, parse frontmatter
   b. Filter to undone slices
   c. If none remain → done
   d. Call generator with remaining slice list
      → Generator picks one, implements it, reports COMPLETED_SLICE: <filename>
   e. Parse COMPLETED_SLICE from response (fallback: first remaining slice)
   f. Call reviewer for that slice
   g. Parse structured JSON response: {"passed": bool, "feedback": str}
   h. If passed=false → call generator again with feedback (one retry, no second review)
   i. Orchestrator marks slice done (YAML frontmatter)
   j. Log result (including cost)
   k. Repeat
4. Print final summary (slices, retries, duration, total cost)
```

Error handling: fail fast. A failed slice likely means subsequent slices fail too. Log the error clearly with the SDK exception type (`CLINotFoundError`, `ProcessError`, `CLIJSONDecodeError`) so the user knows what happened.

### CLI

```
Usage: python -m claude_multi_agent <prompt> [options]

Options:
  --model MODEL    Model override for all agents (default: claude-sonnet-4.6, optional)
```

Model is optional. If omitted, defaults to `claude-sonnet-4.6`. Override with `--model claude-opus-4` or any supported model string. `argparse`. `asyncio.run()`.

### Key Differences from Copilot Version

| Aspect | Copilot | Claude |
|--------|---------|--------|
| SDK | `github-copilot-sdk` 0.1.0 (preview) | `claude-agent-sdk` (pip) |
| Agent call | `CopilotClient` → `create_session` → events → `session.idle` | `query()` → async iterator → `ResultMessage` |
| Skills | `skill_directories` file loading | Runtime `Path.read_text()` into system prompts |
| Read-only enforcement | Custom permission handler + prompt | `disallowed_tools` (SDK-enforced) |
| Reviewer output | Freeform text, silence = pass | Structured JSON `{"passed": bool, "feedback": str}` |
| Cost tracking | None | `ResultMessage.total_cost_usd` per call |
| Runaway protection | None | `max_turns` per agent |
| Auth | GitHub token (Copilot subscription) | Claude Code CLI (logged in) |
| Install | From GitHub source | `pip install claude-agent-sdk` |
| Error handling | Crash on failure | Fail fast with typed exceptions |

## Testing & Observability

### Testing

- Unit tests for `types.py` — same dataclasses as Copilot, same tests
- Unit tests for `agents.py` — mock `query()`, verify `ClaudeAgentOptions` passed correctly, verify response parsing (text extraction, `COMPLETED_SLICE` regex, structured reviewer JSON parsing)
- Unit tests for skill loading — mock filesystem, verify graceful failure on missing skills
- Integration test: run against a known prompt, assert `PROJECT_BRIEF.md` + `slices/` created with correct format. Behind `pytest -m integration`.

### Observability

Structured JSON logs to stderr:

```json
{"ts": "...", "agent": "planner",   "slice": null,               "duration_s": 12.3, "status": "ok",    "cost_usd": 0.042}
{"ts": "...", "agent": "generator", "slice": "01-project-setup",  "duration_s": 45.1, "status": "ok",    "cost_usd": 0.089}
{"ts": "...", "agent": "reviewer",  "slice": "01-project-setup",  "duration_s": 8.2,  "status": "pass",  "cost_usd": 0.015}
{"ts": "...", "agent": "generator", "slice": "01-project-setup",  "duration_s": 20.0, "status": "retry", "cost_usd": 0.052}
```

Final summary to stdout: slices completed, retries used, total duration, total cost (or `N/A` if SDK returned `None`).

## Risks & Open Questions

1. **`query()` spawns a subprocess per call.** Each `query()` starts a Claude Code CLI subprocess. For 5 slices: ~15 subprocesses (planner + 5 generators + 5 reviewers + retries). Subprocess startup is ~1-2s, negligible vs agent runtime of 10-60s per call. If measured performance disagrees, switch to `ClaudeSDKClient` — but only if measured.

2. **Structured reviewer output reliability.** The SDK's `output_format` with JSON schema should enforce the `{"passed": bool, "feedback": str}` shape. If the model produces invalid JSON despite the schema constraint, the orchestrator needs a fallback. Parse with `json.loads()`, catch `JSONDecodeError`, treat parse failure as a pass (don't block on a reviewer malfunction). Log the raw response for debugging.

3. **Skill file dependency at runtime.** Skills loaded from `~/.cursor/skills/` must exist. If they don't, the run fails immediately. This is correct — running without methodology produces garbage. But it means the harness isn't portable to machines without the skills installed. Acceptable for a personal dev tool.

4. **`bypassPermissions` is a loaded gun.** Auto-approves everything including destructive commands. Git is the safety net. Only run in directories you're willing to lose or can recover. No safety hook for v1 — keep it simple.

5. **`max_turns` tuning.** 30/50/10 are educated guesses. Too low = slice can't finish. Too high = burns money on a bad path. Log actual turn counts (from `ResultMessage.num_turns`) and adjust the constants based on real data.

6. **Reviewer softness.** Same risk as Copilot version, but structured output helps — the model must commit to `passed: true` or `passed: false`. No wiggle room for "looks mostly fine but maybe consider..." The boolean forces a decision. The prompt still needs to be aggressive to get real feedback in the `feedback` field.

7. **Claude Code CLI auth.** The SDK requires Claude Code CLI installed and authenticated (`claude` login). This is not raw `ANTHROPIC_API_KEY` auth. If the user's CLI session expires mid-run, the harness fails. Fail fast with `CLINotFoundError` or `CLIConnectionError` — no silent degradation.

8. **Model availability.** Default is `claude-sonnet-4.6` but optional. If the user passes a model string that doesn't exist or they don't have access to, the SDK will error. Let it bubble up — don't validate model names ourselves.
