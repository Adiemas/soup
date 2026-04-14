# disler/install-and-maintain

A hybrid deterministic-script + agentic-supervision framework for app
initialization and ongoing maintenance. Defines **three execution
modes** (`cldi` deterministic, `cldii` supervised, `cldit`
interactive) over a single set of hooks — the source of soup's
three-mode justfile. Relevance rating: 5/5.

- URL: https://github.com/disler/install-and-maintain (representative)
- Research summary: `research/02-disler.md`

## What we took

- **Three-mode CLI** — `just plan` (deterministic, dry-run),
  `just go` (supervised), `just go-i` (interactive with HITL). All
  three share the same hook chain; only the CLI entry point differs.
- Hook-first observability: `.claude/settings.json` registers
  matchers, hooks write JSON logs, commands analyze logs post-hoc.
- SessionStart `.env` loader pattern — secrets enter via env file,
  never via prompts.
- HITL via AskUserQuestion with validation (e.g.
  `grep -q "^VAR_NAME=.\+" .env && echo "set"`).
- Meta-prompting output style: "Status / What worked / What failed /
  Next steps" — same shape used by our QA reports and `just doctor`.
- `install.md` command reads hook log → analyzes → writes
  `install_results.md`. Our `just install` follows the same pattern.
