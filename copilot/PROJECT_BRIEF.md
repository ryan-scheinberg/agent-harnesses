# copilot-multi-agent

## Context

Coding agents are powerful but single-threaded: one prompt, one execution pass, hope it works. For non-trivial work — features that touch multiple files, multi-step refactors, new projects — a single pass produces sprawl. The agent tries to hold everything in its head and drifts.

This project builds a thin Python harness on `github-copilot-sdk` that decomposes work into vertical slices and executes them sequentially. Three agents, one loop, structured handoff: plan, build, review.

The harness is a CLI tool. You give it a broad prompt. It plans, then builds and reviews — slice by slice. It leverages existing Copilot skills (`define-project`, `plan-to-jira`, `complete-ticket`) rather than reinventing their logic.

## Audience

Ryan. Solo + agents. The harness is a local dev tool that sits between "I have an idea" and "the code exists." It's the orchestrator that turns a vague intent into sequenced, scoped agent work. Runs from the local terminal against your repo checkout.

## Scope

### The MVP Slice

A user runs `python -m copilot_multi_agent "Build a FastAPI service with health check and user CRUD"` and gets:
1. A `PROJECT_BRIEF.md` written to the working directory
2. A `slices/` directory with numbered markdown files — each a self-contained story
3. Each slice implemented by the generator, reviewed by the reviewer, fixed if needed
4. Final summary of what was done

### In Scope

- **Planning agent**: Takes a broad prompt → creates `PROJECT_BRIEF.md` (using `define-project` skill) → creates numbered slice files in `slices/` (using `plan-to-jira` methodology, but writing local files instead of Jira tickets). Has full tool access to write files. Single session, two-phase.
- **Generator agent**: Sees remaining undone slices and picks which one to work on each iteration. Implements it using Copilot's built-in toolset (file read/write/edit, bash, etc.). Uses `complete-ticket` skill for execution methodology. New session per slice — clean boundaries.
- **Reviewer agent**: Runs after each generator pass. Read-only access only — no bash, no writes. Outputs only failures. Silence = pass. Harsh, terse, serious. If feedback exists, generator gets one retry with the feedback (no second review).
- **Orchestrator loop**: Reads `slices/` for undone files. Calls generator (which picks a slice). Calls reviewer. If feedback, calls generator again with feedback. Marks slice done via YAML frontmatter. Repeats until all slices done.
- **CLI entry point**: `python -m copilot_multi_agent "<prompt>"` with optional `--model` override.
- **Structured logging**: Each agent call logged with slice index, duration, success/failure. JSON to stderr so stdout stays clean.

### Out of Scope

- Parallel slice execution. Sequential is correct for v1 — slices build on each other.
- Web UI or API server. This is a CLI tool.
- Custom MCP tools beyond what Copilot CLI provides built-in.
- Persistent state across runs. Each invocation is standalone.
- Agent-to-agent communication beyond the orchestrator. No direct message passing.
- Jira integration. The planner uses `plan-to-jira` methodology for slicing, but writes local files — no Jira API.
- Session persistence / resume. If a run fails partway, re-run from scratch. Slices with `status: done` frontmatter could support future `--resume` but it's not v1.

## Technical Approach

### Stack

- Python 3.12+, `github-copilot-sdk` 0.1.0 (installed from GitHub source into `~/.venv`)
- Auth via GitHub token (Copilot subscription). SDK's `SubprocessConfig.github_token` or logged-in user.
- `pydantic` (comes with SDK), stdlib. No additional deps.
- `~/.venv` as the runtime environment

### Architecture

```
copilot_multi_agent/
├── __main__.py    # CLI entry point (argparse) + orchestrator loop
├── agents.py      # Session creation for planner, generator, reviewer
├── types.py       # Dataclasses: Slice, SliceResult, ReviewResult
└── log.py         # Structured JSON logging to stderr
```

Four files. Planner, generator, and reviewer are all thin session configurations in `agents.py` — different system prompts, different skill access, different tool permissions. No separate modules per agent.

No plan parser. Slices are physical files, not parsed from a markdown blob.

### SDK Pattern

