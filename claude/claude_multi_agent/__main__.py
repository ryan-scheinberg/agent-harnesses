"""CLI entry point and orchestrator loop for claude_multi_agent."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

from claude_multi_agent.log import log_event
from claude_multi_agent.types import ReviewResult, Slice, SliceResult, mark_slice_done


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="claude_multi_agent",
        description="Multi-agent orchestrator for Claude",
    )
    parser.add_argument("prompt", help="The broad prompt describing what to build")
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Model override for all agents (default: claude-sonnet-4-6)",
    )
    return parser.parse_args(argv)


def discover_slices(slices_dir: Path) -> list[Slice]:
    """Read all markdown slice files from a directory, sorted by name."""
    if not slices_dir.is_dir():
        return []
    return [Slice.from_file(p) for p in sorted(slices_dir.glob("*.md"))]


def _add_cost(total: Optional[float], amount: float) -> float:
    return (total or 0.0) + amount


async def run_orchestrator(
    prompt: str,
    model: str,
    slices_dir: Path,
    *,
    generator_fn=None,
    reviewer_fn=None,
) -> dict:
    """Core orchestrator loop. Returns a summary dict.

    generator_fn(prompt, model, remaining_slices, feedback=None) -> (SliceResult, cost)
    reviewer_fn(model, slice_filename) -> (ReviewResult, cost)
    """
    if generator_fn is None:
        from claude_multi_agent.agents import run_generator as _gen
        generator_fn = _gen
    if reviewer_fn is None:
        from claude_multi_agent.agents import run_reviewer as _rev
        reviewer_fn = _rev

    total_start = time.monotonic()
    completed = 0
    retries = 0
    total_cost: Optional[float] = None

    while True:
        slices = discover_slices(slices_dir)
        remaining = [s for s in slices if not s.is_done]
        if not remaining:
            break

        t0 = time.monotonic()
        gen_result, gen_cost = await generator_fn(
            prompt=prompt,
            model=model,
            remaining_slices=remaining,
        )
        gen_duration = time.monotonic() - t0
        total_cost = _add_cost(total_cost, gen_cost)

        log_event(
            agent="generator",
            slice_name=gen_result.slice_filename,
            duration_s=round(gen_duration, 2),
            status="ok",
            cost_usd=gen_cost,
        )

        t0 = time.monotonic()
        review_result, rev_cost = await reviewer_fn(
            model=model,
            slice_filename=gen_result.slice_filename,
        )
        review_duration = time.monotonic() - t0
        total_cost = _add_cost(total_cost, rev_cost)

        if review_result.passed:
            log_event(
                agent="reviewer",
                slice_name=gen_result.slice_filename,
                duration_s=round(review_duration, 2),
                status="pass",
                cost_usd=rev_cost,
            )
        else:
            log_event(
                agent="reviewer",
                slice_name=gen_result.slice_filename,
                duration_s=round(review_duration, 2),
                status="feedback",
                cost_usd=rev_cost,
            )

            retries += 1
            t0 = time.monotonic()
            _, retry_cost = await generator_fn(
                prompt=prompt,
                model=model,
                remaining_slices=remaining,
                feedback=review_result.feedback,
            )
            retry_duration = time.monotonic() - t0
            total_cost = _add_cost(total_cost, retry_cost)

            log_event(
                agent="generator",
                slice_name=gen_result.slice_filename,
                duration_s=round(retry_duration, 2),
                status="retry",
                cost_usd=retry_cost,
            )

        slice_path = slices_dir / gen_result.slice_filename
        mark_slice_done(slice_path)
        completed += 1

    total_duration = round(time.monotonic() - total_start, 2)
    return {
        "slices_completed": completed,
        "retries": retries,
        "total_duration_s": total_duration,
        "total_cost_usd": total_cost,
    }


def print_summary(summary: dict) -> None:
    """Print final summary to stdout."""
    cost = summary["total_cost_usd"]
    cost_str = f"${cost:.2f}" if cost is not None else "N/A"

    print(f"\n=== Done ===")
    print(f"Slices completed: {summary['slices_completed']}")
    print(f"Retries used:     {summary['retries']}")
    print(f"Total duration:   {summary['total_duration_s']}s")
    print(f"Total cost:       {cost_str}")


async def _async_main(prompt: str, model: str, working_dir: str) -> dict:
    """Full pipeline: load skills → plan → build/review loop → summary."""
    from claude_multi_agent.agents import (
        _load_skill,
        run_planner,
        run_generator,
        run_reviewer,
    )

    skills = {
        "define-project": _load_skill("define-project"),
        "plan-to-jira": _load_skill("plan-to-jira"),
        "complete-ticket": _load_skill("complete-ticket"),
    }

    slices_dir = Path(working_dir) / "slices"
    total_cost: Optional[float] = None

    t0 = time.monotonic()
    planner_cost = await run_planner(
        prompt=prompt,
        model=model,
        working_dir=working_dir,
        skills=skills,
    )
    total_cost = _add_cost(total_cost, planner_cost)
    log_event(
        agent="planner",
        slice_name=None,
        duration_s=round(time.monotonic() - t0, 2),
        status="ok",
        cost_usd=planner_cost,
    )

    async def gen_fn(prompt, model, remaining_slices, feedback=None):
        return await run_generator(
            prompt=prompt,
            model=model,
            remaining_slices=remaining_slices,
            working_dir=working_dir,
            skills=skills,
            feedback=feedback,
        )

    async def rev_fn(model, slice_filename):
        return await run_reviewer(
            model=model,
            slice_filename=slice_filename,
            working_dir=working_dir,
        )

    summary = await run_orchestrator(
        prompt=prompt,
        model=model,
        slices_dir=slices_dir,
        generator_fn=gen_fn,
        reviewer_fn=rev_fn,
    )

    summary["total_cost_usd"] = _add_cost(total_cost, summary["total_cost_usd"] or 0.0)
    return summary


def main() -> None:
    args = parse_args()
    working_dir = str(Path.cwd())
    try:
        summary = asyncio.run(_async_main(args.prompt, args.model, working_dir))
    except FileNotFoundError as e:
        print(f"Required skill not found: {e}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as e:
        _handle_sdk_error(e)
    print_summary(summary)


def _handle_sdk_error(exc: Exception) -> None:
    from claude_agent_sdk import CLINotFoundError, CLIConnectionError, ProcessError

    if isinstance(exc, CLINotFoundError):
        print(
            "Claude Code CLI not found. Install and authenticate with: "
            "npm install -g @anthropic-ai/claude-code && claude login",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if isinstance(exc, CLIConnectionError):
        print("Claude Code CLI auth failed. Run: claude login", file=sys.stderr)
        raise SystemExit(1)
    if isinstance(exc, ProcessError):
        msg = f"Claude Code process failed (exit {exc.exit_code})"
        if exc.stderr:
            msg += f": {exc.stderr[:500]}"
        print(msg, file=sys.stderr)
        raise SystemExit(1)
    raise exc


if __name__ == "__main__":
    main()
