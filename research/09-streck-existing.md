# Streck-agentic-workflow — Internal Repo Review

**Location:** `C:\Users\ethan\AIEngineering\streck-agentic-workflow\`
**Review date:** 2026-04-14
**Stats:** 120 config files, 15 skills, 18 agents, 10 Python hooks, 11 rule modules

## 1. Repo snapshot

```
streck-agentic-workflow/
├── .claude/
│   ├── agents/
│   │   ├── orchestrators/    [planner, meta-prompter, qa-orchestrator]
│   │   ├── specialists/      [dotnet-developer, react-developer, sql-specialist, debugger, test-writer]
│   │   ├── reviewers/        [code-reviewer, security-scanner, architecture-reviewer]
│   │   ├── utility/          [doc-writer, docs-scraper, git-ops, researcher]
│   │   └── REGISTRY.md       [task→agent routing table]
│   ├── commands/             [7 user-facing]
│   ├── skills/               [15 compound workflows]
│   ├── hooks/                [10 Python validators/gates]
│   ├── rules/                [11 MD routed by stack]
│   ├── schemas/              [Pydantic validation]
│   ├── memory/               [agent-specific lessons.md]
│   ├── templates/            [code templates by pattern]
│   ├── settings.json
│   └── scratchpad.md         [inter-agent communication]
├── apps/pipette-verification-system/
├── shared/                   [dotnet/ + react/]
├── ai_docs/                  [cached external docs]
├── docker-compose.yml        [SQL Server 2022]
├── justfile                  [three-mode CLI]
├── library.yaml
└── CLAUDE.md
```

**Stack:** .NET 8 / C# 12 + EF Core + Serilog + xUnit; React 19 + TS + Vite + TanStack Query + Vitest; SQL Server 2022 + T-SQL + tSQLt; Python 3.11+ (UV) for hooks.

## 2. Agent roster (vs soup)

Streck has: 3 orchestrators (planner, meta-prompter, qa-orchestrator), 5 specialists (dotnet, react, sql, debugger, test-writer), 3 reviewers (code, security, architecture), 4 utility (doc-writer, docs-scraper, git-ops, researcher). **Soup lacks:** utility tier, architecture-reviewer, explicit REGISTRY.

**Model tier pattern:** Opus for orchestrators, Sonnet for specialists + reviewers, Haiku for utilities. Cleaner and more cost-aware than soup's current pattern.

## 3. Utility agents deep-dive

**doc-writer** (haiku, tools: Read/Write/Edit/Glob/Grep):
- Hardblock: scope = `docs/**,*.md`; only recently-modified code; must cross-reference CLAUDE.md + REGISTRY + related docs.
- Flow: read CLAUDE.md + lessons → Glob/Grep recent changes → match doc type (README/API/Architecture/ADR/Changelog) → cross-ref → report files + types + concerns.

**docs-scraper** (haiku, tools: Read/Bash/Glob/Grep; NO Write/Edit):
- Parses `ai_docs/README.md` manifest; checks `.fetched` timestamps; classifies fresh/stale/missing; `curl --max-time 15`; 50KB truncate; reports status table.

**git-ops** (haiku, tools: Read/Bash/Glob/Grep):
- Hardblocks: Conventional Commits format; NO force-push main/master; must include ticket number.
- Branch: `{type}/{app-name}/{ticket}-{description}`.
- Merge strategy: squash for features/fixes, merge-commit for releases.
- Conflict resolution: preserve BOTH intents; run full tests; escalate migration conflicts to sql-specialist.

**researcher** (haiku, tools: Read/Glob/Grep; NO Write/Edit/Bash, max 20 turns):
- Hardblocks: no file modifications; findings table format `file|line|relevance|excerpt`; 10-search budget.
- 3-level discipline: Glob (1-3) → Grep (2-5) → Read top 3 (with offset/limit). Forces depth over breadth.

## 4. Commands/skills/hooks catalog

**7 commands:** `/plan {task}`, `/build {plan}`, `/test`, `/review`, `/prime`, `/deploy` (stub), `/load-docs`.

**15 skills:** scaffold-dotnet-feature, scaffold-react-component, scaffold-sql-migration, scaffold-api-endpoint, new-app-workflow, feature-update-workflow, import-existing-app, review-pr, damage-control, install-and-maintain, gather-requirements, generate-adr, generate-diagram, library.

**10 hooks:**
| Hook | Trigger | Purpose |
|---|---|---|
| session-start.py | SessionStart | Detect stack, inject context |
| validate-bash.py | PreToolUse(Bash) | Block `rm -rf`, `sudo`, `curl|bash`, `git push --force` |
| damage-control.py | PreToolUse(*) | Safety gate; escalates risky ops |
| enforce-rules.py | PreToolUse(Edit/Write) | Inject language rules by ext |
| log-changes.py | PostToolUse | JSONL audit trail |
| validate-output.py | PostToolUse | Lint/typecheck after writes |
| subagent-start.py | SubagentStart | Load agent MEMORY; isolate |
| subagent-stop.py | SubagentStop | Consolidate logs + memory |
| qa-gate.py | Stop | Final QA before commit |
| status-line.py | StatusLine | `[dotnet-dev @ T5/25] ...` |

## 5. Streck-specific integrations

- **Logging:** `{Domain}.{Action}_{State}` (e.g. `Order.Process_started`); Serilog structured; CorrelationId through middleware→managers→accessors.
- **DI:** `AddScoped<IInterface, Implementation>` convention; agents infer lifetimes.
- **Validation:** FluentValidation (C#) + Zod (React) at boundaries; parameterized queries always.
- **State hierarchy (React):** TanStack Query > useSearchParams > controlled > useState > Zustand (last resort).
- **Conventions:** Layered (Accessors/Managers/Common) vs Vertical-Slice (Features/{Name}/); detected automatically.
- **Branch naming:** `{type}/{app}/{STRECK-nnn}-{desc}`.
- **ADO:** Commit footer `STRECK-{n}`; ADO-agent planned but not implemented.
- **Cookies:** HttpOnly, Secure=Always, SameSite=Strict, 8-hour expiry.

## 6. Patterns worth stealing (not in 17 external repos)

| Pattern | Where | Why |
|---|---|---|
| **REGISTRY.md routing** | `.claude/agents/REGISTRY.md` | Explicit task-type → agent + complexity tier + dispatch context template. |
| **Scratchpad inter-agent** | `.claude/scratchpad.md` | File-based state exchange; orchestrators reset, specialists append, reviewers read. Prevents assumption regression. |
| **Brownfield-First Protocol** | CLAUDE.md + `rules/global/brownfield.md` | Read existing tests first, baseline, regression tests before modifying behavior. Hard rule. |
| **Wave decomposition rule** | REGISTRY.md | Two tasks in same wave must not read-then-write same file; max 8 agents/wave. |
| **Tier→model binding** | REGISTRY.md | Opus=orchestrators, Sonnet=specialists+reviewers, Haiku=utilities. Explicit. |
| **Damage-control hooks** | `hooks/pre-tool-use/damage-control.py` | Centralized pre-execution safety gates. |
| **Hard blockers field** | Every agent YAML | Non-negotiable constraints + escalation target. |
| **Dispatch context template** | REGISTRY.md | Standardized: Task\|Mode\|Target\|Scope\|Deps\|Prior Wave\|Success Criteria\|Verify\|Guard\|References. |
| **Stack-aware rule injection** | `enforce-rules.py` | Per-file-extension rule loading (not blanket). |
| **Memory consolidation** | subagent-start/stop hooks | Copies `agent-memory/<name>/lessons.md` in; appends findings out. |
| **10-search budget + findings table** | researcher agent | Prevents rabbit-holing; standardizes handoff. |
| **Logging convention** | `rules/global/logging.md` | `{Domain}.{Action}_{State}` structured + correlation IDs. |

## 7. Gaps where soup goes further

- Soup has deterministic `orchestrator/` DAG executor; Streck's planner outputs DAG but dispatch is manual.
- Soup has `meta_prompter.py` (opus) generating Task objects from spec+codebase; Streck manually dispatches.
- Soup has LightRAG + Postgres for org docs; Streck has `ai_docs/cache/` via scraper.
- Soup has ADO-agent planned + implemented; Streck has it planned only.
- Soup has `python-dev` specialist; Streck is .NET+React only.
- Soup has `/specify → /clarify → /plan → /tasks → /implement → /verify` spec-driven flow; Streck uses `/plan → /build → /review`.
- Soup has worktree isolation per step; Streck single cwd.
- Soup has CONSTITUTION.md immutable spec; Streck has CLAUDE.md only.

## 8. Integration plan

### CREATE in soup (Priority 1 — verbatim/near-verbatim copies)
- `.claude/agents/utility/doc-writer.md`
- `.claude/agents/utility/git-ops.md`
- `.claude/agents/utility/researcher.md`
- `.claude/agents/utility/docs-scraper.md`
- `.claude/agents/REGISTRY.md` — routing table + dispatch context template + complexity tiers + wave rules
- `.claude/scratchpad.md` — initial format with header
- `rules/global/logging.md` — `{Domain}.{Action}_{State}` + correlation IDs
- `rules/global/brownfield.md` — read-first protocol, regression tests

### CREATE (Priority 2 — adaptations)
- `.claude/agents/architecture-reviewer.md` (opus) — pattern detection + veto
- `.claude/hooks/damage_control.py` — fold into existing pre_tool_use.py or split out

### EDIT in soup
- `library.yaml` — add utility tier + architecture-reviewer
- `docs/DESIGN.md` §6 — expand roster with utility tier + tier→model binding
- `CLAUDE.md` — add Brownfield-First Protocol + Dispatch Context Template references
- Each existing agent .md — add `hardBlockers` and `escalation` fields

## Summary

Streck is production-hardened. Its utility-agent patterns, REGISTRY, scratchpad, brownfield discipline, and tier→model binding are immediately adoptable. Soup's direction is consistent but strictly more ambitious (spec-driven + orchestrator + RAG + worktrees). Integration: copy utility agents + REGISTRY + rules; preserve soup's orchestrator layer.
