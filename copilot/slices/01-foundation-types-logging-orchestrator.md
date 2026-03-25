# Scaffold package with types, logging, CLI, and orchestrator loop

## What

Create the `copilot_multi_agent` package with all four files. Implement `types.py`, `log.py`, and `__main__.py` fully — the orchestrator loop runs end-to-end with **stubbed agent calls**. Agent stubs return canned results so the loop can be tested in isolation without the SDK.

Demoable outcome: `python -m copilot_multi_agent "test prompt"` runs, reads pre-placed slice files from `slices/`, loops through them, logs structured JSON to stderr, marks each slice done via YAML frontmatter, and prints a final summary to stdout.

## Acceptance Criteria

1. Package structure exists: `copilot_multi_agent/__init__.py`, `__main__.py`, `types.py`, `log.py`, `agents.py` (empty stub module with async function signatures that raise `NotImplementedError`)
2. `types.py` — `Slice` dataclass parses a slice markdown file including YAML frontmatter (`status`, `completed_at`). `SliceResult` and `ReviewResult` dataclasses exist with fields per the brief
3. `types.py` — `Slice` can read a markdown file from disk, detect whether it has `status: done` frontmatter, and a function can prepend/update YAML frontmatter on a slice file
4. `log.py` — `log_event()` writes structured JSON to stderr with fields: `ts`, `agent`, `slice`, `duration_s`, `status`. Timestamps are ISO 8601
5. `__main__.py` — CLI parses `<prompt>` positional arg and `--model` optional arg (default `claude-sonnet-4.5`) via argparse
6. `__main__.py` — Orchestrator loop: reads `slices/` dir, finds undone slices, calls generator stub, calls reviewer stub, handles retry logic (one retry if reviewer returns feedback), marks slice done, repeats until all done
7. `__main__.py` — Final summary printed to stdout: slices completed, retries used, total duration
8. All unit tests pass: frontmatter parsing, frontmatter writing, log output format, CLI arg parsing, orchestrator loop with stubs (use tmp dirs with pre-placed slice files)
9. `python -m copilot_multi_agent "anything"` runs without error when stubs are in place and slice files exist

## Key Decisions

- Agent functions in `agents.py` are async stubs (`async def run_planner(...)`, `async def run_generator(...)`, `async def run_reviewer(...)`) that raise `NotImplementedError` — slice 2 fills them in
- The orchestrator calls these functions and handles their return types (`SliceResult`, `ReviewResult`)
- Frontmatter is the orchestrator's responsibility — no agent modifies slice files
- Reviewer stub returns empty string (silence = pass) by default in tests; tests also cover the retry path with non-empty feedback
- No SDK dependency in this slice — only stdlib and pydantic
- Tests use `pytest` with `tmp_path` fixtures for file operations
