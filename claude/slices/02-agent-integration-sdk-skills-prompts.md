# Implement agents with SDK integration, skill loading, and system prompts

## What

Fill in `agents.py` with real `claude-agent-sdk` `query()` calls. Runtime skill loading from `~/.cursor/skills/`. System prompts for planner, generator, and reviewer. Structured JSON output for reviewer. Wire agents into the orchestrator, replacing stubs.

Demoable outcome: `python -m claude_multi_agent "Build a simple Flask hello world app"` runs end-to-end — planner writes `PROJECT_BRIEF.md` + slices, generator implements each slice, reviewer checks with structured pass/fail, summary includes per-call cost.

## Acceptance Criteria

1. `agents.py` — `_run_agent(user_prompt, options)` helper: iterates `query()` async iterator, collects `TextBlock` text from `AssistantMessage`, captures `total_cost_usd` from `ResultMessage`, returns `tuple[str, float]`
2. `agents.py` — `_load_skill(name)` reads `~/.cursor/skills/{name}/SKILL.md`, returns content as string. Raises `FileNotFoundError` with clear message if skill doesn't exist.
3. `agents.py` — Planner system prompt: two-phase instructions with runtime-loaded `define-project` and `plan-to-jira` methodology injected. Tells agent to write `PROJECT_BRIEF.md` then `slices/*.md` files.
4. `agents.py` — Generator system prompt: runtime-loaded `complete-ticket` methodology injected. Instructions to pick a slice, implement it, end with `COMPLETED_SLICE: <filename>`.
5. `agents.py` — Reviewer system prompt: harsh, terse, failures-only personality. No runtime skill loading — prompt is handcrafted.
6. `agents.py` — `run_planner(prompt, model, working_dir)` → calls `_run_agent` with `ClaudeAgentOptions(permission_mode="bypassPermissions", max_turns=30, cwd=working_dir)`. Returns cost.
7. `agents.py` — `run_generator(prompt, model, remaining_slices, working_dir, feedback=None)` → builds user prompt with slice list + original prompt + optional feedback, calls `_run_agent` with `ClaudeAgentOptions(permission_mode="bypassPermissions", max_turns=50, cwd=working_dir)`. Parses `COMPLETED_SLICE` from response. Returns `SliceResult` + cost.
8. `agents.py` — `run_reviewer(model, slice_filename, working_dir)` → calls `_run_agent` with `ClaudeAgentOptions(disallowed_tools=["Write", "Edit", "Bash", "NotebookEdit"], permission_mode="default", max_turns=10, cwd=working_dir, output_format=reviewer_schema)`. Parses structured JSON. Returns `ReviewResult` + cost.
9. `agents.py` — Reviewer JSON parsing: `json.loads()` the `ResultMessage.result` (structured output). If `JSONDecodeError`, treat as pass and log warning. Return `ReviewResult(passed=..., feedback=...)`.
10. `__main__.py` — `_async_main()` loads skills once, then calls `run_planner`, then enters orchestrator loop with real agent functions. Accumulates cost from each call.
11. `__main__.py` — `print_summary()` includes total cost (sum of all agent calls) or `N/A` if all costs were zero/None.
12. Unit tests: mock `query()` to yield canned `AssistantMessage`/`ResultMessage` sequences. Verify `ClaudeAgentOptions` fields (system_prompt contains skill text, permission_mode, disallowed_tools, output_format, max_turns, cwd). Verify `COMPLETED_SLICE` regex parsing. Verify reviewer JSON parsing + fallback on invalid JSON.
13. Unit test: mock `Path.read_text` for `_load_skill`, verify `FileNotFoundError` propagation.

## Dependencies

- 01-foundation-types-logging-cli-orchestrator

## Key Decisions

- `_run_agent` is the only function that touches `claude-agent-sdk`. All three agent functions call through it. If the SDK API changes, one function to update.
- Skills are loaded once in `_async_main` and passed into agent functions (or used to build system prompts at that point). Not loaded per-agent-call — avoid redundant file reads.
- Structured output for reviewer uses `ResultMessage.result` field (the SDK places structured output there), not parsed from `AssistantMessage` text blocks.
- Generator and reviewer return `(result, cost)` tuples so the orchestrator can accumulate cost without reaching into SDK internals.
- `COMPLETED_SLICE` regex fallback: if no match, assume first remaining slice (same as copilot version).
- Model passed through from CLI `--model` arg. Each agent function receives it, passes to `ClaudeAgentOptions.model`. No per-agent model override in v1.
