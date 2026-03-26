"""Integration tests — require Claude Code auth. Run with: pytest -m integration"""

import shutil
from pathlib import Path

import pytest

from claude_multi_agent.types import Slice


EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "example-test-from-integration"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_creates_brief_and_slices(tmp_path):
    """Run the full pipeline against a simple prompt and verify outputs."""
    from claude_multi_agent.__main__ import _async_main

    working_dir = str(tmp_path)
    summary = await _async_main(
        prompt="Build a simple Flask hello world app with a single / route that returns 'Hello, World!'",
        model="claude-sonnet-4-6",
        working_dir=working_dir,
        debug=True,
    )

    brief = tmp_path / "PROJECT_BRIEF.md"
    slices_dir = tmp_path / "slices"

    assert brief.exists(), "PROJECT_BRIEF.md should be created"
    assert slices_dir.is_dir(), "slices/ directory should exist"

    slice_files = list(slices_dir.glob("*.md"))
    assert len(slice_files) >= 1, "At least one slice file should be created"

    for sf in slice_files:
        s = Slice.from_file(sf)
        assert s.is_done, f"{sf.name} should be marked done"

    assert summary["slices_completed"] >= 1
    assert summary["total_cost_usd"] is not None
    assert summary["total_cost_usd"] > 0

    # Copy outputs to example dir for reference (like copilot/example-test-from-integration/)
    if EXAMPLE_DIR.exists():
        shutil.rmtree(EXAMPLE_DIR)
    shutil.copytree(tmp_path, EXAMPLE_DIR)
