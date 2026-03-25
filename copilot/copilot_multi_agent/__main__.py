"""CLI entry point and orchestrator loop for copilot_multi_agent."""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path
from typing import Optional

from copilot_multi_agent.log import log_event
from copilot_multi_agent.types import ReviewResult, Slice, SliceResult, mark_slice_done


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="copilot_multi_agent",
        description="Multi-agent orchestrator for Copilot",
    )
    parser.add_argument("prompt", help="The broad prompt describing what to build")
    parser.add_argument(
        "--model",
        default="claude-sonnet-4.5",
        help="Model override for all agents (default: claude-sonnet-4.5)",
    )
    return parser.parse_args(argv)


def discover_slices(slices_dir: Path) -> list[Slice]:
    """Read all markdown slice files from a directory, sorted by name."""
    if not slices_dir.is_dir():
        return []
    paths = sorted(slices_dir.glob("*.md"))
    return [Slice.from_file(p) for p in paths]


async def run_orchestrator(
    prompt: str,
    model: str,
    slices_dir: Path,
    *,
    generator_fn=None,
    reviewer_fn=None,
) -> dict:
    """Core orchestrator loop. Returns a summary dict.

    generator_fn and reviewer_fn are async callables injected for testing.
    When None, they import from agents.py and require a CopilotClient
    (handled by main()).
    """
    if generator_fn is None:
        from copilot_multi_agent.agents import run_generator as _gen
        generator_fn = _gen
    if reviewer_fn is None:
        from copilot_multi_agent.agents import run_reviewer as _rev
        reviewer_fn = _rev

    total_start = time.monotonic()
    completed = 0
    retries = 0

    while True:
        slices = discover_slices(slices_dir)
        remaining = [s for s in slices if not s.is_done]
        if not remaining:
            break

        # Generator picks a slice
        t0 = time.monotonic()
        gen_result: SliceResult = await generator_fn(
            prompt=prompt,
            model=model,
            remaining_slices=remaining,
        )
        gen_duration = time.monotonic() - t0

        log_event(
            agent="generator",
            slice_name=gen_result.slice_filename,
            duration_s=round(gen_duration, 2),
            status="ok",
        )

        # Reviewer checks the work
        t0 = time.monotonic()
        review_result: ReviewResult = await reviewer_fn(
            model=model,
            slice_filename=gen_result.slice_filename,
        )
        review_duration = time.monotonic() - t0

        if review_result.passed:
            log_event(
                agent="reviewer",
                slice_name=gen_result.slice_filename,
                duration_s=round(review_duration, 2),
                status="pass",
            )
        else:
            log_event(
                agent="reviewer",
                slice_name=gen_result.slice_filename,
                duration_s=round(review_duration, 2),
                status="feedback",
            )

            # One retry with feedback
            retries += 1
            t0 = time.monotonic()
            await generator_fn(
                prompt=prompt,
                model=model,
                remaining_slices=remaining,
                feedback=review_result.feedback,
            )
            retry_duration = time.monotonic() - t0

            log_event(
                agent="generator",
                slice_name=gen_result.slice_filename,
                duration_s=round(retry_duration, 2),
                status="retry",
            )

        # Mark slice done
        slice_path = slices_dir / gen_result.slice_filename
        mark_slice_done(slice_path)
        completed += 1

    total_duration = round(time.monotonic() - total_start, 2)
    return {
        "slices_completed": completed,
        "retries": retries,
        "total_duration_s": total_duration,
    }


def print_summary(summary: dict) -> None:
    """Print final summary to stdout."""
    print(f"\n=== Done ===")
    print(f"Slices completed: {summary['slices_completed']}")
    print(f"Retries used:     {summary['retries']}")
    print(f"Total duration:   {summary['total_duration_s']}s")


async def _async_main(prompt: str, model: str, working_dir: str) -> dict:
    """Full pipeline: start client → plan → build/review loop → stop client."""
    from copilot_multi_agent.agents import (
        start_client,
        stop_client,
        run_planner,
        run_generator,
        run_reviewer,
    )
    from functools import partial

    slices_dir = Path(working_dir) / "slices"
    client = await start_client(working_dir)

    try:
        # Phase 1: Planner creates PROJECT_BRIEF.md and slices/
        t0 = time.monotonic()
        await run_planner(
            client=client,
            prompt=prompt,
            model=model,
            working_dir=working_dir,
        )
        log_event(
            agent="planner",
            slice_name=None,
            duration_s=round(time.monotonic() - t0, 2),
            status="ok",
        )

        # Phase 2: Build/review loop with client-bound agent functions
        async def gen_fn(prompt, model, remaining_slices, feedback=None):
            return await run_generator(
                client=client,
                prompt=prompt,
                model=model,
                remaining_slices=remaining_slices,
                feedback=feedback,
            )

        async def rev_fn(model, slice_filename):
            return await run_reviewer(
                client=client,
                model=model,
                slice_filename=slice_filename,
            )

        summary = await run_orchestrator(
            prompt=prompt,
            model=model,
            slices_dir=slices_dir,
            generator_fn=gen_fn,
            reviewer_fn=rev_fn,
        )
        return summary
    finally:
        await stop_client(client)


def main() -> None:
    args = parse_args()
    working_dir = str(Path.cwd())
    summary = asyncio.run(_async_main(args.prompt, args.model, working_dir))
    print_summary(summary)


if __name__ == "__main__":
    main()
