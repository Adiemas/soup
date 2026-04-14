---
description: Survey the codebase for pre-planning context. Writes docs/codebase-map.md.
argument-hint: [root-path]
---

# /map-codebase

## Purpose
Produce a concise, navigable map of the current codebase so downstream planners have accurate structural context (files, modules, dependencies, entry points).

## Variables
- `$ARGUMENTS` — optional root path; defaults to repo root.

## Workflow
1. Dispatch the `researcher` agent (`.claude/agents/utility/researcher.md`, model: haiku, tools: Read/Grep/Glob only). Per its 10-search budget and findings-table contract, instruct it to:
   - Enumerate top-level dirs with one-line purpose each.
   - Identify entry points (main, CLI, server, etc.).
   - Build a module dependency sketch (import graph for Python; references for .NET).
   - List external deps per stack (pyproject.toml, package.json, .csproj).
   - Flag suspicious files (e.g., >500 lines single-responsibility violations).
2. The `researcher` writes `docs/codebase-map.md` with sections:
   - `# Codebase Map — <YYYY-MM-DD>`
   - `## Top-level layout` (tree ≤ depth 3)
   - `## Entry points`
   - `## Key modules` (name / purpose / depends on / used by)
   - `## Dependency inventory` (table per stack)
   - `## Hotspots` (files likely to be touched often or worth refactoring)
3. Invalidate by timestamp — regenerate when >7 days old.

## Output
- Path to `docs/codebase-map.md`.
- Stat summary (file count, LOC, deps).

## Notes
- Do not execute code. Static analysis only.
- Keep output under 400 lines of markdown.
