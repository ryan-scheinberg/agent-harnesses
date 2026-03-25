"""Tests for copilot_multi_agent.log — structured JSON logging."""

import json
from datetime import datetime


def test_log_event_writes_json_to_stderr(capsys):
    from copilot_multi_agent.log import log_event

    log_event(agent="generator", slice_name="01-setup", duration_s=12.3, status="ok")

    captured = capsys.readouterr()
    assert captured.out == ""  # nothing on stdout
    line = captured.err.strip()
    data = json.loads(line)
    assert data["agent"] == "generator"
    assert data["slice"] == "01-setup"
    assert data["duration_s"] == 12.3
    assert data["status"] == "ok"
    # ts is ISO 8601
    datetime.fromisoformat(data["ts"])


def test_log_event_with_null_slice(capsys):
    from copilot_multi_agent.log import log_event

    log_event(agent="planner", slice_name=None, duration_s=5.0, status="ok")

    data = json.loads(capsys.readouterr().err.strip())
    assert data["slice"] is None
    assert data["agent"] == "planner"
