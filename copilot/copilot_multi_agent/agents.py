"""Agent sessions using github-copilot-sdk."""

from __future__ import annotations

import asyncio
import os
import re
from typing import Optional

from copilot import CopilotClient, SubprocessConfig, PermissionHandler, PermissionRequest, PermissionRequestResult
from copilot.generated.session_events import SessionEvent, SessionEventType

from copilot_multi_agent.types import ReviewResult, Slice, SliceResult


# ---------------------------------------------------------------------------
# Client lifecycle
# ---------------------------------------------------------------------------

async def start_client(working_dir: str) -> CopilotClient:
    """Create and start a shared CopilotClient."""
    client = CopilotClient(SubprocessConfig(cwd=working_dir))
    await client.start()
    return client


async def stop_client(client: CopilotClient) -> None:
    """Stop the shared CopilotClient."""
    await client.stop()


# ---------------------------------------------------------------------------
# Shared event-collection helper
# ---------------------------------------------------------------------------

async def _run_session(client: CopilotClient, *, prompt: str, **session_kwargs) -> str:
    """Create a session, send a prompt, collect assistant messages, return text."""
    session = await client.create_session(**session_kwargs)

    done = asyncio.Event()
    result_text: list[str] = []

    def on_event(event: SessionEvent) -> None:
        if event.type == SessionEventType.ASSISTANT_MESSAGE:
            result_text.append(event.data.content)
        elif event.type == SessionEventType.SESSION_IDLE:
            done.set()

    session.on(on_event)
    await session.send(prompt)
    await done.wait()
    await session.disconnect()

    return "\n".join(result_text)


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """\
You are a planning agent. Your job has two phases:

PHASE 1 — PROJECT BRIEF:
Using the define-project methodology, understand the user's prompt and write \
a complete PROJECT_BRIEF.md to the working directory. Explore the cwd if there's \
existing code. The brief should cover context, scope, technical approach, and risks.

PHASE 2 — SLICE PLANNING:
Using the plan-to-jira story-slicing methodology, break the brief into vertical \
slices. Write each slice as a numbered markdown file in slices/ (e.g. \
slices/01-project-setup.md). Do NOT create Jira tickets — write local files only.

Each slice file must follow this format:
```
# <Title>

## What
<What to build — the demoable outcome>

## Acceptance Criteria
- <Testable criterion 1>
- <Testable criterion 2>

## Key Decisions
- <Constraints, interfaces, architectural decisions>
```

Execute both phases in order. Write real files to disk using your tools."""

GENERATOR_SYSTEM_PROMPT = """\
You are a generator agent. You receive a list of remaining undone slices. \
Pick the most appropriate one to implement next (usually the first/lowest-numbered).

Using the complete-ticket methodology: read the slice, understand its acceptance \
criteria, implement it using TDD where applicable, and verify your work.

After completing the work, respond with EXACTLY this format on the LAST line:
COMPLETED_SLICE: <filename>

For example: COMPLETED_SLICE: 01-project-setup.md

This line tells the orchestrator which slice you completed."""

REVIEWER_SYSTEM_PROMPT = """\
You are a code reviewer. You have READ-ONLY access — no file writes, no shell commands.

Your job: review the code changes for the slice that was just implemented. \
Look for bugs, missing tests, unmet acceptance criteria, security issues, and bad design.

RULES:
- Only report problems. If everything is acceptable, say NOTHING — output an empty response.
- Silence = pass. Empty response means the work is acceptable.
- No praise. No encouragement. No "looks good overall." ONLY issues.
- Be specific: file, line, what's wrong, why it matters.
- Be terse and harsh. Every word must convey a problem."""


# ---------------------------------------------------------------------------
# Skill directories
# ---------------------------------------------------------------------------

_SKILLS_BASE = os.path.expanduser("~/.copilot/skills")

PLANNER_SKILLS = [
    os.path.join(_SKILLS_BASE, "define-project"),
    os.path.join(_SKILLS_BASE, "plan-to-jira"),
]

GENERATOR_SKILLS = [
    os.path.join(_SKILLS_BASE, "complete-ticket"),
]


# ---------------------------------------------------------------------------
# Reviewer permission handler — read-only
# ---------------------------------------------------------------------------

def _reviewer_permission_handler(
    request: PermissionRequest, invocation: dict[str, str]
) -> PermissionRequestResult:
    """Approve reads, deny everything else."""
    if request.kind == "read":
        return PermissionRequestResult(kind="approved")
    return PermissionRequestResult(kind="denied-by-rules", message="Reviewer is read-only")


# ---------------------------------------------------------------------------
# Agent functions
# ---------------------------------------------------------------------------

_COMPLETED_SLICE_RE = re.compile(r"COMPLETED_SLICE:\s*(\S+)")


async def run_planner(
    *,
    client: CopilotClient,
    prompt: str,
    model: str,
    working_dir: str,
) -> None:
    """Run the planning agent — writes PROJECT_BRIEF.md and slices/*.md."""
    await _run_session(
        client,
        prompt=prompt,
        on_permission_request=PermissionHandler.approve_all,
        model=model,
        system_message={"mode": "append", "content": PLANNER_SYSTEM_PROMPT},
        skill_directories=PLANNER_SKILLS,
        working_directory=working_dir,
    )


async def run_generator(
    *,
    client: CopilotClient,
    prompt: str,
    model: str,
    remaining_slices: list[Slice],
    feedback: Optional[str] = None,
) -> SliceResult:
    """Run the generator agent — implements one slice, returns SliceResult."""
    slice_list = "\n".join(
        f"- {s.filename}: {s.title}" for s in remaining_slices
    )

    user_prompt = f"""Original prompt: {prompt}

Remaining undone slices:
{slice_list}

Pick the most appropriate slice and implement it."""

    if feedback:
        user_prompt += f"\n\nREVIEWER FEEDBACK from previous attempt:\n{feedback}"

    response = await _run_session(
        client,
        prompt=user_prompt,
        on_permission_request=PermissionHandler.approve_all,
        model=model,
        system_message={"mode": "append", "content": GENERATOR_SYSTEM_PROMPT},
        skill_directories=GENERATOR_SKILLS,
    )

    # Extract which slice was completed from the response
    match = _COMPLETED_SLICE_RE.search(response)
    if match:
        chosen = match.group(1)
    else:
        # Fallback: assume first remaining slice
        chosen = remaining_slices[0].filename

    return SliceResult(slice_filename=chosen, summary=response[-500:] if response else "")


async def run_reviewer(
    *,
    client: CopilotClient,
    model: str,
    slice_filename: str,
) -> ReviewResult:
    """Run the reviewer agent — read-only review, returns ReviewResult."""
    user_prompt = (
        f"Review the implementation of slice: {slice_filename}\n"
        "Read the slice file for its acceptance criteria, then review the code. "
        "Only report problems. If acceptable, say nothing."
    )

    response = await _run_session(
        client,
        prompt=user_prompt,
        on_permission_request=_reviewer_permission_handler,
        model=model,
        system_message={"mode": "append", "content": REVIEWER_SYSTEM_PROMPT},
    )

    return ReviewResult(slice_filename=slice_filename, feedback=response.strip())
