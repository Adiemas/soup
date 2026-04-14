# Soup — Cycle 1 Critic (Developer Experience)

Independent DX review of `soup/`. No prior familiarity. Focus: what a Streck
engineer sees, does, and gets stuck on.

---

## 1. First 10 minutes — new engineer onramp

**What helps**

- `README.md:15-24` TL;DR is copy-paste runnable on paper.
- `docs/ONBOARDING.md:69-115` shows a concrete narrated `just go` trace. Best
  single onboarding asset in the repo.
- `CLAUDE.md:5-13` iron laws are short and non-wiggly.

**What hurts**

- `README.md:19` `git clone <this repo>` — placeholder URL. New dev doesn't
  know what to paste. **Fix:** replace with the actual remote or
  `git clone https://github.com/streck/soup.git`.
- `README.md:22` says `cp .env.example .env && $EDITOR .env`, but
  `justfile:40-43` `just init` *already* copies `.env.example` → `.env`.
  The two steps collide and the README implies you must do the copy before
  `just init`. **Fix:** drop the `cp` line and re-order: `just init` first,
  then "edit `.env` to add `ANTHROPIC_API_KEY`".
- `README.md:165` lists `uv` as optional, but `justfile:29-39` clearly
  prefers it (pip fallback path is untested in CI). Say so: "strongly
  recommended" + one line on Windows `winget install astral-sh.uv`.
- `.env.example` — referenced 4× but I can't find any reference to what keys
  it must contain (only `ANTHROPIC_API_KEY` in README). **Fix:** have
  `docs/ONBOARDING.md` enumerate required env vars.
- No discoverable "what do I type at the Claude Code prompt vs. shell?"
  table. The `/specify` vs `just go` distinction trips newcomers (both
  appear in the first page). **Fix:** add a one-line rule in
  `ONBOARDING.md` §1: "slash commands inside a Claude Code session; `just`
  recipes in the terminal."
- `CLAUDE.md` has no pointer to `docs/ONBOARDING.md`. The first-session
  loader has 0 guidance to the onboarding doc.

## 2. Happy path walkthrough — `just init` → `just go "add a /health endpoint"`

Tracing mentally:

1. `just init` (`justfile:26-52`) — **first stumble:** line 36 does
   `. .venv/bin/activate 2>/dev/null || . .venv/Scripts/activate` — that's
   the pip fallback only. If `uv` succeeds (line 32), venv is never
   activated before `uv pip install -e ".[dev]"` — `uv` uses the venv it
   just made, so it's actually fine, but subsequent recipes that run
   `pytest`, `ruff`, `python -m orchestrator.cli` assume the venv is
   active, and on Windows `bash -cu` won't inherit venv activation across
   recipes. **Fix:** add `VIRTUAL_ENV` + `PATH` prefixing in the justfile,
   or require all python invocations to use `uv run python …`.
2. `just install` runs `python -m orchestrator.cli install` — but
   `orchestrator/` is the framework code; I have no evidence from the docs
   that the `install` subcommand exists. `.claude/commands/install.md:20`
   says "Execute `just install` via Bash" then read `.claude/hooks/setup.init.log` —
   a file path that nothing else in the framework writes. **Fix:** either
   have `install.py` write that log, or update the command.
3. `just go "add a /health endpoint"` (`justfile:70-72`) — calls
   `orchestrator.cli go`. `docs/ONBOARDING.md:69-115` promises a clean trace;
   real problems would surface around:
   - ExecutionPlan validation: `TaskStep.agent` is a `Literal` in
     `schemas/execution_plan.py`. If the meta-prompter picks `test-runner`
     (heavily advertised across README, ARCHITECTURE, DESIGN, hooks/stop.py)
     it will fail validation because `test-runner` is **not** an agent —
     see §4 below. This is a latent P0.
   - Worktree creation needs `git`. `just init` never verifies a git
     repo; if the clone is shallow or this is a ZIP extract, the first
     `git worktree add` bombs with no helpful error.
4. Stop hook → qa-orchestrator. `qa-orchestrator.md:21` explicitly says
   "delegate the `test-runner` role to `verifier`." Good in code —
   but everywhere else (`DESIGN.md:152`, `ARCHITECTURE.md:60`,
   `README.md:68,90`, `verify.md:2`, `stop.py:121`) claims a literal
   `test-runner` agent. Engineers reading the docs before the agent card
   will be confused when they try to register or invoke it.

