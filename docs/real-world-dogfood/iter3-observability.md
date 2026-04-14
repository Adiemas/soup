# iter-3 dogfood — Observability + Incident Response

**Date:** 2026-04-14
**Framework under test:** `soup` at `C:\Users\ethan\AIEngineering\soup`
**Mode:** Report-only. No framework changes. No app changes.
**Focus:** What happens when an agent-built app goes sideways in prod —
or when a soup run itself goes sideways and an engineer has to debug it.

---

## Current observability posture

Soup ships three observability surfaces today:

1. **Per-session JSONL.** `.claude/hooks/post_tool_use.py` writes one
   line per tool call to `logging/agent-runs/session-<session_id>.jsonl`.
   Schema lives in `schemas/agent_log.py::AgentLogEntry` (ts, session_id,
   agent, action, input/output summaries truncated to 200/500 chars,
   duration_ms, status, cost_estimate). Secret redaction runs at write
   time via `REDACT_KEY_RE`.
2. **Run-level append-only TSV.** `orchestrator/orchestrator.py::
   _append_experiment` appends one row per run to
   `logging/experiments.tsv` with columns (ts, run_id, status,
   duration_sec, n_steps, budget_sec, cost_usd, aborted_reason, goal).
   `cost_usd` is prefixed `~` to flag it as an estimate. The Stop hook
   *also* appends to the same TSV with a different schema
   (`ts, session_id, files_touched, verdict_placeholder`) — the file
   carries two row shapes simultaneously, which is a parsing bug for
   anyone consuming the TSV from a second tool.
3. **Brownfield baseline diffs.** When `plan.regression_baseline_cmd`
   is set, the orchestrator captures pre/post test rosters under
   `.soup/baseline/<run_id>/{pre,post,diff}.txt` and a single-event
   JSONL at `logging/agent-runs/baseline-<run_id>.jsonl`.

Engineer-facing surface: `just logs`, `just experiments`, `just last-qa`.
All three call `python -m orchestrator.cli logs --tail|--experiments|
--last-qa`. The Typer command does exactly three things:

- `--tail N` prints the last N lines of the **most recent** session
  JSONL (no filter, no search, no time range).
- `--experiments` cats `logging/experiments.tsv` raw — no sort, no
  filter, no per-agent rollup.
- `--last-qa` pretty-prints the most recent `qa_report.json`.

`just doctor` runs an env health check (Python/git/Postgres/Anthropic
key/hooksPath) — orthogonal to runtime observability.

The Constitution + `rules/global/logging.md` set strong conventions for
**hand-written** code: `{Domain}.{Action}_{State}` event names,
correlation IDs propagated through the call chain, structlog/Serilog
JSON, `/api/telemetry` shipping. None of those conventions are wired
into the templates that soup itself scaffolds.

---

## Gap matrix

