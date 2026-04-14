# Agentic Claude Code Workflow Patterns: Adiemas Research

## Repository Availability
Research attempted on 5 Adiemas GitHub repos. Status:
- **agentic-workflow**: EXISTS, fully analyzed
- **claude-code-training**: 404 Not Found
- **agent-factory**: 404 Not Found
- **agent-forge**: 404 Not Found
- **agentic-dev-framework**: 404 Not Found

Only `agentic-workflow` is available for analysis.

---

## Repo: agentic-workflow

**Purpose**: Production-grade agentic coding workflow orchestrator with Claude Code hooks, multi-stack agent teams, and deterministic + agentic execution patterns for C#/.NET, Python, React, and Blender.

**Directory Layout**:
```
agentic-workflow/
├── .claude/
│   ├── agent-memory/
│   ├── agents/                 # 18 specialized agent definitions
│   │   ├── architect.md
│   │   ├── qa-orchestrator.md
│   │   ├── code-reviewer.md
│   │   └── ... (18 total)
│   ├── commands/               # 3 root-level skills
│   ├── skills/                 # 13 reusable workflow skills
│   └── settings.json           # 40+ permissions, 6 hook types
├── hooks/
│   ├── pre-tool-use/           # enforce-rules.sh
│   ├── post-tool-use/          # log-changes.sh, validate-output.sh
│   ├── user-prompt-submit/     # inject-stack-rules.sh
│   ├── subagent-start/         # inject-context.sh
│   ├── session-start/          # setup-env.sh
│   └── stop/                   # qa-gate.sh
├── rules/
│   ├── global/                 # security.md
│   ├── dotnet/
│   ├── python/                 # coding-standards.md
│   └── react/
├── orchestration/
│   ├── src/
│   │   ├── orchestrator.ts     # DAG execution engine
│   │   ├── agent-factory.ts    # Agent spawn & logging
│   │   ├── meta-prompter.ts    # Task decomposition
│   │   └── types.ts            # Zod schemas
│   └── workflows/
├── logging/
│   └── agent-runs/             # JSONL logs
├── scripts/
└── templates/                  # Stack-specific scaffolding
```

**Patterns Worth Stealing**:

1. **Layered Permissions Model** (`.claude/settings.json`)
   - 40+ granular permissions: `Bash(git *)`, `Bash(npm *)`, `Agent(researcher)`. Denies: `Bash(rm -rf *)`, `Bash(curl | bash)`.
   - Prevents catastrophic mistakes. Principle of least privilege per agent role. Easy to audit.

2. **Hook-Driven Rule Injection** (`hooks/pre-tool-use/enforce-rules.sh`)
   - Parses file extension → loads matching rules from `rules/{stack}/` → injects as `additionalContext`.
   - Rules stay DRY. No prompt bloat. Example: Edit `.cs` file → get .NET rules; edit `.py` → get Python rules.

3. **Orchestrator: Deterministic DAG + Agentic Fallback** (`orchestration/src/orchestrator.ts`)
   - ExecutionPlan: steps with `dependsOn`, `parallel`, `modelOverride`. Finds ready steps, spawns parallelizable steps concurrently, chains sequential with result injection.
   - Hybrid: meta-prompter generates plan (agentic); orchestrator executes (deterministic). No hallucination-driven branching. Cost-optimized per step (haiku for research, opus for architecture).

4. **Meta-Prompting for Task Decomposition** (`orchestration/src/meta-prompter.ts`)
   - User task → meta-prompter (opus) generates ExecutionPlan JSON with step #, agent name, detailed prompt, dependencies, validation, model choice, parallel flag.
   - Shifts agentic reasoning to plan level. Reusable prompts. Cost-aware model selection.

5. **Multi-Agent QA Orchestration** (`.claude/agents/qa-orchestrator.md`)
   - Delegates to code-reviewer, security-scanner, test-runner in parallel → synthesizes QAReport with verdict (APPROVE/BLOCK/NEEDS_ATTENTION).
   - Blocking rules: 1+ critical security = BLOCK, 3+ code review critical = BLOCK, test failures = BLOCK, coverage <70% = NEEDS_ATTENTION.
   - Single source of QA truth. Prevents incomplete PRs.

6. **Structured Logging with SessionID** (`orchestration/src/agent-factory.ts`)
   - Every agent run: `{timestamp, sessionId, agent, action, input (200 chars), output (500 chars), duration, status}` → JSONL in `logging/agent-runs/`.
   - SessionId: `{agent-name}-{timestamp}`. Audit trail. Detect stuck agents. Cost rollup per agent.

7. **Stack-Aware Agent Roster** (18 `.md` agent definitions)
   - architect (opus, 25 turns, design), python-developer (sonnet, Python-only), dotnet-developer (sonnet, C#), sql-specialist (opus, schema), security-scanner (sonnet, OWASP), blender-designer (sonnet, 3D+STL).
   - No generic "code agent." Each role has hardcoded expertise, model level, tool budget. Easy to add domain.

**Gaps/Weaknesses**:

1. **No Visible Persistent Context Store** - Agent memory declared (`memory: project`) but implementation hidden. How do agents share state? No git-based memory, Redis, or vector DB shown. May hit token limits on large projects.

2. **Hook Scripts Depend on Python** - `enforce-rules.sh` pipes through `python -c "import json; ..."`. Assumes Python in PATH. No Bash-only JSON fallback.

3. **No Plan Validation Before Orchestration** - meta-prompter output must match ExecutionPlan Zod schema or orchestrator throws. No recovery. No schema-guided generation.

**Relevance Score**: 5/5

Production-ready. Directly applicable to Streck's AI Engineer. Steal: hooks, orchestrator, rule injection, QA gate, structured logging, agent roster.

---

## Cross-Repo Synthesis

**Patterns That Compound**:
- Hooks + Rules Injection = self-documenting agents (no manual rule prompts).
- Meta-Prompting + Orchestrator + Zod = verifiable execution plans (no hallucinated DAGs).
- QA Orchestrator + Hook-Driven Stop Gate = automated quality checkpoints.
- Stack-Aware Agents + Rule Routing = multi-language coherence (C# and Python follow own standards).

**What NOT to Copy**:
- Don't adopt all 18 agents at once. Start with 5-6 core roles (architect, code-reviewer, python-dev, dotnet-dev, security-scanner).
- Don't make hooks too prescriptive. Keep them simple (grep extension, inject rules). Avoid parameterized hooks.
- Don't expose meta-prompter result unparsed. Always validate ExecutionPlan against schema.

**Immediate Actions for `soup` Framework**:
1. Copy `settings.json` permission structure. Add ADO-specific permissions (Azure DevOps CLI).
2. Implement hooks: PreToolUse (rule injection), PostToolUse (validation), Stop (QA gate).
3. Build orchestrator in target language (C# or Python). Zod → Pydantic or FluentValidation.
4. Define 6 core agents: architect, python-dev, dotnet-dev, react-dev, security-scanner, code-reviewer.
5. Logging: SessionId, duration, status per agent run → JSONL in `logging/agent-runs/`.
