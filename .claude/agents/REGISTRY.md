# Agent REGISTRY

Single-source-of-truth mapping for task routing, model tiering, and dispatch context.

## Skill cross-refs

Agents invoke skills; when you dispatch an agent below, check whether the task
shape maps to a skill's iron law:

- `brownfield-baseline-capture` — pair with any brownfield plan (`verifier`,
  `qa-orchestrator`, or any step with `regression_baseline_cmd` active on the
  parent plan). See `.claude/skills/brownfield-baseline-capture/SKILL.md`.
- `contract-drift-detection` — pair with `full-stack-integrator` on every
  cross-stack contract change.
- `systematic-debugging` — mandatory for `verifier` fix-cycle invocations.
- `tdd` — mandatory for every `test-engineer` + implementer pair.

## Tier → model binding

| Tier | Model | Purpose |
|---|---|---|
| **Orchestrator** | `opus` | Planning, decomposition, cross-agent coordination |
| **Specialist** | `sonnet` | Stack-specific implementation and review |
| **Reviewer** | `sonnet` | Quality/security/correctness gates |
| **Utility** | `haiku` | Bounded, read-mostly tasks (research, docs, git) |

Override only with written rationale in the PR body.

## Roster

### Orchestrators (opus)
| Agent | File | Task types |
|---|---|---|
| `orchestrator` | `.claude/agents/orchestrator.md` | Top-level dispatcher; runs validated `ExecutionPlan`; owns wave lifecycle |
| `meta-prompter` | `.claude/agents/meta-prompter.md` | Goal + spec + codebase → `ExecutionPlan` JSON |
| `architect` | `.claude/agents/architect.md` | System design, tech choices, no code |
| `qa-orchestrator` | `.claude/agents/qa-orchestrator.md` | Dispatches reviewer+scanner+verifier in parallel → `QAReport` |

### Specialists (sonnet)
| Agent | File | Stack / domain |
|---|---|---|
| `implementer` | `.claude/agents/implementer.md` | Generic single-task writer; TDD-gated |
| `python-dev` | `.claude/agents/python-dev.md` | FastAPI, pytest, async, typing-strict |
| `dotnet-dev` | `.claude/agents/dotnet-dev.md` | ASP.NET Core 8, xUnit, EF Core, layered or vertical-slice |
| `react-dev` | `.claude/agents/react-dev.md` | React 18+, functional+hooks, RTL, Vite |
| `ts-dev` | `.claude/agents/ts-dev.md` | TypeScript strict, Zod at boundaries |
| `sql-specialist` | `.claude/agents/sql-specialist.md` | Postgres schemas + migrations (owns both up+down) |
| `full-stack-integrator` | `.claude/agents/full-stack-integrator.md` | Cross-stack contracts (OpenAPI ↔ TS, SQL ↔ ORM, Protobuf). Regenerates both sides in one step. |
| `test-engineer` | `.claude/agents/test-engineer.md` | Writes failing tests first; never prod code |
| `spec-writer` | `.claude/agents/spec-writer.md` | `/specify` author (EARS format) |
| `plan-writer` | `.claude/agents/plan-writer.md` | `/plan` author — markdown plan only |
| `tasks-writer` | `.claude/agents/tasks-writer.md` | `/tasks` author — converts markdown plan → `ExecutionPlan` JSON |
| `verifier` | `.claude/agents/verifier.md` | Runs `verify_cmd` AND owns the fix cycle on failure (absorbs former `test-runner` and `fix-cycle` aliases) |

### Reviewers (sonnet)
| Agent | File | Focus |
|---|---|---|
| `code-reviewer` | `.claude/agents/code-reviewer.md` | Spec compliance + style; read-only |
| `security-scanner` | `.claude/agents/security-scanner.md` | OWASP + secrets + supply chain; respects repo `.gitleaks.toml` |

### Critics (sonnet)
Invoked by `/review --rounds N` with N ≥ 2, in parallel with each other. Read-only. Emit a structured `CritiqueReport` JSON to `.soup/reviews/<ts>-<kind>.json`. Orthogonal to cycle-1 reviewers — never duplicate their findings.

| Agent | File | Lens |
|---|---|---|
| `red-team-critic` | `.claude/agents/red-team-critic.md` | Adversarial. "How does this fail?" Failure modes, adversarial input, concurrency, degraded deps, rollback. |
| `over-eng-critic` | `.claude/agents/over-eng-critic.md` | Radical simplification. "What's unnecessary?" Unused abstractions, premature generalization, framework ceremony. Enforces CLAUDE.md "Don't add features, refactor, or introduce abstractions beyond what the task requires." |