| Concern | Status | Evidence | Severity |
|---|---|---|---|
| Query agent-run logs by session | partial | `just logs --tail` only tails latest JSONL; no `--session`, no `--agent`, no `--since`, no full-text grep wrapper | high |
| Reconstruct wave tree from logs alone | missing | `AgentLogEntry` has no `parent_session_id`, `root_run_id`, or `wave_idx`; orchestrator never threads the spawn tree into the JSONL | high |
| Cumulative cost rollup | missing | `experiments.tsv` has `cost_usd` per row but no `cost-report` command, no per-agent / per-plan / monthly aggregation; orchestrator never sums beyond the single run | high |
| Per-step token + cost detail | partial | `AgentLogEntry.cost_estimate` exists but the field is set to default `0.0` in the post_tool_use hook (the hook never reads token counts from the Claude Code CLI) | high |
| Budget-ceiling explanation in logs | partial | Orchestrator writes `aborted_reason="budget_sec=X exceeded before wave Y"`; no per-step "this is what we were doing when the budget hit" trace; the JSONL line that crossed the budget is not flagged | medium |
| TSV schema discipline | broken | Stop hook writes a 4-col row; Orchestrator writes a 9-col row; same file. `_append_experiment` writes its own header on first row but the Stop hook writes a *different* header on first row. Order-dependent: whichever runs first wins, second consumer sees a corrupt parse | high |
| Structured logging in scaffolded apps | missing | `templates/python-fastapi-postgres/app/main.py` uses `print`-friendly defaults; no `structlog`, no correlation-ID middleware, no JSON renderer; `templates/nextjs-app-router/src/app/api/health/route.ts` returns `{ok:true}` plain — no event name, no `console.info("<Event>", {...})` | high |
| Health endpoints | partial | Both Python + Next templates ship a `/health` route. Neither has a `/ready` (readiness) split, neither emits a structured log line on the call, neither returns build SHA / version metadata | medium |
| Error tracking integration | missing | No Sentry / App Insights / Rollbar wiring in any template; no rule under `rules/observability/` (the directory does not exist); no agent reminds you to add one | high |
| Metrics export (Prometheus / App Insights counters) | missing | No Prometheus client in `pyproject.toml`/`package.json`; no `/metrics` endpoint; no rule | medium |
| Distributed tracing | missing | No OpenTelemetry instrumentation, no `traceparent` header propagation; the framework's own correlation_id rule is not exported into templates | medium |
| Incident-responder agent | missing | `.claude/agents/` has no `incident-responder.md`; nothing matches `*incident*`, `*sre*`, `*on-call*`. Closest is `verifier` (fix-cycle role) but it's spawned by the orchestrator at QA-fail, not by an operator with a Sentry alert in hand | high |
| Incident runbooks (different from env runbooks) | missing | `docs/runbooks/` carries 5 *environmental* runbooks (anthropic rate-limit, pkgutil, postgres container, playwright hydration, npgsql utc). None describe an incident-response flow ("alert fires → triage → rollback → write postmortem"). The README format template has `Symptom / Cause / Fix / Related` — fine for env, wrong for incidents | high |
| Audit trail (Constitution Art. IV / lab-data) | partial | `rules/compliance/lab-data.md §2` *requires* per-mutation audit rows in the **app's** database, with retention + dual-attestation. Nothing in soup scaffolds an `audit_log` table, an `AuditMiddleware`, or a write-side enforcement check. The framework's own JSONL is operational, not regulatory | high |
| Tamper-evidence on audit logs | missing | `session-*.jsonl` is plain append-only; no HMAC chain, no signature, no monotonic counter. A privileged operator can edit history and the framework would not detect it | high |
| Audit logs separated from operational | missing | One JSONL per session mixes tool-call telemetry with what would be audit-relevant events (e.g. `Edit` on a `migrations/` file, secret-scan result). No dedicated `logging/audit/` sink | high |
| PII redaction in templates | missing | `rules/global/logging.md` says "never log PII"; no template carries a redaction middleware or a `log_safe_user(user)` helper | medium |
| Cross-tool correlation | missing | When a `qa-orchestrator` spawn fans out 3 subagents (code-reviewer / security-scanner / verifier), the parent session_id does not appear in the children's JSONL. Reconstructing "what did QA do for run X" is a manual file-find | high |
| Stop hook QA-trigger logging | partial | `stop.py` writes `verdict_placeholder=PENDING_QA` — but never updates the row when QA actually completes. Result: every TSV row is permanently `PENDING_QA` from the stop hook's perspective; no engineer can answer "how many sessions ended in BLOCK" from the file alone | medium |
| `cost_usd` in experiments visible to operator | partial | The column exists; `just experiments` cats the TSV but never sorts by cost. The `--by-cost` knob promised in `docs/ARCHITECTURE.md §7` ("`just experiments` sorts by `cost_usd` descending with `--by-cost`") is **not implemented** in `orchestrator/cli.py`. Doc lies | medium |

---

## Specific gaps (ranked)

### 1. No way to follow the wave tree
A `/implement` run with 3 waves of 5 steps each spawns at least 16
sessions (1 meta-prompter + 15 step subagents + 1 qa-orchestrator + N
qa fan-out). Every session writes its own JSONL. Nothing in the
schema connects them. To reconstruct "what did wave 2 do," an engineer
must `ls -t logging/agent-runs/`, eyeball timestamps, and guess. There
is no `root_run_id`, no `parent_session_id`, no `wave_idx` field on
`AgentLogEntry`. The orchestrator's `RunState` (in `.soup/runs/`) does
hold the step→session mapping, but `just logs` does not join the two.

### 2. Cost ceiling is wall-clock only; dollars are advisory
`ExecutionPlan.budget_sec` is hard-enforced. There is no
`budget_usd`, no per-agent dollar cap, no cumulative monthly tally.
`AgentLogEntry.cost_estimate` defaults to `0.0` because
`post_tool_use.py` does not parse Claude Code CLI token output —
the field exists in the schema and stays empty. The
`_estimate_cost_usd` function in the orchestrator runs once at Stop
against `step_results`, but those `cost_estimate` values come from
`spawn_res.cost_estimate` which is itself unset by the agent_factory
(needs verification but no evidence in `post_tool_use.py` that it ever
gets populated). End-state: cost_usd in experiments.tsv is, in
practice, zero or near-zero on every row.

