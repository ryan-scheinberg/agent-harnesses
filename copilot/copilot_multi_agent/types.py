"""Core data types for copilot_multi_agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


@dataclass
class Slice:
    filename: str
    title: str
    body: str
    status: Optional[str] = None
    completed_at: Optional[str] = None

    @property
    def is_done(self) -> bool:
        return self.status == "done"

    @classmethod
    def from_markdown(cls, content: str, filename: str) -> Slice:
        status = None
        completed_at = None
        body = content

        fm_match = _FRONTMATTER_RE.match(content)
        if fm_match:
            for line in fm_match.group(1).splitlines():
                key, _, value = line.partition(":")
                key, value = key.strip(), value.strip()
                if key == "status":
                    status = value
                elif key == "completed_at":
                    completed_at = value
            body = content[fm_match.end():]

        title_match = _TITLE_RE.search(body)
        title = title_match.group(1) if title_match else filename

        return cls(
            filename=filename,
            title=title,
            body=body,
            status=status,
            completed_at=completed_at,
        )

    @classmethod
    def from_file(cls, path: Path) -> Slice:
        content = path.read_text()
        return cls.from_markdown(content, filename=path.name)


@dataclass
class SliceResult:
    slice_filename: str
    summary: str


@dataclass
class ReviewResult:
    slice_filename: str
    feedback: str

    @property
    def passed(self) -> bool:
        return not self.feedback.strip()


def mark_slice_done(path: Path) -> None:
    """Prepend or update YAML frontmatter on a slice file to mark it done."""
    content = path.read_text()
    now = datetime.now(timezone.utc).isoformat()
    new_fm = f"---\nstatus: done\ncompleted_at: {now}\n---\n"

    fm_match = _FRONTMATTER_RE.match(content)
    if fm_match:
        body = content[fm_match.end():]
    else:
        body = content

    path.write_text(new_fm + body)
