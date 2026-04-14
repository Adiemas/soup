---
name: cli-wrapper-authoring
description: Use when exposing a new external CLI tool (az, psql, docker, dotnet, gh, git, etc.) to soup agents. Follows the CLI-Anything 7-phase pattern producing a JSON-first wrapper.
---

# CLI Wrapper Authoring

## Overview
Soup agents interact with external tools (Azure DevOps, Postgres, Docker, .NET, GitHub, Git) through thin wrappers in `cli_wrappers/`. Each wrapper produces stable JSON on stdout so agent outputs are parseable. This skill encodes the CLI-Anything 7-phase method for authoring one.

## Iron Law
```
EVERY WRAPPER EMITS STABLE JSON TO STDOUT AND A NON-ZERO EXIT ON FAILURE. NO INTERACTIVE PROMPTS.
```

## Process

### Phase 1 — Survey
1. Read the target tool's help (`<tool> --help`, `man <tool>`) and docs. Identify subcommands you actually need.

### Phase 2 — Map
2. List the soup capabilities needed (e.g., "list PRs", "create work item"). One wrapper subcommand per capability.

### Phase 3 — Design
3. Design the wrapper CLI: `<tool>-wrapper <verb> [flags]`. Flags map to tool flags; add `--json` default. Prefer POSIX-style flags.

### Phase 4 — Implement
4. Write the wrapper as a small Python or bash script. Shell out to the real tool; capture stdout/stderr separately; post-process into JSON if the tool doesn't output JSON natively.

### Phase 5 — Test
5. Write tests (real invocations where safe; mocked otherwise). Cover: happy path, known error (auth failure), empty result, bad flag.

### Phase 6 — Document
6. Add a `README.md` in the wrapper's directory: capabilities, examples, env vars, error codes.

### Phase 7 — Register
7. Expose the wrapper path to agents that need it (via `Bash` tool allow-list in the agent's frontmatter). Add to `library.yaml` if shared across projects.

## Red Flags

| Thought | Reality |
|---|---|
| "The tool already outputs JSON — no wrapper needed." | You still need error handling, env setup, rate-limit retries. Wrapper stays thin but exists. |
| "Wrapper prompts for password interactively." | Agents can't respond to prompts. Use env var or non-interactive auth. |
| "Wrapper returns prose on stderr, JSON on stdout, mix on failure." | Never mix. Stdout always JSON (even error objects); stderr for diagnostics. |
| "Version-pin the target tool." | Yes. Record the tested version in the wrapper README. Tools change output formats. |
| "Add the wrapper without tests — agents will catch errors." | Agents shouldn't debug your wrapper; they rely on it. Test it. |

## Related skills
- `subagent-driven-development` — agents use wrappers
- `systematic-debugging` — when wrapper output surprises
- `tdd` — test the wrapper first