### 3. No incident-responder agent
The 20-agent roster has `verifier` (fix-cycle), `qa-orchestrator`,
`code-reviewer`, `security-scanner`. None of them have the operator-
facing brief: "An alert just fired in prod for an app soup built. Find
the relevant code, reproduce locally, propose a fix, ship it." That
flow is the literal day-job of an SRE/on-call. Soup builds the app and
then ghosts.

### 4. Templates ship without observability
A fresh `just new python-fastapi-postgres my-service` produces an app
with one health endpoint that returns `{"status":"ok","db":true}` and
zero structured logs. A fresh `just new nextjs-app-router my-app`
produces a `force-static` health route that returns `{ok:true}`. The
`rules/global/logging.md` `{Domain}.{Action}_{State}` rule has no
template enforcement; the rule applies to **maintainers of soup**,
not to apps soup creates.

### 5. Audit trail is regulated but unscaffolded
`rules/compliance/lab-data.md §2` requires every mutation to record
actor / timestamp / reason / prior value in an append-only audit
table with 7-year retention and dual attestation for retroactive
edits. Soup encodes the *rule* and a `lab-data` compliance flag on
the intake form. It does **not** ship: an `audit_log` migration in
any template; an `AuditedRepository` Python helper; a Supabase RLS
policy template for audit tables; a code-reviewer check for "this
mutation has no corresponding audit write." A team gets the rule,
gets a flag in the intake YAML, and is then expected to invent the
implementation from scratch — every time, per app.

### 6. Tamper-evidence is absent
`logging/agent-runs/session-*.jsonl` and `logging/experiments.tsv`
are plain text. Anyone with write access to the repo can edit
history. For a CAP/CLIA-adjacent compliance posture (per
`lab-data.md`), this is a non-starter at the framework level — and
since soup's own claim is "everything file-based and inspectable" it
matters that "inspectable" includes "demonstrably unforged."

### 7. `experiments.tsv` is corrupted by dual schemas
`stop.py` writes `ts\tsession_id\tfiles_touched\tverdict_placeholder`.
`orchestrator.py::_append_experiment` writes
`ts\trun_id\tstatus\tduration_sec\tn_steps\tbudget_sec\tcost_usd\t
aborted_reason\tgoal`. Both write their own header line on first
encounter. Whichever writes second appends rows that don't match the
existing header. Any TSV-loading script breaks. This is the highest-
severity functional defect found in this dogfood.

### 8. `just experiments --by-cost` does not exist
The doc (`docs/ARCHITECTURE.md §7 Local cost dashboards`) advertises
`just experiments` sorts by `cost_usd` descending with `--by-cost`. The
implementation in `orchestrator/cli.py::logs` cats the TSV. No sort,
no filter. Doc/code drift.

### 9. Incident runbook format is wrong
`docs/runbooks/README.md` defines the format as
`Symptom / Cause / Fix / Related`. That fits an environmental glitch
("pip install fails" → "upgrade setuptools"). It does **not** fit
"prod app is down" — those need `Detection / Severity / Communicate /
Mitigate / Rollback / Postmortem owner / SLO impact`. Conflating the
two will get done badly.

### 10. No `correlation_id` in templates
`rules/global/logging.md §Correlation IDs` mandates one per request,
propagated through the call chain, included in every log line. The
FastAPI template has no middleware that creates one. The Next.js
template has no equivalent for Server Components / Route Handlers.

---

## Proposed soup additions

### A. `incident-responder` agent
New file `.claude/agents/incident-responder.md`. Brief: takes an
incident description (alert text, Sentry link, log excerpt, customer
report) and:

1. Runs the `researcher` agent against the affected app's repo to
   localise the suspect code.
2. Constructs a minimal repro spec via `spec-writer --extends` if
   `/specify --extends` ships first; otherwise authors a regression
   test against the suspect surface.
3. Dispatches `verifier` (fix-cycle role) with the repro context.
4. Drafts a postmortem skeleton to `docs/incidents/<date>-<slug>.md`
   using a new template (see G).
5. Model: `sonnet` for triage, escalates to `opus` only on
   `severity: SEV1` (constitution-pinned).

Pairs with: existing `verifier` (fix-cycle) — `incident-responder`
becomes its operator-facing entry point.