**Ambiguities surfaced:**

- `README.md:38` says "dry-run plan only: `just plan "<goal>"`" — but
  `justfile:64-66` calls `orchestrator.cli plan … --dry-run`. What does
  non-dry-run `plan` look like? There isn't one. The flag is redundant
  and confusing.
- `/specify` defaults to `specs/<slug>-<YYYY-MM-DD>.md`
  (`commands/specify.md:26`), but `/plan` defaults to "most recent
  `specs/*.md` with no open questions" (`commands/plan.md:12`). What if
  two specs match? Ties are undefined.

## 3. Command ergonomics

| Command | Argument discoverability | Failure output | Prevention |
|---|---|---|---|
| `/specify` | Good — frontmatter `argument-hint` | Silent on empty `$ARGUMENTS` — spec_writer will just make something up. Add: "if empty, AskUserQuestion" | Weak |
| `/plan` | Optional arg; ambiguous default (§2). **Fix:** if >1 candidate, list them and AskUserQuestion. | No fail path if `## Open Questions` section missing entirely | Partial |
| `/tasks` | Same default ambiguity. Relies on `soup plan validate` (`tasks.md:22`) — command not registered anywhere. **Fix:** wire it in justfile as `just plan-validate <path>` | Retry-3 on schema fail is good | Good |
| `/implement` | Fine. | Mentions `.soup/runs/<run_id>.json` (`implement.md:23`) but `ARCHITECTURE.md:72` says `.soup/runs/<run-id>/trace.jsonl`. Pick one. | — |
| `/verify` | Zero args — good. | Mentions `schemas/qa_report.py` + blocking rules; clear. | Good |
| `/quick` | Good. Explicit bounce contract. `quick.md:19` JSON shape is the nicest touch in the whole repo. | Mentions `implementer` — but implementer (`agents/implementer.md:19-20`) refuses without a failing test in scope; `/quick` never spawns test-engineer first. **Contradiction.** | **Broken** |
| `/rag-search` | Good. Graceful LightRAG-down fallback (`rag-search.md:30`). | No retry/fallback for empty results | Good |

**Concrete `/quick` fix:** update `commands/quick.md:15-17` to say the
implementer should *either* adopt a one-shot TDD micro-flow (write test,
write code, pass) *or* invoke `test-engineer` first. As written, `/quick`
cannot succeed on any real implementation task.

## 4. Agent-command coupling

- **Orphan/ghost agent:** `test-runner`. Referenced 10+ places; no
  `.claude/agents/test-runner.md`. `qa-orchestrator` quietly remaps to
  `verifier`. **Fix:** either create `test-runner.md` (stub delegating
  to `verifier`) or do a global rename. Current state is a footgun for
  meta-prompter output validation.
- **Orphan agent files:** `ts-dev.md`, `react-dev.md` exist but no command
  or justfile recipe references them directly — they're only reachable via
  meta-prompter schema whitelist. That's fine; but if a user runs
  `/quick "tweak this tsx"` the implementer generic gets the job, not
  `ts-dev`. Document: *implementer is generic; stack specialists are only
  selected by meta-prompter.*
- **Orphan agents:** `github-agent`, `ado-agent`, `docs-ingester`,
  `rag-researcher` have agent cards but no slash-command surfaces them
  directly (only `/rag-search` → `rag-researcher`, `/rag-ingest` →
  `docs-ingester`). `github-agent` and `ado-agent` are not invoked from
  any command or hook. **Fix:** either add `/pr` + `/work-item` commands
  or drop the agents.
- **`fix-cycle` subagent:** referenced in `orchestrator.md:19`,
  `DESIGN.md:108`, `ARCHITECTURE.md:53, 67, 191`, `ONBOARDING.md:120`,
  `PATTERNS.md:297`, but no `agents/fix-cycle.md` exists. Fix-cycle is
  described as a dynamic role; doc this explicitly: "fix-cycle is a
  runtime label the orchestrator applies to a new `implementer` instance
  with `systematic-debugging` skill context — it is not a separate agent
  card."
- **Commands don't name the agents they invoke uniformly.** `/specify`
  names `spec-writer`. `/plan` names `architect` + `plan-writer`. `/verify`
  names three. `/review` names two. Good. But `/map-codebase` says
  "Explore-style subagent" (`commands/map-codebase.md:15`) — no named
  agent. **Fix:** create `explorer.md` or reuse `code-reviewer` in a
  read-only mode; name it explicitly.

