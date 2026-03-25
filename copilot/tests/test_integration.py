"""Integration tests — require Copilot auth. Run with: pytest -m integration"""

import os
from pathlib import Path

import pytest


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_creates_brief_and_slices(tmp_path):
    """Run the full pipeline against a simple prompt and verify outputs."""
    from copilot_multi_agent.__main__ import _async_main

    working_dir = str(tmp_path)
    summary = await _async_main(
        prompt="Build a hello world Flask app with a single / route that returns 'Hello, World!'",
        model="claude-sonnet-4.6",
        working_dir=working_dir,
    )

    brief = tmp_path / "PROJECT_BRIEF.md"
    slices_dir = tmp_path / "slices"

    assert brief.exists(), "PROJECT_BRIEF.md should be created"
    assert slices_dir.is_dir(), "slices/ directory should exist"
    slice_files = list(slices_dir.glob("*.md"))
    assert len(slice_files) >= 1, "At least one slice file should be created"
    assert summary["slices_completed"] >= 1