### B. `logs` Typer subcommand with search/filter
Replace the current single-file tail in `orchestrator/cli.py::logs`
with subcommands:

```
soup logs tail [--session <id>] [--agent <name>] [--follow]
soup logs search "<regex>" [--since 1h] [--until now] [--agent <name>]
                          [--status error|timeout|blocked]
soup logs run <run_id>          # cat all session JSONLs for one run
soup logs tree <run_id>         # ASCII wave tree from .soup/runs + JSONL
soup logs export --format json|ndjson|csv  # for piping into jq/duckdb
```

Implementation: glob `logging/agent-runs/*.jsonl`, parse line-by-line,
apply filters, tabulate via `rich.Table`. No new dep — `rich` and
`typer` already in.

### C. `cost-report` command
```
soup cost-report [--by agent|plan|day|month] [--since 7d] [--top N]
soup cost-report --over-budget  # rows where cost > budget hint
soup cost-report --csv          # for finance team
```

Reads `experiments.tsv` (after schema-fix below) plus per-step
`cost_estimate` if/when populated. Provides "you spent $X on the
last N runs of agent Y."

Pre-req: actually populate `cost_estimate` in `post_tool_use.py` from
the Claude Code CLI's token-count event. Right now it stays at
`0.0`. This is the load-bearing fix for cost discipline.

### D. `rules/observability/` rules dir
New directory with template-level rules so scaffolded apps inherit
observability instead of having it as a maintainer concern:

- `rules/observability/structured-logging.md` — `{Domain}.{Action}_
  {State}` enforcement at the **app** level (currently only on soup
  itself). Includes the structlog/Serilog/console.info recipes.
- `rules/observability/correlation-id.md` — middleware recipe per
  stack (FastAPI dependency, Next.js Route Handler wrapper,
  ASP.NET filter).
- `rules/observability/health-endpoints.md` — separate `/health`
  (liveness, no deps), `/ready` (deps + warm-up), `/version`
  (build SHA + start time).
- `rules/observability/error-tracking.md` — Sentry integration
  recipes for FastAPI, Next.js, .NET. Wires sample_rate, env tag,
  release version. Calls out PII scrubbing per `rules/compliance/
  pii.md`.
- `rules/observability/metrics.md` — Prometheus client (Python:
  `prometheus_client`; .NET: `prometheus-net`) wiring + `/metrics`
  endpoint + the four golden signals.

Wired by `pre_tool_use.py` the same way the existing per-ext rules
work — when a template scaffold writes `app/main.py`, the rules
inject themselves into the implementer's context.

### E. Sentry / App Insights template integration
Each template gets:

- `app/observability.py` (Python) / `lib/observability.ts` (TS) /
  `Observability/` folder (.NET) with init, traceback wrapping, and
  PII-aware scrubbers.
- A `SENTRY_DSN` (or `APPLICATIONINSIGHTS_CONNECTION_STRING`) env
  in `.env.example` — empty by default, optional at app boot.
- An integration test that asserts a deliberately-thrown exception
  surfaces a captured event (mocked transport).
- Documented in the template `CLAUDE.md`.

### F. Incident runbook format (different from env runbooks)
New file `docs/incidents/_TEMPLATE.md` with sections:

```
# <YYYY-MM-DD> — <one-line title>
## Severity      SEV1|2|3|4
## Status        active | mitigated | resolved
## Detection     how did we find out + timestamp
## Impact        users / requests / revenue / regulated-records?
## Timeline      bullet list of UTC timestamps + actions
## Mitigation    what stopped the bleeding
## Root cause    five whys; cite commits + log lines
## Action items  owner + due date per item
## Postmortem    [link to retro doc once written]
```

Tracked under `docs/incidents/<date>-<slug>.md`. The
`incident-responder` agent (see A) drafts the skeleton.