## 5. Skill / command / hook orthogonality

Separation is mostly clear from `DESIGN.md §2`:
- **Commands** = user-facing UX entry points.
- **Agents** = roles with tools + model choice.
- **Skills** = procedural gates (iron law + checklist).
- **Hooks** = automatic, non-bypassable infra.

Problems:

- `spec-driven-development` skill (`skills/spec-driven-development/SKILL.md:11-14`)
  is a prose flow description — it *is* what `/specify → /plan → /tasks …`
  does. The skill and the commands carry nearly identical content. A new
  dev doesn't know: do I follow the skill, or call the commands? **Fix:**
  have the skill explicitly say "invoke the canonical commands; the skill
  exists to remind you when you're tempted to skip a phase."
- `tdd` skill and `test-engineer` agent overlap 90%. That's OK (skill is
  cross-cutting, agent is role), but **documents nowhere say so**. Add one
  sentence in `PATTERNS.md §2`: "skills are invoked by agents; agents do
  not replicate skill iron laws."
- `verification-before-completion` skill is basically what `/verify` does,
  but at a per-claim granularity. Missing guidance: when does an agent
  invoke this skill inline vs. rely on the Stop-hook QA gate? **Fix:**
  one paragraph in `CLAUDE.md` mapping: per-step → skill; per-run → `/verify`.
- No answer to "when should a new rule be a rule vs. a skill?" —
  `PATTERNS.md §4` tells you *how* to add a rule, not when. Add a decision
  rubric: rule = static, glob-routed, applied to files. Skill = procedural,
  applied to tasks. Hook = automatic enforcement.

## 6. Windows compatibility

Ethan's primary env is Windows 10. Findings:

- `justfile:11` `set shell := ["bash", "-cu"]`. Assumes bash on PATH —
  Windows needs Git Bash (`C:\Program Files\Git\bin\bash.exe`). **Fix:**
  detect via `just --evaluate` or document "install Git for Windows;
  ensure bash is on PATH" in README's Windows section (currently
  absent — `README.md:170-181` only lists winget installs).
- `justfile:36` `. .venv/bin/activate 2>/dev/null || . .venv/Scripts/activate`
  — correct Scripts path fallback for Windows; good.
- `justfile:28, 29, 45` `command -v` — works under Git Bash. Good.
- `justfile:105-109` `just clean` forwards to python. Good (avoids `rm -rf`).
- `justfile:188` `@rm -rf .venv __pycache__ …` — **breaks on Windows** outside
  Git Bash; `rm` isn't on cmd/PowerShell PATH. **Fix:** shell out to python:
  `python -m orchestrator.cli clean --caches`.
- `.claude/settings.json:151, 164, 177, 190, 203, 214` every hook runs
  `python .claude/hooks/*.py` with `"shell": "bash"`. On Windows, Claude
  Code's `bash` shell config works if Git Bash is installed, but the path
  `.claude/hooks/session_start.py` is forward-slash-OK on both.
- `.claude/settings.json:141-142` `"SOUP_ROOT": "${workspaceFolder}"` —
  VS Code variable; not a standard Claude-Code substitution. Unclear if
  it resolves in CLI sessions. **Fix:** let hooks compute via `os.cwd()`
  rather than relying on this env var, OR document that it only works in
  VS Code / Cursor.
- `/dev/null` appears 8× in `justfile` — all inside `bash -cu` blocks.
  Safe as long as bash is the invoker. No `NUL`-required usage.
- `&&` / `||` pipeline chaining — all inside bash `-cu` strings. Safe.
- `docker compose -f docker/docker-compose.yml` (`justfile:47`) uses
  forward slashes. On Windows Docker Desktop this is fine.
- `/soup-init` uses `${SOUP_APPS_DIR:-../<app-name>}` (`soup-init.md:17`) —
  bash parameter expansion. Fine inside a command prompt that runs under
  bash, but Windows engineers typing raw paths in cmd/PowerShell will
  hit confusion. Document this lives under `bash -cu`.
- Line 36 `2>/dev/null` before `.Scripts/activate` — if `.venv/bin/activate`
  is absent (Windows), the first `.` fails silently and the second runs.
  Works under Git Bash. Outside (pure Windows cmd), this line never runs.

