---
name: subagent-driven-development
description: Use when executing any substantive task — spawn a fresh subagent with only the task's scope, not your rolling context. Prevents conversation rot.
---

# Subagent-Driven Development

## Overview
Every substantive unit of work runs in a fresh subagent. The caller hands down only the task prompt, `files_allowed`, `verify_cmd`, and necessary spec excerpts. No history leaks across tasks.

## Iron Law
```
ONE TASK = ONE FRESH SUBAGENT. NEVER REUSE A LONG-RUNNING CONTEXT FOR AN INDEPENDENT TASK.
```

## Process

1. **Identify the task.** It should have a clear `verify_cmd` and narrow `files_allowed`.
2. **Pick the agent.** From `.claude/agents/` by specialization (python-dev, react-dev, test-engineer, etc.).
3. **Compose the subagent brief.** Include:
   - Task prompt (goal, acceptance)
   - `files_allowed` (hard boundary)
   - `verify_cmd` (gate)
   - Relevant spec excerpt (NOT the whole spec)
   - Rules are injected automatically by `pre_tool_use` hook.
4. **Do NOT include:** upstream agent chatter, unrelated history, other tasks' prompts, full conversation logs.
5. **Dispatch via the `Agent` tool** (or orchestrator for plan-level runs).
6. **Await result.** Capture: final message, verify_cmd output, tool call count.
7. **If verify fails:** apply `systematic-debugging` skill — do NOT just re-prompt the same subagent. Either dispatch `verifier` (fix-cycle role) or escalate.

## Red Flags

| Thought | Reality |
|---|---|
| "I'll just keep this conversation going — saves spawn overhead." | Context rot kills quality long before spawn cost matters. |
| "Let me give it the full spec for context." | Narrow excerpts outperform full specs. More context = worse focus. |
| "The subagent failed — let me give it more history and retry." | History was not the problem. Diagnose before re-dispatching. |
| "Multiple tasks, one subagent — efficient." | That's a megasession. Split. |
| "The subagent edited outside `files_allowed`." | Hook should block. If not, surface as a hook bug — don't accept the wider diff. |

## Related skills
- `dispatching-parallel-agents` — many fresh subagents at once
- `executing-plans` — the orchestration layer above this
- `tdd` — what each subagent executes
