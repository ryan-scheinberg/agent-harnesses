"""Tests for claude_multi_agent.types — Slice, SliceResult, ReviewResult, mark_slice_done."""

from claude_multi_agent.types import Slice, SliceResult, ReviewResult, mark_slice_done


# --- Slice.from_markdown ---

def test_from_markdown_extracts_title_and_body():
    content = "# My Slice\n\nSome description.\n"
    s = Slice.from_markdown(content, filename="01-setup.md")
    assert s.filename == "01-setup.md"
    assert s.title == "My Slice"
    assert s.status is None
    assert s.completed_at is None
    assert "Some description." in s.body


def test_from_markdown_parses_done_frontmatter():
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
    assert "Body text." in s.body


def test_from_markdown_uses_filename_when_no_heading():
    content = "No heading here, just text.\n"
    s = Slice.from_markdown(content, filename="03-orphan.md")
    assert s.title == "03-orphan.md"


# --- Slice.is_done ---

def test_is_done_true_when_status_done():
    s = Slice(filename="a.md", title="A", body="", status="done", completed_at="t")
    assert s.is_done is True


def test_is_done_false_when_no_status():
    s = Slice(filename="b.md", title="B", body="", status=None)
    assert s.is_done is False


def test_is_done_false_when_status_pending():
    s = Slice(filename="c.md", title="C", body="", status="pending")
    assert s.is_done is False


# --- Slice.from_file ---

def test_from_file_reads_and_parses(tmp_path):
    p = tmp_path / "03-api.md"
    p.write_text("# API Endpoints\n\nBuild the REST API.\n")
    s = Slice.from_file(p)
    assert s.filename == "03-api.md"
    assert s.title == "API Endpoints"
    assert s.is_done is False


def test_from_file_with_frontmatter(tmp_path):
    p = tmp_path / "01-done.md"
    p.write_text("---\nstatus: done\ncompleted_at: 2026-03-25T12:00:00\n---\n# Done\n\nBody.\n")
    s = Slice.from_file(p)
    assert s.is_done is True
    assert s.completed_at == "2026-03-25T12:00:00"


# --- SliceResult ---

def test_slice_result_fields():
    r = SliceResult(slice_filename="01-setup.md", summary="Created project structure.")
    assert r.slice_filename == "01-setup.md"
    assert r.summary == "Created project structure."


# --- ReviewResult (explicit passed field) ---

def test_review_result_passed_true():
    r = ReviewResult(slice_filename="01-setup.md", passed=True, feedback="")
    assert r.passed is True


def test_review_result_passed_false():
    r = ReviewResult(slice_filename="01-setup.md", passed=False, feedback="Missing tests.")
    assert r.passed is False
    assert r.feedback == "Missing tests."


def test_review_result_passed_is_explicit_not_derived():
    """passed=True with non-empty feedback is valid — the bool is the gate."""
    r = ReviewResult(slice_filename="x.md", passed=True, feedback="Minor nits, but fine.")
    assert r.passed is True


# --- mark_slice_done ---

def test_mark_slice_done_adds_frontmatter(tmp_path):
    p = tmp_path / "01-setup.md"
    p.write_text("# Setup\n\nDo the setup.\n")
    mark_slice_done(p)
    content = p.read_text()
    assert content.startswith("---\n")
    assert "status: done" in content
    assert "completed_at:" in content
    assert "# Setup" in content
    assert "Do the setup." in content


def test_mark_slice_done_updates_existing_frontmatter(tmp_path):
    p = tmp_path / "02-models.md"
    p.write_text("---\nstatus: pending\n---\n# Models\n\nBuild models.\n")
    mark_slice_done(p)
    content = p.read_text()
    assert "status: done" in content
    assert "status: pending" not in content
    assert "# Models" in content


def test_mark_slice_done_timestamp_is_iso8601(tmp_path):
    from datetime import datetime

    p = tmp_path / "03-ts.md"
    p.write_text("# TS Test\n")
    mark_slice_done(p)
    content = p.read_text()
    for line in content.splitlines():
        if line.strip().startswith("completed_at:"):
            ts = line.split(":", 1)[1].strip()
            datetime.fromisoformat(ts)
            break
    else:
        raise AssertionError("No completed_at found")
