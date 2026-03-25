---
status: done
completed_at: 2026-03-25T18:26:28.010026+00:00
---
# Tune system prompts and harden end-to-end flow

## What

Craft and iterate on the system prompts for all three agents — especially the reviewer, which is the hardest to get right. Add error handling for SDK failures, generator misreports, and edge cases. Ensure the final summary is useful.

Demoable outcome: Run the full harness against a real prompt. The planner produces well-structured slices. The generator implements them. The reviewer catches real issues (not false passes) and the retry loop fixes them. The final stdout summary shows slices completed, retries used, and total duration. Structured JSON logs on stderr tell the full story.

## Acceptance Criteria

1. Planner system prompt: instructs the agent to first write `PROJECT_BRIEF.md` using `define-project` methodology, then create numbered slice files in `slices/` using `plan-to-jira` vertical slicing. Explicitly tells the agent to write local files, not Jira tickets. Specifies the slice markdown format (title, description, acceptance criteria, key decisions)
2. Generator system prompt: instructs the agent to read remaining undone slices, pick one, implement it fully (code + tests), and report which slice filename it completed. References `complete-ticket` methodology — understand criteria, build incrementally, verify
3. Reviewer system prompt: harsh, failure-only. Instructions include: only output problems; silence means pass; no praise, no encouragement, no "looks good overall"; be specific — file, line, what's wrong, why it matters; if everything is acceptable, respond with an empty message or nothing
4. Reviewer read-only enforcement tested: verify that the reviewer session config denies write/bash tool requests. Unit test confirms the permission handler approves reads and denies writes
5. Retry flow works end-to-end: when reviewer returns non-empty feedback, generator is called again with that feedback appended to its prompt. The retry generator session is fresh (new session, not the same one)
6. Generator slice identification: orchestrator extracts which slice the generator claimed to complete from `SliceResult` and marks that specific file done. If the generator's response doesn't clearly identify a slice, log a warning and mark the first remaining slice
7. Error handling: if an agent session fails (SDK error, timeout), log the error and skip that slice rather than crashing the entire run. The orchestrator continues with remaining slices
8. Final summary to stdout includes: total slices, slices completed, slices failed, retries used, total wall-clock duration
9. End-to-end integration test: full run against a simple prompt (e.g., "Create a Python CLI that prints hello world") produces working code in the target directory

## Key Decisions

- Reviewer prompt is the highest-risk element — expect to iterate. Start with extremely harsh language and dial back only if it produces incoherent output. False passes are worse than false fails
- Generator retry gets the reviewer feedback verbatim prepended to the standard generator prompt — no summarization or filtering
- Slice identification is best-effort: generator is prompted to report the filename, orchestrator does fuzzy matching against remaining slice filenames
- SDK errors are caught at the session level — each agent call is wrapped in try/except, failures are logged and reported in the final summary
- No retry on SDK errors — only on reviewer feedback. SDK failures are logged and the slice is skipped
