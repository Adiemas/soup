# CLI-Anything

A 7-phase methodology for wrapping arbitrary CLI tools into
agent-callable primitives: Survey → Contract → Wrap → Skill →
Agent (optional) → Test → Doc. Each wrapper exposes a Pydantic-typed
input/output surface so agents can reason about the tool without
parsing arbitrary text. Relevance rating: high for tool-surface
coverage.

- URL: https://github.com/disler/cli-anything (representative)
- Research summary: referenced across `research/02-disler.md` and
  `research/07-gsd.md`.

## What we took

- The 7-phase methodology (see `docs/PATTERNS.md §7`).
- Pydantic contracts for every wrapper input/output — no raw text
  parsing in agent prompts.
- Preference for `--output=json` / `--format=json` flags; parse text
  only as a last resort.
- `cli_wrappers/<tool>/` directory convention: `wrapper.py`,
  `_survey.md`, `README.md`, fixture recordings for tests.
- Five v1 wrappers: `az devops`, `psql`, `docker`, `dotnet`, `git`.

Explicitly NOT copied: CLI-Anything's auto-generation of wrappers
from tool help text — v1 writes wrappers manually; automate later
(`DESIGN.md §10`).