The existing `docs/runbooks/` stays for env recipes; rename its
README to clarify scope ("environmental runbooks; for incidents see
`docs/incidents/`").

### G. Audit trail immutability
For soup's own log stream:

- Add an HMAC chain to `session-<id>.jsonl`. Every line includes a
  `prev_hmac` field; the value is `HMAC(SHA256, secret, prev_line)`.
  Secret lives in `.env` as `SOUP_AUDIT_HMAC_KEY` (rotation
  documented; rotation produces a chain-segment break recorded in a
  marker line, not a silent reset).
- Add `soup logs verify <session-id>` that walks the chain end-to-
  end and reports any tampered or missing line.
- Move security-relevant events out of the per-session JSONL into a
  dedicated `logging/audit/<date>.jsonl` sink (Edit/Write on
  `migrations/`, secret-scan results, hook denials, plan/spec
  approvals). One line per event, same HMAC chain.

For apps soup builds (the regulatory side):
- New skill `audit-trail-scaffold` that, when a template's intake
  carries `compliance_flags: [lab-data|phi|financial]`, generates
  the migration pair, the `AuditedRepository` helper, and the
  integration test asserting the audit row was written. Failure
  to scaffold = `BLOCK` from `code-reviewer`.

### H. Template enrichment — observability wired at scaffold time
Every template ships with:

- `/health`, `/ready`, `/version` endpoints (the `/version` returns
  `{git_sha, started_at, env}`).
- A correlation-ID middleware (FastAPI: dependency wrapper that
  reads/sets `X-Request-ID`; Next.js: middleware.ts middleware
  setting `x-request-id`).
- Structured JSON logger pre-wired (structlog for Python,
  `pino`-equivalent for Node, Serilog for .NET).
- Sentry init code, gated on env presence.
- A `/metrics` endpoint exposing process + framework counters.
- `tests/test_observability.py` (or equiv) asserting a request with
  `X-Request-ID: foo` produces a log line carrying `correlation_id=
  foo`.

This eliminates "we forgot to add observability" as a class.

### I. Fix the dual-schema TSV bug
- Move stop-hook rows out of `experiments.tsv` into
  `logging/sessions.tsv` (its own schema: ts, session_id,
  files_touched, verdict). One file, one schema.
- `experiments.tsv` becomes orchestrator-only (one row per
  ExecutionPlan run).
- `just experiments` then makes sense as "show me the plan-level
  ledger" and `just sessions` (new) shows the QA-relevant per-
  Claude-Code-session rows.
- Both files versioned via a leading comment line:
  `# soup-schema:experiments-v1` so consumers can detect drift.

### J. Wave tree threading
- Add `parent_session_id`, `root_run_id`, `wave_idx`, `step_id` to
  `AgentLogEntry`. Make the orchestrator pass them as env
  variables (`SOUP_PARENT_SESSION_ID`, `SOUP_ROOT_RUN_ID`, ...) on
  every `agent_factory.spawn`. Update `post_tool_use.py` to read
  the env and stamp every JSONL line.
- Then `soup logs tree <run_id>` (see B) becomes a one-pass scan
  over `logging/agent-runs/*.jsonl` filtered by `root_run_id`,
  rendered as a tree.

---

## Pairs with iter-2

- **iter2-brownfield-integration.md** — proposed `regression_baseline_
  cmd` already lands a baseline JSONL at
  `logging/agent-runs/baseline-<run_id>.jsonl`. That JSONL is *not*
  searchable by `just logs` today because the search doesn't exist.
  Proposal B (`soup logs search`) closes that. Also: the
  `_run_baseline` log entry includes only `phase + exit_code + out`;
  add `wave_idx` + `step_id` (proposal J) so a baseline regression
  can be tied to a specific step.
- **iter2-rag-context.md** — RAG retrievals carry `[source:path#span]`
  citations enforced by `code-reviewer`. The `incident-responder`
  agent (proposal A) inherits that requirement: any postmortem citing
  log lines must use the same `[file#L<line>]` shape so audit can
  re-resolve the evidence.
- **iter2-intake-form.md** — intake `compliance_flags` already drive
  rule injection. Extend the same mechanism: `compliance_flags:
  [lab-data]` triggers proposal G's audit-scaffold skill, plus
  proposal D's `rules/observability/error-tracking.md` PII section.
- **Constitution Article IV (Quality Gate) + new
  rules/compliance/lab-data.md** — currently demand audit trails
  but provide no infrastructure. Proposals D/E/G/H jointly close
  the loop: scaffolded apps produce the audit table, the structured
  logs, the redaction, and the immutability chain by default rather
  than as recurring greenfield invention.
- **Cost discipline (Constitution Art. VIII)** — pinned model tiers
  by agent role, but `cost_usd` in experiments.tsv is functionally
  zero (proposal C pre-req). Without the populate-step, every cost-
  related decision is theatre.

---

## Out of scope for this iter

- Fixing the items (this is report-only).
- Picking a specific Sentry vs App Insights vendor — proposal E
  presents both. Choice belongs in a soup-level ADR.
- Designing the HMAC key rotation policy in detail — proposal G
  flags it; rotation deserves its own runbook.