### Utility (haiku)
| Agent | File | Scope |
|---|---|---|
| `researcher` | `.claude/agents/utility/researcher.md` | Read-only codebase survey; 10-search budget; findings table |
| `doc-writer` | `.claude/agents/utility/doc-writer.md` | Docs updates scoped to recently-modified code |
| `git-ops` | `.claude/agents/utility/git-ops.md` | Branch/commit/merge; Conventional Commits; force-push blocked |
| `docs-scraper` | `.claude/agents/utility/docs-scraper.md` | Refresh cached external docs in `ai_docs/` |
| `docs-ingester` | `.claude/agents/docs-ingester.md` | Add source to RAG index |
| `rag-researcher` | `.claude/agents/rag-researcher.md` | Cited knowledge retrieval; autoresearch loop |
| `github-agent` | `.claude/agents/github-agent.md` | `gh` CLI wrapper |
| `ado-agent` | `.claude/agents/ado-agent.md` | `az devops` CLI wrapper |

## Rule routing (non-catalog)

Rules are not agents or skills; they route via hooks, not the Library
catalog. For reference:

- `rules/global/*.md` — always injected by `.claude/hooks/subagent_start.py`
  into every subagent's `additionalContext`.
- `rules/<stack>/*.md` — injected by `.claude/hooks/pre_tool_use.py` on
  Edit/Write, based on file-extension and path routing.
- `rules/compliance/<flag>.md` — injected by
  `.claude/hooks/subagent_start.py` when `.soup/intake/active.yaml`
  carries a matching `compliance_flags[]` entry (flags:
  `lab-data`, `pii`, `phi`, `financial`). See
  `rules/compliance/README.md` for the flag table.

## Complexity tiers → routing

| Complexity | Flow | Example |
|---|---|---|
| **trivial** | `/quick` → implementer | typo, one-line fix |
| **simple** | spec+plan+tasks (≤4 steps) → orchestrator | single-endpoint CRUD |
| **moderate** | full flow → orchestrator with waves (5-12 steps) | new feature across backend+frontend |
| **complex** | full flow + architect pre-pass → orchestrator (13-30 steps) | new service, new schema, cross-app |
| **epic** | multiple plans, coordinated via meta-prompter supervising sub-plans | net-new internal app |

## Wave decomposition rules

1. **No same-file read-then-write across steps in the same wave.** Orchestrator sequentializes such conflicts automatically.
2. **Max 8 agents per wave.** Coordination overhead dominates beyond that.
3. **Test step before impl step.** TDD iron law — cannot be put in the same wave.
4. **Worktree-eligible steps prefer worktree isolation.** See `using-git-worktrees` skill.

## Dispatch context template

Every subagent spawn must include these fields (see `orchestrator/agent_factory.py`):

```
## Task
<one sentence>

## Mode
<deterministic | supervised | interactive>

## Target
<app name, paths scope>

## Scope
files_allowed: [<globs>]
max_turns: N
model: <haiku|sonnet|opus>

## Dependencies
<prior step outputs or artifact paths>

## Prior wave context
<excerpts from .claude/scratchpad.md>

## Success criteria
<how we know it worked>

## Verify command
<bash one-liner whose exit 0 = pass>

## Guard command
<optional bash that must pass before success>

## References
- spec: <path>
- plan: <path>
- constitution: CONSTITUTION.md v<n>
- rules: <auto-injected by pre_tool_use hook>
```

## Inter-agent communication

- **`.claude/scratchpad.md`** — append-only during a run; orchestrator resets at the start of each `ExecutionPlan`.
- **Format:** `## [<wave>.<step>] <agent> @ <ts>\n<findings or decisions>`.
- Reviewers read the full scratchpad; specialists append their wave findings; orchestrator compacts at wave boundaries.

## Hard blockers (cross-cutting)

Every agent inherits these; individual agents may add more:
- MUST NOT write to files outside `files_allowed`.
- MUST NOT commit secrets (env vars, keys, tokens).
- MUST NOT bypass the Stop hook QA gate.
- MUST NOT force-push to `main` / `master`.
- MUST cite any claim derived from RAG retrievals: `[source:path#span]`.
- MUST escalate after 3 failed fix attempts on the same bug (→ architect).

## Escalation targets

| Situation | Escalate to |
|---|---|
| Architectural pattern ambiguity | `architect` |
| Auth/authz changes | `security-scanner` (auto-dispatched) |
| Migration conflict | `sql-specialist` |
| Repeated verify failures (≥3) | `architect` + human HITL |
| Out-of-scope file edit requested | `orchestrator` (denies or re-plans) |
