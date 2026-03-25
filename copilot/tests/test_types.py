"""Tests for copilot_multi_agent.types — Slice, SliceResult, ReviewResult."""

from pathlib import Path

from copilot_multi_agent.types import Slice, SliceResult, ReviewResult


# --- Slice dataclass construction ---

def test_slice_from_markdown_without_frontmatter():
    content = "# My Slice\n\nSome description.\n"
    s = Slice.from_markdown(content, filename="01-setup.md")
    assert s.filename == "01-setup.md"
    assert s.title == "My Slice"
    assert s.status is None
    assert s.completed_at is None
    assert "Some description." in s.body


def test_slice_from_markdown_with_done_frontmatter():
    content = (
        "---\n"
        "status: done\n"
        "completed_at: 2026-03-25T10:00:00\n"
        "---\n"
        "# Finished Slice\n\nBody text.\n"
    )
    s = Slice.from_markdown(content, filename="02-models.md")
    assert s.status == "done"
    assert s.completed_at == "2026-03-25T10:00:00"
    assert s.title == "Finished Slice"


def test_slice_is_done_property():
    done = Slice(filename="a.md", title="A", body="", status="done", completed_at="t")
    not_done = Slice(filename="b.md", title="B", body="", status=None, completed_at=None)
    assert done.is_done is True
    assert not_done.is_done is False


# --- SliceResult and ReviewResult ---

def test_slice_result_fields():
    r = SliceResult(slice_filename="01-setup.md", summary="Created project structure.")
    assert r.slice_filename == "01-setup.md"
    assert r.summary == "Created project structure."


def test_review_result_pass():
    r = ReviewResult(slice_filename="01-setup.md", feedback="")
    assert r.passed is True


def test_review_result_fail():
    r = ReviewResult(slice_filename="01-setup.md", feedback="Missing tests.")
    assert r.passed is False


# --- File I/O ---

def test_slice_from_file(tmp_path):
    p = tmp_path / "03-api.md"
    p.write_text("# API Endpoints\n\nBuild the REST API.\n")
    s = Slice.from_file(p)
    assert s.filename == "03-api.md"
    assert s.title == "API Endpoints"
    assert s.is_done is False


def test_slice_from_file_with_frontmatter(tmp_path):
    p = tmp_path / "01-done.md"
    p.write_text("---\nstatus: done\ncompleted_at: 2026-03-25T12:00:00\n---\n# Done\n\nBody.\n")
    s = Slice.from_file(p)
    assert s.is_done is True


# --- Frontmatter writing ---

def test_mark_slice_done_adds_frontmatter(tmp_path):
    from copilot_multi_agent.types import mark_slice_done
    p = tmp_path / "01-setup.md"
    p.write_text("# Setup\n\nDo the setup.\n")
    mark_slice_done(p)
    content = p.read_text()
    assert content.startswith("---\n")
    assert "status: done" in content
    assert "completed_at:" in content
    # Body is preserved
    assert "# Setup" in content
    assert "Do the setup." in content


def test_mark_slice_done_updates_existing_frontmatter(tmp_path):
    from copilot_multi_agent.types import mark_slice_done
    p = tmp_path / "02-models.md"
    p.write_text("---\nstatus: pending\n---\n# Models\n\nBuild models.\n")
    mark_slice_done(p)
    content = p.read_text()
    assert "status: done" in content
    assert "status: pending" not in content
    assert "# Models" in content