All three agents use `CopilotClient` with `create_session()`. The client spawns a Copilot CLI subprocess with built-in tool access. Each agent session is created, sent a message, events collected until `session.idle`, then disconnected.

```python
client = CopilotClient(SubprocessConfig(cwd=working_dir))
await client.start()

session = await client.create_session(
    on_permission_request=PermissionHandler.approve_all,
    model="claude-sonnet-4.5",
    system_message={"mode": "append", "content": system_prompt},
    skill_directories=["~/.copilot/skills/define-project", "~/.copilot/skills/plan-to-jira"],
    working_directory=working_dir,
)

done = asyncio.Event()
result_text = []

def on_event(event):
    if event.type.value == "assistant.message":
        result_text.append(event.data.content)
    elif event.type.value == "session.idle":
        done.set()

session.on(on_event)
await session.send(user_prompt)
await done.wait()
await session.disconnect()
```

One `CopilotClient` instance shared across all agent sessions. Each agent gets its own `create_session` call with its own system prompt, skill directories, and permission config.

### Skill Integration

The harness loads existing Copilot skills selectively per agent via `skill_directories`:

| Agent | Skills | Why |
|-------|--------|-----|
| Planner | `define-project`, `plan-to-jira` | Scoping methodology + story-slicing methodology |
| Generator | `complete-ticket` | TDD execution, acceptance criteria, incremental delivery |
| Reviewer | None (system prompt only) | Custom behavior: harsh, failure-only, read-only |

Skills are loaded from `~/.copilot/skills/`. The system prompt for each agent explains how to use the loaded skills in this context (e.g., planner told to write local files, not Jira tickets).

### Planning Agent (in `agents.py`)

Single session, two phases:

**Phase 1**: Uses `define-project` methodology to understand the prompt, explore the cwd if there's existing code, and write `PROJECT_BRIEF.md` to disk.

**Phase 2**: Uses `plan-to-jira` story-slicing methodology to break the brief into vertical slices. Writes each slice as a numbered markdown file in `slices/`:

```
slices/
├── 01-project-setup.md
├── 02-data-models.md
├── 03-api-endpoints.md
└── 04-tests-and-validation.md
```

Each slice file follows the plan-to-jira story format:

```markdown
# <Title>

## Description
<What to build — the demoable outcome>

## Acceptance Criteria
- <Testable criterion 1>
- <Testable criterion 2>

## Key Decisions
- <Constraints, interfaces, architectural decisions relevant to this slice>
```

Session config:
- `skill_directories`: `[~/.copilot/skills/define-project, ~/.copilot/skills/plan-to-jira]`
- `system_message`: Two-phase instructions — brief first, then slice. Write files, not Jira tickets.
- `on_permission_request`: `PermissionHandler.approve_all` — needs to write PROJECT_BRIEF.md and slices/
- `working_directory`: user's working directory
- `model`: configurable, defaults to `claude-sonnet-4.5`

### Generator Agent (in `agents.py`)

New session per slice iteration. The generator prompt includes:
- List of remaining undone slice filenames and their titles
- The user's original prompt for context
- Instructions to pick a slice, implement it, and report which one it chose

The generator uses `complete-ticket` skill methodology: understand criteria, build incrementally, verify.

Session config:
- `skill_directories`: `[~/.copilot/skills/complete-ticket]`
- `system_message`: Execution instructions — pick a remaining slice, implement it, report which one
- `on_permission_request`: `PermissionHandler.approve_all` — auto-approve file changes and shell commands
- `working_directory`: user's working directory
- `model`: configurable, defaults to `claude-sonnet-4.5`

### Reviewer Agent (in `agents.py`)

New session per review. Read-only access only — no bash, no file writes. The reviewer gets told which slice was just implemented and reviews the work.

**Critical prompt design**: The reviewer must be tuned for harsh, real criticism. Claude tends toward politeness and false passes. The system prompt must:
- Instruct: only report problems. If everything is fine, say nothing.
- Silence = pass. Empty or minimal response means the work is acceptable.
- No praise, no encouragement, no "looks good overall." Only issues.
- Be specific: file, line, what's wrong, why it matters.