## 7. Docs gaps — one per missing section

1. **Decision rubric "rule vs skill vs hook vs command"** — nowhere in
   PATTERNS.md. Essential for extension.
2. **`test-runner` isn't an agent** — needs an explicit note in
   `qa-orchestrator.md` + DESIGN table (replace row or mark aliased).
3. **`fix-cycle` explained** — add a "dynamic roles" subsection in
   `ARCHITECTURE.md §5`.
4. **`.env.example` contract** — what keys are required (ANTHROPIC_API_KEY,
   POSTGRES_PASSWORD, GITHUB_TOKEN, ADO_PAT, embedding model endpoint)?
   Absent. Add to ONBOARDING.md §2.
5. **Windows-specific setup** — no troubleshooting for bash-not-found,
   venv activation, Docker Desktop shared drives. The README Windows block
   (`README.md:170-181`) stops at `just init`.
6. **"How do I add a new agent?"** — `PATTERNS.md §1` exists. But it
   doesn't say how the Pydantic `Literal[...]` is kept in sync. The
   `schemas/execution_plan.py::TaskStep.agent` Literal will reject
   unregistered names — engineers will discover this by breaking
   `just go`. Add a one-line "run `just plan-validate` after editing
   `TaskStep.agent` Literal."
7. **"Where do logs go on Windows?"** — `SOUP_LOG_DIR` uses
   `${workspaceFolder}` which isn't guaranteed to resolve.
8. **`just doctor` output** — referenced (`ONBOARDING.md:54`,
   `README.md:255`) but no example output shown. Screenshot or snippet.
9. **HITL mode in detail** — `just go-i` (`justfile:76-78`) is 3 lines of
   docs. What does the wave-boundary prompt look like? Add a sample
   transcript to ONBOARDING.md.
10. **Cycle-cap behavior** — CLAUDE.md says "Never let an agent span >10
    turns" but there's no doc on what happens on turn 11. Does it abort?
    Escalate? Silently stop? Document in `orchestrator.md`.

---

## Top 10 actionable fixes (impact / effort)

| # | File | Change | Impact | Effort |
|---|------|--------|--------|--------|
| 1 | `.claude/agents/test-runner.md` (new) or rename across 10+ refs | Resolve `test-runner` ghost agent — either create the card or rename every reference to `verifier` | H | L |
| 2 | `.claude/commands/quick.md:15-17` | Fix `/quick` contradiction: implementer refuses w/o failing test, but `/quick` doesn't spawn test-engineer first. Inline a micro TDD loop or invoke both agents | H | L |
| 3 | `README.md:19, 22` | Replace `<this repo>` with actual URL; drop redundant `cp .env.example .env` (`just init` does it) | H | L |
| 4 | `docs/ONBOARDING.md` §2 (new) | Enumerate `.env.example` required keys and expected values | H | L |
| 5 | `justfile:188` and Windows section in `README.md` | Replace `rm -rf` with python-based clean; add "install Git Bash + ensure bash on PATH" note | H | L |
| 6 | `docs/PATTERNS.md` (new §0) | Decision rubric: rule vs skill vs hook vs command | H | L |
| 7 | `.claude/commands/map-codebase.md:15` + new `agents/explorer.md` | Name the actual agent invoked; remove hand-waves | M | L |
| 8 | `.claude/agents/fix-cycle.md` (new OR doc section) | Explain that fix-cycle is a runtime role, not a card; update 6 refs to point to the note | M | L |
| 9 | `justfile` + `README.md:38` | Drop unused `--dry-run` flag on `just plan`; add `just plan-validate <path>` recipe used by `/tasks` | M | L |
| 10 | `.claude/commands/plan.md:12` + `tasks.md:12` | Disambiguate "most recent" default — if >1 candidate, list + AskUserQuestion | M | L |

---

_Review cutoff: 2026-04-14. Reviewed files: README, CLAUDE, CONSTITUTION,
justfile, .claude/settings.json, all 14 commands, 5 agents (orchestrator,
meta-prompter, qa-orchestrator, implementer, test-engineer, architect),
4 skills (spec-driven-development, tdd, subagent-driven-development,
verification-before-completion), docs/DESIGN, ONBOARDING, ARCHITECTURE,
PATTERNS._
