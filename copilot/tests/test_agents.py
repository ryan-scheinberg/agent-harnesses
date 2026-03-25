"""Tests for copilot_multi_agent.agents — SDK session wiring."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from copilot_multi_agent.types import Slice, SliceResult, ReviewResult
from copilot.generated.session_events import SessionEventType


# --- Client lifecycle ---

@pytest.mark.asyncio
async def test_start_client_creates_and_starts_copilot_client():
    from copilot_multi_agent.agents import start_client

    mock_client = AsyncMock()
    with patch("copilot_multi_agent.agents.CopilotClient", return_value=mock_client) as MockCls:
        client = await start_client("/some/dir")

    MockCls.assert_called_once()
    config = MockCls.call_args[0][0]
    assert config.cwd == "/some/dir"
    mock_client.start.assert_awaited_once()
    assert client is mock_client


@pytest.mark.asyncio
async def test_stop_client_calls_stop():
    from copilot_multi_agent.agents import stop_client

    mock_client = AsyncMock()
    await stop_client(mock_client)
    mock_client.stop.assert_awaited_once()


# --- Event collection (_run_session) ---

@pytest.mark.asyncio
async def test_run_session_collects_messages_and_waits_for_idle():
    """Verify the event-driven pattern: on_event collects messages, idle signals done."""
    from copilot_multi_agent.agents import _run_session

    mock_session = AsyncMock()
    # session.on() is a sync method that registers a callback
    mock_session.on = MagicMock()
    mock_client = AsyncMock()
    mock_client.create_session.return_value = mock_session

    # Capture the on_event callback when session.on() is called
    captured_handler = None

    def capture_on(handler):
        nonlocal captured_handler
        captured_handler = handler
        return lambda: None  # unsubscribe function

    mock_session.on.side_effect = capture_on

    # Make session.send trigger events via the captured handler
    async def fake_send(prompt, **kwargs):
        # Simulate assistant message then idle
        msg_event = MagicMock()
        msg_event.type = SessionEventType.ASSISTANT_MESSAGE
        msg_event.data.content = "Hello from agent"
        captured_handler(msg_event)

        idle_event = MagicMock()
        idle_event.type = SessionEventType.SESSION_IDLE
        captured_handler(idle_event)
        return "msg-id"

    mock_session.send.side_effect = fake_send

    result = await _run_session(
        mock_client,
        prompt="test prompt",
        on_permission_request=lambda r, i: None,
        model="test-model",
    )

    assert result == "Hello from agent"
    mock_session.disconnect.assert_awaited_once()
    mock_client.create_session.assert_awaited_once()


# --- Helper to build a mock client whose session fires events on send ---

def _make_mock_client(response_text: str = ""):
    """Return (mock_client, mock_session) that simulates the event-driven pattern."""
    mock_session = AsyncMock()
    mock_session.on = MagicMock()
    mock_client = AsyncMock()
    mock_client.create_session.return_value = mock_session

    captured_handler = None

    def capture_on(handler):
        nonlocal captured_handler
        captured_handler = handler
        return lambda: None

    mock_session.on.side_effect = capture_on

    async def fake_send(prompt, **kwargs):
        if response_text:
            msg = MagicMock()
            msg.type = SessionEventType.ASSISTANT_MESSAGE
            msg.data.content = response_text
            captured_handler(msg)
        idle = MagicMock()
        idle.type = SessionEventType.SESSION_IDLE
        captured_handler(idle)
        return "msg-id"

    mock_session.send.side_effect = fake_send
    return mock_client, mock_session


# --- run_planner ---

@pytest.mark.asyncio
async def test_run_planner_creates_session_with_correct_config():
    from copilot_multi_agent.agents import run_planner, PLANNER_SKILLS, PLANNER_SYSTEM_PROMPT
    from copilot import PermissionHandler

    mock_client, mock_session = _make_mock_client()

    await run_planner(
        client=mock_client,
        prompt="Build a Flask app",
        model="claude-haiku",
        working_dir="/tmp/test",
    )

    mock_client.create_session.assert_awaited_once()
    kwargs = mock_client.create_session.call_args.kwargs
    assert kwargs["model"] == "claude-haiku"
    assert kwargs["on_permission_request"] == PermissionHandler.approve_all
    assert kwargs["skill_directories"] == PLANNER_SKILLS
    assert kwargs["working_directory"] == "/tmp/test"
    assert kwargs["system_message"]["mode"] == "append"
    assert PLANNER_SYSTEM_PROMPT in kwargs["system_message"]["content"]
    mock_session.send.assert_awaited_once()
    # The prompt sent should be the user's prompt
    assert "Build a Flask app" in mock_session.send.call_args[0][0]


# --- run_generator ---

@pytest.mark.asyncio
async def test_run_generator_returns_slice_result_from_response():
    from copilot_multi_agent.agents import run_generator, GENERATOR_SKILLS, GENERATOR_SYSTEM_PROMPT
    from copilot import PermissionHandler

    mock_client, mock_session = _make_mock_client(
        response_text="I implemented the setup.\nCOMPLETED_SLICE: 01-setup.md"
    )

    slices = [
        Slice(filename="01-setup.md", title="Project Setup", body="..."),
        Slice(filename="02-models.md", title="Data Models", body="..."),
    ]

    result = await run_generator(
        client=mock_client,
        prompt="Build an app",
        model="claude-haiku",
        remaining_slices=slices,
    )

    assert isinstance(result, SliceResult)
    assert result.slice_filename == "01-setup.md"

    kwargs = mock_client.create_session.call_args.kwargs
    assert kwargs["on_permission_request"] == PermissionHandler.approve_all
    assert kwargs["skill_directories"] == GENERATOR_SKILLS
    assert kwargs["system_message"]["mode"] == "append"
    assert GENERATOR_SYSTEM_PROMPT in kwargs["system_message"]["content"]

    # Prompt includes remaining slice filenames
    sent_prompt = mock_session.send.call_args[0][0]
    assert "01-setup.md" in sent_prompt
    assert "02-models.md" in sent_prompt


@pytest.mark.asyncio
async def test_run_generator_falls_back_to_first_slice_if_no_marker():
    from copilot_multi_agent.agents import run_generator

    mock_client, _ = _make_mock_client(response_text="Done with everything.")
    slices = [Slice(filename="03-api.md", title="API", body="...")]

    result = await run_generator(
        client=mock_client,
        prompt="p",
        model="m",
        remaining_slices=slices,
    )
    assert result.slice_filename == "03-api.md"


@pytest.mark.asyncio
async def test_run_generator_includes_feedback_in_prompt():
    from copilot_multi_agent.agents import run_generator

    mock_client, mock_session = _make_mock_client(
        response_text="COMPLETED_SLICE: 01-x.md"
    )
    slices = [Slice(filename="01-x.md", title="X", body="...")]

    await run_generator(
        client=mock_client,
        prompt="p",
        model="m",
        remaining_slices=slices,
        feedback="Missing error handling in routes.py",
    )

    sent_prompt = mock_session.send.call_args[0][0]
    assert "Missing error handling in routes.py" in sent_prompt
    assert "REVIEWER FEEDBACK" in sent_prompt


# --- run_reviewer ---

@pytest.mark.asyncio
async def test_run_reviewer_returns_pass_on_empty_response():
    from copilot_multi_agent.agents import run_reviewer, REVIEWER_SYSTEM_PROMPT

    mock_client, mock_session = _make_mock_client(response_text="")

    result = await run_reviewer(
        client=mock_client,
        model="claude-haiku",
        slice_filename="01-setup.md",
    )

    assert isinstance(result, ReviewResult)
    assert result.passed is True
    assert result.feedback == ""

    kwargs = mock_client.create_session.call_args.kwargs
    assert kwargs["system_message"]["mode"] == "append"
    assert REVIEWER_SYSTEM_PROMPT in kwargs["system_message"]["content"]
    # No skill directories for reviewer
    assert "skill_directories" not in kwargs or kwargs.get("skill_directories") is None


@pytest.mark.asyncio
async def test_run_reviewer_returns_feedback_on_issues():
    from copilot_multi_agent.agents import run_reviewer

    mock_client, _ = _make_mock_client(response_text="routes.py:12 — no input validation.")

    result = await run_reviewer(
        client=mock_client,
        model="m",
        slice_filename="01-setup.md",
    )

    assert result.passed is False
    assert "no input validation" in result.feedback


# --- Reviewer permission handler ---

def test_reviewer_permission_handler_approves_reads():
    from copilot_multi_agent.agents import _reviewer_permission_handler

    req = MagicMock()
    req.kind = "read"
    result = _reviewer_permission_handler(req, {"session_id": "s1"})
    assert result.kind == "approved"


def test_reviewer_permission_handler_denies_writes():
    from copilot_multi_agent.agents import _reviewer_permission_handler

    req = MagicMock()
    req.kind = "write"
    result = _reviewer_permission_handler(req, {"session_id": "s1"})
    assert result.kind == "denied-by-rules"


def test_reviewer_permission_handler_denies_shell():
    from copilot_multi_agent.agents import _reviewer_permission_handler

    req = MagicMock()
    req.kind = "shell"
    result = _reviewer_permission_handler(req, {"session_id": "s1"})
    assert result.kind == "denied-by-rules"
