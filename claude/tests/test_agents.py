"""Tests for claude_multi_agent.agents — SDK wrappers, skill loading, agent functions."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from claude_agent_sdk import AssistantMessage, TextBlock, ResultMessage
from claude_multi_agent.types import Slice, SliceResult, ReviewResult


def _make_result_message(
    cost: float | None = 0.05,
    result: str | None = None,
    structured_output=None,
) -> ResultMessage:
    return ResultMessage(
        subtype="result",
        duration_ms=1000,
        duration_api_ms=900,
        is_error=False,
        num_turns=3,
        session_id="test-session",
        total_cost_usd=cost,
        result=result,
        structured_output=structured_output,
    )


def _make_assistant_message(text: str) -> AssistantMessage:
    return AssistantMessage(
        content=[TextBlock(text=text)],
        model="claude-sonnet-4.6",
    )


async def _fake_query_factory(text: str, cost: float = 0.05, result: str | None = None):
    """Returns an async generator that yields one AssistantMessage and one ResultMessage."""
    yield _make_assistant_message(text)
    yield _make_result_message(cost=cost, result=result)


# --- _load_skill ---

def test_load_skill_reads_file(tmp_path):
    from claude_multi_agent.agents import _load_skill

    skills_dir = tmp_path / "skills" / "test-skill"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text("# Test Skill\nDo things.")

    content = _load_skill("test-skill", skills_root=tmp_path / "skills")
    assert "# Test Skill" in content
    assert "Do things." in content


def test_load_skill_raises_on_missing():
    from claude_multi_agent.agents import _load_skill

    with pytest.raises(FileNotFoundError):
        _load_skill("nonexistent-skill", skills_root=Path("/tmp/no-such-dir"))


# --- _run_agent ---

@pytest.mark.asyncio
async def test_run_agent_collects_text_and_cost():
    from claude_multi_agent.agents import _run_agent

    async def fake_query(prompt, options):
        yield _make_assistant_message("Hello ")
        yield _make_assistant_message("World")
        yield _make_result_message(cost=0.042)

    with patch("claude_multi_agent.agents.query", fake_query):
        text, cost, result = await _run_agent("test prompt", MagicMock())

    assert text == "Hello \nWorld"
    assert cost == 0.042
    assert result is None


@pytest.mark.asyncio
async def test_run_agent_captures_result_message_result():
    from claude_multi_agent.agents import _run_agent

    async def fake_query(prompt, options):
        yield _make_assistant_message("thinking...")
        yield _make_result_message(cost=0.01, result='{"passed": true, "feedback": ""}')

    with patch("claude_multi_agent.agents.query", fake_query):
        text, cost, result = await _run_agent("test", MagicMock())

    assert result == '{"passed": true, "feedback": ""}'


@pytest.mark.asyncio
async def test_run_agent_cost_defaults_to_zero():
    from claude_multi_agent.agents import _run_agent

    async def fake_query(prompt, options):
        yield _make_assistant_message("ok")
        yield _make_result_message(cost=None)

    with patch("claude_multi_agent.agents.query", fake_query):
        _, cost, _ = await _run_agent("test", MagicMock())

    assert cost == 0.0


# --- run_planner ---

@pytest.mark.asyncio
async def test_run_planner_options_and_return():
    from claude_multi_agent.agents import run_planner

    captured_options = {}

    async def fake_query(prompt, options):
        captured_options["prompt"] = prompt
        captured_options["opts"] = options
        yield _make_assistant_message("planned")
        yield _make_result_message(cost=0.08)

    with patch("claude_multi_agent.agents.query", fake_query):
        cost = await run_planner(
            prompt="Build a thing",
            model="claude-sonnet-4.6",
            working_dir="/tmp/test",
            skills={"define-project": "dp content", "plan-to-jira": "ptj content"},
        )

    assert cost == 0.08
    opts = captured_options["opts"]
    assert opts.permission_mode == "bypassPermissions"
    assert opts.max_turns == 30
    assert str(opts.cwd) == "/tmp/test"
    assert opts.model == "claude-sonnet-4.6"
    assert "dp content" in opts.system_prompt
    assert "ptj content" in opts.system_prompt


# --- run_generator ---

@pytest.mark.asyncio
async def test_run_generator_parses_completed_slice():
    from claude_multi_agent.agents import run_generator

    async def fake_query(prompt, options):
        yield _make_assistant_message("Did the work.\nCOMPLETED_SLICE: 01-setup.md")
        yield _make_result_message(cost=0.12)

    remaining = [Slice(filename="01-setup.md", title="Setup", body="")]

    with patch("claude_multi_agent.agents.query", fake_query):
        sr, cost = await run_generator(
            prompt="Build it",
            model="claude-sonnet-4.6",
            remaining_slices=remaining,
            working_dir="/tmp/test",
            skills={"complete-ticket": "ct content"},
        )

    assert sr.slice_filename == "01-setup.md"
    assert cost == 0.12


@pytest.mark.asyncio
async def test_run_generator_fallback_to_first_remaining():
    from claude_multi_agent.agents import run_generator

    async def fake_query(prompt, options):
        yield _make_assistant_message("Done, no marker.")
        yield _make_result_message(cost=0.10)

    remaining = [
        Slice(filename="02-models.md", title="Models", body=""),
        Slice(filename="03-api.md", title="API", body=""),
    ]

    with patch("claude_multi_agent.agents.query", fake_query):
        sr, cost = await run_generator(
            prompt="Build",
            model="m",
            remaining_slices=remaining,
            working_dir="/tmp",
            skills={"complete-ticket": "ct"},
        )

    assert sr.slice_filename == "02-models.md"


@pytest.mark.asyncio
async def test_run_generator_includes_feedback_in_prompt():
    from claude_multi_agent.agents import run_generator

    captured_prompt = None

    async def fake_query(prompt, options):
        nonlocal captured_prompt
        captured_prompt = prompt
        yield _make_assistant_message("COMPLETED_SLICE: 01-a.md")
        yield _make_result_message(cost=0.05)

    remaining = [Slice(filename="01-a.md", title="A", body="")]

    with patch("claude_multi_agent.agents.query", fake_query):
        await run_generator(
            prompt="Build",
            model="m",
            remaining_slices=remaining,
            working_dir="/tmp",
            skills={"complete-ticket": "ct"},
            feedback="Missing tests for edge cases.",
        )

    assert "Missing tests for edge cases." in captured_prompt


@pytest.mark.asyncio
async def test_run_generator_options():
    from claude_multi_agent.agents import run_generator

    captured_opts = None

    async def fake_query(prompt, options):
        nonlocal captured_opts
        captured_opts = options
        yield _make_assistant_message("COMPLETED_SLICE: 01-a.md")
        yield _make_result_message(cost=0.05)

    remaining = [Slice(filename="01-a.md", title="A", body="")]

    with patch("claude_multi_agent.agents.query", fake_query):
        await run_generator(
            prompt="Build",
            model="claude-sonnet-4.6",
            remaining_slices=remaining,
            working_dir="/tmp/wd",
            skills={"complete-ticket": "ct content"},
        )

    assert captured_opts.permission_mode == "bypassPermissions"
    assert captured_opts.max_turns == 50
    assert str(captured_opts.cwd) == "/tmp/wd"
    assert "ct content" in captured_opts.system_prompt


# --- run_reviewer ---

@pytest.mark.asyncio
async def test_run_reviewer_parses_structured_json():
    from claude_multi_agent.agents import run_reviewer

    review_json = json.dumps({"passed": True, "feedback": ""})

    async def fake_query(prompt, options):
        yield _make_assistant_message("reviewing...")
        yield _make_result_message(cost=0.02, result=review_json)

    with patch("claude_multi_agent.agents.query", fake_query):
        rr, cost = await run_reviewer(
            model="claude-sonnet-4.6",
            slice_filename="01-setup.md",
            working_dir="/tmp/test",
        )

    assert rr.passed is True
    assert rr.feedback == ""
    assert rr.slice_filename == "01-setup.md"
    assert cost == 0.02


@pytest.mark.asyncio
async def test_run_reviewer_parses_failure():
    from claude_multi_agent.agents import run_reviewer

    review_json = json.dumps({"passed": False, "feedback": "No error handling."})

    async def fake_query(prompt, options):
        yield _make_assistant_message("")
        yield _make_result_message(cost=0.03, result=review_json)

    with patch("claude_multi_agent.agents.query", fake_query):
        rr, cost = await run_reviewer(
            model="m",
            slice_filename="02-api.md",
            working_dir="/tmp",
        )

    assert rr.passed is False
    assert "No error handling" in rr.feedback


@pytest.mark.asyncio
async def test_run_reviewer_fallback_on_invalid_json(capsys):
    from claude_multi_agent.agents import run_reviewer

    async def fake_query(prompt, options):
        yield _make_assistant_message("not json")
        yield _make_result_message(cost=0.01, result="not valid json {{{")

    with patch("claude_multi_agent.agents.query", fake_query):
        rr, cost = await run_reviewer(
            model="m",
            slice_filename="01-x.md",
            working_dir="/tmp",
        )

    assert rr.passed is True
    assert rr.slice_filename == "01-x.md"


@pytest.mark.asyncio
async def test_run_reviewer_fallback_on_none_result(capsys):
    from claude_multi_agent.agents import run_reviewer

    async def fake_query(prompt, options):
        yield _make_assistant_message("done")
        yield _make_result_message(cost=0.01, result=None)

    with patch("claude_multi_agent.agents.query", fake_query):
        rr, cost = await run_reviewer(
            model="m",
            slice_filename="01-x.md",
            working_dir="/tmp",
        )

    assert rr.passed is True


@pytest.mark.asyncio
async def test_run_reviewer_options():
    from claude_multi_agent.agents import run_reviewer

    captured_opts = None

    async def fake_query(prompt, options):
        nonlocal captured_opts
        captured_opts = options
        yield _make_assistant_message("")
        yield _make_result_message(cost=0.01, result='{"passed": true, "feedback": ""}')

    with patch("claude_multi_agent.agents.query", fake_query):
        await run_reviewer(
            model="claude-sonnet-4.6",
            slice_filename="01-setup.md",
            working_dir="/tmp/wd",
        )

    assert captured_opts.permission_mode == "default"
    assert captured_opts.max_turns == 10
    assert str(captured_opts.cwd) == "/tmp/wd"
    assert set(captured_opts.disallowed_tools) == {"Write", "Edit", "Bash", "NotebookEdit"}
    assert captured_opts.output_format is not None
    assert "passed" in json.dumps(captured_opts.output_format)
