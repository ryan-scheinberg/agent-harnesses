"""Tests for claude_multi_agent.__main__ — CLI, discover_slices, orchestrator, summary."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_multi_agent.types import Slice, SliceResult, ReviewResult


# --- CLI arg parsing ---

def test_cli_parses_prompt():
    from claude_multi_agent.__main__ import parse_args

    args = parse_args(["Build a FastAPI service"])
    assert args.prompt == "Build a FastAPI service"
    assert args.model == "claude-sonnet-4-6"


def test_cli_parses_model_override():
    from claude_multi_agent.__main__ import parse_args

    args = parse_args(["Do something", "--model", "claude-opus-4"])
    assert args.prompt == "Do something"
    assert args.model == "claude-opus-4"


# --- discover_slices ---

def test_discover_slices_returns_sorted_list(tmp_path):
    from claude_multi_agent.__main__ import discover_slices

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "02-models.md").write_text("# Models\n")
    (slices_dir / "01-setup.md").write_text("# Setup\n")
    (slices_dir / "03-api.md").write_text("# API\n")

    result = discover_slices(slices_dir)
    assert len(result) == 3
    assert [s.filename for s in result] == ["01-setup.md", "02-models.md", "03-api.md"]


def test_discover_slices_empty_when_no_dir(tmp_path):
    from claude_multi_agent.__main__ import discover_slices

    result = discover_slices(tmp_path / "nonexistent")
    assert result == []


def test_discover_slices_ignores_non_md_files(tmp_path):
    from claude_multi_agent.__main__ import discover_slices

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-setup.md").write_text("# Setup\n")
    (slices_dir / "notes.txt").write_text("not a slice")

    result = discover_slices(slices_dir)
    assert len(result) == 1
    assert result[0].filename == "01-setup.md"


# --- Orchestrator loop ---

@pytest.mark.asyncio
async def test_orchestrator_completes_all_slices(tmp_path):
    from claude_multi_agent.__main__ import run_orchestrator

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-setup.md").write_text("# Setup\n\nDo setup.\n")
    (slices_dir / "02-models.md").write_text("# Models\n\nBuild models.\n")

    call_order = []

    async def fake_gen(prompt, model, remaining_slices, feedback=None):
        fname = remaining_slices[0].filename
        call_order.append(("gen", fname, feedback))
        return SliceResult(slice_filename=fname, summary=f"Implemented {fname}"), 0.05

    async def fake_rev(model, slice_filename):
        call_order.append(("review", slice_filename))
        return ReviewResult(slice_filename=slice_filename, passed=True, feedback=""), 0.02

    summary = await run_orchestrator(
        prompt="test",
        model="test-model",
        slices_dir=slices_dir,
        generator_fn=fake_gen,
        reviewer_fn=fake_rev,
    )

    assert summary["slices_completed"] == 2
    assert summary["retries"] == 0
    for f in slices_dir.glob("*.md"):
        assert Slice.from_file(f).is_done

    assert len(call_order) == 4
    assert call_order[0][0] == "gen"
    assert call_order[1][0] == "review"
    assert call_order[2][0] == "gen"
    assert call_order[3][0] == "review"


@pytest.mark.asyncio
async def test_orchestrator_retries_on_reviewer_failure(tmp_path):
    from claude_multi_agent.__main__ import run_orchestrator

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-api.md").write_text("# API\n\nBuild the API.\n")

    review_count = 0

    async def fake_gen(prompt, model, remaining_slices, feedback=None):
        return SliceResult(slice_filename="01-api.md", summary="done"), 0.10

    async def fake_rev(model, slice_filename):
        nonlocal review_count
        review_count += 1
        return ReviewResult(slice_filename=slice_filename, passed=False, feedback="Missing tests."), 0.02

    summary = await run_orchestrator(
        prompt="test",
        model="m",
        slices_dir=slices_dir,
        generator_fn=fake_gen,
        reviewer_fn=fake_rev,
    )

    assert summary["slices_completed"] == 1
    assert summary["retries"] == 1
    assert review_count == 1


@pytest.mark.asyncio
async def test_orchestrator_skips_done_slices(tmp_path):
    from claude_multi_agent.__main__ import run_orchestrator

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-done.md").write_text(
        "---\nstatus: done\ncompleted_at: 2026-01-01\n---\n# Done\n\nAlready done.\n"
    )
    (slices_dir / "02-todo.md").write_text("# Todo\n\nDo this.\n")

    gen_calls = []

    async def fake_gen(prompt, model, remaining_slices, feedback=None):
        fname = remaining_slices[0].filename
        gen_calls.append(fname)
        return SliceResult(slice_filename=fname, summary="ok"), 0.05

    async def fake_rev(model, slice_filename):
        return ReviewResult(slice_filename=slice_filename, passed=True, feedback=""), 0.02

    summary = await run_orchestrator(
        prompt="t",
        model="m",
        slices_dir=slices_dir,
        generator_fn=fake_gen,
        reviewer_fn=fake_rev,
    )

    assert summary["slices_completed"] == 1
    assert gen_calls == ["02-todo.md"]


@pytest.mark.asyncio
async def test_orchestrator_accumulates_cost(tmp_path):
    """cost from generator and reviewer calls are summed."""
    from claude_multi_agent.__main__ import run_orchestrator

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-setup.md").write_text("# Setup\n")

    async def fake_gen(prompt, model, remaining_slices, feedback=None):
        return SliceResult(slice_filename="01-setup.md", summary="ok"), 0.10

    async def fake_rev(model, slice_filename):
        return ReviewResult(slice_filename=slice_filename, passed=True, feedback=""), 0.03

    summary = await run_orchestrator(
        prompt="t",
        model="m",
        slices_dir=slices_dir,
        generator_fn=fake_gen,
        reviewer_fn=fake_rev,
    )

    assert summary["total_cost_usd"] == pytest.approx(0.13, abs=0.001)


@pytest.mark.asyncio
async def test_orchestrator_accumulates_cost_with_retry(tmp_path):
    from claude_multi_agent.__main__ import run_orchestrator

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-setup.md").write_text("# Setup\n")

    async def fake_gen(prompt, model, remaining_slices, feedback=None):
        return SliceResult(slice_filename="01-setup.md", summary="ok"), 0.10

    async def fake_rev(model, slice_filename):
        return ReviewResult(slice_filename=slice_filename, passed=False, feedback="bad"), 0.03

    summary = await run_orchestrator(
        prompt="t",
        model="m",
        slices_dir=slices_dir,
        generator_fn=fake_gen,
        reviewer_fn=fake_rev,
    )

    # gen(0.10) + rev(0.03) + retry gen(0.10) = 0.23
    assert summary["total_cost_usd"] == pytest.approx(0.23, abs=0.001)


@pytest.mark.asyncio
async def test_orchestrator_no_slices_returns_immediately(tmp_path):
    from claude_multi_agent.__main__ import run_orchestrator

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()

    summary = await run_orchestrator(
        prompt="t",
        model="m",
        slices_dir=slices_dir,
        generator_fn=None,
        reviewer_fn=None,
    )

    assert summary["slices_completed"] == 0
    assert summary["retries"] == 0
    assert summary["total_cost_usd"] is None


# --- print_summary ---

def test_print_summary_with_cost(capsys):
    from claude_multi_agent.__main__ import print_summary

    print_summary({
        "slices_completed": 3,
        "retries": 1,
        "total_duration_s": 42.5,
        "total_cost_usd": 0.146,
    })
    out = capsys.readouterr().out
    assert "3" in out
    assert "1" in out
    assert "42.5" in out
    assert "0.15" in out or "0.146" in out


def test_print_summary_without_cost(capsys):
    from claude_multi_agent.__main__ import print_summary

    print_summary({
        "slices_completed": 2,
        "retries": 0,
        "total_duration_s": 10.0,
        "total_cost_usd": None,
    })
    out = capsys.readouterr().out
    assert "N/A" in out


# --- Full run with stubs ---

@pytest.mark.asyncio
async def test_full_run_with_stubs(tmp_path, capsys):
    from claude_multi_agent.__main__ import run_orchestrator, print_summary

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-first.md").write_text("# First\n\nFirst slice.\n")
    (slices_dir / "02-second.md").write_text("# Second\n\nSecond slice.\n")

    async def gen(prompt, model, remaining_slices, feedback=None):
        return SliceResult(slice_filename=remaining_slices[0].filename, summary="ok"), 0.05

    async def rev(model, slice_filename):
        return ReviewResult(slice_filename=slice_filename, passed=True, feedback=""), 0.02

    summary = await run_orchestrator(
        prompt="build it",
        model="test-model",
        slices_dir=slices_dir,
        generator_fn=gen,
        reviewer_fn=rev,
    )
    print_summary(summary)

    out = capsys.readouterr().out
    assert "2" in out
    assert summary["slices_completed"] == 2
    assert summary["retries"] == 0


# --- E2E smoke ---

@pytest.mark.asyncio
async def test_e2e_cli_to_summary(tmp_path, capsys):
    """Full CLI-to-summary path with stubs and pre-placed slice files."""
    from claude_multi_agent.__main__ import parse_args, discover_slices, run_orchestrator, print_summary

    slices_dir = tmp_path / "slices"
    slices_dir.mkdir()
    (slices_dir / "01-setup.md").write_text("# Setup\n\nScaffold the project.\n")
    (slices_dir / "02-api.md").write_text("# API\n\nBuild REST endpoints.\n")

    args = parse_args(["anything"])
    assert args.prompt == "anything"
    assert args.model == "claude-sonnet-4-6"

    initial = discover_slices(slices_dir)
    assert len(initial) == 2
    assert all(not s.is_done for s in initial)

    async def gen(prompt, model, remaining_slices, feedback=None):
        return SliceResult(slice_filename=remaining_slices[0].filename, summary="ok"), 0.05

    async def rev(model, slice_filename):
        return ReviewResult(slice_filename=slice_filename, passed=True, feedback=""), 0.02

    summary = await run_orchestrator(
        prompt=args.prompt,
        model=args.model,
        slices_dir=slices_dir,
        generator_fn=gen,
        reviewer_fn=rev,
    )

    assert summary["slices_completed"] == 2
    assert summary["retries"] == 0
    assert "total_duration_s" in summary
    assert summary["total_cost_usd"] is not None

    final = discover_slices(slices_dir)
    assert all(s.is_done for s in final)

    print_summary(summary)
    out = capsys.readouterr().out
    assert "Done" in out
    assert "2" in out


# --- _async_main wiring ---

@pytest.mark.asyncio
async def test_async_main_calls_planner_then_orchestrator(tmp_path):
    """Verify _async_main loads skills, calls planner, runs loop, prints summary."""
    from claude_multi_agent.__main__ import _async_main

    working_dir = str(tmp_path)
    slices_dir = tmp_path / "slices"
    call_log = []

    async def fake_planner(*, prompt, model, working_dir, skills, debug=False):
        call_log.append("planner")
        slices_dir.mkdir(exist_ok=True)
        (slices_dir / "01-setup.md").write_text("# Setup\n\nSetup.\n")
        return 0.08

    async def fake_generator(*, prompt, model, remaining_slices, working_dir, skills, feedback=None, debug=False):
        call_log.append("generator")
        return SliceResult(slice_filename=remaining_slices[0].filename, summary="ok"), 0.12

    async def fake_reviewer(*, model, slice_filename, working_dir, debug=False):
        call_log.append("reviewer")
        return ReviewResult(slice_filename=slice_filename, passed=True, feedback=""), 0.03

    def fake_load_skill(name, *, skills_root=None):
        return f"skill content for {name}"

    with patch("claude_multi_agent.agents.run_planner", fake_planner), \
         patch("claude_multi_agent.agents.run_generator", fake_generator), \
         patch("claude_multi_agent.agents.run_reviewer", fake_reviewer), \
         patch("claude_multi_agent.agents._load_skill", fake_load_skill):
        summary = await _async_main("test prompt", "claude-sonnet-4.6", working_dir)

    assert call_log == ["planner", "generator", "reviewer"]
    assert summary["slices_completed"] == 1
    assert summary["total_cost_usd"] == pytest.approx(0.23, abs=0.01)


# --- Error handling in main() ---

def test_main_catches_cli_not_found(capsys):
    from claude_multi_agent.__main__ import main
    from claude_agent_sdk import CLINotFoundError

    with patch("claude_multi_agent.__main__._async_main", side_effect=CLINotFoundError("not found")), \
         patch("claude_multi_agent.__main__.parse_args", return_value=type("Args", (), {"prompt": "x", "model": "m", "debug": False})()), \
         pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "Claude Code CLI not found" in err


def test_main_catches_cli_connection_error(capsys):
    from claude_multi_agent.__main__ import main
    from claude_agent_sdk import CLIConnectionError

    with patch("claude_multi_agent.__main__._async_main", side_effect=CLIConnectionError("auth expired")), \
         patch("claude_multi_agent.__main__.parse_args", return_value=type("Args", (), {"prompt": "x", "model": "m", "debug": False})()), \
         pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "auth" in err.lower()


def test_main_catches_process_error(capsys):
    from claude_multi_agent.__main__ import main
    from claude_agent_sdk import ProcessError

    with patch("claude_multi_agent.__main__._async_main", side_effect=ProcessError("boom", exit_code=1, stderr="some error")), \
         patch("claude_multi_agent.__main__.parse_args", return_value=type("Args", (), {"prompt": "x", "model": "m", "debug": False})()), \
         pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "some error" in err


def test_main_catches_missing_skill(capsys):
    from claude_multi_agent.__main__ import main

    with patch("claude_multi_agent.__main__._async_main", side_effect=FileNotFoundError("~/.cursor/skills/define-project/SKILL.md")), \
         patch("claude_multi_agent.__main__.parse_args", return_value=type("Args", (), {"prompt": "x", "model": "m", "debug": False})()), \
         pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert "skill" in err.lower() or "SKILL.md" in err
