# Onboarding — Soup for new Streck engineers

Welcome. This walkthrough gets you from zero to shipping a trivial
feature through the soup framework in ~30 minutes. Read each section
before running the commands — the iron laws have teeth.

> **Returning to this repo with an existing session?** The steering
> context is [`../CLAUDE.md`](../CLAUDE.md) — iron laws, stack, and
> canonical flow in one file. Read it first if Claude Code just
> auto-loaded this doc; it's the shorter of the two and it wins any
> contradiction.

---

## 1. What soup is (and isn't)

**Soup is** an opinionated Claude Code configuration for Streck internal
apps. It bundles:

- a canonical spec-driven flow (`/specify → /plan → /implement → /verify`),
- a 20-agent roster routed by stack (Python / .NET / React / Postgres),
- a Pydantic-validated orchestrator that runs waves of fresh subagents
  with git-worktree isolation,
- automatic QA via a Stop-hook gate,
- a LightRAG-backed knowledge layer over our repos and ADO wiki,
- a three-mode `just` CLI for deterministic, supervised, and
  interactive runs.

**Soup is not** a chatbot, an autonomous agent that merges to main
without review, or a replacement for thinking. You still own the spec
and the final code review; soup handles decomposition, execution,
and the mechanical QA gates.

If your task is a one-line hotfix, soup is overkill — use `/quick` or
edit directly. If it's a feature, soup is how you do it here.

---

## 2. Install prerequisites

