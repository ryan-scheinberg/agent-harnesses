# Add error handling, integration test, and polish

## What

Harden the harness with fail-fast error handling for SDK exceptions and missing skills. Add an integration test that runs the full pipeline against a real prompt. Polish the summary output and log format.

Demoable outcome: `pytest -m integration` runs the harness against a trivial prompt, produces `PROJECT_BRIEF.md` + completed slices in a temp directory, and the test asserts the output structure is correct. `python -m claude_multi_agent` with a missing Claude CLI or expired auth gives a clear error, not a stack trace.

## Acceptance Criteria

1. `__main__.py` — Top-level `try/except` in `main()` catches `CLINotFoundError` → prints "Claude Code CLI not found. Install and authenticate with: npm install -g @anthropic-ai/claude-code && claude login" and exits 1
2. `__main__.py` — Catches `CLIConnectionError` → prints "Claude Code CLI auth failed. Run: claude login" and exits 1
3. `__main__.py` — Catches `ProcessError` → prints error message with exit code and stderr excerpt, exits 1
4. `agents.py` — `_load_skill` failure (skill file missing) → caught in `_async_main`, prints "Required skill not found: ~/.cursor/skills/{name}/SKILL.md" and exits 1
5. `agents.py` — Reviewer JSON parse failure (`JSONDecodeError`) → logs warning with raw response to stderr, returns `ReviewResult(passed=True, feedback="")` (don't block on reviewer malfunction)
6. `log.py` — `log_event` includes `num_turns` field (from `ResultMessage.num_turns`) for max_turns tuning data
7. `__main__.py` — `print_summary` output format: slices completed, retries used, total duration, total cost (formatted as `$X.XX` or `N/A`)
8. `pyproject.toml` — pytest config with `asyncio_mode = "auto"` and `integration` marker
9. Integration test: uses `tmp_path`, runs `_async_main("Build a hello world Flask app", model, tmp_dir)`, asserts `PROJECT_BRIEF.md` exists, asserts `slices/` dir has at least one `.md` file, asserts all slice files have `status: done` frontmatter. Marked `@pytest.mark.integration`.
10. All existing unit tests still pass
11. `README.md` for the claude harness (short — requirements, usage, layout, test commands)

## Dependencies

- 02-agent-integration-sdk-skills-prompts

## Key Decisions

- Error messages are human-readable, not stack traces. The `try/except` in `main()` is the only place that catches SDK exceptions — everything else lets them propagate.
- Reviewer JSON fallback is a pass, not a fail. Rationale: a broken reviewer shouldn't block the entire pipeline. The user reviews the final diff anyway. Log the malfunction so it's visible.
- Integration test hits the real Claude Code API — no mocking. This is expensive, so it's behind `pytest -m integration` and should only run intentionally.
- `num_turns` in logs is for observability only — used to tune `max_turns` constants based on real data. Not exposed in the summary.
- Cost formatted as `$X.XX` in summary for readability. Raw float in JSON logs for machine parsing.
