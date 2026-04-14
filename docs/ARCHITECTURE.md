# Architecture — Soup Framework

Deep technical reference. For design rationale see
[`DESIGN.md`](DESIGN.md); for day-to-day use see
[`../README.md`](../README.md) and [`ONBOARDING.md`](ONBOARDING.md).

---

## 1. Pillar map

Soup is organized into 16 architecture pillars, each citing the
reference repo(s) it inherits from. Full table in
[`DESIGN.md §2`](DESIGN.md#2-architecture-pillars). Summary:

| Layer | Pillars | Where it lives |
|---|---|---|
| Interface | justfile (3-mode CLI), commands, slash UX | `justfile`, `.claude/commands/` |
| Agents | roster (20), skills (12), library catalog | `.claude/agents/`, `.claude/skills/`, `library.yaml` |
| Execution | orchestrator DAG, meta-prompter, worktrees | `orchestrator/`, `.soup/worktrees/` |
| Policy | schemas (Pydantic), rules (by ext), hooks | `schemas/`, `rules/`, `.claude/hooks/` |
| Knowledge | RAG (LightRAG + Postgres + MCP) | `rag/` |
| Scaffolding | templates (4 stacks), CLI wrappers | `templates/`, `cli_wrappers/` |
| State | plans, runs, memory, JSONL logs | `.soup/`, `logging/` |

---

## 2. Data flow — a full `/implement` run

```
User intent (`just go "<goal>"`)
    │
    ▼
[meta-prompter] — opus — produces ExecutionPlan JSON
    inputs:  goal, CONSTITUTION.md snapshot, top-k RAG hits
    outputs: ExecutionPlan{ goal, constitution_ref, steps[], budget_sec, worktree }
    │ Pydantic validation against schemas/execution_plan.py
    │ invalid → reject, re-prompt with schema errors
    ▼
[orchestrator]
    │ checkout/create worktree under .soup/worktrees/<slug>/
    │ compute topological layers (waves) from depends_on
    │ for each wave:
    │   spawn one fresh subagent per TaskStep (parallel where .parallel=true)
    │   each subagent receives:
    │     - step.prompt
    │     - constitution excerpt relevant to its agent
    │     - rules/<ext>/ injected by pre_tool_use hook per edit
    │     - rag_queries resolved + injected by subagent_start hook
    │     - files_allowed glob (enforced by pre_tool_use)
    │     - max_turns hard cap
    │   subagent exits → verify_cmd runs in worktree
    │     pass → atomic commit (Conventional Commits); continue
    │     fail → dispatch `verifier` (fix-cycle role) with failure context; retry up to 3
    │   wave boundary → in interactive mode, prompt user via ask-user-question
    ▼
[stop hook]
    │ dispatch qa-orchestrator (sonnet) → parallel fan-out:
    │   - code-reviewer  (spec compliance + rule violations)
    │   - security-scanner (OWASP, secrets, supply chain)
    │   - verifier        (pytest / xunit / vitest, coverage)
    │ synthesize QAReport per schemas/qa_report.py
    ▼
[verdict]
    APPROVE          → merge worktree → feature branch → `gh pr create`
    NEEDS_ATTENTION  → human review required; PR stays draft
    BLOCK            → orchestrator reverts, dispatches `verifier` (fix-cycle role), loops
```

State persisted at every step:

- `.soup/plans/<ts>-<slug>.json` — the ExecutionPlan that was executed
- `.soup/runs/<run-id>/trace.jsonl` — per-step subagent transcript
- `.soup/runs/<run-id>/qa-report.json` — synthesized verdict
- `logging/agent-runs/session-<session>.jsonl` — every tool call, hooked
- `logging/experiments.tsv` — one row per run (goal, duration, tokens,
  verdict, cost estimate) in autoresearch-style append-only format

---

## 3. Hook choreography

Hooks are the nervous system. Prompts never carry responsibilities
hooks can enforce.

```
                ┌──────────────────────── claude code session ────────────────────────┐
                │                                                                     │
     SessionStart ──► hooks/session_start.py                                           │
                       load .env; prime codebase summary into context                 │
                                                                                      │
     UserPromptSubmit ──► hooks/user_prompt_submit.py                                  │
                       regex-match intent; suggest skill/command; sticky banner       │
                                                                                      │
     ┌──── Edit|Write ──► hooks/pre_tool_use.py                                        │
     │                   a. resolve file ext (.py/.cs/.tsx/.ts/.sql/other)            │
     │                   b. inject rules/global/*.md + rules/<ext>/*.md               │
     │                   c. enforce TaskStep.files_allowed glob (deny out-of-scope)   │
     │                   d. block commits with --no-verify                            │
     │                                                                                │
     │    Any tool ──► hooks/post_tool_use.py                                         │
     │                   append structured event to agent-runs/session-*.jsonl       │
     │                   redact (?i)(secret|token|key|password) values                │
     │                   detect high-entropy strings → warn, do not block             │
     │                                                                                │
     │    SubagentStart ──► hooks/subagent_start.py                                   │
     │                   resolve rag_queries via rag/search.py; inject top-k          │
     │                   inject constitution excerpt + agent card + files_allowed     │
     │                                                                                │
     Stop ──────► hooks/stop.py                                                        │
                 dispatch qa-orchestrator                                              │
                 after QAReport: append row to logging/experiments.tsv                 │
                 write .soup/runs/<run-id>/qa-report.json                              │
                                                                                      │
                └─────────────────────────────────────────────────────────────────────┘
```

### Interaction with the three-mode justfile

| Mode | CLI | Hook behavior diff |
|---|---|---|
| Deterministic | `just plan` | meta-prompter runs; hooks off below SubagentStart |
| Supervised | `just go` | full hook chain, no HITL prompts |
| Interactive | `just go-i` | full hook chain + `ask-user-question` at each wave boundary |

All three share the same hook modules; modes differ only by the CLI
entry point signaling `--interactive` / `--dry-run` to the orchestrator.

---

## 4. RAG architecture

```
                ┌─── sources ────────────────────────────┐
                │  github: org/repo                      │
                │  ado:    org/project/repo              │
                │  fs:     /local/path                   │
                │  web:    https://docs.example.com/*    │
                └───────────────┬────────────────────────┘
                                │ rag/ingest.py (adapters per scheme)
                                ▼
                ┌─── LightRAG pipeline ──────────────────┐
                │  chunk → embed → graph-build → index    │
                │  (embeddings: OpenAI / local fallback)  │
                └───────────────┬────────────────────────┘
                                │ psycopg3 (binary)
                                ▼
                ┌─── Postgres 16 (`soup_rag` DB) ────────┐
                │  LightRAG tables: chunks, graph, kv    │
                │  pgvector extension for similarity     │
                └───────────────┬────────────────────────┘
                                │ rag/search.py
                                ▼
                ┌─── query surface ──────────────────────┐
                │  rag/mcp_server.py (stdin/stdout MCP)  │
                │  orchestrator subagent_start injection │
                │  just rag "<q>" → cli entry            │
                └────────────────────────────────────────┘
```

Citation policy (Constitution VII.3): every retrieval result carries
`{source, path, span_start, span_end}`. Agents consuming the result
must preserve `[source:path#span]` in any downstream claim. The
`code-reviewer` subagent flags uncited RAG-derived claims as a high-
severity finding.

Ingestion is additive; `just rag-reindex` rebuilds the graph across
all registered sources without re-downloading content (idempotent).

---

## 5. Worktree lifecycle

Per-feature isolation borrowed from superpowers + Archon. Every
non-trivial plan opens its own worktree; no plan ever touches main
until QA approves.

```
just go "<goal>"
    │
    ▼ orchestrator derives slug from ExecutionPlan.goal
       → .soup/worktrees/<slug>/   (git worktree add -b feature/<slug>)
    │
    ▼ orchestrator cd's into worktree; all subagents inherit it
       atomic commits land here; never on main
    │
    ▼ QA verdict:
       APPROVE          → git merge feature/<slug> → gh pr create → worktree kept until PR closes
       NEEDS_ATTENTION  → worktree kept; PR draft; human owns next move
       BLOCK            → `verifier` (fix-cycle role) continues in same worktree;
                          up to 3 attempts per wave; escalate on 3rd failure
    │
    ▼ cleanup:
       `just worktree-rm <slug>` after merge
       `just clean` removes .soup/runs older than 30d; worktrees untouched
```

Constitution IX.3: broken worktree → discard, re-plan. No
half-committed state merges to main.

---

## 6. Memory model

Four tiers. They do not overlap.

| Tier | File(s) | Lifetime | Writer | Reader |
|---|---|---|---|---|
| Session steering | `CLAUDE.md` | always in window | human-curated | every session |
| Long-term facts | `MEMORY.md` | append-mostly | human or `/remember` | summarizer |
| Dream-consolidated | `.soup/memory/<slug>.md` | per-project | `stop` hook (on APPROVE) | `subagent_start` hook injects relevant ones |
| Per-session trace | `logging/agent-runs/session-*.jsonl` | 30-day rolling | `post_tool_use` hook | `just logs`, postmortems |

Sizes: `CLAUDE.md` capped at 500 lines (Constitution VII.1). Dream
summaries capped at ~2 KB each; the `stop` hook triggers a summarizer
when a worktree merges, producing a distilled paragraph-per-feature
note in `.soup/memory/`.

No runtime DB for orchestration state — everything file-based and
inspectable, per Tenet 8.

---

## 7. Cost accounting

Two dimensions: Anthropic token spend and compute (if deployed).

### TSV layout (split per writer — iter-3 ε2)

Soup keeps two separate TSV ledgers under `logging/`. Each file is owned
by exactly one writer to avoid the dual-schema corruption shipped in
soup v0.x:

| File | Owner | Schema | Cardinality |
|---|---|---|---|
| `logging/experiments.tsv` | `orchestrator/orchestrator.py::_append_experiment` | `# soup-schema:experiments-v1` + 9 cols (`ts run_id status duration_sec n_steps budget_sec cost_usd aborted_reason goal`) | One row per ExecutionPlan run |
| `logging/sessions.tsv` | `.claude/hooks/stop.py` | `# soup-schema:sessions-v1` + 4 cols (`ts session_id files_touched verdict_placeholder`) | One row per Claude Code session that touched production files |

Both files start with a `# soup-schema:<name>-v<n>` comment so consumers
can detect drift across releases. The Stop hook **must not** write to
`experiments.tsv`; the orchestrator **must not** write to
`sessions.tsv`. A one-shot migration script
`scripts/split_experiments_tsv.py` rewrites a legacy mixed file in
place, classifying each row by tab-count.

### Observability pillar (iter-3 ε)

The framework's observability surface comprises three concentric layers:

1. **Per-tool-call JSONL** (`logging/agent-runs/session-<id>.jsonl`).
   Schema: `schemas/agent_log.py::AgentLogEntry`. Now carries
   wave-tree threading fields (`parent_session_id`, `root_run_id`,
   `wave_idx`, `step_id`) so `soup logs tree <run_id>` can reconstruct
   the dispatch hierarchy without `.soup/runs/`.
2. **Per-session ledger** (`logging/sessions.tsv`). One row per
   Claude Code session, owned by the Stop hook. Carries the QA
   verdict placeholder (`PENDING_QA` / `NO_EDITS`).
3. **Per-run ledger** (`logging/experiments.tsv`). One row per
   ExecutionPlan run, owned by the orchestrator. Carries `cost_usd`,
   duration, `n_steps`, `budget_sec`, and the run verdict.

App-side observability is governed by `rules/observability/`
(structured-logging, correlation-ids, health/readiness, error-
tracking, metrics) which `pre_tool_use.py` injects into any
template-scaffolded surface. Templates ship with structured loggers,
correlation-id middleware, and `/health|/ready|/version` endpoints
out of the box. The `incident-responder` agent owns the
"alert→triage→postmortem" loop; postmortems land in
`docs/incidents/<date>-<slug>.md` using the template under
`docs/incidents/TEMPLATE.md`.

### Anthropic tokens

The `post_tool_use` hook captures per-tool token counts from Claude
Code telemetry. `logging/experiments.tsv` columns include:

```
run_id  ts  mode  goal_hash  duration_sec  waves  steps  tokens_in  tokens_out  cost_usd  verdict
```

**`cost_usd` column.** Each row in `experiments.tsv` now carries a
`cost_usd` field — a USD estimate of the Anthropic spend for the
whole run, computed by the orchestrator at Stop time by multiplying
per-model `tokens_in` / `tokens_out` by the published Anthropic price
list (`orchestrator/pricing.py`) and summing across every subagent
the run dispatched. Semantics:

- Units: US dollars, float, four decimal places (`0.0123`).
- Includes meta-prompter, all wave subagents, qa-orchestrator, and
  every `verifier` fix-cycle retry — the full run envelope.
- **Estimate only.** Real billing is whatever Anthropic invoices;
  `cost_usd` is a consistent relative metric across runs, not an
  authoritative ledger. It drifts when Anthropic adjusts prices; the
  pricing table is versioned and dated.
- Written once at Stop, append-only. Mid-run crashes produce a row
  with `cost_usd` equal to the partial spend up to the crash.
- `just experiments` sorts by `cost_usd` descending with `--by-cost`
  to surface expensive runs for triage.

Downstream: postmortems use `cost_usd` + `verdict` to flag runs that
spent `opus` budget on a `BLOCK` outcome — those are the review-loop
priorities.

Budget enforcement: `ExecutionPlan.budget_sec` caps wall-clock. Token
and dollar budgets are advisory (logged, not enforced) at v1;
Constitution VIII caps tokens per model tier (opus for
orchestrator/meta-prompter only, etc.).

### Active CPU (Vercel-aware note)

When soup is deployed to Vercel Functions (e.g. `rag-mcp` behind an
HTTP gateway), *Active CPU* time is the billing unit, not wall clock.
The framework is designed to be mostly I/O-bound inside RAG queries,
so Active CPU tracks well with LLM latency. If you expose the
orchestrator behind Vercel Functions (unusual but supported):

- prefer `sonnet` streaming endpoints over `opus` batch, to reduce
  the Active CPU window;
- cache RAG embeddings in Vercel Edge Config (the session_start
  hook reads `VERCEL_EDGE_CONFIG` and, if present, uses it as a
  read-through cache over Postgres);
- never run the orchestrator inside an Edge Function runtime — use
  Node.js/Serverless Functions only.

See [Vercel Fluid Compute docs](https://vercel.com/docs) for the
Active-CPU billing model; the `vercel-cli` skill plugin-side can
bootstrap a deployment.

### Local cost dashboards

`just experiments` prints the last N rows of `experiments.tsv` as a
rich table. `just last-qa` dumps the most recent QA verdict. Neither
is required in CI; they exist for dev introspection.

### `soup cost-report` CLI (iter-3 ε4)

For aggregated views across many runs, use `soup cost-report`:

```bash
soup cost-report --group-by plan                  # cost per plan/goal
soup cost-report --group-by run --since 2026-04-01
soup cost-report --until 2026-04-30 --group-by model
```

The command parses `logging/experiments.tsv` (skipping the `#
soup-schema:` header + any malformed legacy rows), applies the
`--since` / `--until` date filters against the `ts` column, buckets
by the requested key (`plan`, `run`, `agent`, `model`), strips the
`~` estimate prefix from `cost_usd`, sums per bucket, and prints a
`rich.Table` sorted descending by cost. A trailing `total:` line
gives the overall spend across filtered runs. Per-agent and per-
model splits are placeholder buckets today — populating them requires
the per-step cost data that ε5 threads through `post_tool_use.py`
once Claude Code CLI token-count events land in the JSONL.

### Incident response (iter-3 ε7)

When a production alert fires, the flow is logs-first:

1. Operator invokes the `incident-responder` agent with the symptom
   + time range + severity.
2. `incident-responder` queries `soup logs search "<pattern>"
   --since <t0> --until <t1>` and `soup logs tree <run_id>` to pull
   the matching JSONL entries. Citations carry
   `session-<id>.jsonl#L<line>`.
3. `incident-responder` traces log event -> emitter (`Grep`) ->
   caller -> request handler, then dispatches `test-engineer`
   (regression test) and `verifier` (fix cycle) via `Agent`.
4. A postmortem is drafted to
   `docs/incidents/<YYYY-MM-DD>-<slug>.md` from
   `docs/incidents/TEMPLATE.md`. Action items carry owner + due
   date; every log citation carries a line number.

`docs/incidents/` (novel production failures) is deliberately
separate from `docs/runbooks/` (known environmental glitches with
codified fixes). A third recurrence of an incident pattern is the
trigger to extract a runbook. See `docs/incidents/README.md` for
the distinction.

---

## 8. Claude Code CLI invocation contract

> **Stability note.** The exact flag set below is what the current
> `orchestrator/agent_factory.py::_build_invocation` emits. Treat it
> as *subject to change when the Claude Code CLI contract evolves*.
> Keep `_build_invocation` as the single adapter point — never shell
> out to `claude` from anywhere else in the orchestrator.

### 8.1 The argv shape

Every `TaskStep` spawn boils down to a single subprocess invocation.
`orchestrator/agent_factory.py::spawn` constructs it from the step
plus a session id generated per spawn:

```
claude -p <brief>
       --agent <role>
       --model <tier>           # haiku | sonnet | opus
       --max-turns <N>
       --session-id <uuid>
       --files-allowed <csv>    # optional; comma-separated globs
       --rag-queries <json>     # optional; JSON array of strings
```

- `<brief>` — composed by `_compose_brief`; header lines (task id,
  agent role, model tier, max turns, files allowed, verify cmd, plan
  goal, constitution ref) followed by `---` and the literal
  `step.prompt`. If the TaskStep declares `context_excerpts` or
  `spec_refs`, they are resolved at brief-compose time (i.e. **before**
  the subagent process is spawned) and appended under a trailing
  `## Context excerpts (verbatim)` section. Resolution runs against
  the orchestrator's cwd (repo root). Missing files / bad anchors emit
  a `logging.WARNING` and are skipped — they **never** block the
  spawn. Size caps: 20 KB per `context_excerpts` entry, 40 KB per
  `spec_refs` entry, truncated with a marker when exceeded. Injection
  happens once at spawn; the subagent sees the resolved text in its
  first turn and does not need to re-`Read` the source file. See
  `DESIGN.md §3` for the schema fields and §17 for the brownfield flow
  that populates them.
- `--files-allowed` — comma-separated, identical globs to
  `TaskStep.files_allowed`. The hook `pre_tool_use.py` enforces the
  scope on every Edit/Write tool call; the `.githooks/pre-commit`
  script enforces it again at commit time via the `SOUP_FILES_ALLOWED`
  env var (see §8.4).
- `--rag-queries` — a JSON array; `.claude/hooks/subagent_start.py`
  consumes the equivalent env var and resolves the top-k hits into
  the child prompt at session start. The CLI flag is the wire shape;
  the env var is the hook-side consumer.

### 8.2 Event forwarding (hook → orchestrator)

Hooks emit structured events as *one JSON object per stderr line*.
`agent_factory._forward_stderr_events` parses each line, validates
against `schemas/agent_log.py::AgentLogEntry`, and appends it to the
session JSONL under `logging/agent-runs/session-<session_id>.jsonl`.
Non-JSON stderr chatter is counted and summarized at the end so grep
is still useful — never silently dropped.

The `AgentLogEntry` contract (session_id, agent, action, ts,
input_summary, output_summary, duration_ms, status) is the wire
format hook authors must emit. A hook crashing or emitting a
malformed line degrades to the noise counter; the session still
completes.

### 8.3 Reproducing a step locally (debugging)

When a step fails, the session JSONL captures every argv + stdout
tail, but operators often want to replay the spawn directly. The
forwarded env vars (below) and the argv line in the JSONL are
sufficient to reconstruct it:

```bash
# From the repo root, with the failing step's slug and files scope:
SOUP_FILES_ALLOWED="app/routes/health.py:tests/test_health.py" \
ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
claude -p "<brief>" \
       --agent implementer \
       --model sonnet \
       --max-turns 10 \
       --files-allowed 'app/routes/health.py,tests/test_health.py' \
       --session-id debug-repro
```

`SOUP_FILES_ALLOWED` uses the POSIX `$PATH` separator (`:`); the CLI
flag uses `,`. This is a deliberate split: env variables naturally
follow the PATH convention, and CLI flags with commas parse more
predictably under Windows PowerShell.

### 8.4 Forwarded env whitelist

`orchestrator/agent_factory.py::_filter_parent_env` builds the child
environment from an *explicit whitelist*, not an os.environ spread.
The whitelist lives in `agent_factory.py` and is the single source of
truth:

- `_DEFAULT_ENV_KEYS` — baseline keys forwarded to every subagent:
  `PATH`, `HOME`, `USER`, `USERNAME`/`USERPROFILE`/`SYSTEMROOT`/`COMSPEC`
  (Windows), `TEMP`/`TMP`/`TMPDIR`, `LANG`/`LC_ALL`, `PWD`, `SHELL`,
  `TERM`, `PYTHONIOENCODING`, `PYTHONUNBUFFERED`, and `ANTHROPIC_API_KEY`
  (the Claude binary cannot function without it).
- `_DEFAULT_ENV_PREFIXES` — every variable matching one of `LC_`,
  `CLAUDE_`, `SOUP_` is also forwarded. This covers per-step settings
  like `SOUP_FILES_ALLOWED` (set by the orchestrator) or
  `CLAUDE_MODEL_OPUS` (read by the CLI at spawn).
- `_STEP_INJECTABLE_ENV_KEYS` — the set of *credential* keys a step
  may opt in to via `TaskStep.env`: `GITHUB_TOKEN`, `GH_TOKEN`,
  `ADO_PAT`, `AZURE_DEVOPS_EXT_PAT`, `POSTGRES_DSN`, `POSTGRES_HOST`,
  `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
  `OPENAI_API_KEY`. Anything not in this list is silently dropped
  from the child env so a typo'd step declaration cannot smuggle
  parent-env values.

### 8.5 Adding a new provider

The Claude Code CLI is the *default* provider, not *the* provider.
See `orchestrator/providers.py` for the `ProviderAdapter` Protocol
that formalises the seam:

```python
class ProviderAdapter(Protocol):
    async def spawn_agent(
        self, step: TaskStep, env: Mapping[str, str] | None = None
    ) -> StepResult: ...

    async def plan_with_goal(
        self, goal: str, context: Mapping[str, Any] | None = None
    ) -> ExecutionPlan: ...
```

To add a non-Anthropic provider (e.g. OpenAI, a local OSS model):

1. Implement a new class (e.g. `OpenAIAdapter`) that satisfies the
   `ProviderAdapter` protocol — `spawn_agent` becomes the only place
   that knows how to invoke the underlying CLI/SDK.
2. Register the adapter in `orchestrator/orchestrator.py` at init
   time (swap the default `ClaudeCodeAdapter` via the config knob).
3. Update `_MODEL_PRICING_USD_PER_MTOKEN` in `orchestrator.py` with
   the new provider's rate card so `experiments.tsv` cost estimates
   stay comparable.
4. The schema (`schemas/execution_plan.py::ModelTier`) may need a
   widened literal if the new provider's tier names differ from
   `haiku | sonnet | opus`.

No orchestrator wave logic, no schema beyond `ModelTier`, and no
hooks need to change — the adapter is the single insertion point.
This is the v1 extensibility commitment against the architecture
audit's §5 "new model provider = Hard" finding.
