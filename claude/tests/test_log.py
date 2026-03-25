"""Tests for claude_multi_agent.log — structured JSON logging with cost_usd and num_turns."""

import json
from datetime import datetime

from claude_multi_agent.log import log_event


def test_log_event_writes_json_to_stderr(capsys):
    log_event(agent="generator", slice_name="01-setup", duration_s=12.3, status="ok")

    captured = capsys.readouterr()
    assert captured.out == ""
    data = json.loads(captured.err.strip())
    assert data["agent"] == "generator"
    assert data["slice"] == "01-setup"
    assert data["duration_s"] == 12.3
    assert data["status"] == "ok"
    assert data["cost_usd"] is None
    datetime.fromisoformat(data["ts"])


def test_log_event_with_null_slice(capsys):
    log_event(agent="planner", slice_name=None, duration_s=5.0, status="ok")

    data = json.loads(capsys.readouterr().err.strip())
    assert data["slice"] is None
    assert data["agent"] == "planner"


def test_log_event_with_cost(capsys):
    log_event(
        agent="generator",
        slice_name="02-models",
        duration_s=45.1,
        status="ok",
        cost_usd=0.089,
    )

    data = json.loads(capsys.readouterr().err.strip())
    assert data["cost_usd"] == 0.089


def test_log_event_cost_defaults_to_none(capsys):
    log_event(agent="reviewer", slice_name="01-setup", duration_s=8.2, status="pass")

    data = json.loads(capsys.readouterr().err.strip())
    assert data["cost_usd"] is None


def test_log_event_with_num_turns(capsys):
    log_event(agent="generator", slice_name="01-setup", duration_s=45.0, status="ok", num_turns=12)

    data = json.loads(capsys.readouterr().err.strip())
    assert data["num_turns"] == 12


def test_log_event_num_turns_defaults_to_none(capsys):
    log_event(agent="planner", slice_name=None, duration_s=5.0, status="ok")

    data = json.loads(capsys.readouterr().err.strip())
    assert data["num_turns"] is None