See [`README.md`](../README.md#installation) for the full matrix. In
short, you need:

- Python 3.12
- `just`
- Docker (for postgres + optional dev container)
- Git
- An Anthropic API key in `.env`

Clone the repo, then:

```bash
just init          # creates .env from .env.example if missing; safe to re-run
$EDITOR .env       # paste your ANTHROPIC_API_KEY
```

`just init` creates a venv, installs deps (uv if available else pip),
starts Postgres in Docker, copies `.env.example` → `.env` (only if
`.env` doesn't already exist), and registers Claude Code hooks.
Idempotent — safe to re-run.

> **Windows users:** Recipes run under Git Bash (not PowerShell).
> See the **Windows setup** section in [`README.md`](../README.md#windows-setup)
> for the full prerequisite list — Git Bash on PATH, Docker Desktop with
> the WSL 2 backend, `winget install Casey.Just`, and Windows Terminal.
> `just init` will fail fast if `bash --version` isn't reachable.

Verify with `just doctor` — prints a health summary of the python
environment, docker, postgres connectivity, and hook registration.

---

## 3. First run: `just go "build me a health endpoint"`

Open a terminal in the repo root and run:

```bash
just go "build me a health endpoint with a liveness probe at /health"
```

Expected flow (also visible in `logging/agent-runs/session-*.jsonl`):

```
[soup] session start — loading .env, priming summary
[meta-prompter/opus] decomposing goal → ExecutionPlan
  goal: "build me a health endpoint with a liveness probe at /health"
  constitution_ref: CONSTITUTION.md@<sha>
  steps:
    S1  spec-writer    sonnet  specs/health.md             (deps: —)
    S2  plan-writer    sonnet  specs/health-plan.md        (deps: S1)
    S3  test-engineer  sonnet  tests/test_health.py        (deps: S2)   # RED
    S4  python-dev     sonnet  app/routes/health.py        (deps: S3)   # GREEN
    S5  verifier       sonnet  pytest tests/test_health.py (deps: S4)
  budget_sec: 3600
  worktree: .soup/worktrees/health-endpoint/
[plan saved] .soup/plans/2026-04-14-health.json

[orchestrator] wave 1 — running S1
  ├─ spec-writer → specs/health.md written
  └─ verify_cmd: test -f specs/health.md              PASS
  [commit] feat(spec): health endpoint spec           a1b2c3d

[orchestrator] wave 2 — running S2
  ├─ plan-writer → specs/health-plan.md written
  └─ verify_cmd: test -f specs/health-plan.md         PASS
  [commit] feat(plan): health endpoint plan           b2c3d4e

[orchestrator] wave 3 — running S3 (RED phase)
  ├─ test-engineer → tests/test_health.py written (failing)
  └─ verify_cmd: pytest tests/test_health.py || true  FAIL (expected)
  [commit] test: failing test for /health             c3d4e5f

[orchestrator] wave 4 — running S4 (GREEN phase)
  ├─ python-dev → app/routes/health.py written
  └─ verify_cmd: pytest tests/test_health.py -q       PASS (1 passed)
  [commit] feat(api): /health liveness endpoint       d4e5f6g

[orchestrator] wave 5 — running S5
  ├─ verifier → full suite green, coverage 92%
  └─ verify_cmd: pytest -q                            PASS

[stop] → qa-orchestrator dispatching...
  ├─ code-reviewer  → 0 critical, 1 low (docstring nit)
  ├─ security-scanner → 0 findings
  └─ verifier       → 24 passed, 0 failed, coverage 92%
[qa] verdict: APPROVE
[merge] .soup/worktrees/health-endpoint → feature/health-endpoint
[pr] gh pr create → #231 opened
```

Timings vary; budget typically 2–8 minutes for a task this size.

If any wave fails verification, the orchestrator auto-dispatches
`verifier` (fix-cycle role) scoped by the `systematic-debugging` skill.
Three failed attempts → escalate to architect (Article IX).

---

## 4. Your first spec — `/specify`

Pop open Claude Code inside the repo and run:

```
/specify a nightly job that emails last 24h of failed pipelines to #payroll-ops
```

`spec-writer` produces `specs/<slug>.md` using EARS requirements
("The system shall..."). Read it. If anything is ambiguous, run
`/clarify` — the HITL prompter will pause and ask. Only when the spec
is frozen should you `/plan` and then `/implement`.

Rules (Constitution, Article I):
- Specs describe **what** and **outcomes**, never **how**.
- Approved specs are frozen — edits become new versions, not diffs.

---

## 5. Using RAG

The knowledge layer is pre-wired with LightRAG + Postgres. Ingest a
repo you want the agents to consult:

```bash
just rag-ingest github:streck/payroll-api
# or local: just rag-ingest fs:/c/Users/ethan/streck-wiki
# or web:   just rag-ingest https://docs.streck.example/auth
# or ADO:   just rag-ingest ado:streck/internal/wiki
```

Then query:

```bash
just rag "how does payroll-api authenticate callers?"
```

Output includes `[source:path#span]` citations. Agents inherit these
citations automatically (the `subagent_start` hook injects the top-k
results for every new subagent), so answering "what does our auth
middleware look like?" during `/plan` requires zero extra prompting.

Expose to other MCP clients (Claude Desktop, etc.):

```bash
just rag-mcp
# listens on stdin/stdout per the MCP protocol
```

---

## 6. When things go wrong

Most failures are diagnosed by reading `logging/agent-runs/session-*.jsonl`.
Each line is one tool invocation with:

```json
{
  "ts": "2026-04-14T14:31:02Z",
  "session_id": "...",
  "agent": "python-dev",
  "tool": "Bash",
  "input": {"command": "pytest -q"},
  "output_preview": "1 failed, 23 passed",
  "duration_ms": 2410,
  "files_allowed": ["app/routes/health.py", "tests/test_health.py"],
  "violated_rule": null
}
```

Quick tail: `just logs` (most recent session). QA report: `just last-qa`.

If QA BLOCKs, do not bypass. Instead:

```bash
just go "fix the failing test_health_contract regression"
```

The orchestrator scopes `verifier` (fix-cycle role) to only the failing
file(s). Three consecutive failed fixes escalate automatically to
architect per Article IX — you don't need to remember this, the
hooks do.

If a worktree is corrupted:

```bash
just worktree-rm <name>
just worktree <name>
```

Never commit a partially-working state to main (Article IX.3).

---

## 7. Adding a new agent or skill

You will eventually want to extend soup. Before picking an extension
surface, skim [`docs/PATTERNS.md §0`](PATTERNS.md) — the decision
rubric for **skill vs. command vs. hook vs. rule** saves hours of
going down the wrong path.

Then see [`docs/PATTERNS.md`](PATTERNS.md) for step-by-step playbooks:

- **Add a new agent** — write `.claude/agents/<name>.md`, register in
  `library.yaml`, add tests in `tests/`.
- **Add a new skill** — write `.claude/skills/<name>/SKILL.md` with the
  iron-law format, register in `library.yaml`.
- **Add a new command** — write `.claude/commands/<name>.md`, wire it
  into `justfile` if appropriate.
- **Wrap a new CLI tool** — use the CLI-Anything 7-phase in
  `cli_wrappers/`.

Every addition must pass `just lint` + `just test`.

---

## 8. Validating framework changes — mock-apps

When you change anything under `.claude/agents/`, `schemas/`, `rules/`,
or the orchestrator, exercise the change end-to-end against a mock
app before opening a PR. See [`mock-apps/README.md`](../mock-apps/README.md)
and [`docs/PATTERNS.md §8`](PATTERNS.md) — the pattern is: pick a
realistic goal, run `just go`, collect reviewer panel feedback into
`FEEDBACK.md`, and file any surfaced framework bugs back into `soup`
itself (not into the mock app).

Mock apps are dogfooding artifacts, not production. Do not import
from or depend on them in a real Streck service.

---

Welcome to soup. Read the Constitution; it'll save you a bad PR.
