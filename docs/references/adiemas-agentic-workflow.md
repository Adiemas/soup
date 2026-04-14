# Adiemas Agentic Workflow

A monorepo of Claude Code patterns by Adiemas. The relevant pieces for
soup are the hook-driven observability layer, the stack-aware rules
routing, and the JSONL/TSV logging conventions that tie everything
into a reviewable append-only trace. Relevance rating: 5/5.

- URL: https://github.com/adiemas/agentic-workflow (representative)
- Research summary: `research/01-adiemas.md`

## What we took

- Hook-as-nervous-system model: SessionStart, UserPromptSubmit,
  PreToolUse, PostToolUse, SubagentStart, Stop — each with a focused
  responsibility.
- `rules/` tree routed by file extension (.py/.cs/.ts/.tsx/.sql),
  injected into prompts by `pre_tool_use`.
- JSONL per-session log with redaction of secret-shaped values
  (`(?i)(secret|token|key|password)`).
- Stop-hook QA gate that dispatches `qa-orchestrator` with a
  parallel code-reviewer + security-scanner + verifier fan-out.
- Structured `QAReport` verdict (APPROVE / NEEDS_ATTENTION / BLOCK)
  with explicit blocking rules.
- `experiments.tsv` append-only metric table, one row per run.
- 20-agent roster topology (orchestrator, meta-prompter, architect,
  stack specialists, quality, knowledge, platform).
- `files_allowed` glob enforcement for scope-limited subagents.

Explicitly NOT copied: Adiemas's full AST graph (TDAD) — deferred to
v2 per `DESIGN.md §10`.
