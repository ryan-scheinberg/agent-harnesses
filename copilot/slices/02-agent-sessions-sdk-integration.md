# Implement agent sessions with SDK integration

## What

Fill in `agents.py` with real `CopilotClient` / `create_session` calls for all three agents (planner, generator, reviewer). Wire them into the orchestrator loop, replacing the stubs from slice 01. Each agent function starts a session, sends a message, collects events until idle, disconnects, and returns a typed result.

Demoable outcome: `python -m copilot_multi_agent "Build a hello world Flask app"` calls the planner (which writes `PROJECT_BRIEF.md` and `slices/*.md` via Copilot tools), then loops through slices calling the generator and reviewer with real SDK sessions. The full plan-build-review cycle runs against the real Copilot backend.

## Acceptance Criteria

1. `agents.py` — `start_client(working_dir)` creates and starts a shared `CopilotClient` with `SubprocessConfig(cwd=working_dir)`. `stop_client()` stops it. Client instance is module-level or passed through
2. `agents.py` — `run_planner(client, prompt, model, working_dir)` creates a session with `define-project` and `plan-to-jira` skill directories, `PermissionHandler.approve_all`, appended system message with two-phase instructions. Returns after `session.idle`
3. `agents.py` — `run_generator(client, remaining_slices, original_prompt, model, working_dir, feedback=None)` creates a new session per call with `complete-ticket` skill directory, `PermissionHandler.approve_all`. Prompt includes remaining slice filenames/titles and optional reviewer feedback. Returns `SliceResult` with the slice filename the generator chose
4. `agents.py` — `run_reviewer(client, slice_filename, model, working_dir)` creates a session with no skill directories, read-only permission handler (approves file reads, denies writes and bash), `excluded_tools` for write/shell tools. Returns `ReviewResult` with feedback text (empty = pass)
5. Event handler pattern: each agent function uses `asyncio.Event` + `session.on()` callback to collect `assistant.message` events and wait for `session.idle`, per the SDK pattern in the brief
6. `__main__.py` — Orchestrator updated to call real agent functions instead of stubs. Single `CopilotClient` started at the top, stopped at the end
7. Planner creates real `PROJECT_BRIEF.md` and `slices/*.md` files when given a prompt — verified by integration test
8. Integration test (`pytest -m integration`): runs the full CLI against a simple prompt, asserts `PROJECT_BRIEF.md` and at least one slice file are created

## Key Decisions

- One `CopilotClient` instance shared across all sessions — started once, stopped once
- Each agent function creates and disconnects its own session — clean session boundaries per the brief
- Generator session is new per slice iteration (not reused) — avoids context accumulation
- Reviewer permission handler is a custom callable that checks the tool name: approve `read_file`/`list_directory` type tools, deny everything else
- System prompts are string constants defined at module level in `agents.py` — not loaded from external files
- `skill_directories` paths use `os.path.expanduser("~/.copilot/skills/...")` 
- Integration tests are slow and require auth — gated behind `@pytest.mark.integration`
