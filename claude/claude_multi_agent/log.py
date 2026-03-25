"""Structured JSON logging to stderr."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Optional


def log_event(
    *,
    agent: str,
    slice_name: Optional[str],
    duration_s: float,
    status: str,
    cost_usd: Optional[float] = None,
    num_turns: Optional[int] = None,
) -> None:
    """Write a single structured JSON log line to stderr."""
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": agent,
        "slice": slice_name,
        "duration_s": duration_s,
        "status": status,
        "cost_usd": cost_usd,
        "num_turns": num_turns,
    }
    print(json.dumps(record), file=sys.stderr)
