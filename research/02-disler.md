# Disler Repos — Research Report

## 1. Bowser: Browser Automation Framework

**Purpose:** Four-layer agentic browser automation system. Composable skills + subagents + commands + justfile for testability at each abstraction level.

**Layout:**
- `.claude/skills/` — playwright-bowser, claude-bowser (CLI wrappers)
- `.claude/agents/` — playwright-bowser-agent.md, claude-bowser-agent.md, bowser-qa-agent.md
- `.claude/commands/bowser/` — hop-automate, ui-review orchestration
- `justfile` — four-layer recipe exposure (skill→subagent→command→just)

**Patterns Worth Stealing:**
1. **Layered Abstraction** — each layer independently callable; justfile exposes three execution modes per task (`test-playwright-skill`, `test-playwright-agent`, `ui-review`). Enables parallel sessions; testing one layer without orchestration overhead.
2. **Skill + Subagent Pairing** — `@playwright-bowser-agent` → calls `/playwright-bowser` skill. Decouples agent logic from tool logic.
3. **YAML Story-Driven Testing** — stories as YAML files, auto-discovered, executed in parallel. Non-technical, versionable test cases.

**Gaps:** No hook-driven observability; no meta-prompting for output style.
**Relevance: 4/5**

## 2. The Library: Skill Distribution

**Purpose:** Private-first meta-skill for managing AI agent capabilities without duplication. Reference catalog model.

**Layout:**
- `SKILL.md` — entire system as skill (no CLI, no build)
- `library.yaml` — catalog entries pointing to source repos/paths
- `cookbook/` — command-specific guides (add.md, use.md, push.md, sync.md, search.md)
- `justfile` — terminal shortcuts

**Patterns Worth Stealing:**
1. **Reference-Based Catalog** — `source: https://raw.githubusercontent.com/org/repo/main/path/SKILL.md`. Pull on demand via `/library use <name>` → clones temp → copies to target. Single source of truth.
2. **No-Build Distribution** — everything markdown + agent instructions. Portable, agent-agnostic.
3. **Typed Dependency Resolution** — `requires: [skill:name, agent:name, prompt:name]`. Explicit graph.

**Gaps:** No orchestration; no hooks; no output-style patterns.
**Relevance: 5/5**

## 3. Install-and-Maintain: Hook-Driven Setup

**Purpose:** Hybrid deterministic-script + agentic-supervision for app initialization. Three execution modes.

**Layout:**
- `.claude/settings.json` — hook matchers (SessionStart, Setup/init, Setup/maintenance)
- `.claude/hooks/` — session_start.py, setup_init.py, setup_maintenance.py
- `.claude/commands/install.md` — orchestrator
- `.claude/commands/install-hil.md` — human-in-the-loop variant
- `justfile` — `cldi` (deterministic), `cldii` (supervised), `cldit` (interactive)

### Deep Dive: `install.md`
```
---
description: Run setup_init hook and report installation results
argument-hint: [hil]
---
## Workflow
1. Execute Skill(/prime) — understand codebase
2. If MODE="true", run Skill(/install-hil) and exit
3. Read .claude/hooks/setup.init.log
4. Analyze successes/failures
5. Write app_docs/install_results.md
6. Report: Status, What worked, What failed, Next steps
```

Hook runs first (via `claude --init`), writes structured log. Command reads log post-hoc, analyzes, reports.

**Patterns Worth Stealing:**
1. **Hook-Driven Observability** — settings define matchers; hooks write structured JSON logs; commands read logs post-hoc. Deterministic preserved for CI; agent supervision optional.
2. **Three-Mode Execution** — same underlying hooks, different agent wrapping: `cldi` (CI), `cldii` (supervised), `cldit` (interactive). One source of truth.
3. **SessionStart Env Hook** — loads `.env` into CLAUDE_ENV_FILE, persists across session. Secrets without exposure.
4. **HITL via AskUserQuestion** — multiSelect options drive conditional workflows. Validation: `grep -q "^VAR_NAME=.\+" .env && echo "set"`.
5. **Meta-Prompting Output Style** — Status → What worked → What failed → Next steps. Written to `app_docs/install_results.md`.

**Gaps:** Single-codebase; no parallel subagent example.
**Relevance: 5/5**

## Cross-Repo Synthesis

### Orchestration Stack (Bowser-inspired)
```
justfile
  ↓
.claude/commands/   (orchestrators)
  ↓
.claude/agents/     (parallel subagent pools)
  ↓
.claude/skills/     (primitive CLI wrappers)
```

### Hooks + Config (install-and-maintain)
```
.claude/settings.json  (matchers)
  ↓
.claude/hooks/*.py     (deterministic, JSON logs)
  ↓
.claude/commands/      (post-hoc analysis, HITL)
```

### Skill Distribution (The Library)
- `library.yaml` distributed catalog
- Pull on demand, no pre-install
- Typed dependencies

### Winning Patterns for Streck Stack
1. Hook matchers for postgres migrations (`Setup.migration`), Docker build (`Build.docker`), pre-push GitHub (`PrePush`).
2. Subagent parallelization: `@docker-agent`, `@postgres-agent`, `@ci-agent`.
3. Three-mode execution for dev velocity.
4. Output-style parameterization (markdown|json|plain) → integrates with GitHub Issues, ADO Work Items.
5. Reference-based shared orchestrators via GitHub raw URLs.

### Immediate Priorities
1. settings.json hook registration (install-and-maintain)
2. Justfile three-mode template
3. SKILL.md meta-skill for distribution (The Library)
4. Subagent pool templates per tech (Bowser)
