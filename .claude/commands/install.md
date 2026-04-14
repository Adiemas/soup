---
description: Bootstrap the project. Three modes — deterministic (default), supervised, interactive (hil).
argument-hint: [hil]
---

# /install

## Purpose
Stand up a working dev environment — venv, deps, Postgres (docker), hooks registered, MCP server configured. Disler-style three-mode.

## Variables
- `$ARGUMENTS` — empty (deterministic), `supervised`, or `hil` (human-in-the-loop).

## Workflow
1. Mode selection:
   - (default) deterministic: run `just install` and read log.
   - `supervised`: run `just install`, then agent analyzes log.
   - `hil`: use AskUserQuestion to confirm each major step (Postgres start? .env file? MCP register?).
2. Deterministic path:
   - Execute `just install` via Bash.
   - Reads `.claude/hooks/setup.init.log`.
   - Agent summarizes: what worked, what failed, next steps.
3. Supervised/HIL path:
   - Same as deterministic, plus AskUserQuestion gates before: Postgres container start, MCP server register in user Claude Code settings, GitHub/ADO credential check (stubbed OK).
4. Artifact: `.soup/install-report.md` with Status / What worked / What failed / Next steps.

## Output
- Install report path.
- Mode used.
- Blocking issues (if any).

## Notes
- Never write secrets to the report.
- If deps install fails, do NOT retry blindly — surface error and suggest manual fix.
