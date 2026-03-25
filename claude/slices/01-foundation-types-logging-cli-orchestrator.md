# Scaffold package with types, logging, CLI, and orchestrator loop

## What

Create the `claude_multi_agent` package with all four files. Implement `types.py`, `log.py`, and `__main__.py` fully — the orchestrator loop runs end-to-end with **stubbed agent calls**. Agent stubs return canned results so the loop can be tested in isolation without the SDK.

Demoable outcome: `python -m claude_multi_agent "test prompt"` runs, reads pre-placed slice files from `slices/`, loops through them, logs structured JSON to stderr, marks each slice done via YAML frontmatter, and prints a final summary to stdout.

## Acceptance Criteria

1. Package structure exists: `claude_multi_agent/__init__.py`, `__main__.py`, `types.py`, `log.py`, `agents.py` (stub module with async function signatures that raise `NotImplementedError`)
2. `types.py` — `Slice` dataclass with `from_file()` and `from_markdown()` classmethods. Parses YAML frontmatter (`status`, `completed_at`), extracts title from first `# heading`. `is_done` property returns `True` when `status == "done"`
3. `types.py` — `SliceResult(slice_filename: str, summary: str)` and `ReviewResult(slice_filename: str, passed: bool, feedback: str)` dataclasses. `ReviewResult.passed` is now an explicit field (not derived from empty feedback) since the reviewer returns structured JSON
4. `types.py` — `mark_slice_done(path)` prepends/updates YAML frontmatter with `status: done` and `completed_at: <ISO 8601>`
5. `log.py` — `log_event()` writes structured JSON to stderr with fields: `ts`, `agent`, `slice`, `duration_s`, `status`, `cost_usd`. Timestamps are ISO 8601. `cost_usd` is `Optional[float]`
6. `__main__.py` — CLI parses `<prompt>` positional arg and `--model` optional arg (default `claude-sonnet-4.6`) via argparse
7. `__main__.py` — `discover_slices(slices_dir)` reads `slices/` dir, returns `list[Slice]` sorted by filename
8. `__main__.py` — Orchestrator loop: finds undone slices, calls generator stub, calls reviewer stub, handles retry logic (one retry if `passed=false`), marks slice done, repeats until all done
9. `__main__.py` — `print_summary()` to stdout: slices completed, retries used, total duration, total cost (or `N/A`)
10. All unit tests pass: frontmatter parsing/writing, log output format, CLI arg parsing, orchestrator loop with injected stubs (use `tmp_path` fixtures with pre-placed slice files)
11. `python -m claude_multi_agent "anything"` runs without error when stubs are wired in and slice files exist in cwd

## Key Decisions

- Agent functions in `agents.py` are async stubs: `run_planner()`, `run_generator()`, `run_reviewer()` — raise `NotImplementedError`. Slice 2 fills them in.
- `ReviewResult.passed` is an explicit `bool` field, not derived from empty feedback. Matches the structured JSON schema `{"passed": bool, "feedback": str}` that the reviewer will return.
- The orchestrator accepts `generator_fn` and `reviewer_fn` as injectable callables (same pattern as copilot version) so tests can inject stubs without touching `agents.py`.
- Frontmatter is the orchestrator's responsibility — no agent modifies slice files.
- No SDK dependency in this slice — stdlib only. `claude-agent-sdk` is not imported.
- Tests use `pytest` with `tmp_path`. `asyncio_mode = "auto"` in pyproject.toml.
- `log_event` includes `cost_usd` field (defaults to `None`). Slice 2 populates it from `ResultMessage`.