Session config:
- `system_message`: Harsh reviewer instructions — only failures, terse, no praise
- `on_permission_request`: custom handler that approves reads, denies everything else
- `excluded_tools`: all write/shell tools — read-only file access only
- `working_directory`: user's working directory
- `model`: configurable, defaults to `claude-sonnet-4.5`

### Orchestrator (in `__main__.py`)

```
1. Start CopilotClient
2. Call planner with user prompt
   → Planner writes PROJECT_BRIEF.md and slices/*.md
3. Loop:
   a. Read slices/ directory
   b. Find files without `status: done` YAML frontmatter
   c. If none remain → done, go to step 4
   d. Call generator with list of remaining slice filenames
      → Generator picks one, implements it, reports which one
   e. Call reviewer for that slice
   f. If reviewer has feedback:
      - Call generator again with reviewer feedback (one retry)
      - No second review
   g. Orchestrator prepends YAML frontmatter to the slice file:
      ```yaml
      ---
      status: done
      completed_at: <ISO 8601 timestamp>
      ---
      ```
   h. Log result
   i. Back to step 3a
4. Print final summary
5. Stop CopilotClient
```

Nobody modifies slice files except the orchestrator (to mark done). The planner creates them, the generator and reviewer read them, the orchestrator marks them.

### CLI (`__main__.py`)

```
Usage: python -m copilot_multi_agent <prompt> [options]

Options:
  --model MODEL    Model override for all agents (default: claude-sonnet-4.5)
```

Minimal surface. No `--cwd`, `--dry-run`, `--hitl`, or `--verbose`. Run it and let it go. Uses `argparse`. Runs the async orchestrator via `asyncio.run()`.

## Testing & Observability

### Testing

- Unit tests for `types.py` (dataclass construction, YAML frontmatter parsing)
- Integration test: run against a known prompt, assert slices/ created with correct format
- No mocking the SDK — integration tests hit the real API. Keep them behind a marker (`pytest -m integration`).

### Observability

- Structured JSON logs to stderr for every agent invocation:
  ```json
  {"ts": "...", "agent": "planner", "slice": null, "duration_s": 12.3, "status": "ok"}
  {"ts": "...", "agent": "generator", "slice": "01-project-setup", "duration_s": 45.1, "status": "ok"}
  {"ts": "...", "agent": "reviewer", "slice": "01-project-setup", "duration_s": 8.2, "status": "pass"}
  {"ts": "...", "agent": "generator", "slice": "01-project-setup", "duration_s": 20.0, "status": "retry"}
  ```
- Final summary to stdout: slices completed, slices failed, retries used, total duration

## Risks & Open Questions

1. **Reviewer effectiveness**: This is the hardest part. Claude defaults to polite, which means false passes. The reviewer prompt needs aggressive tuning — only failures, no praise, silence = pass. Expect to iterate on this prompt more than anything else. If the reviewer is consistently too soft, consider: stronger language in the prompt, few-shot examples of harsh reviews, or a dedicated reviewer skill.

2. **Skill loading via `skill_directories`**: Untested assumption that the SDK loads skills from arbitrary directories and the agent uses them correctly. If skills don't load or the agent ignores them, fall back to inlining the skill content into the system prompt.

3. **Generator slice selection**: The generator picks which slice to work on. It might pick poorly (wrong order, skip dependencies) or claim it completed a slice it didn't. The orchestrator has no way to verify which slice was actually implemented beyond trusting the generator's report. If this is unreliable, fall back to orchestrator-assigned ordering.

4. **Copilot SDK maturity**: The `github-copilot-sdk` is in technical preview. API may change. Pin to the current commit. If it breaks, we vendor the working version.

5. **Slice count is unconstrained**: The planner decides how many slices based on complexity. This could produce too many (20+) or too few (1). Monitor in practice. If it's consistently wrong, add guidance to the system prompt — but don't constrain it with a hard limit.

6. **Context window on generator**: New session per slice avoids accumulated context, but the generator still needs to understand the codebase state. For large projects, the generator might struggle to orient. The `complete-ticket` skill's "explore the codebase" step should help.

7. **No second review after retry**: The generator gets one retry with feedback but no second review. If the retry makes things worse, that goes undetected. Acceptable for v1 — the user reviews the final diff.
