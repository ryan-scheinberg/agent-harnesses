"""Tests for copilot_multi_agent.__main__ — CLI parsing and orchestrator loop."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


# --- CLI arg parsing ---

def test_cli_parses_prompt():
    from copilot_multi_agent.__main__ import parse_args
    args = parse_args(["Build a FastAPI service"])
    assert args.prompt == "Build a FastAPI service"
    assert args.model == "claude-sonnet-4.5"


def test_cli_parses_model_override():
    from copilot_multi_agent.__main__ import parse_args
    args = parse_args(["Do something", "--model", "gpt-4o"])
    assert args.prompt == "Do something"
    assert args.model == "gpt-4o"


# --- Orchestrator loop ---

@pytest.mark.asyncio
async def test_orchestrator_completes_all_slices(tmp_path):
    """Happy path: two slices, reviewer passes both, both marked done."""
    from copilot_multi_agent.__main__ import run_orchestrator
    from copilot_multi_agent.types import Slice, SliceResult, ReviewResult

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-setup.md").write_text("# Setup\n\nDo setup.\n")
    (slices_dir / "02-models.md").write_text("# Models\n\nBuild models.\n")

    call_order = []

    async def fake_generator(prompt, model, remaining_slices, feedback=None):
        fname = remaining_slices[0].filename
        call_order.append(("gen", fname, feedback))
        return SliceResult(slice_filename=fname, summary=f"Implemented {fname}")

    async def fake_reviewer(model, slice_filename):
        call_order.append(("review", slice_filename))
        return ReviewResult(slice_filename=slice_filename, feedback="")

    summary = await run_orchestrator(
        prompt="test",
        model="test-model",
        slices_dir=slices_dir,
        generator_fn=fake_generator,
        reviewer_fn=fake_reviewer,
    )

    assert summary["slices_completed"] == 2
    assert summary["retries"] == 0

    # Both files now have done frontmatter
    for f in slices_dir.glob("*.md"):
        s = Slice.from_file(f)
        assert s.is_done, f"{f.name} should be done"

    # Call order: gen → review × 2 slices
    assert len(call_order) == 4
    assert call_order[0][0] == "gen"
    assert call_order[1][0] == "review"
    assert call_order[2][0] == "gen"
    assert call_order[3][0] == "review"


@pytest.mark.asyncio
async def test_orchestrator_retries_on_reviewer_feedback(tmp_path):
    """Reviewer gives feedback on first pass → generator retried once."""
    from copilot_multi_agent.__main__ import run_orchestrator
    from copilot_multi_agent.types import SliceResult, ReviewResult

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-api.md").write_text("# API\n\nBuild the API.\n")

    review_count = 0

    async def fake_generator(prompt, model, remaining_slices, feedback=None):
        return SliceResult(slice_filename="01-api.md", summary="done")

    async def fake_reviewer(model, slice_filename):
        nonlocal review_count
        review_count += 1
        # First review fails; shouldn't be called again (no second review)
        return ReviewResult(slice_filename=slice_filename, feedback="Missing tests.")

    summary = await run_orchestrator(
        prompt="test",
        model="m",
        slices_dir=slices_dir,
        generator_fn=fake_generator,
        reviewer_fn=fake_reviewer,
    )

    assert summary["slices_completed"] == 1
    assert summary["retries"] == 1
    # Reviewer called only once (no second review after retry)
    assert review_count == 1


@pytest.mark.asyncio
async def test_orchestrator_skips_done_slices(tmp_path):
    """Already-done slice is skipped."""
    from copilot_multi_agent.__main__ import run_orchestrator
    from copilot_multi_agent.types import SliceResult, ReviewResult

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-done.md").write_text(
        "---\nstatus: done\ncompleted_at: 2026-01-01\n---\n# Done\n\nAlready done.\n"
    )
    (slices_dir / "02-todo.md").write_text("# Todo\n\nDo this.\n")

    gen_calls = []

    async def fake_generator(prompt, model, remaining_slices, feedback=None):
        fname = remaining_slices[0].filename
        gen_calls.append(fname)
        return SliceResult(slice_filename=fname, summary="ok")

    async def fake_reviewer(model, slice_filename):
        return ReviewResult(slice_filename=slice_filename, feedback="")

    summary = await run_orchestrator(
        prompt="t",
        model="m",
        slices_dir=slices_dir,
        generator_fn=fake_generator,
        reviewer_fn=fake_reviewer,
    )

    assert summary["slices_completed"] == 1
    # Generator was only called for the undone slice
    assert gen_calls == ["02-todo.md"]


# --- Summary output ---

def test_print_summary(capsys):
    from copilot_multi_agent.__main__ import print_summary
    print_summary({"slices_completed": 3, "retries": 1, "total_duration_s": 42.5})
    out = capsys.readouterr().out
    assert "3" in out
    assert "1" in out
    assert "42.5" in out


# --- End-to-end with stubs ---

@pytest.mark.asyncio
async def test_full_run_with_stubs(tmp_path, capsys):
    """Simulates what the CLI does: discover slices, run loop, print summary."""
    from copilot_multi_agent.__main__ import run_orchestrator, print_summary
    from copilot_multi_agent.types import SliceResult, ReviewResult

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-first.md").write_text("# First\n\nFirst slice.\n")
    (slices_dir / "02-second.md").write_text("# Second\n\nSecond slice.\n")

    async def gen(prompt, model, remaining_slices, feedback=None):
        return SliceResult(
            slice_filename=remaining_slices[0].filename,
            summary="ok",
        )

    async def rev(model, slice_filename):
        return ReviewResult(slice_filename=slice_filename, feedback="")

    summary = await run_orchestrator(
        prompt="build it",
        model="test-model",
        slices_dir=slices_dir,
        generator_fn=gen,
        reviewer_fn=rev,
    )
    print_summary(summary)

    out = capsys.readouterr().out
    assert "2" in out  # 2 slices completed
    assert summary["slices_completed"] == 2
    assert summary["retries"] == 0


# --- _async_main wiring ---

@pytest.mark.asyncio
async def test_async_main_calls_planner_then_orchestrator(tmp_path):
    """Verify _async_main starts client, calls planner, runs loop, stops client."""
    from copilot_multi_agent.__main__ import _async_main
    from copilot_multi_agent.types import SliceResult, ReviewResult

    working_dir = str(tmp_path)
    slices_dir = tmp_path / "slices"

    mock_client = AsyncMock()
    call_log = []

    async def fake_start(wd):
        call_log.append("start")
        return mock_client

    async def fake_stop(c):
        call_log.append("stop")

    async def fake_planner(*, client, prompt, model, working_dir):
        call_log.append("planner")
        # Planner creates slice files
        slices_dir.mkdir(exist_ok=True)
        (slices_dir / "01-setup.md").write_text("# Setup\n\nSetup.\n")

    async def fake_generator(*, client, prompt, model, remaining_slices, feedback=None):
        call_log.append("generator")
        return SliceResult(slice_filename=remaining_slices[0].filename, summary="ok")

    async def fake_reviewer(*, client, model, slice_filename):
        call_log.append("reviewer")
        return ReviewResult(slice_filename=slice_filename, feedback="")

    with patch("copilot_multi_agent.agents.start_client", fake_start), \
         patch("copilot_multi_agent.agents.stop_client", fake_stop), \
         patch("copilot_multi_agent.agents.run_planner", fake_planner), \
         patch("copilot_multi_agent.agents.run_generator", fake_generator), \
         patch("copilot_multi_agent.agents.run_reviewer", fake_reviewer):
        summary = await _async_main("test", "model", working_dir)

    assert call_log == ["start", "planner", "generator", "reviewer", "stop"]
    assert summary["slices_completed"] == 1
