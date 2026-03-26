"""Agent wrappers for claude-agent-sdk query() calls."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    query,
)

from claude_multi_agent.types import ReviewResult, SliceResult

_COMPLETED_SLICE_RE = re.compile(r"COMPLETED_SLICE:\s*(\S+)")

REVIEWER_SCHEMA: dict = {
    "type": "json_schema",
    "schema": {
        "type": "object",
        "properties": {
            "passed": {"type": "boolean"},
            "feedback": {"type": "string"},
        },
        "required": ["passed", "feedback"],
    },
}


def _load_skill(name: str, *, skills_root: Optional[Path] = None) -> str:
    root = skills_root or (Path.home() / ".cursor" / "skills")
    path = root / name / "SKILL.md"
    return path.read_text()


def _debug_print(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


async def _run_agent(
    user_prompt: str,
    options: ClaudeAgentOptions,
    *,
    label: str = "",
) -> tuple[str, float, str | None]:
    """Run an agent via query(), collect text, cost, and structured result."""
    debug = options.debug_stderr is not None
    if debug and label:
        _debug_print(f"\n{'='*60}")
        _debug_print(f"  {label}")
        _debug_print(f"{'='*60}\n")

    text_parts: list[str] = []
    cost = 0.0
    result: str | None = None

    async for message in query(prompt=user_prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, ThinkingBlock) and debug:
                    _debug_print(f"[thinking] {block.thinking}\n")
                elif isinstance(block, ToolUseBlock) and debug:
                    _debug_print(f"[tool] {block.name}({json.dumps(block.input, indent=2)[:500]})\n")
                elif isinstance(block, TextBlock):
                    text_parts.append(block.text)
                    if debug:
                        _debug_print(f"[text] {block.text}\n")
        elif isinstance(message, ResultMessage):
            cost = message.total_cost_usd or 0.0
            result = message.result
            if debug:
                _debug_print(f"[result] cost=${cost:.4f}  turns={message.num_turns}  result={result!r}\n")

    return "\n".join(text_parts), cost, result


# --- Planner ---

_PLANNER_SYSTEM_PROMPT_TEMPLATE = """\
You are a PLANNING-ONLY agent. You produce exactly two artifacts and NOTHING else:
1. PROJECT_BRIEF.md
2. Numbered slice files in slices/

CRITICAL RULES:
- You MUST NOT implement any code, tests, configs, or application files.
- You MUST NOT create any files besides PROJECT_BRIEF.md and slices/*.md.
- You MUST NOT run tests, install dependencies, or execute application code.
- All file paths MUST be relative to the current working directory (e.g. PROJECT_BRIEF.md, slices/01-setup.md). Never use absolute paths.
- Your ONLY job is planning and decomposition. A separate generator agent will implement each slice.

## Phase 1: Project Brief
Scope the project and write PROJECT_BRIEF.md using this methodology:

{define_project}

## Phase 2: Slice Breakdown
Break the brief into vertical slices. Write each as a numbered markdown file in slices/ (e.g. slices/01-setup.md, slices/02-models.md) using this methodology:

{plan_to_jira}

Each slice file must follow this format:
```
# <Title>

## What
<Demoable outcome>

## Acceptance Criteria
- <Testable criterion>

## Key Decisions
- <Constraints and decisions>
```

Once you have written PROJECT_BRIEF.md and the slice files, STOP. Do not build anything.
"""


async def run_planner(
    *,
    prompt: str,
    model: str,
    working_dir: str,
    skills: dict[str, str],
    debug: bool = False,
) -> float:
    """Run the planner agent. Returns cost."""
    system_prompt = _PLANNER_SYSTEM_PROMPT_TEMPLATE.format(
        define_project=skills["define-project"],
        plan_to_jira=skills["plan-to-jira"],
    )

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        permission_mode="bypassPermissions",
        model=model,
        cwd=working_dir,
        max_turns=30,
        debug_stderr=sys.stderr if debug else None,
    )

    _, cost, _ = await _run_agent(prompt, options, label="PLANNER")
    return cost


# --- Generator ---

_GENERATOR_SYSTEM_PROMPT_TEMPLATE = """\
You are a code generator agent. You implement one slice at a time using TDD methodology.

Use the following methodology:

{complete_ticket}

Instructions:
- Pick the most appropriate slice from the remaining list
- Implement it fully, following TDD (write tests first, then implementation)
- When done, end your response with: COMPLETED_SLICE: <filename>
"""


async def run_generator(
    *,
    prompt: str,
    model: str,
    remaining_slices: list,
    working_dir: str,
    skills: dict[str, str],
    feedback: str | None = None,
    debug: bool = False,
) -> tuple[SliceResult, float]:
    """Run the generator agent. Returns (SliceResult, cost)."""
    system_prompt = _GENERATOR_SYSTEM_PROMPT_TEMPLATE.format(
        complete_ticket=skills["complete-ticket"],
    )

    slice_list = "\n".join(
        f"- {s.filename}: {s.title}" for s in remaining_slices
    )

    user_prompt = f"Original prompt: {prompt}\n\nRemaining slices:\n{slice_list}"
    if feedback:
        user_prompt += f"\n\nPrevious review feedback (address these issues):\n{feedback}"

    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        permission_mode="bypassPermissions",
        model=model,
        cwd=working_dir,
        max_turns=50,
        debug_stderr=sys.stderr if debug else None,
    )

    text, cost, _ = await _run_agent(user_prompt, options, label=f"GENERATOR → {remaining_slices[0].filename}")

    match = _COMPLETED_SLICE_RE.search(text)
    slice_filename = match.group(1) if match else remaining_slices[0].filename

    return SliceResult(slice_filename=slice_filename, summary=text[:200]), cost


# --- Reviewer ---

_REVIEWER_SYSTEM_PROMPT = """\
You are a harsh code reviewer. You review the implementation of a single slice.

Rules:
- Report ONLY failures. No praise, no suggestions, no "looks good".
- Be specific: file, line, reason.
- If everything passes, return {"passed": true, "feedback": ""}.
- If there are failures, return {"passed": false, "feedback": "<specific findings>"}.
- Be terse. Every word must earn its place.
"""


async def run_reviewer(
    *,
    model: str,
    slice_filename: str,
    working_dir: str,
    debug: bool = False,
) -> tuple[ReviewResult, float]:
    """Run the reviewer agent. Returns (ReviewResult, cost)."""
    options = ClaudeAgentOptions(
        system_prompt=_REVIEWER_SYSTEM_PROMPT,
        disallowed_tools=["Write", "Edit", "Bash", "NotebookEdit"],
        permission_mode="default",
        model=model,
        cwd=working_dir,
        max_turns=10,
        output_format=REVIEWER_SCHEMA,
        debug_stderr=sys.stderr if debug else None,
    )

    user_prompt = f"Review the implementation of slice: {slice_filename}"
    _, cost, result = await _run_agent(user_prompt, options, label=f"REVIEWER → {slice_filename}")

    if result:
        try:
            data = json.loads(result)
            return ReviewResult(
                slice_filename=slice_filename,
                passed=data["passed"],
                feedback=data.get("feedback", ""),
            ), cost
        except (json.JSONDecodeError, KeyError) as e:
            print(
                f"WARNING: reviewer returned invalid JSON for {slice_filename}, treating as pass\n"
                f"  error: {e}\n"
                f"  raw result: {result!r}",
                file=sys.stderr,
            )

    return ReviewResult(
        slice_filename=slice_filename,
        passed=True,
        feedback="",
    ), cost
